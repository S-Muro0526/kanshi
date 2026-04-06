##
# Path: wasabi-log-monitor/main.py
# Purpose: メイン実行・スケジューラスクリプト
# Rationale: 全てのコンポーネントを繋ぎ合わせ、定期実行を行う
# Key Dependencies: collectors/, analyzers/, alerting/, storage/
# Last Modified: 2026-04-06
##
import os
import time
import yaml
import logging
from datetime import datetime, timedelta, timezone
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
        
        # ローカルテストモード判定
        bucket_source = config.get('bucket_log', {}).get('source', 'bucket')
        audit_source = config.get('audit_log', {}).get('source', 'bucket')
        self.is_local_mode = (bucket_source == 'local' or audit_source == 'local')

    def collect_logs(self):
        logger.info("--- Starting Log Collection ---")
        try:
            b_count = self.bucket_collector.collect()
            a_count = self.audit_collector.collect()
            logger.info(f"Colletion summary: BucketLogs={b_count}, AuditLogs={a_count}")
        except Exception as e:
            logger.error(f"Error during collection phase: {e}")

    def _get_analysis_time_window(self):
        """分析対象の時間範囲を決定する"""
        end_time = datetime.now(timezone.utc)
        
        if self.is_local_mode:
            # ローカルモード: DB内の全データを対象とする
            start_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
            logger.info("Local test mode: analyzing ALL data in database.")
        else:
            # 本番モード: 一定間隔分のみ
            start_time = end_time - timedelta(seconds=self.analysis_interval)
        
        return start_time, end_time

    def analyze_and_alert(self):
        logger.info("--- Starting Log Analysis ---")
        start_time, end_time = self._get_analysis_time_window()
        
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
            
            # メトリクスをoutput.txtとコンソールに出力
            if all_metrics:
                self._output_metrics(all_metrics)
            
            # Zabbixへ送信（本番モードのみ）
            if all_metrics and not self.is_local_mode:
                success = self.zabbix_sender.send_metrics(all_metrics)
                if success:
                    logger.info("Metrics successfully sent to Zabbix.")
                else:
                    logger.warning("Failed to send some/all metrics to Zabbix. (expected if zabbix_sender is not configured)")
                    
        except Exception as e:
            logger.error(f"Error during analysis or alerting phase: {e}", exc_info=True)

    def _output_metrics(self, metrics):
        """メトリクスをコンソールとoutput.txtに出力する"""
        # コンソール出力
        logger.info("========== Analysis Results ==========")
        for key, value in metrics:
            logger.info(f"  {key}: {value}")
        logger.info("======================================")
        
        # output.txt に書き出し
        output_path = './output.txt'
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"# Wasabi Monitor Analysis Results\n")
                f.write(f"# Generated: {datetime.now(timezone.utc).isoformat()}\n")
                f.write(f"# Mode: {'LOCAL TEST' if self.is_local_mode else 'PRODUCTION'}\n")
                f.write(f"# Database: {os.path.abspath(self.config['database']['sqlite']['path'])}\n")
                f.write(f"\n")
                for key, value in metrics:
                    f.write(f"{key}: {value}\n")
            logger.info(f"Metrics written to {os.path.abspath(output_path)}")
        except Exception as e:
            logger.error(f"Failed to write output.txt: {e}")

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
    
    if app.is_local_mode:
        # ローカルテスト: 一度実行して終了
        logger.info("Local test mode completed. Check output.txt for results.")
        return
    
    # 本番モード: スケジューラで定期実行
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
