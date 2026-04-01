import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import load_config, MonitorApp

# Test run without blocking scheduler
config = load_config(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.yaml'))
app = MonitorApp(config)
app.run_job()
