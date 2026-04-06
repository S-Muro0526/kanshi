import yaml
from main import MonitorApp

def test_local_collection():
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    # Force local source
    config['bucket_log']['source'] = 'local'
    config['bucket_log']['local_path'] = './bucket_logs/'
    config['database']['sqlite']['path'] = './data/test_monitor.db'

    app = MonitorApp(config)

    # Test collection
    count = app.bucket_collector.collect()
    print(f"Collected {count} logs from local.")

    # Verify in DB
    res = app.db.execute_query("SELECT count(*) FROM bucket_logs")
    print(f"Total logs in DB: {res[0][0]}")

    if res[0][0] > 0:
        print("Local collection successful!")
    else:
        print("Local collection failed.")

if __name__ == "__main__":
    test_local_collection()
