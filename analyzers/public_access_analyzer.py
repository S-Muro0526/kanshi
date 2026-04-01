##
# Path: wasabi-log-monitor/analyzers/public_access_analyzer.py
# Purpose: 意図しない外部公開の監視
# Rationale: パブリックアクセスの兆候やアクセス元から外部への漏洩リスクを検知する
# Last Modified: 2026-04-01
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

    def analyze(self, start_time: datetime, end_time: datetime) -> List[Tuple[str, Any]]:
        metrics = []
        metrics.extend(self._analyze_bucket_logs(start_time, end_time))
        metrics.extend(self._analyze_audit_logs(start_time, end_time))
        return metrics

    def _analyze_bucket_logs(self, start: datetime, end: datetime) -> List[Tuple[str, Any]]:
        metrics = []

        # PUB-01: 匿名GETアクセス検知
        res = self.db.execute_query('''
            SELECT COUNT(*) FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ? 
            AND requester = '-' AND operation = 'REST.GET.OBJECT' AND http_status = 200
        ''', (start, end))
        count_anon_get = res[0][0] if res else 0
        metrics.append(('wasabi.pub.anon_get.count', count_anon_get))

        # PUB-03: ACL変更検知
        res = self.db.execute_query('''
            SELECT COUNT(*) FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ? 
            AND operation IN ('REST.PUT.OBJECT_ACL', 'REST.PUT.BUCKET_ACL')
        ''', (start, end))
        count_acl = res[0][0] if res else 0
        metrics.append(('wasabi.pub.acl_change.count', count_acl))

        # PUB-05: 外部リファラーからのアクセス
        res = self.db.execute_query('''
            SELECT referer FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ? 
            AND referer != '-'
        ''', (start, end))
        
        external_referer_count = 0
        for (referer,) in res:
            if referer:
                # 許可リストに含まれていなければカウント
                is_allowed = any(domain in referer for domain in self.allowed_referers)
                if not is_allowed:
                    external_referer_count += 1
                
        metrics.append(('wasabi.pub.external_referer.count', external_referer_count))

        # PUB-06: バケットリスト操作の匿名アクセス
        res = self.db.execute_query('''
            SELECT COUNT(*) FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ? 
            AND requester = '-' AND operation = 'REST.GET.BUCKET' AND http_status = 200
        ''', (start, end))
        count_anon_list = res[0][0] if res else 0
        metrics.append(('wasabi.pub.anon_list.count', count_anon_list))

        # PUB-07: ブラウザからの直接アクセス (簡易判定)
        res = self.db.execute_query('''
            SELECT COUNT(*) FROM bucket_logs 
            WHERE request_time >= ? AND request_time < ? 
            AND operation = 'REST.GET.OBJECT' AND http_status = 200
            AND (LOWER(user_agent) LIKE '%mozilla%' OR LOWER(user_agent) LIKE '%chrome%' OR LOWER(user_agent) LIKE '%safari%')
        ''', (start, end))
        count_browser = res[0][0] if res else 0
        metrics.append(('wasabi.pub.browser_access.count', count_browser))

        return metrics

    def _analyze_audit_logs(self, start: datetime, end: datetime) -> List[Tuple[str, Any]]:
        metrics = []

        # PUB-02: バケットポリシー変更検知
        res = self.db.execute_query('''
            SELECT COUNT(*) FROM audit_logs 
            WHERE timestamp >= ? AND timestamp < ? 
            AND LOWER(action) LIKE '%bucketpolicy%'
        ''', (start, end))
        count_policy = res[0][0] if res else 0
        metrics.append(('wasabi.pub.policy_change.count', count_policy))

        # PUB-04: パブリックアクセス設定変更
        res = self.db.execute_query('''
            SELECT COUNT(*) FROM audit_logs 
            WHERE timestamp >= ? AND timestamp < ? 
            AND LOWER(action) LIKE '%publicaccess%'
        ''', (start, end))
        count_pub_config = res[0][0] if res else 0
        metrics.append(('wasabi.pub.public_config_change.count', count_pub_config))

        return metrics
