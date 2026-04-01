##
# Path: wasabi-log-monitor/main.py
# Purpose: メイン実行・スケジューラスクリプト
# Rationale: 全てのコンポーネントを繋ぎ合わせ、定期実行を行う
# Last Modified: 2026-04-01
##
import os
import time
import yaml
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler

from storage.db_manager import DBManager
from collectors.bucket_log_collector import BucketLogCollector
from collectors.audit_log_collector import AuditLogCollector
from analyzers.security_analyzer import SecurityAnalyzer
from analyzers.upload_analyzer import UploadAnalyzer
from analyzers.public_access_analyzer import PublicAccessAnalyzer
from analyzers.ops_analyzer import OpsAnalyzer
from alerting.zabbix_sender import ZabbixSenderWrapper

# ロガー設定
os.makedirs('./logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./logs/wasabi_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('main')

def load_config(path='config.yaml'):
    with open(path, 'r', encoding='utf-8') as f:
        # 環境変数展開は未実装（POC用途）
        return yaml.safe_load(f)

class MonitorApp:
    def __init__(self, config):
        self.config = config
        
        db_path = config['database']['sqlite']['path']
        self.db = DBManager(db_path)
        
        self.bucket_collector = BucketLogCollector(config, self.db)
        self.audit_collector = AuditLogCollector(config, self.db)
        
        self.security_analyzer = SecurityAnalyzer(config, self.db)
        self.upload_analyzer = UploadAnalyzer(config, self.db)
        self.public_access_analyzer = PublicAccessAnalyzer(config, self.db)
        self.ops_analyzer = OpsAnalyzer(config, self.db)
        
        self.zabbix_sender = ZabbixSenderWrapper(config)
        
        self.analysis_interval = config['scheduler'].get('analysis_interval', 300)

    def collect_logs(self):
        logger.info("--- Starting Log Collection ---")
        try:
            b_count = self.bucket_collector.collect()
            a_count = self.audit_collector.collect()
            logger.info(f"Colletion summary: BucketLogs={b_count}, AuditLogs={a_count}")
        except Exception as e:
            logger.error(f"Error during collection phase: {e}")

    def analyze_and_alert(self):
        logger.info("--- Starting Log Analysis ---")
        end_time = datetime.now()
        # 一定間隔分より長めに取る場合はここを調整する
        start_time = end_time - timedelta(seconds=self.analysis_interval)
        
        all_metrics = []
        try:
            logger.info(f"Analyzing time window: {start_time} to {end_time}")
            all_metrics.extend(self.security_analyzer.analyze(start_time, end_time))
            all_metrics.extend(self.upload_analyzer.analyze(start_time, end_time))
            all_metrics.extend(self.public_access_analyzer.analyze(start_time, end_time))
            all_metrics.extend(self.ops_analyzer.analyze(start_time, end_time))
            
            # nullの場合は0にする
            all_metrics = [(k, v if v is not None else 0) for k, v in all_metrics]
            
            logger.info(f"Generated {len(all_metrics)} metrics.")
            
            # Zabbixへ送信
            if all_metrics:
                success = self.zabbix_sender.send_metrics(all_metrics)
                if success:
                    logger.info("Metrics successfully sent to Zabbix.")
                else:
                    logger.warning("Failed to send some/all metrics to Zabbix. (expected if zabbix_sender is not configured)")
                    
        except Exception as e:
            logger.error(f"Error during analysis or alerting phase: {e}")

    def run_job(self):
        self.collect_logs()
        self.analyze_and_alert()

def main():
    logger.info("Initializing Wasabi Log Monitor POC...")
    try:
        config = load_config()
    except FileNotFoundError:
         logger.error("config.yaml is missing.")
         return
         
    app = MonitorApp(config)
    
    # 起動時に一度実行
    app.run_job()
    
    # スケジューラで定期実行
    interval = config['scheduler'].get('collection_interval', 300)
    scheduler = BlockingScheduler()
    scheduler.add_job(app.run_job, 'interval', seconds=interval)
    
    logger.info(f"Scheduler started with interval {interval} seconds. Press Ctrl+C to exit.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")

if __name__ == "__main__":
    main()
