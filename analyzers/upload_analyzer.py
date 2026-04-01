##
# Path: wasabi-log-monitor/analyzers/upload_analyzer.py
# Purpose: 正常アップロード監視
# Rationale: バックアップの確実性を担保するための監査を行う
# Last Modified: 2026-04-01
##
import logging
import re
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from storage.db_manager import DBManager

logger = logging.getLogger(__name__)

class UploadAnalyzer:
    def __init__(self, config: Dict[str, Any], db_manager: DBManager):
        self.config = config.get('monitoring', {}).get('upload', {})
        self.expected_schedules = self.config.get('expected_schedules', [])
        # バックアップIPリストをホワイトリストとして利用
        self.ip_whitelist = config.get('ip_whitelist', {}).get('backup_server_ips', [])
        self.db = db_manager

    def analyze(self, start_time: datetime, end_time: datetime) -> List[Tuple[str, Any]]:
        metrics = []
        
        # UPL-01: 定期アップロード完了確認
        # 過去24時間以内に全スケジュールパターンに対する成功したPUTが存在するか確認（POC仕様）
        all_schedules_ok = 1
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

        # UPL-02: アップロードサイズ量
        res = self.db.execute_query('''
            SELECT SUM(object_size) FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ? AND operation = 'REST.PUT.OBJECT' AND http_status = 200
        ''', (start_time, end_time))
        upload_size = res[0][0] if res and res[0][0] else 0
        metrics.append(('wasabi.upl.upload.bytes', upload_size))

        # UPL-03: アップロード失敗検知
        res = self.db.execute_query('''
            SELECT COUNT(*) FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ? 
            AND operation = 'REST.PUT.OBJECT' AND http_status != 200
        ''', (start_time, end_time))
        count_fail = res[0][0] if res else 0
        metrics.append(('wasabi.upl.upload_failure.count', count_fail))

        # UPL-04: アップロード元IP確認
        import ipaddress
        allowed_networks = []
        for ip in self.ip_whitelist:
            try:
                allowed_networks.append(ipaddress.ip_network(ip))
            except ValueError:
                pass
                
        ips_res = self.db.execute_query('''
            SELECT DISTINCT remote_ip FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ? AND operation = 'REST.PUT.OBJECT'
        ''', (start_time, end_time))
        
        unknown_upload_ip_count = 0
        for (ip_str,) in ips_res:
             try:
                 ip_obj = ipaddress.ip_address(ip_str)
                 if allowed_networks:
                     is_known = any(ip_obj in net for net in allowed_networks)
                     if not is_known:
                         unknown_upload_ip_count += 1
             except ValueError:
                 unknown_upload_ip_count += 1
                 
        metrics.append(('wasabi.upl.unknown_ip.count', unknown_upload_ip_count))

        # UPL-05: マルチパートアップロード未完了 (差分での簡易計上)
        res = self.db.execute_query('''
            SELECT 
                SUM(CASE WHEN operation = 'REST.POST.UPLOADS' THEN 1 ELSE 0 END),
                SUM(CASE WHEN operation = 'REST.POST.UPLOAD' THEN 1 ELSE 0 END)
            FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ? 
        ''', (start_time, end_time))
        
        init_count = res[0][0] if res and res[0][0] else 0
        complete_count = res[0][1] if res and res[0][1] else 0
        uncompleted = max(0, init_count - complete_count)
        metrics.append(('wasabi.upl.multipart_uncompleted.count', uncompleted))

        # UPL-06: 期間内アップロード件数
        res = self.db.execute_query('''
            SELECT COUNT(*) FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ? AND operation = 'REST.PUT.OBJECT' AND http_status = 200
        ''', (start_time, end_time))
        count_put = res[0][0] if res else 0
        metrics.append(('wasabi.upl.daily_upload.count', count_put))

        return metrics
