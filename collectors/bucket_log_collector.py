##
# Path: wasabi-log-monitor/collectors/bucket_log_collector.py
# Purpose: バケットログをS3から収集
# Rationale: Boto3等を利用しWasabiの保管バケットから定期的に取得・パース・保存する
# Last Modified: 2026-04-01
##
import boto3
import logging
from typing import Dict, Any
from storage.db_manager import DBManager
from parsers.bucket_log_parser import parse_bucket_log_line

logger = logging.getLogger(__name__)

class BucketLogCollector:
    def __init__(self, config: Dict[str, Any], db_manager: DBManager):
        self.config = config['wasabi']
        self.db = db_manager
        
        # S3クライアント初期化
        self.s3 = boto3.client(
            's3',
            endpoint_url=self.config.get('endpoint_url', 'https://s3.ap-northeast-1.wasabisys.com'),
            aws_access_key_id=self.config['access_key'],
            aws_secret_access_key=self.config['secret_key'],
            region_name=self.config.get('region', 'ap-northeast-1')
        )
        self.bucket = self.config['log_bucket']
        self.prefix = self.config.get('log_prefix', '')

    def collect(self) -> int:
        """未処理のログファイルをS3からダウンロードしてDBに保存する"""
        logger.info(f"Starting bucket log collection from {self.bucket}/{self.prefix}")
        total_inserted = 0
        
        try:
            # S3オブジェクトのリストア
            paginator = self.s3.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket, Prefix=self.prefix)
            
            for page in pages:
                if 'Contents' not in page:
                    continue
                
                for obj in page['Contents']:
                    file_key = obj['Key']
                    
                    # 既に処理済みかチェック
                    if self.db.is_file_processed(file_key):
                        continue
                        
                    logger.debug(f"Processing new log file: {file_key}")
                    inserted = self._process_file(file_key)
                    total_inserted += inserted
                    
                    # 処理済みとしてマーク
                    self.db.mark_file_processed(file_key)
                    
            logger.info(f"Bucket log collection completed. Inserted {total_inserted} new records.")
            return total_inserted
            
        except Exception as e:
            logger.error(f"Error during bucket log collection: {e}")
            return total_inserted

    def _process_file(self, file_key: str) -> int:
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=file_key)
            body = response['Body'].read().decode('utf-8')
            
            logs = []
            for line in body.splitlines():
                parsed = parse_bucket_log_line(file_key, line)
                if parsed:
                    logs.append(parsed)
            
            if logs:
                return self.db.insert_bucket_logs(logs)
            return 0
            
        except Exception as e:
            logger.error(f"Failed to process log file {file_key}: {e}")
            return 0
