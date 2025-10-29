"""Check if running Day Trader has database integration"""
import inspect
import day_trading_agents

# Check if the code has database integration
source = inspect.getsource(day_trading_agents.IntradayTraderAgent)

has_add = 'add_active_position' in source
has_remove = 'remove_active_position' in source
has_db_attr = 'self.db' in source

print("=== DATABASE INTEGRATION CHECK ===")
print(f"✓ Has add_active_position calls: {has_add}")
print(f"✓ Has remove_active_position calls: {has_remove}")
print(f"✓ Has self.db attribute: {has_db_attr}")

if has_add and has_remove and has_db_attr:
    print("\n✓ CURRENT CODE HAS DATABASE INTEGRATION")
    print("\nBUG: Code has integration but trades aren't being added.")
    print("Possible causes:")
    print("1. Exception being raised in add_active_position()")
    print("2. Database connection issue")
    print("3. Transaction not committing")
    print("4. Running bots loaded OLD bytecode (.pyc cache)")
else:
    print("\n✗ CURRENT CODE MISSING DATABASE INTEGRATION")
    print("This explains why trades aren't added!")

# Check for __pycache__
import os
pyc_files = []
for root, dirs, files in os.walk('__pycache__'):
    for f in files:
        if 'day_trading_agents' in f:
            full_path = os.path.join(root, f)
            pyc_files.append(full_path)

if pyc_files:
    print(f"\n⚠ WARNING: Found {len(pyc_files)} bytecode cache files:")
    for f in pyc_files:
        mtime = os.path.getmtime(f)
        print(f"  {f} (modified: {mtime})")
    print("\nRunning bots might be using OLD cached bytecode!")
    print("Solution: Stop bots, delete __pycache__, restart")
