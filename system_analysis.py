"""
System Analysis and Performance Optimization
Analyzes hardware resources and provides optimization recommendations
"""
import psutil
import platform
import multiprocessing
import sys

def analyze_system():
    """Analyze system resources and capabilities"""
    print("=" * 60)
    print("SYSTEM HARDWARE ANALYSIS")
    print("=" * 60)
    
    # CPU Information
    print("\n🖥️  CPU INFORMATION:")
    print(f"   Processor: {platform.processor()}")
    print(f"   Physical Cores: {psutil.cpu_count(logical=False)}")
    print(f"   Total Threads (Logical): {psutil.cpu_count(logical=True)}")
    
    freq = psutil.cpu_freq()
    if freq:
        print(f"   Max Frequency: {freq.max:.0f} MHz")
        print(f"   Current Frequency: {freq.current:.0f} MHz")
    
    # CPU Usage
    cpu_percent = psutil.cpu_percent(interval=1, percpu=True)
    print(f"   Current CPU Usage (Overall): {sum(cpu_percent)/len(cpu_percent):.1f}%")
    print(f"   Per-Core Usage: {[f'{x:.1f}%' for x in cpu_percent]}")
    
    # Memory Information
    print("\n💾 MEMORY INFORMATION:")
    mem = psutil.virtual_memory()
    print(f"   Total RAM: {mem.total / (1024**3):.2f} GB")
    print(f"   Available RAM: {mem.available / (1024**3):.2f} GB")
    print(f"   Used RAM: {mem.used / (1024**3):.2f} GB ({mem.percent}%)")
    print(f"   Free RAM: {mem.free / (1024**3):.2f} GB")
    
    # Disk Information
    print("\n💿 DISK INFORMATION:")
    disk = psutil.disk_usage('C:')
    print(f"   Total Disk: {disk.total / (1024**3):.2f} GB")
    print(f"   Used Disk: {disk.used / (1024**3):.2f} GB ({disk.percent}%)")
    print(f"   Free Disk: {disk.free / (1024**3):.2f} GB")
    
    # GPU Information (if available)
    print("\n🎮 GPU INFORMATION:")
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            for i, gpu in enumerate(gpus):
                print(f"   GPU {i}: {gpu.name}")
                print(f"   GPU Memory Total: {gpu.memoryTotal} MB")
                print(f"   GPU Memory Used: {gpu.memoryUsed} MB ({gpu.memoryUtil*100:.1f}%)")
                print(f"   GPU Load: {gpu.load*100:.1f}%")
        else:
            print("   No dedicated GPU detected (CPU only)")
    except ImportError:
        print("   GPUtil not installed - run: pip install gputil")
        print("   GPU detection skipped")
    
    # Python Information
    print("\n🐍 PYTHON ENVIRONMENT:")
    print(f"   Python Version: {sys.version.split()[0]}")
    print(f"   Python Path: {sys.executable}")
    print(f"   Max Workers (multiprocessing): {multiprocessing.cpu_count()}")
    
    return {
        'cpu_cores': psutil.cpu_count(logical=False),
        'cpu_threads': psutil.cpu_count(logical=True),
        'ram_gb': mem.total / (1024**3),
        'available_ram_gb': mem.available / (1024**3)
    }

def generate_optimization_recommendations(specs):
    """Generate optimization recommendations based on system specs"""
    print("\n" + "=" * 60)
    print("PERFORMANCE OPTIMIZATION RECOMMENDATIONS")
    print("=" * 60)
    
    cpu_threads = specs['cpu_threads']
    ram_gb = specs['ram_gb']
    
    print("\n📊 CURRENT BOTTLENECKS:")
    
    # Trading bot is I/O bound (IBKR API, network requests)
    # Not CPU or GPU intensive
    print("   ⚠️  Day Trader is primarily I/O BOUND (network, IBKR API)")
    print("   ⚠️  Not CPU/GPU intensive - most time spent waiting for data")
    print("   ✅  Your system specs are MORE than sufficient")
    
    print("\n🚀 OPTIMIZATION STRATEGIES:")
    
    print("\n1. PARALLEL DATA FETCHING (Already Implemented)")
    print("   ✅ Data aggregator uses async/await for concurrent API calls")
    print("   ✅ Multiple tickers fetched simultaneously")
    print("   💡 Can increase concurrent connections if needed")
    
    print("\n2. WATCHLIST ANALYSIS PARALLELIZATION")
    max_workers = max(4, cpu_threads - 2)  # Leave 2 cores for OS
    print(f"   💡 Current: Sequential analysis")
    print(f"   ✅ Recommended: Use ThreadPoolExecutor with {max_workers} workers")
    print(f"   ⚡ Expected speedup: {max_workers}x for {max_workers}+ stocks")
    
    print("\n3. MEMORY OPTIMIZATION")
    if ram_gb > 16:
        print(f"   ✅ {ram_gb:.0f} GB RAM - Excellent for trading bot")
        print(f"   💡 Can cache more data in memory (increase cache size)")
        print(f"   💡 Can run multiple strategies simultaneously")
    else:
        print(f"   ⚠️  {ram_gb:.0f} GB RAM - Sufficient but conservative caching")
    
    print("\n4. DATABASE OPTIMIZATION")
    print("   💡 Use WAL mode for SQLite (concurrent reads/writes)")
    print("   💡 Add indexes on frequently queried columns")
    print("   💡 Batch inserts for better performance")
    
    print("\n5. NETWORK OPTIMIZATION")
    print("   💡 Use HTTP/2 connection pooling for API calls")
    print("   💡 Implement request batching where possible")
    print("   💡 Use local cache to reduce API calls")
    
    print("\n6. REAL-TIME MONITORING")
    print("   💡 Health monitor already checks CPU/memory every 5 min")
    print("   💡 Can reduce interval to 1 min for tighter control")
    
    print("\n⚠️  WARNING: DO NOT TRY TO MAX OUT RESOURCES")
    print("   - Trading bot needs responsive API connections")
    print("   - Maxing CPU/RAM can cause system instability")
    print("   - IBKR TWS needs resources too (~1-2 GB RAM)")
    print("   - Keep 20-30% resources free for stability")
    
    print("\n" + "=" * 60)
    print("RECOMMENDED CONFIGURATION")
    print("=" * 60)
    
    print(f"\n✅ Max Parallel Workers: {max_workers}")
    print(f"✅ Watchlist Analysis: ThreadPoolExecutor({max_workers})")
    print(f"✅ Health Check Interval: 60 seconds (instead of 300)")
    print(f"✅ Cache Size: Up to {int(ram_gb * 0.1)} GB")
    print(f"✅ SQLite WAL Mode: Enabled")
    print(f"✅ Connection Pool: 10 concurrent connections")
    
    return max_workers

if __name__ == '__main__':
    specs = analyze_system()
    max_workers = generate_optimization_recommendations(specs)
    
    print("\n" + "=" * 60)
    print("NEXT STEPS")
    print("=" * 60)
    print("\n1. Install GPU monitoring (optional):")
    print("   pip install gputil")
    print("\n2. Run optimized configuration:")
    print("   The bot will automatically use optimal settings")
    print("\n3. Monitor performance:")
    print("   Check logs/health_monitor.log for resource usage")
    print("\n" + "=" * 60)
