import os
import sqlite3
from datetime import datetime, timedelta

def generate_dummy_data(db_path: str):
    # Fix relative paths to work from script dir
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), db_path)

    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='bucket_logs'")
        if cursor.fetchone()[0] == 0:
            print("DB Schema not found at {db_path}. Run main.py once first to initialize DB.")
            return
            
        now = datetime.now()
        time_a_bit_ago = now - timedelta(minutes=2)
        
        cursor.execute('''
            INSERT INTO bucket_logs (
                log_file_name, bucket_owner, bucket, request_time, remote_ip, requester,
                request_id, operation, key, request_uri, http_status, error_code,
                bytes_sent, object_size, total_time, turn_around_time, referer, user_agent,
                version_id, host_id, signature_version, cipher_suite, authentication_type,
                host_header, tls_version
            ) VALUES (
                'dummy_log_1', 'owner_1', 'my-bucket', ?, '192.168.99.99', '-',
                'REQ123456', 'REST.GET.OBJECT', 'secret.txt', 'GET /secret.txt HTTP/1.1', 200, '-',
                1024, 1024, 10, 5, '-', 'curl/7.64.1', 
                '-', 'hostID123', '-', 'TLS_AES_128', '-', 
                'my-bucket.s3.wasabisys.com', 'TLSv1.3'
            )
        ''', (time_a_bit_ago,))
        
        cursor.execute('''
            INSERT INTO bucket_logs (
                log_file_name, bucket_owner, bucket, request_time, remote_ip, requester,
                request_id, operation, key, request_uri, http_status, error_code,
                bytes_sent, object_size, total_time, turn_around_time, referer, user_agent,
                version_id, host_id, signature_version, cipher_suite, authentication_type,
                host_header, tls_version
            ) VALUES (
                'dummy_log_2', 'owner_1', 'my-bucket', ?, '192.168.1.1', 'user_a',
                'REQ789012', 'REST.PUT.OBJECT', 'backup/2026/db.bak', 'PUT /backup/2026/db.bak HTTP/1.1', 200, '-',
                0, 5000000, 100, 50, '-', 'aws-cli/2.0.0', 
                '-', 'hostID456', '-', 'TLS_AES_256', '-', 
                'my-bucket.s3.wasabisys.com', 'TLSv1.3'
            )
        ''', (time_a_bit_ago,))
        
        cursor.execute('''
            INSERT INTO audit_logs (
                timestamp, user, action, resource, result, source_ip, raw_data
            ) VALUES (
                ?, 'admin_user', 'ConsoleLogin', '-', 'Failed', '203.0.113.50', 'raw_csv_row_dummy'
            )
        ''', (time_a_bit_ago,))
        
        conn.commit()
        print(f"Dummy data inserted into {db_path}.")
        
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    generate_dummy_data('data/wasabi_monitor.db')
