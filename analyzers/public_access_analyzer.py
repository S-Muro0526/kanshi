##
# Path: wasabi-log-monitor/analyzers/public_access_analyzer.py
# Purpose: 意図しない外部公開の監視
# Rationale: パブリックアクセスの兆候やアクセス元から外部への漏洩リスクを検知する
# Key Dependencies: storage/db_manager.py
# Last Modified: 2026-04-02
##
import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime
from storage.db_manager import DBManager

logger = logging.getLogger(__name__)

class PublicAccessAnalyzer:
    def __init__(self, config: Dict[str, Any], db_manager: DBManager):
        self.config = config.get('monitoring', {}).get('public_access', {})
        self.allowed_referers = self.config.get('allowed_referer_domains', [])
        self.db = db_manager

    def analyze(self) -> List[Tuple[str, Any]]:
        metrics = []
        metrics.extend(self._analyze_bucket_logs())
        metrics.extend(self._analyze_audit_logs())
        return metrics

    def _analyze_bucket_logs(self) -> List[Tuple[str, Any]]:
        metrics = []

        # PUB-01: 匿名GETアクセス検知（バケット別）
        res = self.db.execute_query('''
            SELECT bucket, COUNT(*) FROM bucket_logs
            WHERE analyzed = 0
            AND requester = '-' AND operation = 'REST.GET.OBJECT' AND http_status = 200
            GROUP BY bucket
        ''')
        total = 0
        for bucket, count in res:
            metrics.append((f'wasabi.pub.anon_get.count[{bucket}]', count))
            total += count
        metrics.append(('wasabi.pub.anon_get.count', total))

        # PUB-03: ACL変更検知（バケット別）
        res = self.db.execute_query('''
            SELECT bucket, COUNT(*) FROM bucket_logs
            WHERE analyzed = 0
            AND operation IN ('REST.PUT.OBJECT_ACL', 'REST.PUT.BUCKET_ACL')
            GROUP BY bucket
        ''')
        total = 0
        for bucket, count in res:
            metrics.append((f'wasabi.pub.acl_change.count[{bucket}]', count))
            total += count
        metrics.append(('wasabi.pub.acl_change.count', total))

        # PUB-05: 外部リファラーからのアクセス（バケット別）
        res = self.db.execute_query('''
            SELECT bucket, referer FROM bucket_logs
            WHERE analyzed = 0
            AND referer != '-'
        ''')

        ext_ref_by_bucket = {}
        for bucket, referer in res:
            if referer:
                is_allowed = any(domain in referer for domain in self.allowed_referers)
                if not is_allowed:
                    ext_ref_by_bucket[bucket] = ext_ref_by_bucket.get(bucket, 0) + 1

        total = 0
        for bucket, count in ext_ref_by_bucket.items():
            metrics.append((f'wasabi.pub.external_referer.count[{bucket}]', count))
            total += count
        metrics.append(('wasabi.pub.external_referer.count', total))

        # PUB-06: バケットリスト操作の匿名アクセス（バケット別）
        res = self.db.execute_query('''
            SELECT bucket, COUNT(*) FROM bucket_logs
            WHERE analyzed = 0
            AND requester = '-' AND operation = 'REST.GET.BUCKET' AND http_status = 200
            GROUP BY bucket
        ''')
        total = 0
        for bucket, count in res:
            metrics.append((f'wasabi.pub.anon_list.count[{bucket}]', count))
            total += count
        metrics.append(('wasabi.pub.anon_list.count', total))

        # PUB-07: ブラウザからの直接アクセス（バケット別）
        res = self.db.execute_query('''
            SELECT bucket, COUNT(*) FROM bucket_logs
            WHERE analyzed = 0
            AND operation = 'REST.GET.OBJECT' AND http_status = 200
            AND (LOWER(user_agent) LIKE '%mozilla%' OR LOWER(user_agent) LIKE '%chrome%' OR LOWER(user_agent) LIKE '%safari%')
            GROUP BY bucket
        ''')
        total = 0
        for bucket, count in res:
            metrics.append((f'wasabi.pub.browser_access.count[{bucket}]', count))
            total += count
        metrics.append(('wasabi.pub.browser_access.count', total))

        return metrics

    def _analyze_audit_logs(self) -> List[Tuple[str, Any]]:
        metrics = []

        # PUB-02: バケットポリシー変更検知（ユーザー別）
        res = self.db.execute_query('''
            SELECT user, COUNT(*) FROM audit_logs
            WHERE analyzed = 0
            AND LOWER(action) LIKE '%bucketpolicy%'
            GROUP BY user
        ''')
        total = 0
        for user, count in res:
            metrics.append((f'wasabi.pub.policy_change.count[{user}]', count))
            total += count
        metrics.append(('wasabi.pub.policy_change.count', total))

        # PUB-04: パブリックアクセス設定変更（ユーザー別）
        res = self.db.execute_query('''
            SELECT user, COUNT(*) FROM audit_logs
            WHERE analyzed = 0
            AND LOWER(action) LIKE '%publicaccess%'
            GROUP BY user
        ''')
        total = 0
        for user, count in res:
            metrics.append((f'wasabi.pub.public_config_change.count[{user}]', count))
            total += count
        metrics.append(('wasabi.pub.public_config_change.count', total))

        return metrics
