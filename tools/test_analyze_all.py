import os
import sys
from datetime import datetime, timedelta

# Add parent directory to path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import load_config
from storage.db_manager import DBManager
from analyzers.security_analyzer import SecurityAnalyzer
from analyzers.upload_analyzer import UploadAnalyzer
from analyzers.public_access_analyzer import PublicAccessAnalyzer
from analyzers.ops_analyzer import OpsAnalyzer
import sqlite3

# Patch sqlite built-in timestamp converter to avoid ValueError on +00 timezone string
sqlite3.register_converter("timestamp", lambda v: v.decode("utf-8"))
sqlite3.register_converter("TIMESTAMP", lambda v: v.decode("utf-8"))

def main():
    print("Initializing analyzers for historical data test...")
    
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.yaml')
    config = load_config(config_path)
    
    # DB Initialize
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'wasabi_monitor.db')
    db = DBManager(db_path)
    
    sec_analyzer = SecurityAnalyzer(config, db)
    up_analyzer = UploadAnalyzer(config, db)
    pub_analyzer = PublicAccessAnalyzer(config, db)
    ops_analyzer = OpsAnalyzer(config, db)
    
    # タイムウィンドウの設定（2026年3月1日〜現在）
    start_time = datetime(2026, 3, 1)
    end_time = datetime.now()
    print(f"Analyzing time window: {start_time} to {end_time}")
    
    all_metrics = []
    
    print("\n[Running Security Analyzer...]")
    metrics = sec_analyzer.analyze()
    all_metrics.extend(metrics)
    for k, v in metrics:
        print(f"  {k}: {v}")
        
    print("\n[Running Upload Analyzer...]")
    metrics = up_analyzer.analyze()
    all_metrics.extend(metrics)
    for k, v in metrics:
        print(f"  {k}: {v}")
        
    print("\n[Running Public Access Analyzer...]")
    metrics = pub_analyzer.analyze()
    all_metrics.extend(metrics)
    for k, v in metrics:
        print(f"  {k}: {v}")
        
    print("\n[Running Ops Analyzer...]")
    metrics = ops_analyzer.analyze()
    all_metrics.extend(metrics)
    for k, v in metrics:
        print(f"  {k}: {v}")
        
    print("\n--- Summary ---")
    print(f"Total metrics generated: {len(all_metrics)}")
    
if __name__ == "__main__":
    main()
