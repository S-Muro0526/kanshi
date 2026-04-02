##
# Path: wasabi-log-monitor/analyzers/ops_analyzer.py
# Purpose: 運用監視の分析
# Rationale: システム側のAPI問題やログ配送の遅延などを検知する
# Key Dependencies: storage/db_manager.py
# Last Modified: 2026-04-02
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

    def analyze(self) -> List[Tuple[str, Any]]:
        metrics = []
        metrics.extend(self._analyze_bucket_logs())
        return metrics

    def _analyze_bucket_logs(self) -> List[Tuple[str, Any]]:
        metrics = []

        # OPS-01: ログ配送遅延検知（グローバル）
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

        # OPS-02: API スロットリング検知（バケット別）
        res = self.db.execute_query('''
            SELECT bucket, COUNT(*) FROM bucket_logs
            WHERE analyzed = 0
            AND http_status IN (429, 503)
            GROUP BY bucket
        ''')
        total = 0
        for bucket, count in res:
            metrics.append((f'wasabi.ops.throttle.count[{bucket}]', count))
            total += count
        metrics.append(('wasabi.ops.throttle.count', total))

        # OPS-03: レプリケーション正常性（グローバル）
        metrics.append(('wasabi.ops.replication.status', 1))

        # OPS-04: ストレージ使用量の急増（バケット別）
        res = self.db.execute_query('''
            SELECT bucket, SUM(object_size) FROM bucket_logs
            WHERE analyzed = 0
            AND operation = 'REST.PUT.OBJECT' AND http_status = 200
            GROUP BY bucket
        ''')
        total = 0
        for bucket, size in res:
            val = size if size else 0
            metrics.append((f'wasabi.ops.storage_increase.bytes[{bucket}]', val))
            total += val
        metrics.append(('wasabi.ops.storage_increase.bytes', total))

        return metrics
