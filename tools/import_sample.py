import os
import sys
import glob
from storage.db_manager import DBManager
from parsers.bucket_log_parser import parse_bucket_log_line
from parsers.audit_log_parser import parse_audit_log_csv

def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(root_dir, 'data', 'wasabi_monitor.db')
    
    # Initialize DB (creates tables if they don't exist)
    db = DBManager(db_path)
    
    data_dir = os.path.abspath(os.path.join(root_dir, '..', 'data_'))
    print(f"Reading sample data from: {data_dir}")
    
    # 1. Audit Logs
    audit_log_dir = os.path.join(data_dir, 'logging-2026-4-admin')
    total_audit_inserted = 0
    if os.path.exists(audit_log_dir):
        for filepath in glob.glob(os.path.join(audit_log_dir, '*.csv')):
            filename = os.path.basename(filepath)
            if db.is_file_processed(filename):
                print(f"Skipping already processed audit log: {filename}")
                continue
            
            with open(filepath, 'r', encoding='utf-8') as f:
                csv_content = f.read()
            
            logs = parse_audit_log_csv(csv_content)
            if logs:
                inserted = db.insert_audit_logs(logs)
                total_audit_inserted += inserted
                print(f"Inserted {inserted} records from {filename}")
            
            db.mark_file_processed(filename)
    else:
        print(f"Audit log directory not found: {audit_log_dir}")
        
    print(f"Total Audit Logs Inserted: {total_audit_inserted}")
    
    # 2. Bucket Logs
    total_bucket_inserted = 0
    for prefix in ['shunki-test-01', 'shunki-test-02']:
        bucket_dir = os.path.join(data_dir, prefix)
        if os.path.exists(bucket_dir):
            for filepath in glob.glob(os.path.join(bucket_dir, '*')):
                if os.path.isdir(filepath) or filepath.endswith('.DS_Store'):
                    continue
                    
                filename = os.path.basename(filepath)
                if db.is_file_processed(filename):
                    print(f"Skipping already processed bucket log: {filename}")
                    continue
                
                logs = []
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    for line in f:
                        parsed = parse_bucket_log_line(filename, line)
                        if parsed:
                            logs.append(parsed)
                
                if logs:
                    inserted = db.insert_bucket_logs(logs)
                    total_bucket_inserted += inserted
                    print(f"Inserted {inserted} records from {filename}")
                else:
                    print(f"No valid records found in {filename}")
                
                db.mark_file_processed(filename)
        else:
            print(f"Bucket directory not found: {bucket_dir}")

    print(f"Total Bucket Logs Inserted: {total_bucket_inserted}")

if __name__ == "__main__":
    main()
