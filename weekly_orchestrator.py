"""
Weekly Bot Orchestrator
Runs all phases sequentially with error handling and restart capability.
"""
import json
import logging
import os
import sys
import subprocess
from datetime import datetime
import time

# Import shared utilities
from shared_state.state_manager import read_state, write_state

# Configuration
WEEKLY_BOT_DIR = "weekly_bot"
PHASE_SCRIPTS = [
    "01_data_aggregator.py",
    "02_analyst.py",
    "03_portfolio_manager.py",
    "04_monitor_positions.py"  # Optional - runs in background
]

# Generate run ID
RUN_ID = datetime.now().strftime('%Y%m%d_%H%M%S')

# Setup logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f'orchestrator_{RUN_ID}.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Orchestrator] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_phase(script_name, phase_num):
    """
    Run a single phase script.
    Returns: (success: bool, output: str, error: str)
    """
    script_path = os.path.join(WEEKLY_BOT_DIR, script_name)
    
    if not os.path.exists(script_path):
        logger.error(f"Phase script not found: {script_path}")
        return (False, "", f"Script not found: {script_path}")
    
    logger.info(f"=" * 80)
    logger.info(f"PHASE {phase_num}: {script_name}")
    logger.info(f"=" * 80)
    
    start_time = time.time()
    
    try:
        # Run the phase script
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout per phase
        )
        
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            logger.info(f"✅ Phase {phase_num} completed successfully in {elapsed:.1f}s")
            return (True, result.stdout, result.stderr)
        else:
            logger.error(f"❌ Phase {phase_num} failed with exit code {result.returncode}")
            logger.error(f"STDOUT: {result.stdout}")
            logger.error(f"STDERR: {result.stderr}")
            return (False, result.stdout, result.stderr)
    
    except subprocess.TimeoutExpired:
        logger.error(f"⏰ Phase {phase_num} timed out after 1 hour")
        return (False, "", "Phase timeout after 1 hour")
    
    except Exception as e:
        logger.error(f"💥 Phase {phase_num} crashed: {e}", exc_info=True)
        return (False, "", str(e))


def initialize_state():
    """Initialize phase state for a new cycle."""
    write_state('phase_state', {
        'current_phase': 'initialized',
        'timestamp': datetime.now().isoformat(),
        'orchestrator_run_id': RUN_ID
    })
    logger.info("Initialized phase state")


def get_phase_state():
    """Read current phase state."""
    return read_state('phase_state')


def main():
    """Main orchestrator execution."""
    logger.info("=" * 80)
    logger.info("WEEKLY BOT ORCHESTRATOR - Starting")
    logger.info(f"Run ID: {RUN_ID}")
    logger.info("=" * 80)
    
    # Menu for user
    print("\n" + "=" * 60)
    print("WEEKLY BOT - Main Menu")
    print("=" * 60)
    print("1. Full Cycle (Aggregation → Analysis → Rebalance → Monitor)")
    print("2. Quick Start (Skip aggregation, use existing data)")
    print("3. Analysis Only (Run analyst with existing aggregation)")
    print("4. Rebalance Only (Execute trades with existing analysis)")
    print("5. Monitor Only (Start position monitoring)")
    print("6. Exit")
    print("=" * 60)
    
    choice = input("\nSelect option [1-6]: ").strip()
    
    if choice == '6':
        logger.info("User chose to exit.")
        sys.exit(0)
    
    # Initialize state
    initialize_state()
    
    phases_to_run = []
    
    if choice == '1':
        # Full cycle
        logger.info("Selected: Full Cycle")
        phases_to_run = [(1, PHASE_SCRIPTS[0]), (2, PHASE_SCRIPTS[1]), (3, PHASE_SCRIPTS[2])]
        start_monitoring = True
    
    elif choice == '2':
        # Quick start - skip aggregation
        logger.info("Selected: Quick Start (skip aggregation)")
        # Check if aggregation data exists
        if not os.path.exists('full_market_data.json'):
            logger.error("❌ full_market_data.json not found. Cannot skip aggregation.")
            logger.error("Please run Full Cycle (Option 1) first.")
            sys.exit(1)
        
        # Set phase state to aggregation_complete
        phase_data = get_phase_state()
        # Load stocks from full_market_data.json
        with open('full_market_data.json', 'r') as f:
            market_data = json.load(f)
        
        phase_data['current_phase'] = 'aggregation_complete'
        phase_data['stocks_for_analysis'] = market_data
        write_state('phase_state', phase_data)
        
        phases_to_run = [(2, PHASE_SCRIPTS[1]), (3, PHASE_SCRIPTS[2])]
        start_monitoring = True
    
    elif choice == '3':
        # Analysis only
        logger.info("Selected: Analysis Only")
        phases_to_run = [(2, PHASE_SCRIPTS[1])]
        start_monitoring = False
    
    elif choice == '4':
        # Rebalance only
        logger.info("Selected: Rebalance Only")
        # Check if analysis results exist
        phase_data = get_phase_state()
        if phase_data.get('current_phase') != 'analysis_complete':
            logger.error("❌ No analysis results found. Cannot rebalance.")
            logger.error("Please run Analysis first (Option 3).")
            sys.exit(1)
        
        phases_to_run = [(3, PHASE_SCRIPTS[2])]
        start_monitoring = True
    
    elif choice == '5':
        # Monitor only
        logger.info("Selected: Monitor Only")
        phases_to_run = [(4, PHASE_SCRIPTS[3])]
        start_monitoring = False  # Already included in phases
    
    else:
        logger.error(f"Invalid choice: {choice}")
        sys.exit(1)
    
    # Run phases sequentially
    all_success = True
    
    for phase_num, script_name in phases_to_run:
        success, stdout, stderr = run_phase(script_name, phase_num)
        
        if not success:
            logger.error(f"Phase {phase_num} failed. Stopping orchestration.")
            all_success = False
            break
        
        # Brief pause between phases
        time.sleep(2)
    
    if not all_success:
        logger.error("=" * 80)
        logger.error("ORCHESTRATION FAILED")
        logger.error("=" * 80)
        sys.exit(1)
    
    # Start monitoring in background if requested
    if start_monitoring and choice != '5':
        logger.info("\n" + "=" * 80)
        logger.info("Starting position monitoring in background...")
        logger.info("=" * 80)
        
        monitor_script = os.path.join(WEEKLY_BOT_DIR, PHASE_SCRIPTS[3])
        
        try:
            # Start monitor as background process
            monitor_process = subprocess.Popen(
                [sys.executable, monitor_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            logger.info(f"✅ Monitor started (PID: {monitor_process.pid})")
            logger.info(f"Monitor logs: logs/monitor_{RUN_ID}.log")
            
            # Don't wait for monitor to finish (it runs until market close)
            logger.info("Monitor is running in background. Orchestrator will exit now.")
        
        except Exception as e:
            logger.error(f"Failed to start monitor: {e}")
    
    logger.info("\n" + "=" * 80)
    logger.info("WEEKLY BOT ORCHESTRATOR - Complete")
    logger.info(f"Total phases executed: {len(phases_to_run)}")
    logger.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nOrchestrator interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Fatal orchestrator error: {e}", exc_info=True)
        sys.exit(1)
