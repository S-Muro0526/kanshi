##
# Path: wasabi-log-monitor/collectors/bucket_log_collector.py
# Purpose: バケットログをS3またはローカルから収集
# Rationale: Boto3等を利用しWasabiの保管バケットから、またはローカルファイルから取得・パース・保存する
# Key Dependencies: parsers/bucket_log_parser.py, storage/db_manager.py
# Last Modified: 2026-04-06
##
import boto3
import os
import logging
from typing import Dict, Any
from storage.db_manager import DBManager
from parsers.bucket_log_parser import parse_bucket_log_line

logger = logging.getLogger(__name__)

class BucketLogCollector:
    def __init__(self, config: Dict[str, Any], db_manager: DBManager):
        self.wasabi_config = config['wasabi']
        self.bucket_log_config = config.get('bucket_log', {})
        self.db = db_manager
        
        self.source = self.bucket_log_config.get('source', 'bucket')
        
        if self.source == 'bucket':
            # S3クライアント初期化（バケットモード時のみ）
            self.s3 = boto3.client(
                's3',
                endpoint_url=self.wasabi_config.get('endpoint_url', 'https://s3.ap-northeast-1.wasabisys.com'),
                aws_access_key_id=self.wasabi_config['access_key'],
                aws_secret_access_key=self.wasabi_config['secret_key'],
                region_name=self.wasabi_config.get('region', 'ap-northeast-1')
            )
            self.bucket = self.wasabi_config['log_bucket']
            self.prefix = self.wasabi_config.get('log_prefix', '')

    def collect(self) -> int:
        """未処理のログファイルを取得してDBに保存する"""
        if self.source == 'bucket':
            return self._collect_from_bucket()
        else:
            return self._collect_from_local()

    def _collect_from_bucket(self) -> int:
        """S3からバケットログを収集"""
        logger.info(f"Starting bucket log collection from {self.bucket}/{self.prefix}")
        total_inserted = 0
        
        try:
            paginator = self.s3.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket, Prefix=self.prefix)
            
            for page in pages:
                if 'Contents' not in page:
                    continue
                
                for obj in page['Contents']:
                    file_key = obj['Key']
                    
                    if self.db.is_file_processed(file_key):
                        continue
                        
                    logger.debug(f"Processing new log file: {file_key}")
                    inserted = self._process_s3_file(file_key)
                    total_inserted += inserted
                    
                    self.db.mark_file_processed(file_key)
                    
            logger.info(f"Bucket log collection (bucket) completed. Inserted {total_inserted} new records.")
            return total_inserted
            
        except Exception as e:
            logger.error(f"Error during bucket log collection: {e}")
            return total_inserted

    def _collect_from_local(self) -> int:
        """ローカルディレクトリからバケットログを収集"""
        local_path = self.bucket_log_config.get('local_path', './test/bucket_logs/')
        logger.info(f"Starting bucket log collection from local path {local_path}")
        total_inserted = 0
        
        if not os.path.exists(local_path):
            logger.warning(f"Local bucket log path {local_path} does not exist.")
            return 0
            
        try:
            for filename in os.listdir(local_path):
                filepath = os.path.join(local_path, filename)
                
                # ディレクトリはスキップ
                if os.path.isdir(filepath):
                    continue
                
                # 既に処理済みかチェック
                if self.db.is_file_processed(filename):
                    continue
                    
                logger.debug(f"Processing local log file: {filename}")
                inserted = self._process_local_file(filepath, filename)
                total_inserted += inserted
                
                self.db.mark_file_processed(filename)
                
            logger.info(f"Bucket log collection (local) completed. Inserted {total_inserted} new records.")
            return total_inserted
        except Exception as e:
            logger.error(f"Error collecting bucket logs from local path: {e}")
            return total_inserted

    def _process_s3_file(self, file_key: str) -> int:
        """S3上のログファイルを処理"""
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=file_key)
            body = response['Body'].read().decode('utf-8')
            return self._parse_and_insert(file_key, body)
        except Exception as e:
            logger.error(f"Failed to process S3 log file {file_key}: {e}")
            return 0

    def _process_local_file(self, filepath: str, filename: str) -> int:
        """ローカルのログファイルを処理"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                body = f.read()
            return self._parse_and_insert(filename, body)
        except Exception as e:
            logger.error(f"Failed to process local log file {filepath}: {e}")
            return 0

    def _parse_and_insert(self, file_key: str, body: str) -> int:
        """ログ本文をパースしてDBに保存する共通処理"""
        logs = []
        for line in body.splitlines():
            parsed = parse_bucket_log_line(file_key, line)
            if parsed:
                logs.append(parsed)
        
        if logs:
            return self.db.insert_bucket_logs(logs)
        return 0
