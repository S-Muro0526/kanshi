##
# Path: wasabi-log-monitor/alerting/zabbix_sender.py
# Purpose: Zabbixへ監視メトリクスを送信
# Rationale: Zabbix Senderを利用して解析結果を統合管理プラットフォームへ送る
# Last Modified: 2026-04-01
##
import subprocess
import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

class ZabbixSenderWrapper:
    def __init__(self, config: Dict[str, Any]):
        self.config = config['zabbix']
        self.server = self.config.get('server', '127.0.0.1')
        self.port = str(self.config.get('port', 10051))
        self.hostname = self.config.get('hostname', 'wasabi-monitor')
        self.sender_path = self.config.get('sender_path', '/usr/bin/zabbix_sender')

    def send_metrics(self, metrics: List[Tuple[str, Any]]) -> bool:
        """
        metrics: [(key, value), ...] のリスト
        一括送信のために一時ファイルを使うアプローチもあるが、POCのため個別or複数引数で送信。
        ここでは汎用的な -k -o 引数を利用しループで送るか、標準入力経由で送るアプローチを取る。
        標準入力形式: "<hostname> <key> <value>"
        """
        if not metrics:
            return True

        input_data = ""
        for key, value in metrics:
            # vlaueが文字列でスペースを含む可能性がある場合は工夫が必要だが、数値メトリクス中心のため簡略化
            input_data += f'"{self.hostname}" "{key}" "{value}"\n'

        try:
            # -i - を指定して標準入力から読み込ませる
            result = subprocess.run(
                [self.sender_path, "-z", self.server, "-p", self.port, "-i", "-"],
                input=input_data.encode('utf-8'),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            if result.returncode == 0:
                logger.debug(f"Zabbix Sender output: {result.stdout.decode('utf-8').strip()}")
                return True
            else:
                logger.error(f"Zabbix Sender failed: {result.stderr.decode('utf-8')}")
                return False
                
        except FileNotFoundError:
            logger.error(f"zabbix_sender executable not found at {self.sender_path}. Ensure it is installed.")
            # POC: ignore if mostly testing
            return False
        except Exception as e:
            logger.error(f"Error executing zabbix_sender: {e}")
            return False
