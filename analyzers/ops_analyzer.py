##
# Path: wasabi-log-monitor/analyzers/ops_analyzer.py
# Purpose: 運用監視の分析
# Rationale: システム側のAPI問題やログ配送の遅延などを検知する
# Last Modified: 2026-04-01
##
import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime
from storage.db_manager import DBManager

logger = logging.getLogger(__name__)

class OpsAnalyzer:
    def __init__(self, config: Dict[str, Any], db_manager: DBManager):
        self.config = config.get('monitoring', {}).get('ops', {})
        self.db = db_manager

    def analyze(self, start_time: datetime, end_time: datetime) -> List[Tuple[str, Any]]:
        metrics = []
        metrics.extend(self._analyze_bucket_logs(start_time, end_time))
        return metrics

    def _analyze_bucket_logs(self, start: datetime, end: datetime) -> List[Tuple[str, Any]]:
        metrics = []

        # OPS-01: ログ配送遅延検知
        # 最後に保存されたログの時間と現在の時間の差分
        res = self.db.execute_query('''
            SELECT MAX(request_time) FROM bucket_logs
        ''')
        
        delay_seconds = 0
        if res and res[0][0]:
            last_log_time = res[0][0]
            if isinstance(last_log_time, str):
                try:
                    last_log_time = datetime.fromisoformat(last_log_time.split('.')[0])
                except ValueError:
                    pass
            if isinstance(last_log_time, datetime):
                delay = datetime.now() - last_log_time
                delay_seconds = delay.total_seconds()
        
        metrics.append(('wasabi.ops.log_delay.seconds', delay_seconds))

        # OPS-02: API スロットリング検知
        res = self.db.execute_query('''
            SELECT COUNT(*) FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ? 
            AND http_status IN (429, 503)
        ''', (start, end))
        count_throttle = res[0][0] if res else 0
        metrics.append(('wasabi.ops.throttle.count', count_throttle))

        # OPS-03: レプリケーション正常性
        # POCでは UPL-01 と被るため省略 または同様にカウントを返す
        metrics.append(('wasabi.ops.replication.status', 1))

        # OPS-04: ストレージ使用量の急増 (今回の処理期間の増加量)
        res = self.db.execute_query('''
            SELECT SUM(object_size) FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ? 
            AND operation = 'REST.PUT.OBJECT' AND http_status = 200
        ''', (start, end))
        added_bytes = res[0][0] if res and res[0][0] else 0
        metrics.append(('wasabi.ops.storage_increase.bytes', added_bytes))

        return metrics
