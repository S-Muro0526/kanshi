##
# Path: wasabi-log-monitor/storage/db_manager.py
# Purpose: DB管理クラス
# Rationale: SQLiteへのログ保存と問い合わせを抽象化
# Last Modified: 2026-04-01
##
import sqlite3
import os
import logging
from typing import List, Optional
from datetime import datetime
from .models import BucketLog, AuditLog

logger = logging.getLogger(__name__)

class DBManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._register_adapters()
        self._init_db()

    @staticmethod
    def _register_adapters():
        """タイムゾーン付きdatetimeをSQLiteで正しく保存・復元するためのアダプターを登録"""
        # Adapter: datetime → ISO文字列としてDB保存
        def adapt_datetime(dt):
            return dt.isoformat()
        
        # Converter: DB文字列 → datetime復元（タイムゾーン付き対応）
        def convert_datetime(val):
            try:
                return datetime.fromisoformat(val.decode())
            except (ValueError, AttributeError):
                try:
                    # フォールバック: スペース区切りの標準SQLite形式
                    return datetime.strptime(val.decode(), "%Y-%m-%d %H:%M:%S")
                except (ValueError, AttributeError):
                    return None
        
        sqlite3.register_adapter(datetime, adapt_datetime)
        sqlite3.register_converter("TIMESTAMP", convert_datetime)

    def _get_connection(self):
        # タイムスタンプを自動的にパースするため
        return sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )

    def _init_db(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # バケットログテーブル作成
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bucket_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    log_file_name TEXT,
                    bucket_owner TEXT,
                    bucket TEXT,
                    request_time TIMESTAMP,
                    remote_ip TEXT,
                    requester TEXT,
                    request_id TEXT UNIQUE,
                    operation TEXT,
                    key TEXT,
                    request_uri TEXT,
                    http_status INTEGER,
                    error_code TEXT,
                    bytes_sent INTEGER,
                    object_size INTEGER,
                    total_time INTEGER,
                    turn_around_time INTEGER,
                    referer TEXT,
                    user_agent TEXT,
                    version_id TEXT,
                    host_id TEXT,
                    signature_version TEXT,
                    cipher_suite TEXT,
                    authentication_type TEXT,
                    host_header TEXT,
                    tls_version TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # 監査ログテーブル作成
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP,
                    user TEXT,
                    action TEXT,
                    resource TEXT,
                    result TEXT,
                    source_ip TEXT,
                    raw_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # インデックスの作成
            indexes_bucket = [
                "CREATE INDEX IF NOT EXISTS idx_bucket_req_id ON bucket_logs(request_id)",
                "CREATE INDEX IF NOT EXISTS idx_bucket_time ON bucket_logs(request_time)",
                "CREATE INDEX IF NOT EXISTS idx_bucket_op ON bucket_logs(operation)",
                "CREATE INDEX IF NOT EXISTS idx_bucket_status ON bucket_logs(http_status)",
            ]
            for idx_query in indexes_bucket:
                cursor.execute(idx_query)

            indexes_audit = [
                "CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(timestamp)",
                "CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user)",
                "CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action)"
            ]
            for idx_query in indexes_audit:
                cursor.execute(idx_query)
            
            # 処理済みファイル管理テーブル
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS processed_files (
                    file_name TEXT PRIMARY KEY,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            logger.info("Database initialized successfully.")

    def insert_bucket_logs(self, logs: List[BucketLog]) -> int:
        if not logs:
            return 0
        
        inserted_count = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for log in logs:
                try:
                    cursor.execute('''
                        INSERT INTO bucket_logs (
                            log_file_name, bucket_owner, bucket, request_time, remote_ip, requester,
                            request_id, operation, key, request_uri, http_status, error_code,
                            bytes_sent, object_size, total_time, turn_around_time, referer, user_agent,
                            version_id, host_id, signature_version, cipher_suite, authentication_type,
                            host_header, tls_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        log.log_file_name, log.bucket_owner, log.bucket, log.request_time, log.remote_ip, log.requester,
                        log.request_id, log.operation, log.key, log.request_uri, log.http_status, log.error_code,
                        log.bytes_sent, log.object_size, log.total_time, log.turn_around_time, log.referer, log.user_agent,
                        log.version_id, log.host_id, log.signature_version, log.cipher_suite, log.authentication_type,
                        log.host_header, log.tls_version
                    ))
                    inserted_count += 1
                except sqlite3.IntegrityError:
                    # request_id は UNIQUE。重複は無視
                    pass
            conn.commit()
        return inserted_count

    def insert_audit_logs(self, logs: List[AuditLog]) -> int:
        if not logs:
            return 0
        inserted_count = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for log in logs:
                # 簡易的な重複排除
                cursor.execute('''
                    SELECT id FROM audit_logs 
                    WHERE timestamp=? AND user=? AND action=? AND raw_data=?
                ''', (log.timestamp, log.user, log.action, log.raw_data))
                if not cursor.fetchone():
                    cursor.execute('''
                        INSERT INTO audit_logs (timestamp, user, action, resource, result, source_ip, raw_data)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (log.timestamp, log.user, log.action, log.resource, log.result, log.source_ip, log.raw_data))
                    inserted_count += 1
            conn.commit()
        return inserted_count

    def is_file_processed(self, file_name: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM processed_files WHERE file_name=?', (file_name,))
            return cursor.fetchone() is not None

    def mark_file_processed(self, file_name: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT OR IGNORE INTO processed_files (file_name) VALUES (?)', (file_name,))
            conn.commit()

    def execute_query(self, query: str, params: tuple = ()) -> List[tuple]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
