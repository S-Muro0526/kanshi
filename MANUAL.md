# Wasabi Log Monitor — 運用マニュアル (Manual)

> **文書バージョン:** 1.0  
> **最終更新日:** 2026-04-02  
> **対象者:** システム管理者、運用担当者

---

## 目次

1. [事前準備](#1-事前準備)
2. [インストール手順](#2-インストール手順)
3. [設定ファイルの編集](#3-設定ファイルの編集)
4. [起動と停止](#4-起動と停止)
5. [動作確認](#5-動作確認)
6. [Zabbix連携設定](#6-zabbix連携設定)
7. [日常運用](#7-日常運用)
8. [トラブルシューティング](#8-トラブルシューティング)
9. [保守作業](#9-保守作業)

---

## 1. 事前準備

### 1.1 システム要件

| 項目 | 要件 |
|---|---|
| OS | Linux (推奨: Ubuntu 22.04+) / macOS |
| Python | 3.9 以上 |
| ディスク | 1GB以上（DB容量はログ量に依存） |
| ネットワーク | Wasabi S3エンドポイントへのHTTPS通信、Zabbix Serverへの10051/TCP通信 |
| 追加ソフトウェア | `zabbix_sender` (Zabbix Agent パッケージに同梱) |

### 1.2 必要な認証情報

| 情報 | 取得方法 |
|---|---|
| Wasabi Access Key | Wasabi管理コンソール → Access Keys |
| Wasabi Secret Key | 同上（作成時のみ表示） |
| ログ保管バケット名 | Wasabi管理コンソール → Buckets |
| Zabbix Server IP | Zabbix管理者に確認 |

### 1.3 Wasabi側の事前設定

1. **バケットアクセスログの有効化:**
   - Wasabiコンソール → 対象バケット → Properties → Server Access Logging → Enable
   - ログ保管先バケットを指定（例: `log-storage-bucket`）

2. **管理監査ログの有効化:**
   - Wasabiコンソール → Settings → Audit Log → Enable
   - 出力先バケット・プレフィックスを確認

---

## 2. インストール手順

### 2.1 ソースコードの配置

```bash
# プロジェクトディレクトリの作成
sudo mkdir -p /opt/wasabi-log-monitor
cd /opt/wasabi-log-monitor

# ソースコードをコピーまたは git clone
# 例: git clone <repository_url> .
```

### 2.2 Python環境の構築

```bash
# venvの作成（推奨）
python3 -m venv venv
source venv/bin/activate

# 依存パッケージのインストール
pip install -r requirements.txt
```

**依存パッケージ一覧:**

| パッケージ | バージョン | 用途 |
|---|---|---|
| `boto3` | >= 1.28.0 | Wasabi S3 API通信 |
| `pyyaml` | >= 6.0 | 設定ファイル読み込み |
| `apscheduler` | >= 3.10.0 | 定期実行スケジューラ |
| `ipaddress` | >= 1.0.23 | IPアドレス/CIDR判定 |

### 2.3 zabbix_sender のインストール

```bash
# Ubuntu / Debian
sudo apt install zabbix-sender

# CentOS / RHEL
sudo yum install zabbix-sender

# macOS (Homebrew)
# ※ POC環境ではインストール不要（エラーは無視される）
```

---

## 3. 設定ファイルの編集

設定はプロジェクトルートの `config.yaml` に集約されている。

### 3.1 Wasabi接続設定（必須）

```yaml
wasabi:
  endpoint_url: "https://s3.ap-northeast-1.wasabisys.com"
  region: "ap-northeast-1"
  access_key: "<YOUR_ACCESS_KEY>"    # ← 変更必須
  secret_key: "<YOUR_SECRET_KEY>"    # ← 変更必須
  log_bucket: "log-storage-bucket"   # ← ログ保管バケット名に変更
  log_prefix: ""                     # 任意のプレフィックス
```

> ⚠️ **注意:** 本番環境ではアクセスキーを直接記載せず、環境変数やシークレット管理ツールを使用すること。

### 3.2 監査ログ設定

```yaml
audit_log:
  # "bucket": S3バケットから取得 / "local": ローカルCSVから取得
  source: "bucket"
  bucket_prefix: "audit-logs/"
  local_path: "./audit_logs/"    # source: "local" 時のみ使用
```

### 3.3 Zabbix設定

```yaml
zabbix:
  server: "192.168.1.100"            # ← ZabbixサーバーIPに変更
  port: 10051
  hostname: "wasabi-monitor"         # ← Zabbix上のホスト名と一致させる
  sender_path: "/usr/bin/zabbix_sender"
```

### 3.4 スケジューラ設定

```yaml
scheduler:
  collection_interval: 300  # ログ収集・分析の実行間隔（秒）= 5分
  analysis_interval: 300    # 分析間隔（秒）≒ collection_interval と同値
```

### 3.5 監視ルールの閾値調整

環境に応じて以下の閾値を調整する。Zabbix側のトリガーと合わせて設定すること。

```yaml
monitoring:
  security:
    error_403_threshold: 10               # SEC-02: 5分あたりの403エラー閾値
    data_exfil_bytes_threshold: 1073741824  # SEC-04: 1GB (データ流出閾値)
    mass_delete_threshold: 50             # SEC-06: 大量DELETE閾値
    business_hours:
      start: 8    # 業務開始時刻 (JST)
      end: 22     # 業務終了時刻 (JST)
    allowed_tls_versions:
      - "TLSv1.2"
      - "TLSv1.3"
```

### 3.6 IPホワイトリスト設定

```yaml
ip_whitelist:
  allowed_ips:               # 正規アクセス元 (CIDRサポート)
    - "192.168.1.0/24"
    - "10.0.0.0/8"
    - "203.0.113.0/24"       # ← 実際のオフィスIP等を追加
  backup_server_ips:         # バックアップサーバーIP（個別指定）
    - "203.0.113.10"         # ← 実際のバックアップサーバーIPに変更
```

### 3.7 バックアップスケジュール定義

```yaml
monitoring:
  upload:
    expected_schedules:
      - name: "daily_backup"
        key_pattern: "backup/daily/.*"    # ← 実際のキーパターンに変更
        expected_hour_utc: 15             # JST 00:00 = UTC 15:00
        tolerance_minutes: 60
```

---

## 4. 起動と停止

### 4.1 フォアグラウンド起動（テスト・デバッグ用）

```bash
cd /opt/wasabi-log-monitor
source venv/bin/activate
PYTHONPATH=. python3 main.py
```

起動ログ例:
```
2026-04-02 09:00:00,000 - storage.db_manager - INFO - Database initialized successfully.
2026-04-02 09:00:00,100 - main - INFO - --- Starting Log Collection ---
2026-04-02 09:00:01,500 - main - INFO - Colletion summary: BucketLogs=150, AuditLogs=5
2026-04-02 09:00:01,600 - main - INFO - --- Starting Log Analysis ---
2026-04-02 09:00:01,700 - main - INFO - Analyzing newly collected logs (analyzed=0)
2026-04-02 09:00:02,000 - main - INFO - Generated 27 metrics.
2026-04-02 09:00:02,100 - main - INFO - Metrics successfully sent to Zabbix.
2026-04-02 09:00:02,200 - main - INFO - Marked 155 logs as analyzed.
2026-04-02 09:00:02,300 - main - INFO - Scheduler started with interval 300 seconds. Press Ctrl+C to exit.
```

**停止:** `Ctrl+C`

### 4.2 systemd サービス化（本番推奨）

サービスファイルの作成:

```bash
sudo tee /etc/systemd/system/wasabi-monitor.service << 'EOF'
[Unit]
Description=Wasabi Log Monitor
After=network.target

[Service]
Type=simple
User=wasabi-monitor
Group=wasabi-monitor
WorkingDirectory=/opt/wasabi-log-monitor
Environment="PYTHONPATH=/opt/wasabi-log-monitor"
ExecStart=/opt/wasabi-log-monitor/venv/bin/python3 main.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
```

サービスの制御:

```bash
# 起動
sudo systemctl start wasabi-monitor

# 停止
sudo systemctl stop wasabi-monitor

# 自動起動の有効化
sudo systemctl enable wasabi-monitor

# ステータス確認
sudo systemctl status wasabi-monitor

# ログの確認
sudo journalctl -u wasabi-monitor -f
```

---

## 5. 動作確認

### 5.1 サンプルデータによるテスト

ローカル環境にサンプルデータがある場合:

```bash
cd /opt/wasabi-log-monitor
source venv/bin/activate

# サンプルデータのインポート
PYTHONPATH=. python3 tools/import_sample.py

# 全量分析テスト
PYTHONPATH=. python3 tools/test_analyze_all.py
```

期待される出力:
```
[Running Security Analyzer...]
  wasabi.sec.unauth_access.count: 1
  wasabi.sec.403_error.count: 96
  wasabi.sec.unknown_ip.count: 6594
  ...

[Running Upload Analyzer...]
  wasabi.upl.scheduled.status: 0
  wasabi.upl.upload.bytes: 5190588
  ...

--- Summary ---
Total metrics generated: 27
```

### 5.2 統合テスト（S3接続テスト含む）

```bash
PYTHONPATH=. python3 tools/test_run.py
```

このスクリプトは `main.py` の `run_job()` を1回実行する。  
S3接続エラーが出る場合は `config.yaml` のアクセスキー・バケット名を確認すること。

### 5.3 メトリクス確認

```bash
PYTHONPATH=. python3 tools/print_metrics.py
```

---

## 6. Zabbix連携設定

### 6.1 Zabbixホストの作成

1. Zabbix管理画面 → 設定 → ホスト → ホストの作成
2. ホスト名: `wasabi-monitor` （`config.yaml` の `zabbix.hostname` と一致させる）
3. グループ: 適切なグループに所属させる

### 6.2 Zabbixアイテムの作成

以下の27項目をアイテムとして登録する。すべて **Zabbix trapper** タイプとする。

#### セキュリティ監視アイテム

| キー | 名前 | データ型 | 単位 |
|---|---|---|---|
| `wasabi.sec.unauth_access.count` | 未認証アクセス数 | 数値(整数) | 件 |
| `wasabi.sec.403_error.count` | 403エラー数 | 数値(整数) | 件 |
| `wasabi.sec.unknown_ip.count` | 未知IPアクセス数 | 数値(整数) | 件 |
| `wasabi.sec.data_exfil.bytes` | データダウンロード量 | 数値(整数) | B |
| `wasabi.sec.suspicious_ua.count` | 不審UA数 | 数値(整数) | 件 |
| `wasabi.sec.delete_ops.count` | DELETE操作数 | 数値(整数) | 件 |
| `wasabi.sec.off_hours.count` | 業務時間外アクセス数 | 数値(整数) | 件 |
| `wasabi.sec.weak_tls.count` | 弱いTLS使用数 | 数値(整数) | 件 |
| `wasabi.sec.admin_fail.count` | 管理操作認証失敗数 | 数値(整数) | 件 |
| `wasabi.sec.root_usage.count` | rootアカウント使用数 | 数値(整数) | 件 |

#### アップロード監視アイテム

| キー | 名前 | データ型 | 単位 |
|---|---|---|---|
| `wasabi.upl.scheduled.status` | 定期アップロード状態 | 数値(整数) | — |
| `wasabi.upl.upload.bytes` | アップロードサイズ | 数値(整数) | B |
| `wasabi.upl.upload_failure.count` | アップロード失敗数 | 数値(整数) | 件 |
| `wasabi.upl.unknown_ip.count` | 未知IPアップロード数 | 数値(整数) | 件 |
| `wasabi.upl.multipart_uncompleted.count` | マルチパート未完了数 | 数値(整数) | 件 |
| `wasabi.upl.daily_upload.count` | アップロード件数 | 数値(整数) | 件 |

#### 外部公開監視アイテム

| キー | 名前 | データ型 | 単位 |
|---|---|---|---|
| `wasabi.pub.anon_get.count` | 匿名GETアクセス数 | 数値(整数) | 件 |
| `wasabi.pub.acl_change.count` | ACL変更数 | 数値(整数) | 件 |
| `wasabi.pub.external_referer.count` | 外部リファラー数 | 数値(整数) | 件 |
| `wasabi.pub.anon_list.count` | 匿名バケットリスト数 | 数値(整数) | 件 |
| `wasabi.pub.browser_access.count` | ブラウザ直接アクセス数 | 数値(整数) | 件 |
| `wasabi.pub.policy_change.count` | バケットポリシー変更数 | 数値(整数) | 件 |
| `wasabi.pub.public_config_change.count` | パブリックアクセス設定変更数 | 数値(整数) | 件 |

#### 運用監視アイテム

| キー | 名前 | データ型 | 単位 |
|---|---|---|---|
| `wasabi.ops.log_delay.seconds` | ログ配送遅延 | 数値(浮動小数) | s |
| `wasabi.ops.throttle.count` | APIスロットリング数 | 数値(整数) | 件 |
| `wasabi.ops.replication.status` | レプリケーション状態 | 数値(整数) | — |
| `wasabi.ops.storage_increase.bytes` | ストレージ増分 | 数値(整数) | B |

### 6.3 推奨トリガー設定例

| トリガー名 | 条件式 | 深刻度 |
|---|---|---|
| 未認証アクセス検知 | `last(/wasabi-monitor/wasabi.sec.unauth_access.count) > 0` | 警告 |
| 403エラー急増 | `last(/wasabi-monitor/wasabi.sec.403_error.count) > 10` | 警告 |
| 大量データダウンロード | `last(/wasabi-monitor/wasabi.sec.data_exfil.bytes) > 1073741824` | 重度 |
| 大量DELETE操作 | `last(/wasabi-monitor/wasabi.sec.delete_ops.count) > 50` | 重度 |
| 定期バックアップ未完 | `last(/wasabi-monitor/wasabi.upl.scheduled.status) = 0` | 致命的 |
| アップロード失敗 | `last(/wasabi-monitor/wasabi.upl.upload_failure.count) > 0` | 警告 |
| ログ配送遅延 | `last(/wasabi-monitor/wasabi.ops.log_delay.seconds) > 1800` | 警告 |
| APIスロットリング | `last(/wasabi-monitor/wasabi.ops.throttle.count) > 0` | 警告 |
| 匿名GETアクセス | `last(/wasabi-monitor/wasabi.pub.anon_get.count) > 0` | 情報 |
| バケットポリシー変更 | `last(/wasabi-monitor/wasabi.pub.policy_change.count) > 0` | 警告 |

---

## 7. 日常運用

### 7.1 ログファイルの確認

```bash
# アプリケーションログの確認
tail -f /opt/wasabi-log-monitor/logs/wasabi_monitor.log

# 直近のエラーのみ抽出
grep ERROR /opt/wasabi-log-monitor/logs/wasabi_monitor.log | tail -20
```

### 7.2 正常稼働の確認ポイント

以下のログが定期的（5分ごと）に出力されていれば正常:

```
INFO - --- Starting Log Collection ---
INFO - Colletion summary: BucketLogs=XX, AuditLogs=XX
INFO - --- Starting Log Analysis ---
INFO - Analyzing newly collected logs (analyzed=0)
INFO - Generated 27 metrics.
INFO - Metrics successfully sent to Zabbix.
INFO - Marked XX logs as analyzed.
```

### 7.3 注意すべきログメッセージ

| ログメッセージ | 意味 | 対応 |
|---|---|---|
| `InvalidAccessKeyId` | S3認証失敗 | `config.yaml` のアクセスキーを確認 |
| `zabbix_sender executable not found` | zabbix_sender未インストール | zabbix_senderをインストール |
| `Failed to send some/all metrics` | Zabbix送信失敗 | ZabbixサーバーIP/ポートを確認 |
| `Marked 0 logs as analyzed` | 新規ログなし | 正常（ログ発生がない期間）|

### 7.4 データベースの状態確認

```bash
cd /opt/wasabi-log-monitor

# レコード件数の確認
sqlite3 data/wasabi_monitor.db "
  SELECT 'bucket_logs (total)' AS label, COUNT(*) FROM bucket_logs
  UNION ALL
  SELECT 'bucket_logs (unanalyzed)', COUNT(*) FROM bucket_logs WHERE analyzed = 0
  UNION ALL
  SELECT 'audit_logs (total)', COUNT(*) FROM audit_logs
  UNION ALL
  SELECT 'audit_logs (unanalyzed)', COUNT(*) FROM audit_logs WHERE analyzed = 0
  UNION ALL
  SELECT 'processed_files', COUNT(*) FROM processed_files;
"

# 直近のログ時刻を確認
sqlite3 data/wasabi_monitor.db "
  SELECT MAX(request_time) AS latest_bucket_log FROM bucket_logs;
"
```

---

## 8. トラブルシューティング

### 8.1 「InvalidAccessKeyId」エラー

**原因:** Wasabi APIキーが無効/失効している。

**対処:**
1. Wasabiコンソールでキーの有効性を確認
2. 新しいキーを発行し `config.yaml` を更新
3. サービスを再起動

### 8.2 メトリクスが Zabbix に届かない

**確認手順:**
```bash
# zabbix_sender の動作テスト
zabbix_sender -z <ZABBIX_SERVER_IP> -p 10051 -s "wasabi-monitor" -k "wasabi.sec.unauth_access.count" -o 0

# ファイアウォールの確認
telnet <ZABBIX_SERVER_IP> 10051
```

**チェックリスト:**
- [ ] `zabbix_sender` がインストールされているか
- [ ] Zabbix Server の 10051/TCP ポートに到達可能か
- [ ] Zabbix上のホスト名が `config.yaml` と一致しているか
- [ ] Zabbix上にすべてのアイテム（trapperタイプ）が登録されているか

### 8.3 「Marked 0 logs as analyzed」が続く

**原因:** S3からログが取得できていない。

**確認:**
1. S3のアクセスログ出力設定が有効か確認
2. `processed_files` テーブルをチェックし、新しいファイルが追加されているか確認
3. S3バケットにログファイルが存在するか確認

```bash
# processed_files のリセット（全ファイルを再取得させたい場合）
sqlite3 data/wasabi_monitor.db "DELETE FROM processed_files;"
```

### 8.4 SQLiteタイムスタンプエラー

**症状:** `invalid literal for int() with base 10: b'31+00'` のようなエラー。

**原因:** Python 3.9系のSQLite timestamp converter がタイムゾーン文字列を正しく処理できない。

**対処:** `db_manager.py` に以下のパッチが適用済みであることを確認:
```python
sqlite3.register_converter("timestamp", lambda v: v.decode("utf-8"))
sqlite3.register_converter("TIMESTAMP", lambda v: v.decode("utf-8"))
```

### 8.5 データの再分析が必要な場合

analyzedフラグをリセットすることで全データの再分析が可能:

```bash
# 全ログを未分析に戻す
sqlite3 data/wasabi_monitor.db "
  UPDATE bucket_logs SET analyzed = 0;
  UPDATE audit_logs SET analyzed = 0;
"

# 次回のサイクルで自動的に再分析される
```

> ⚠️ **注意:** 再分析を行うと、分析サイクル内のメトリクス値が履歴データの累積値となる。Zabbix側のグラフに一時的なスパイクが発生するため、運用に支障がない時間帯に実施すること。

---

## 9. 保守作業

### 9.1 データベースの肥大化対策

長期運用ではDBサイズが増大するため、定期的な古いデータの削除を検討する:

```bash
# 90日より前の分析済みログを削除
sqlite3 data/wasabi_monitor.db "
  DELETE FROM bucket_logs 
  WHERE analyzed = 1 AND created_at < datetime('now', '-90 days');
  
  DELETE FROM audit_logs 
  WHERE analyzed = 1 AND created_at < datetime('now', '-90 days');
  
  VACUUM;
"
```

> 💡 **推奨:** cron等で月次実行する。

### 9.2 ログファイルのローテーション

`logs/wasabi_monitor.log` はデフォルトでは自動ローテーションされない。  
logrotate の設定例:

```bash
sudo tee /etc/logrotate.d/wasabi-monitor << 'EOF'
/opt/wasabi-log-monitor/logs/wasabi_monitor.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
    copytruncate
}
EOF
```

### 9.3 バージョンアップ手順

1. サービスを停止
2. ソースコードを更新 (`git pull` 等)
3. 依存パッケージを更新 (`pip install -r requirements.txt`)
4. DBマイグレーションは初回起動時に自動実行される
5. サービスを起動
6. ログで正常起動を確認

```bash
sudo systemctl stop wasabi-monitor
cd /opt/wasabi-log-monitor && git pull
source venv/bin/activate && pip install -r requirements.txt
sudo systemctl start wasabi-monitor
sudo journalctl -u wasabi-monitor -f
```

### 9.4 バックアップ

```bash
# データベースのバックアップ
cp data/wasabi_monitor.db data/wasabi_monitor.db.bak.$(date +%Y%m%d)

# 設定ファイルのバックアップ
cp config.yaml config.yaml.bak.$(date +%Y%m%d)
```

---

## 付録: 全メトリクスキー一覧 (クイックリファレンス)

```
wasabi.sec.unauth_access.count        # 未認証アクセス数
wasabi.sec.403_error.count            # 403エラー数
wasabi.sec.unknown_ip.count           # 未知IPアクセス数
wasabi.sec.data_exfil.bytes           # データダウンロード量 (bytes)
wasabi.sec.suspicious_ua.count        # 不審UserAgent数
wasabi.sec.delete_ops.count           # DELETE操作数
wasabi.sec.off_hours.count            # 業務時間外アクセス数
wasabi.sec.weak_tls.count             # 弱いTLS使用数
wasabi.sec.admin_fail.count           # 管理操作認証失敗数
wasabi.sec.root_usage.count           # rootアカウント使用数

wasabi.upl.scheduled.status           # 定期アップロード状態 (1=正常, 0=未達)
wasabi.upl.upload.bytes               # アップロードサイズ (bytes)
wasabi.upl.upload_failure.count       # アップロード失敗数
wasabi.upl.unknown_ip.count           # 未知IPアップロード数
wasabi.upl.multipart_uncompleted.count # マルチパート未完了数
wasabi.upl.daily_upload.count         # アップロード件数

wasabi.pub.anon_get.count             # 匿名GETアクセス数
wasabi.pub.acl_change.count           # ACL変更数
wasabi.pub.external_referer.count     # 外部リファラー数
wasabi.pub.anon_list.count            # 匿名バケットリスト数
wasabi.pub.browser_access.count       # ブラウザ直接アクセス数
wasabi.pub.policy_change.count        # バケットポリシー変更数
wasabi.pub.public_config_change.count # パブリックアクセス設定変更数

wasabi.ops.log_delay.seconds          # ログ配送遅延 (秒)
wasabi.ops.throttle.count             # APIスロットリング数
wasabi.ops.replication.status         # レプリケーション状態
wasabi.ops.storage_increase.bytes     # ストレージ増分 (bytes)
```
