##
# Path: wasabi-log-monitor/parsers/audit_log_parser.py
# Purpose: 監査ログのパース
# Rationale: CSV形式のログからAuditLogオブジェクトを生成
# Last Modified: 2026-04-01
##
import csv
from io import StringIO
from datetime import datetime
from typing import List
from storage.models import AuditLog

def parse_audit_log_csv(csv_content: str) -> List[AuditLog]:
    """
    CSVコンテンツを読み込み、AuditLogオブジェクトのリストを返す。
    Wasabi監査ログのCSVヘッダを柔軟にマッピングする。
    """
    if not csv_content.strip():
        return []
        
    logs = []
    f = StringIO(csv_content)
    reader = csv.DictReader(f)
    
    for row in reader:
        # ヘッダー名が完全にドキュメント通りでないケースを想定し柔軟に取得
        def get_val(possible_keys, default=""):
            for k in possible_keys:
                for row_key in row.keys():
                    if row_key and k.lower() in row_key.lower():
                        return row[row_key]
            return default

        timestamp_str = get_val(['timestamp', 'date', 'time'])
        try:
            # ISO format: 2024-01-01T12:00:00Z 
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            # DateTimeの取得に失敗した場合は現在時刻を設定（あるいは None とする）
            timestamp = datetime.now()
            
        logs.append(AuditLog(
            timestamp=timestamp,
            user=get_val(['user', 'identity']),
            action=get_val(['action', 'operation', 'event']),
            resource=get_val(['resource', 'target']),
            result=get_val(['result', 'status', 'success']),
            source_ip=get_val(['source', 'ip', 'address']),
            raw_data=str(row)
        ))
        
    return logs
