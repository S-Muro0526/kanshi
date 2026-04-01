import sys, os
from datetime import datetime, timedelta

# Fix path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import load_config
from storage.db_manager import DBManager
from analyzers.security_analyzer import SecurityAnalyzer
from analyzers.upload_analyzer import UploadAnalyzer
from analyzers.public_access_analyzer import PublicAccessAnalyzer
from analyzers.ops_analyzer import OpsAnalyzer

config = load_config('config.yaml')

# Check DB path carefully
db_path = config['database']['sqlite']['path']
if not os.path.isabs(db_path):
    # Absolute path calculation relative to config file directory is needed
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), db_path)
    
print(f"Using database: {db_path}")

try:
    db = DBManager(db_path)
except Exception as e:
    print(f"DB Error: {e}")
    sys.exit(1)

sec = SecurityAnalyzer(config, db)
up = UploadAnalyzer(config, db)
pub = PublicAccessAnalyzer(config, db)
ops = OpsAnalyzer(config, db)

end = datetime.now() + timedelta(days=1)
start = end - timedelta(days=2)

metrics = []
metrics.extend(sec.analyze(start, end))
metrics.extend(up.analyze(start, end))
metrics.extend(pub.analyze(start, end))
metrics.extend(ops.analyze(start, end))

for k, v in metrics:
    print(f"{k}: {v}")
