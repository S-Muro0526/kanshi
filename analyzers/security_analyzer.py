##
# Path: wasabi-log-monitor/analyzers/security_analyzer.py
# Purpose: 不正アクセス・操作の分析
# Rationale: DBに蓄積されたバケットログや監査ログからセキュリティルールの判定を行う
# Key Dependencies: storage/db_manager.py
# Last Modified: 2026-04-02
##
import logging
import ipaddress
from typing import Dict, Any, List, Tuple
from datetime import datetime
from storage.db_manager import DBManager

logger = logging.getLogger(__name__)

class SecurityAnalyzer:
    def __init__(self, config: Dict[str, Any], db_manager: DBManager):
        self.config = config.get('monitoring', {}).get('security', {})
        self.ip_whitelist = config.get('ip_whitelist', {}).get('allowed_ips', [])
        self.ip_whitelist.extend(config.get('ip_whitelist', {}).get('backup_server_ips', []))
        self.ua_blacklist_patterns = config.get('ua_blacklist', {}).get('patterns', [])
        self.db = db_manager

        # IPホワイトリストの事前パース
        self._allowed_networks = []
        for ip in self.ip_whitelist:
            try:
                self._allowed_networks.append(ipaddress.ip_network(ip))
            except ValueError:
                pass

    def analyze(self) -> List[Tuple[str, Any]]:
        """未分析のログを調べて送信用メトリクスを返す"""
        metrics = []
        metrics.extend(self._analyze_bucket_logs())
        metrics.extend(self._analyze_audit_logs())
        return metrics

    def _analyze_bucket_logs(self) -> List[Tuple[str, Any]]:
        metrics = []

        # SEC-01: 未認証アクセス検知
        res = self.db.execute_query('''
            SELECT bucket, COUNT(*) FROM bucket_logs
            WHERE analyzed = 0 AND requester = '-'
            GROUP BY bucket
        ''')
        total = 0
        for bucket, count in res:
            metrics.append((f'wasabi.sec.unauth_access.count[{bucket}]', count))
            total += count
        metrics.append(('wasabi.sec.unauth_access.count', total))

        # SEC-02: 403エラー急増
        res = self.db.execute_query('''
            SELECT bucket, COUNT(*) FROM bucket_logs
            WHERE analyzed = 0 AND http_status = 403
            GROUP BY bucket
        ''')
        total = 0
        for bucket, count in res:
            metrics.append((f'wasabi.sec.403_error.count[{bucket}]', count))
            total += count
        metrics.append(('wasabi.sec.403_error.count', total))

        # SEC-03: 未知IPからのアクセス
        ips_res = self.db.execute_query('''
            SELECT bucket, remote_ip, COUNT(*) FROM bucket_logs
            WHERE analyzed = 0
            GROUP BY bucket, remote_ip
        ''')

        unknown_by_bucket = {}
        for bucket, ip_str, count in ips_res:
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                is_known = any(ip_obj in net for net in self._allowed_networks)
                if not is_known:
                    unknown_by_bucket[bucket] = unknown_by_bucket.get(bucket, 0) + count
            except ValueError:
                pass

        total = 0
        for bucket, count in unknown_by_bucket.items():
            metrics.append((f'wasabi.sec.unknown_ip.count[{bucket}]', count))
            total += count
        metrics.append(('wasabi.sec.unknown_ip.count', total))

        # SEC-04: 大量データダウンロード
        res = self.db.execute_query('''
            SELECT bucket, SUM(bytes_sent) FROM bucket_logs
            WHERE analyzed = 0 AND operation LIKE 'REST.GET.OBJECT%'
            GROUP BY bucket
        ''')
        total = 0
        for bucket, bytes_val in res:
            val = bytes_val if bytes_val else 0
            metrics.append((f'wasabi.sec.data_exfil.bytes[{bucket}]', val))
            total += val
        metrics.append(('wasabi.sec.data_exfil.bytes', total))

        # SEC-05: 不審なUserAgent
        uas_res = self.db.execute_query('''
            SELECT bucket, user_agent, COUNT(*) FROM bucket_logs
            WHERE analyzed = 0
            GROUP BY bucket, user_agent
        ''')

        suspicious_by_bucket = {}
        for bucket, ua_str, count in uas_res:
            if not ua_str:
                continue
            ua_lower = ua_str.lower()
            if any(pattern.lower() in ua_lower for pattern in self.ua_blacklist_patterns):
                suspicious_by_bucket[bucket] = suspicious_by_bucket.get(bucket, 0) + count

        total = 0
        for bucket, count in suspicious_by_bucket.items():
            metrics.append((f'wasabi.sec.suspicious_ua.count[{bucket}]', count))
            total += count
        metrics.append(('wasabi.sec.suspicious_ua.count', total))

        # SEC-06: 大量DELETE操作
        res = self.db.execute_query('''
            SELECT bucket, COUNT(*) FROM bucket_logs
            WHERE analyzed = 0 AND operation LIKE 'REST.DELETE.OBJECT%'
            GROUP BY bucket
        ''')
        total = 0
        for bucket, count in res:
            metrics.append((f'wasabi.sec.delete_ops.count[{bucket}]', count))
            total += count
        metrics.append(('wasabi.sec.delete_ops.count', total))

        # SEC-07: 通常時間外のアクセス
        start_hour = self.config.get('business_hours', {}).get('start', 8)
        end_hour = self.config.get('business_hours', {}).get('end', 22)

        off_hours_res = self.db.execute_query('''
            SELECT bucket, request_time FROM bucket_logs
            WHERE analyzed = 0
        ''')

        off_hours_by_bucket = {}
        for bucket, req_time in off_hours_res:
            if isinstance(req_time, str):
                try:
                    req_time = datetime.fromisoformat(req_time.split('.')[0])
                except ValueError:
                    continue

            hour = req_time.hour
            if hour < start_hour or hour >= end_hour:
                off_hours_by_bucket[bucket] = off_hours_by_bucket.get(bucket, 0) + 1

        total = 0
        for bucket, count in off_hours_by_bucket.items():
            metrics.append((f'wasabi.sec.off_hours.count[{bucket}]', count))
            total += count
        metrics.append(('wasabi.sec.off_hours.count', total))

        # SEC-10: 弱いTLS/暗号スイート使用
        allowed_tls = self.config.get('allowed_tls_versions', ['TLSv1.2', 'TLSv1.3'])
        if allowed_tls:
            placeholders = ','.join('?' for _ in allowed_tls)
            query = f'''
                SELECT bucket, COUNT(*) FROM bucket_logs
                WHERE analyzed = 0
                AND tls_version NOT IN ({placeholders}) AND tls_version != '-' AND tls_version IS NOT NULL
                GROUP BY bucket
            '''
            res = self.db.execute_query(query, tuple(allowed_tls))
            total = 0
            for bucket, count in res:
                metrics.append((f'wasabi.sec.weak_tls.count[{bucket}]', count))
                total += count
            metrics.append(('wasabi.sec.weak_tls.count', total))
        else:
            metrics.append(('wasabi.sec.weak_tls.count', 0))

        return metrics

    def _analyze_audit_logs(self) -> List[Tuple[str, Any]]:
        metrics = []

        # SEC-08: 管理操作の認証失敗（ユーザー別）
        res = self.db.execute_query('''
            SELECT user, COUNT(*) FROM audit_logs
            WHERE analyzed = 0 AND LOWER(result) LIKE '%fail%'
            GROUP BY user
        ''')
        total = 0
        for user, count in res:
            metrics.append((f'wasabi.sec.admin_fail.count[{user}]', count))
            total += count
        metrics.append(('wasabi.sec.admin_fail.count', total))

        # SEC-09: rootアカウント使用（グローバル — user=rootに限定済み）
        res = self.db.execute_query('''
            SELECT COUNT(*) FROM audit_logs
            WHERE analyzed = 0 AND user = 'root'
        ''')
        count_root = res[0][0] if res else 0
        metrics.append(('wasabi.sec.root_usage.count', count_root))

        return metrics
