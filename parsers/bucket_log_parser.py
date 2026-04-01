##
# Path: wasabi-log-monitor/parsers/bucket_log_parser.py
# Purpose: バケットログ（S3アクセスログ）のパース
# Rationale: サーバーアクセスログのテキスト行からBucketLogオブジェクトを生成する
# Last Modified: 2026-04-01
##
import re
from datetime import datetime
from typing import Optional
from storage.models import BucketLog

# S3アクセスログの正規表現パターンの定義
# フィールドに空白が含まれる場合（URIやUserAgentなど）はダブルクォーテーションで囲まれる可能性があるため考慮
S3_LOG_PATTERN = re.compile(
    r'^(?P<bucket_owner>\S+) '
    r'(?P<bucket>\S+) '
    r'\[(?P<time>.*?)\] '
    r'(?P<remote_ip>\S+) '
    r'(?P<requester>\S+) '
    r'(?P<request_id>\S+) '
    r'(?P<operation>\S+) '
    r'(?P<key>\S+) '
    r'(?P<request_uri>".*?"|\S+) '
    r'(?P<http_status>\S+) '
    r'(?P<error_code>\S+) '
    r'(?P<bytes_sent>\S+) '
    r'(?P<object_size>\S+) '
    r'(?P<total_time>\S+) '
    r'(?P<turn_around_time>\S+) '
    r'(?P<referer>".*?"|\S+) '
    r'(?P<user_agent>".*?"|\S+) '
    r'(?P<version_id>\S+) '
    r'(?P<host_id>\S+) '
    r'(?P<signature_version>\S+) '
    r'(?P<cipher_suite>\S+) '
    r'(?P<authentication_type>\S+) '
    r'(?P<host_header>".*?"|\S+) '
    r'(?P<tls_version>\S+)(?:.*)$'
)

def _parse_time(time_str: str) -> datetime:
    # 例: 06/Feb/2019:00:00:38 +0000
    try:
        return datetime.strptime(time_str, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return datetime.now()  # Fallback

def _to_int(val_str: str) -> int:
    if val_str == '-' or not val_str:
        return 0
    try:
        return int(val_str)
    except ValueError:
        return 0

def _clean_quotes(val: str) -> str:
    if val and val.startswith('"') and val.endswith('"'):
        return val[1:-1]
    return val

def parse_bucket_log_line(log_file_name: str, line: str) -> Optional[BucketLog]:
    line = line.strip()
    if not line:
        return None
        
    match = S3_LOG_PATTERN.match(line)
    if not match:
        return None
        
    data = match.groupdict()
    
    return BucketLog(
        log_file_name=log_file_name,
        bucket_owner=data['bucket_owner'],
        bucket=data['bucket'],
        request_time=_parse_time(data['time']),
        remote_ip=data['remote_ip'],
        requester=data['requester'],
        request_id=data['request_id'],
        operation=data['operation'],
        key=data['key'],
        request_uri=_clean_quotes(data['request_uri']),
        http_status=_to_int(data['http_status']),
        error_code=data['error_code'],
        bytes_sent=_to_int(data['bytes_sent']),
        object_size=_to_int(data['object_size']),
        total_time=_to_int(data['total_time']),
        turn_around_time=_to_int(data['turn_around_time']),
        referer=_clean_quotes(data['referer']),
        user_agent=_clean_quotes(data['user_agent']),
        version_id=data['version_id'],
        host_id=data['host_id'],
        signature_version=data['signature_version'],
        cipher_suite=data['cipher_suite'],
        authentication_type=data['authentication_type'],
        host_header=_clean_quotes(data['host_header']),
        tls_version=data['tls_version']
    )
