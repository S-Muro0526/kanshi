##
# Path: wasabi-log-monitor/analyzers/security_analyzer.py
# Purpose: 不正アクセス・操作の分析
# Rationale: DBに蓄積されたバケットログや監査ログからセキュリティルールの判定を行う
# Last Modified: 2026-04-01
##
import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime
from storage.db_manager import DBManager

logger = logging.getLogger(__name__)

class SecurityAnalyzer:
    def __init__(self, config: Dict[str, Any], db_manager: DBManager):
        self.config = config.get('monitoring', {}).get('security', {})
        self.ip_whitelist = config.get('ip_whitelist', {}).get('allowed_ips', [])
        # Add backup IPs to whitelist
        self.ip_whitelist.extend(config.get('ip_whitelist', {}).get('backup_server_ips', []))
        self.ua_blacklist_patterns = config.get('ua_blacklist', {}).get('patterns', [])
        self.db = db_manager

    def analyze(self, start_time: datetime, end_time: datetime) -> List[Tuple[str, Any]]:
        """指定された期間のログを分析し、送信用メトリクスを返す"""
        metrics = []
        metrics.extend(self._analyze_bucket_logs(start_time, end_time))
        metrics.extend(self._analyze_audit_logs(start_time, end_time))
        return metrics

    def _analyze_bucket_logs(self, start: datetime, end: datetime) -> List[Tuple[str, Any]]:
        metrics = []
        
        # SEC-01: 未認証アクセス検知
        res = self.db.execute_query('''
            SELECT COUNT(*) FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ? AND requester = '-'
        ''', (start, end))
        count_unauth = res[0][0] if res else 0
        metrics.append(('wasabi.sec.unauth_access.count', count_unauth))

        # SEC-02: 403エラー急増
        res = self.db.execute_query('''
            SELECT COUNT(*) FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ? AND http_status = 403
        ''', (start, end))
        count_403 = res[0][0] if res else 0
        metrics.append(('wasabi.sec.403_error.count', count_403))

        # SEC-03: 未知IPからのアクセス
        ips_res = self.db.execute_query('''
            SELECT DISTINCT remote_ip FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ?
        ''', (start, end))
        
        unknown_ip_count = 0
        import ipaddress
        allowed_networks = []
        for ip in self.ip_whitelist:
            try:
                allowed_networks.append(ipaddress.ip_network(ip))
            except ValueError:
                pass
        
        for (ip_str,) in ips_res:
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                is_known = any(ip_obj in net for net in allowed_networks)
                if not is_known:
                    hits = self.db.execute_query('''
                        SELECT COUNT(*) FROM bucket_logs 
                        WHERE request_time >= ? AND request_time < ? AND remote_ip = ?
                    ''', (start, end, ip_str))
                    unknown_ip_count += hits[0][0] if hits else 0
            except ValueError:
                pass
        
        metrics.append(('wasabi.sec.unknown_ip.count', unknown_ip_count))

        # SEC-04: 大量データダウンロード
        res = self.db.execute_query('''
            SELECT SUM(bytes_sent) FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ? AND operation LIKE 'REST.GET.OBJECT%'
        ''', (start, end))
        bytes_sent = res[0][0] if res and res[0][0] else 0
        metrics.append(('wasabi.sec.data_exfil.bytes', bytes_sent))

        # SEC-05: 不審なUserAgent
        uas_res = self.db.execute_query('''
            SELECT user_agent, COUNT(*) FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ?
            GROUP BY user_agent
        ''', (start, end))
        
        suspicious_ua_count = 0
        for ua_str, count in uas_res:
            if not ua_str:
                continue
            ua_lower = ua_str.lower()
            if any(pattern.lower() in ua_lower for pattern in self.ua_blacklist_patterns):
                suspicious_ua_count += count
                
        metrics.append(('wasabi.sec.suspicious_ua.count', suspicious_ua_count))

        # SEC-06: 大量DELETE操作
        res = self.db.execute_query('''
            SELECT COUNT(*) FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ? AND operation LIKE 'REST.DELETE.OBJECT%'
        ''', (start, end))
        count_delete = res[0][0] if res else 0
        metrics.append(('wasabi.sec.delete_ops.count', count_delete))

        # SEC-07: 通常時間外のアクセス
        start_hour = self.config.get('business_hours', {}).get('start', 8)
        end_hour = self.config.get('business_hours', {}).get('end', 22)
        
        off_hours_res = self.db.execute_query('''
            SELECT request_time FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ?
        ''', (start, end))
        
        off_hours_count = 0
        for (req_time,) in off_hours_res:
             if isinstance(req_time, str):
                 try:
                     # SQLite returns string if parsed failed or using fallback
                     # ISOFormat should be parseable
                     req_time = datetime.fromisoformat(req_time.split('.')[0])
                 except ValueError:
                     continue
             
             hour = req_time.hour
             if hour < start_hour or hour >= end_hour:
                 off_hours_count += 1
                 
        metrics.append(('wasabi.sec.off_hours.count', off_hours_count))

        # SEC-10: 弱いTLS/暗号スイート使用
        allowed_tls = self.config.get('allowed_tls_versions', ['TLSv1.2', 'TLSv1.3'])
        if allowed_tls:
            placeholders = ','.join('?' for _ in allowed_tls)
            query = f'''
                SELECT COUNT(*) FROM bucket_logs 
                WHERE request_time >= ? AND request_time < ? 
                AND tls_version NOT IN ({placeholders}) AND tls_version != '-' AND tls_version IS NOT NULL
            '''
            params = [start, end]
            params.extend(allowed_tls)
            res = self.db.execute_query(query, tuple(params))
            count_weak_tls = res[0][0] if res else 0
        else:
            count_weak_tls = 0
        metrics.append(('wasabi.sec.weak_tls.count', count_weak_tls))

        return metrics

    def _analyze_audit_logs(self, start: datetime, end: datetime) -> List[Tuple[str, Any]]:
        metrics = []

        # SEC-08: 管理操作の認証失敗
        res = self.db.execute_query('''
            SELECT COUNT(*) FROM audit_logs 
            WHERE timestamp >= ? AND timestamp < ? AND LOWER(result) LIKE '%fail%'
        ''', (start, end))
        count_fail = res[0][0] if res else 0
        metrics.append(('wasabi.sec.admin_fail.count', count_fail))

        # SEC-09: rootアカウント使用
        res = self.db.execute_query('''
            SELECT COUNT(*) FROM audit_logs 
            WHERE timestamp >= ? AND timestamp < ? AND user = 'root'
        ''', (start, end))
        count_root = res[0][0] if res else 0
        metrics.append(('wasabi.sec.root_usage.count', count_root))

        return metrics
