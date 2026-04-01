##
# Path: wasabi-log-monitor/storage/models.py
# Purpose: データモデル定義
# Rationale: DBのテーブル構造と対応するPythonクラスを定義
# Last Modified: 2026-04-01
##
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class BucketLog:
    log_file_name: str
    bucket_owner: str
    bucket: str
    request_time: datetime
    remote_ip: str
    requester: str
    request_id: str
    operation: str
    key: str
    request_uri: str
    http_status: int
    error_code: str
    bytes_sent: int
    object_size: int
    total_time: int
    turn_around_time: int
    referer: str
    user_agent: str
    version_id: str
    host_id: str
    signature_version: str
    cipher_suite: str
    authentication_type: str
    host_header: str
    tls_version: str

@dataclass
class AuditLog:
    timestamp: datetime
    user: str
    action: str
    resource: str
    result: str
    source_ip: str
    raw_data: str
