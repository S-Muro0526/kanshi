##
# Path: wasabi-log-monitor/analyzers/upload_analyzer.py
# Purpose: 正常アップロード監視
# Rationale: バックアップの確実性を担保するための監査を行う
# Key Dependencies: storage/db_manager.py
# Last Modified: 2026-04-02
##
import logging
import re
import ipaddress
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from storage.db_manager import DBManager

logger = logging.getLogger(__name__)

class UploadAnalyzer:
    def __init__(self, config: Dict[str, Any], db_manager: DBManager):
        self.config = config.get('monitoring', {}).get('upload', {})
        self.expected_schedules = self.config.get('expected_schedules', [])
        self.ip_whitelist = config.get('ip_whitelist', {}).get('backup_server_ips', [])
        self.db = db_manager

        # IPホワイトリストの事前パース
        self._allowed_networks = []
        for ip in self.ip_whitelist:
            try:
                self._allowed_networks.append(ipaddress.ip_network(ip))
            except ValueError:
                pass

    def analyze(self) -> List[Tuple[str, Any]]:
        metrics = []

        # UPL-01: 定期アップロード完了確認（グローバル）
        all_schedules_ok = 1
        end_time = datetime.now()
        day_ago = end_time - timedelta(days=1)
        for schedule in self.expected_schedules:
            pattern = schedule['key_pattern']
            logs = self.db.execute_query('''
                SELECT key FROM bucket_logs
                WHERE request_time >= ? AND request_time < ?
                AND operation = 'REST.PUT.OBJECT' AND http_status = 200
            ''', (day_ago, end_time))

            p = re.compile(pattern)
            matched = any(p.search(log[0] or "") for log in logs)
            if not matched:
                all_schedules_ok = 0
                break

        metrics.append(('wasabi.upl.scheduled.status', all_schedules_ok))

        # UPL-02: アップロードサイズ量（バケット別）
        res = self.db.execute_query('''
            SELECT bucket, SUM(object_size) FROM bucket_logs
            WHERE analyzed = 0 AND operation = 'REST.PUT.OBJECT' AND http_status = 200
            GROUP BY bucket
        ''')
        total = 0
        for bucket, size in res:
            val = size if size else 0
            metrics.append((f'wasabi.upl.upload.bytes[{bucket}]', val))
            total += val
        metrics.append(('wasabi.upl.upload.bytes', total))

        # UPL-03: アップロード失敗検知（バケット別）
        res = self.db.execute_query('''
            SELECT bucket, COUNT(*) FROM bucket_logs
            WHERE analyzed = 0
            AND operation = 'REST.PUT.OBJECT' AND http_status != 200
            GROUP BY bucket
        ''')
        total = 0
        for bucket, count in res:
            metrics.append((f'wasabi.upl.upload_failure.count[{bucket}]', count))
            total += count
        metrics.append(('wasabi.upl.upload_failure.count', total))

        # UPL-04: アップロード元IP確認（バケット別）
        ips_res = self.db.execute_query('''
            SELECT bucket, remote_ip, COUNT(*) FROM bucket_logs
            WHERE analyzed = 0 AND operation = 'REST.PUT.OBJECT'
            GROUP BY bucket, remote_ip
        ''')

        unknown_by_bucket = {}
        for bucket, ip_str, count in ips_res:
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                if self._allowed_networks:
                    is_known = any(ip_obj in net for net in self._allowed_networks)
                    if not is_known:
                        unknown_by_bucket[bucket] = unknown_by_bucket.get(bucket, 0) + count
            except ValueError:
                unknown_by_bucket[bucket] = unknown_by_bucket.get(bucket, 0) + count

        total = 0
        for bucket, count in unknown_by_bucket.items():
            metrics.append((f'wasabi.upl.unknown_ip.count[{bucket}]', count))
            total += count
        metrics.append(('wasabi.upl.unknown_ip.count', total))

        # UPL-05: マルチパートアップロード未完了（バケット別）
        res = self.db.execute_query('''
            SELECT bucket,
                SUM(CASE WHEN operation = 'REST.POST.UPLOADS' THEN 1 ELSE 0 END),
                SUM(CASE WHEN operation = 'REST.POST.UPLOAD' THEN 1 ELSE 0 END)
            FROM bucket_logs
            WHERE analyzed = 0
            GROUP BY bucket
        ''')

        total = 0
        for bucket, init_count, complete_count in res:
            init_c = init_count if init_count else 0
            comp_c = complete_count if complete_count else 0
            uncompleted = max(0, init_c - comp_c)
            metrics.append((f'wasabi.upl.multipart_uncompleted.count[{bucket}]', uncompleted))
            total += uncompleted
        metrics.append(('wasabi.upl.multipart_uncompleted.count', total))

        # UPL-06: 期間内アップロード件数（バケット別）
        res = self.db.execute_query('''
            SELECT bucket, COUNT(*) FROM bucket_logs
            WHERE analyzed = 0 AND operation = 'REST.PUT.OBJECT' AND http_status = 200
            GROUP BY bucket
        ''')
        total = 0
        for bucket, count in res:
            metrics.append((f'wasabi.upl.daily_upload.count[{bucket}]', count))
            total += count
        metrics.append(('wasabi.upl.daily_upload.count', total))

        return metrics
