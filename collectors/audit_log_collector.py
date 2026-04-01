##
# Path: wasabi-log-monitor/collectors/audit_log_collector.py
# Purpose: 監査ログを収集
# Rationale: S3バケット又はローカルディレクトリからCSVファイルを読み込み保存する
# Last Modified: 2026-04-01
##
import boto3
import os
import glob
import logging
from typing import Dict, Any
from storage.db_manager import DBManager
from parsers.audit_log_parser import parse_audit_log_csv

logger = logging.getLogger(__name__)

class AuditLogCollector:
    def __init__(self, config: Dict[str, Any], db_manager: DBManager):
        self.wasabi_config = config['wasabi']
        self.audit_config = config['audit_log']
        self.db = db_manager
        
        self.source = self.audit_config.get('source', 'local')
        
        if self.source == 'bucket':
            # S3クライアント初期化
            self.s3 = boto3.client(
                's3',
                endpoint_url=self.wasabi_config.get('endpoint_url', 'https://s3.ap-northeast-1.wasabisys.com'),
                aws_access_key_id=self.wasabi_config['access_key'],
                aws_secret_access_key=self.wasabi_config['secret_key'],
                region_name=self.wasabi_config.get('region', 'ap-northeast-1')
            )
            self.bucket = self.wasabi_config['log_bucket']
            self.prefix = self.audit_config.get('bucket_prefix', 'audit-logs/')

    def collect(self) -> int:
        if self.source == 'bucket':
            return self._collect_from_bucket()
        else:
            return self._collect_from_local()

    def _collect_from_bucket(self) -> int:
        logger.info(f"Starting audit log collection from bucket {self.bucket}/{self.prefix}")
        total_inserted = 0
        try:
            paginator = self.s3.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket, Prefix=self.prefix)
            
            for page in pages:
                if 'Contents' not in page:
                    continue
                
                for obj in page['Contents']:
                    file_key = obj['Key']
                    if not file_key.endswith('.csv'):
                        continue
                        
                    if self.db.is_file_processed(file_key):
                        continue
                        
                    response = self.s3.get_object(Bucket=self.bucket, Key=file_key)
                    csv_content = response['Body'].read().decode('utf-8')
                    
                    logs = parse_audit_log_csv(csv_content)
                    if logs:
                        total_inserted += self.db.insert_audit_logs(logs)
                    
                    self.db.mark_file_processed(file_key)
            
            logger.info(f"Audit log collection (bucket) completed. Inserted {total_inserted} records.")
            return total_inserted
        except Exception as e:
            logger.error(f"Error collecting audit logs from bucket: {e}")
            return total_inserted

    def _collect_from_local(self) -> int:
        local_path = self.audit_config.get('local_path', './audit_logs/')
        logger.info(f"Starting audit log collection from local path {local_path}")
        total_inserted = 0
        
        if not os.path.exists(local_path):
            logger.warning(f"Local audit log path {local_path} does not exist.")
            return 0
            
        try:
            for filepath in glob.glob(os.path.join(local_path, '*.csv')):
                filename = os.path.basename(filepath)
                # Ensure we don't process the same file twice
                if self.db.is_file_processed(filename):
                    continue
                    
                with open(filepath, 'r', encoding='utf-8') as f:
                    csv_content = f.read()
                    
                logs = parse_audit_log_csv(csv_content)
                if logs:
                    total_inserted += self.db.insert_audit_logs(logs)
                    
                self.db.mark_file_processed(filename)
                
            logger.info(f"Audit log collection (local) completed. Inserted {total_inserted} records.")
            return total_inserted
        except Exception as e:
            logger.error(f"Error collecting audit logs from local path: {e}")
            return total_inserted
