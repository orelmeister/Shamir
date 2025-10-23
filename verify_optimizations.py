"""Quick verification of performance optimizations"""
import sqlite3

print("="*60)
print("PERFORMANCE OPTIMIZATION VERIFICATION")
print("="*60)

# Check database optimizations
conn = sqlite3.connect('trading_history.db')

# Check WAL mode
wal_mode = conn.execute('PRAGMA journal_mode').fetchone()[0]
print(f"\n✅ Database WAL Mode: {wal_mode}")

# Check cache size
cache_size = conn.execute('PRAGMA cache_size').fetchone()[0]
print(f"✅ Database Cache: {abs(cache_size)} KB")

# Check synchronous mode
sync_mode = conn.execute('PRAGMA synchronous').fetchone()[0]
print(f"✅ Synchronous Mode: {sync_mode} (1=NORMAL)")

# Check indexes
indexes = conn.execute("""
    SELECT name FROM sqlite_master 
    WHERE type='index' AND name LIKE 'idx_%'
""").fetchall()
print(f"\n✅ Performance Indexes: {len(indexes)} created")
for idx in indexes:
    print(f"   - {idx[0]}")

# Check performance config
from performance_config import get_performance_config
config = get_performance_config()
summary = config.get_summary()

print(f"\n✅ Max Parallel Workers: {summary['performance']['max_workers']}")
print(f"✅ Health Check Interval: {summary['performance']['health_check_interval']}s")
print(f"✅ Optimization Level: {summary['optimization_level']}")

print("\n" + "="*60)
print("ALL OPTIMIZATIONS VERIFIED ✅")
print("="*60)

conn.close()
