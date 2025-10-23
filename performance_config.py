"""
Performance Configuration for Day Trading Bot
Optimized based on system hardware analysis
"""

import psutil
import multiprocessing

class PerformanceConfig:
    """
    Dynamic performance configuration based on system resources
    Automatically adjusts to available CPU, RAM, and network capacity
    """
    
    def __init__(self):
        self.cpu_cores = psutil.cpu_count(logical=False) or 4
        self.cpu_threads = psutil.cpu_count(logical=True) or 8
        self.total_ram_gb = psutil.virtual_memory().total / (1024**3)
        
        # Calculate optimal settings
        self._calculate_optimal_settings()
    
    def _calculate_optimal_settings(self):
        """Calculate optimal performance settings"""
        
        # Worker threads for parallel processing
        # Leave 2 cores for OS and other processes
        self.max_workers = max(4, self.cpu_threads - 2)
        
        # Health check frequency
        # More frequent checks for better responsiveness
        self.health_check_interval = 60  # 1 minute
        
        # Database settings
        self.db_cache_size_mb = min(100, int(self.total_ram_gb * 0.3))  # 30% of RAM, max 100MB
        self.db_wal_enabled = True
        
        # Network/API settings
        self.max_concurrent_connections = 10
        self.api_timeout_seconds = 30
        self.connection_pool_size = 10
        
        # Cache settings
        self.max_cache_size_gb = int(self.total_ram_gb * 0.1)  # 10% of RAM
        self.cache_ttl_seconds = 300  # 5 minutes
        
        # Trading loop settings
        self.trading_loop_interval = 5  # seconds
        self.position_check_interval = 5  # seconds
        
        # Data aggregation settings
        self.batch_size = min(50, self.max_workers * 5)
        self.async_fetch_enabled = True
        
    def get_summary(self) -> dict:
        """Get summary of performance configuration"""
        return {
            'system': {
                'cpu_cores': self.cpu_cores,
                'cpu_threads': self.cpu_threads,
                'total_ram_gb': round(self.total_ram_gb, 2),
                'available_ram_gb': round(psutil.virtual_memory().available / (1024**3), 2)
            },
            'performance': {
                'max_workers': self.max_workers,
                'health_check_interval': self.health_check_interval,
                'db_cache_size_mb': self.db_cache_size_mb,
                'max_concurrent_connections': self.max_concurrent_connections,
                'max_cache_size_gb': self.max_cache_size_gb,
                'trading_loop_interval': self.trading_loop_interval,
                'batch_size': self.batch_size
            },
            'optimization_level': self._get_optimization_level()
        }
    
    def _get_optimization_level(self) -> str:
        """Determine optimization level based on resources"""
        if self.total_ram_gb >= 24 and self.cpu_threads >= 8:
            return "HIGH - Excellent hardware for trading bot"
        elif self.total_ram_gb >= 16 and self.cpu_threads >= 4:
            return "MEDIUM - Good hardware for trading bot"
        else:
            return "LOW - Minimal hardware, conservative settings"
    
    def print_configuration(self):
        """Print performance configuration"""
        print("\n" + "="*60)
        print("PERFORMANCE CONFIGURATION")
        print("="*60)
        
        summary = self.get_summary()
        
        print(f"\n🖥️  SYSTEM RESOURCES:")
        print(f"   CPU Cores: {summary['system']['cpu_cores']}")
        print(f"   CPU Threads: {summary['system']['cpu_threads']}")
        print(f"   Total RAM: {summary['system']['total_ram_gb']} GB")
        print(f"   Available RAM: {summary['system']['available_ram_gb']} GB")
        
        print(f"\n⚡ PERFORMANCE SETTINGS:")
        print(f"   Max Workers (Parallel): {summary['performance']['max_workers']}")
        print(f"   Health Check Interval: {summary['performance']['health_check_interval']}s")
        print(f"   Database Cache: {summary['performance']['db_cache_size_mb']} MB")
        print(f"   Max Connections: {summary['performance']['max_concurrent_connections']}")
        print(f"   Memory Cache: Up to {summary['performance']['max_cache_size_gb']} GB")
        print(f"   Trading Loop: Every {summary['performance']['trading_loop_interval']}s")
        print(f"   Batch Size: {summary['performance']['batch_size']} items")
        
        print(f"\n📊 OPTIMIZATION LEVEL:")
        print(f"   {summary['optimization_level']}")
        
        print("\n" + "="*60)

# Global instance
_config = None

def get_performance_config() -> PerformanceConfig:
    """Get global performance configuration instance"""
    global _config
    if _config is None:
        _config = PerformanceConfig()
    return _config

if __name__ == '__main__':
    config = get_performance_config()
    config.print_configuration()
