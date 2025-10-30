"""
Supervisor - Manages both Day Trader and Exit Manager bots
Ensures robust operation with shared state coordination
"""

import os
import sys
import time
import subprocess
import signal
from datetime import datetime
from pathlib import Path
from observability import get_database

# Paths
VENV_PYTHON = Path(".venv-daytrader/Scripts/python.exe")
EXIT_MANAGER_SCRIPT = Path("exit_manager.py")
DAY_TRADER_SCRIPT = Path("day_trader.py")

class BotSupervisor:
    """Manages lifecycle of both trading bots with coordination and scheduling"""
    
    def __init__(self):
        self.db = get_database()
        self.exit_manager_process = None
        self.day_trader_process = None
        self.running = True
        self.sleeping = False
        
        # Schedule times (Pacific Time)
        self.WAKE_HOUR = 5   # 5:00 AM PT = 8:00 AM ET (1.5 hours before market for full analysis)
        self.SLEEP_HOUR = 13  # 1:00 PM PT = 4:00 PM ET (market close)
        
    def start_exit_manager(self):
        """Start exit manager bot (persistent connection) - SHOW OUTPUT"""
        print("🔄 Starting Exit Manager...")
        try:
            # NO output redirection - let it print directly to terminal
            self.exit_manager_process = subprocess.Popen(
                [str(VENV_PYTHON), str(EXIT_MANAGER_SCRIPT)]
            )
            print("✅ Exit Manager started (PID: {})".format(self.exit_manager_process.pid))
            print("   Output will appear below:\n")
            return True
        except Exception as e:
            print(f"❌ Failed to start Exit Manager: {e}")
            return False
    
    def start_day_trader(self, allocation=0.25):
        """Start day trader bot (can restart) - SHOW OUTPUT"""
        print(f"🔄 Starting Day Trader (allocation: {allocation*100:.0f}%)...")
        try:
            # NO output redirection - let it print directly to terminal
            self.day_trader_process = subprocess.Popen(
                [str(VENV_PYTHON), str(DAY_TRADER_SCRIPT), "--allocation", str(allocation)]
            )
            print("✅ Day Trader started (PID: {})".format(self.day_trader_process.pid))
            print("   Output will appear below:\n")
            return True
        except Exception as e:
            print(f"❌ Failed to start Day Trader: {e}")
            return False
    
    def check_day_trader(self):
        """Check if day trader is still running, restart if crashed"""
        if self.day_trader_process is None:
            return False
            
        if self.day_trader_process.poll() is not None:
            print("⚠️  Day Trader crashed! Restarting...")
            return self.start_day_trader()
        
        return True
    
    def check_exit_manager(self):
        """Check if exit manager is still running (critical!)"""
        if self.exit_manager_process is None:
            return False
            
        if self.exit_manager_process.poll() is not None:
            print("🚨 EXIT MANAGER CRASHED! Restarting immediately...")
            return self.start_exit_manager()
        
        return True
    
    def stop_all(self):
        """Stop both bots gracefully"""
        print("\n🛑 Stopping all bots...")
        
        if self.day_trader_process:
            try:
                self.day_trader_process.terminate()
                self.day_trader_process.wait(timeout=10)
                print("✅ Day Trader stopped")
            except Exception as e:
                print(f"⚠️  Error stopping Day Trader: {e}")
                self.day_trader_process.kill()
        
        if self.exit_manager_process:
            try:
                self.exit_manager_process.terminate()
                self.exit_manager_process.wait(timeout=10)
                print("✅ Exit Manager stopped")
            except Exception as e:
                print(f"⚠️  Error stopping Exit Manager: {e}")
                self.exit_manager_process.kill()
    
    def print_status(self):
        """Print current system status"""
        print("\n" + "="*80)
        print(f"📊 Supervisor Status - {datetime.now().strftime('%H:%M:%S')}")
        print("="*80)
        
        # Bot status
        exit_running = self.exit_manager_process and self.exit_manager_process.poll() is None
        day_running = self.day_trader_process and self.day_trader_process.poll() is None
        
        print(f"Exit Manager: {'🟢 RUNNING' if exit_running else '🔴 STOPPED'}")
        print(f"Day Trader:   {'🟢 RUNNING' if day_running else '🔴 STOPPED'}")
        
        # Database stats
        active_positions = self.db.get_active_positions()
        closed_today = self.db.get_closed_today()
        
        print(f"\n📈 Active Positions: {len(active_positions)}")
        print(f"📉 Closed Today: {len(closed_today)}")
        
        if closed_today:
            total_pnl = sum(p['profit_loss_pct'] for p in closed_today if p['profit_loss_pct'])
            print(f"   Total P&L Today: {total_pnl:+.2f}%")
        
        print("="*80)
    
    def should_be_awake(self):
        """Check if bots should be running based on schedule"""
        now = datetime.now()
        current_hour = now.hour
        
        # Market hours: 7 AM - 1 PM PT (10 AM - 4 PM ET)
        return self.WAKE_HOUR <= current_hour < self.SLEEP_HOUR
    
    def run(self):
        """Main supervisor loop with sleep/wake scheduling"""
        print("="*80)
        print("🤖 Trading Bot Supervisor (24/7 with Smart Scheduling)")
        print("="*80)
        print(f"Wake time: {self.WAKE_HOUR}:00 AM PT (10:00 AM ET)")
        print(f"Sleep time: {self.SLEEP_HOUR}:00 PM PT (4:00 PM ET)")
        print("Press Ctrl+C to stop supervisor")
        print("="*80 + "\n")
        
        last_status = time.time()
        
        try:
            # Initial startup check
            now = datetime.now()
            should_be_awake = self.should_be_awake()
            
            if should_be_awake:
                # Start bots immediately on startup if within trading hours
                print(f"\n✅ Within trading hours ({now.strftime('%H:%M:%S')}). Starting bots...")
                print("="*80)
                
                if not self.start_exit_manager():
                    print("❌ Failed to start Exit Manager")
                    return
                
                time.sleep(5)
                
                if not self.start_day_trader():
                    print("⚠️  Failed to start Day Trader. Continuing with Exit Manager only.")
                
                self.sleeping = False
                print("✅ Bots started successfully\n")
            else:
                # Outside trading hours on startup
                print(f"\n💤 Outside trading hours ({now.strftime('%H:%M:%S')}). Sleeping...")
                print(f"Will auto-wake at {self.WAKE_HOUR}:00 AM PT\n")
                self.sleeping = True
            
            while self.running:
                now = datetime.now()
                should_be_awake = self.should_be_awake()
                
                if should_be_awake and self.sleeping:
                    # Time to wake up!
                    print(f"\n⏰ WAKE UP! {now.strftime('%H:%M:%S')} - Starting trading day")
                    print("="*80)
                    
                    # Clear yesterday's closed positions
                    self.db.clear_closed_today()
                    
                    # Start bots
                    if not self.start_exit_manager():
                        print("❌ Failed to start Exit Manager. Retrying in 60s...")
                        time.sleep(60)
                        continue
                    
                    time.sleep(5)  # Give exit manager time to initialize
                    
                    if not self.start_day_trader():
                        print("❌ Failed to start Day Trader. Continuing with Exit Manager only.")
                    
                    self.sleeping = False
                    
                elif not should_be_awake and not self.sleeping:
                    # Time to sleep!
                    print(f"\n💤 SLEEP TIME! {now.strftime('%H:%M:%S')} - Market closed")
                    print("="*80)
                    self.stop_all()
                    self.sleeping = True
                    print(f"Sleeping until {self.WAKE_HOUR}:00 AM PT...")
                    print("Supervisor will keep running and auto-wake\n")
                
                elif not self.sleeping:
                    # Bots should be running - monitor them
                    self.check_exit_manager()  # Critical - must always run
                    self.check_day_trader()     # Can restart if needed
                    
                    # Print status every 5 minutes
                    if time.time() - last_status > 300:
                        self.print_status()
                        last_status = time.time()
                    
                    time.sleep(30)  # Check every 30 seconds
                else:
                    # Sleeping - check less frequently
                    time.sleep(300)  # Check every 5 minutes while sleeping
                
        except KeyboardInterrupt:
            print("\n\n👋 Supervisor stopped by user")
        finally:
            if not self.sleeping:
                self.stop_all()
            print("✅ Supervisor shutdown complete")


if __name__ == "__main__":
    supervisor = BotSupervisor()
    supervisor.run()
