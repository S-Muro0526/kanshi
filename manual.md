# Wasabi ログ監視システム — 運用マニュアル

> **バージョン**: 1.1（POC）  
> **最終更新日**: 2026-04-06

---

## 目次

1. [前提条件](#1-前提条件)
2. [セットアップ手順](#2-セットアップ手順)
3. [config.yaml 設定ガイド](#3-configyaml-設定ガイド)
4. [実行方法](#4-実行方法)
5. [ローカルテスト手順](#5-ローカルテスト手順)
6. [出力内容の見方](#6-出力内容の見方)
7. [Zabbix 連携設定](#7-zabbix-連携設定)
8. [トラブルシューティング](#8-トラブルシューティング)
9. [運用手順書](#9-運用手順書)

---

## 1. 前提条件

### 必須

| 項目 | 要件 |
|---|---|
| Python | 3.9 以上 |
| OS | Linux / macOS / Windows |
| ネットワーク | 本番モード時: Wasabi S3 エンドポイントへの HTTPS アクセス |

### オプション（本番時）

| 項目 | 要件 |
|---|---|
| Zabbix Server | 6.0 以上（トラッパーアイテム対応） |
| zabbix_sender | Zabbix Agent パッケージに含まれるコマンドラインツール |
| Wasabi アカウント | アクセスキー / シークレットキー |

---

## 2. セットアップ手順

### 2.1 リポジトリの取得

```bash
# プロジェクトディレクトリに移動
cd kanshi-main
```

### 2.2 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

**インストールされるパッケージ:**
- `boto3` >= 1.28.0 — S3互換クライアント
- `pyyaml` >= 6.0 — YAML設定ファイル読み込み
- `apscheduler` >= 3.10.0 — 定期実行スケジューラ
- `ipaddress` >= 1.0.23 — IPアドレスのCIDR判定

### 2.3 環境変数の設定（本番モードのみ）

```bash
# Linux / macOS
export WASABI_ACCESS_KEY="your-access-key"
export WASABI_SECRET_KEY="your-secret-key"

# Windows (PowerShell)
$env:WASABI_ACCESS_KEY = "your-access-key"
$env:WASABI_SECRET_KEY = "your-secret-key"
```

> **注意**: 現在のPOC版では `config.yaml` 内の `${WASABI_ACCESS_KEY}` は自動展開されません。直接キーを記入するか、環境変数展開の仕組みを別途実装してください。

---

## 3. config.yaml 設定ガイド

### 3.1 主要設定項目

#### Wasabi S3 接続設定

```yaml
wasabi:
  endpoint_url: "https://s3.ap-northeast-1.wasabisys.com"
  region: "ap-northeast-1"
  access_key: "YOUR_ACCESS_KEY"      # 環境変数未展開のため直書き
  secret_key: "YOUR_SECRET_KEY"      # 環境変数未展開のため直書き
  log_bucket: "log-storage-bucket"   # ログ保管バケット名
  log_prefix: ""                     # ログのプレフィックス（任意）
```

#### ログソースの切り替え

```yaml
# 監査ログ
audit_log:
  source: "local"                    # "bucket" or "local"
  bucket_prefix: "audit-logs/"       # S3モード時のプレフィックス
  local_path: "./test/audit_logs/"   # ローカルモード時のパス

# バケットログ
bucket_log:
  source: "local"                    # "bucket" or "local"
  local_path: "./test/bucket_logs/"  # ローカルモード時のパス
```

| source値 | 動作 | S3接続 | 用途 |
|---|---|---|---|
| `"bucket"` | S3バケットからログ取得 | **必要** | 本番環境 |
| `"local"` | ローカルディレクトリからログ取得 | **不要** | テスト・開発 |

#### 監視ルール

```yaml
monitoring:
  security:
    error_403_threshold: 10           # 403エラー閾値（件/5分）
    data_exfil_bytes_threshold: 1073741824  # 1GB
    mass_delete_threshold: 50         # DELETE閾値（件/5分）
    business_hours:
      start: 8                        # 業務開始時刻（JST）
      end: 22                         # 業務終了時刻（JST）
    allowed_tls_versions:
      - "TLSv1.2"
      - "TLSv1.3"

  upload:
    expected_schedules:
      - name: "daily_backup"
        key_pattern: "backup/daily/.*"    # バックアップファイルのキーパターン（正規表現）
        expected_hour_utc: 15             # 期待する実行時刻（UTC）
        tolerance_minutes: 60             # 許容範囲（分）

  public_access:
    allowed_referer_domains:
      - "example.com"                # 許可するリファラードメイン

  ops:
    log_delay_threshold: 1800         # ログ遅延閾値（秒, 30分）
    daily_storage_increase_threshold: 10737418240  # 10GB
```

#### IPホワイトリスト

```yaml
ip_whitelist:
  allowed_ips:                        # CIDR表記可
    - "192.168.1.0/24"
    - "10.0.0.0/8"
  backup_server_ips:                  # バックアップサーバIP
    - "203.0.113.10"
```

#### UserAgentブラックリスト

```yaml
ua_blacklist:
  patterns:                           # 部分一致で判定
    - "sqlmap"
    - "nikto"
    - "nmap"
    - "masscan"
```

---

## 4. 実行方法

### 4.1 本番モード

```bash
# config.yaml の source を "bucket" に設定してから実行
python main.py
```

**動作:**
1. 起動時に1回ログ収集・分析を実行
2. 300秒間隔（デフォルト）でスケジューラがループ実行
3. `Ctrl+C` で停止

### 4.2 ローカルテストモード

```bash
# config.yaml の source を "local" に設定してから実行
python main.py
```

**動作:**
1. `test/bucket_logs/` と `test/audit_logs/` からログを読み込み
2. DB内の全データを対象に分析
3. 結果を `output.txt` とコンソールに出力
4. **自動的に終了**（スケジューラは起動しない）

---

## 5. ローカルテスト手順

### 5.1 クイックスタート

```bash
# 1. config.yaml を確認（source が "local" であること）
#    audit_log.source: "local"
#    bucket_log.source: "local"

# 2. 既存のDBを削除してクリーンな状態で試す場合
#    Windows:
Remove-Item .\data\wasabi_monitor.db -Force -ErrorAction SilentlyContinue
#    Linux/Mac:
rm -f ./data/wasabi_monitor.db

# 3. 実行
python main.py

# 4. 結果確認
cat output.txt          # Linux/Mac
type output.txt         # Windows
```

### 5.2 期待される出力例

```
# Wasabi Monitor Analysis Results
# Generated: 2026-04-06T07:31:47.181102+00:00
# Mode: LOCAL TEST
# Database: /path/to/data/wasabi_monitor.db

wasabi.sec.unauth_access.count: 0
wasabi.sec.403_error.count: 96
wasabi.sec.unknown_ip.count: 6593
wasabi.sec.data_exfil.bytes: 15097109752
...（27項目）
```

### 5.3 テストデータの追加

独自のテストデータを追加する場合:

- **バケットログ**: `test/bucket_logs/` にS3アクセスログ形式のテキストファイルを配置（拡張子不問）
- **監査ログ**: `test/audit_logs/` にCSVファイル（`.csv` 拡張子必須）を配置

テストログのフォーマット例は既存のファイルを参照してください。

### 5.4 ダミーログによるテスト

```bash
# DBを初期化（main.pyの初回実行でテーブル作成）
python main.py

# ダミーデータ挿入
python tools/generate_dummy_logs.py

# メトリクスのみ確認
python tools/print_metrics.py
```

---

## 6. 出力内容の見方

### 6.1 output.txt

実行ごとに上書きされる分析結果ファイルです。

| ヘッダー | 内容 |
|---|---|
| `# Generated` | 生成日時（UTC） |
| `# Mode` | `LOCAL TEST` or `PRODUCTION` |
| `# Database` | 使用したDBファイルの絶対パス |

### 6.2 メトリクスの読み方

#### セキュリティ系（SEC-*）

| メトリクス | 正常値 | 要注意 | 対応 |
|---|---|---|---|
| `unauth_access.count` | 0 | >0 | 匿名アクセスの発生源IP確認 |
| `403_error.count` | 少数 | 閾値超過 | ブルートフォース攻撃の可能性調査 |
| `unknown_ip.count` | 0 | >0 | IPホワイトリスト更新 or 不審アクセス調査 |
| `data_exfil.bytes` | 通常範囲内 | 急増 | データ流出の可能性調査 |
| `suspicious_ua.count` | 0 | >0 | 攻撃ツールによるスキャン調査 |
| `delete_ops.count` | 少数 | 閾値超過 | ランサムウェア/内部不正の可能性 |
| `off_hours.count` | 0 | >0 | 業務時間外の不審操作確認 |
| `weak_tls.count` | 0 | >0 | TLS設定の見直し |
| `admin_fail.count` | 0 | >0 | パスワードスプレー攻撃の可能性 |
| `root_usage.count` | 0 | >0 | rootアカウント使用のポリシー違反 |

#### アップロード系（UPL-*）

| メトリクス | 正常値 | 要注意 | 対応 |
|---|---|---|---|
| `scheduled.status` | 1 | 0 | バックアップ未実行の調査 |
| `upload_failure.count` | 0 | >0 | アップロードエラーの原因調査 |

#### 外部公開系（PUB-*）

| メトリクス | 正常値 | 要注意 | 対応 |
|---|---|---|---|
| `anon_get.count` | 0 | >0 | バケットACL設定の確認 |
| `policy_change.count` | 0 | >0 | 意図しないポリシー変更の確認 |
| `acl_change.count` | 想定内 | 想定外 | ACL変更の妥当性確認 |

### 6.3 ログファイル

アプリケーションログは `./logs/wasabi_monitor.log` に出力されます。

```
2026-04-06 16:31:46 - main - INFO - Initializing Wasabi Log Monitor POC...
2026-04-06 16:31:46 - storage.db_manager - INFO - Database initialized successfully.
2026-04-06 16:31:46 - collectors.bucket_log_collector - INFO - Bucket log collection (local) completed. Inserted 6593 new records.
...
```

---

## 7. Zabbix 連携設定

### 7.1 Zabbix Server 側の設定

各メトリクスに対応するトラッパーアイテムを作成する必要があります。

**ホスト名**: `wasabi-monitor`（`config.yaml` の `zabbix.hostname` と一致させる）

**作成するアイテム一覧（27項目）:**

```
wasabi.sec.unauth_access.count      (数値 unsigned)
wasabi.sec.403_error.count          (数値 unsigned)
wasabi.sec.unknown_ip.count         (数値 unsigned)
wasabi.sec.data_exfil.bytes         (数値 unsigned)
wasabi.sec.suspicious_ua.count      (数値 unsigned)
wasabi.sec.delete_ops.count         (数値 unsigned)
wasabi.sec.off_hours.count          (数値 unsigned)
wasabi.sec.weak_tls.count           (数値 unsigned)
wasabi.sec.admin_fail.count         (数値 unsigned)
wasabi.sec.root_usage.count         (数値 unsigned)
wasabi.upl.scheduled.status         (数値 unsigned)
wasabi.upl.upload.bytes             (数値 unsigned)
wasabi.upl.upload_failure.count     (数値 unsigned)
wasabi.upl.unknown_ip.count         (数値 unsigned)
wasabi.upl.multipart_uncompleted.count (数値 unsigned)
wasabi.upl.daily_upload.count       (数値 unsigned)
wasabi.pub.anon_get.count           (数値 unsigned)
wasabi.pub.acl_change.count         (数値 unsigned)
wasabi.pub.external_referer.count   (数値 unsigned)
wasabi.pub.anon_list.count          (数値 unsigned)
wasabi.pub.browser_access.count     (数値 unsigned)
wasabi.pub.policy_change.count      (数値 unsigned)
wasabi.pub.public_config_change.count (数値 unsigned)
wasabi.ops.log_delay.seconds        (数値 float)
wasabi.ops.throttle.count           (数値 unsigned)
wasabi.ops.replication.status       (数値 unsigned)
wasabi.ops.storage_increase.bytes   (数値 unsigned)
```

### 7.2 config.yaml のZabbix設定

```yaml
zabbix:
  server: "192.168.1.100"            # Zabbix ServerのIPアドレス
  port: 10051                        # Zabbixトラッパーポート
  hostname: "wasabi-monitor"         # Zabbixホスト名（一致必須）
  sender_path: "/usr/bin/zabbix_sender"  # zabbix_senderのパス
```

### 7.3 トリガー設定例

| トリガー名 | 条件式 | 重要度 |
|---|---|---|
| SEC: 403エラー急増 | `last(wasabi.sec.403_error.count) > 10` | 警告 |
| SEC: 大量データ送信 | `last(wasabi.sec.data_exfil.bytes) > 1073741824` | 重度 |
| SEC: 大量DELETE | `last(wasabi.sec.delete_ops.count) > 50` | 致命的 |
| UPL: バックアップ未実行 | `last(wasabi.upl.scheduled.status) = 0` | 重度 |
| PUB: 匿名アクセス検知 | `last(wasabi.pub.anon_get.count) > 0` | 警告 |
| OPS: ログ遅延 | `last(wasabi.ops.log_delay.seconds) > 1800` | 情報 |

---

## 8. トラブルシューティング

### 8.1 よくあるエラーと対処法

#### `ModuleNotFoundError: No module named 'apscheduler'`

```bash
pip install -r requirements.txt
```

#### `InvalidAccessKeyId` エラー

- Wasabi のアクセスキー/シークレットキーが正しいか確認
- ローカルテスト時は `source: "local"` に設定されているか確認

#### `can't subtract offset-naive and offset-aware datetimes`

- `db_manager.py` のカスタム Adapter/Converter が正しく登録されているか確認
- DB ファイルを削除して再作成: `rm ./data/wasabi_monitor.db`

#### `Bucket log collection completed. Inserted 0 new records.`

- 既に処理済みのファイルは再取り込みされません
- DB を削除すると `processed_files` テーブルもリセットされ、再取り込みが可能になります

#### `zabbix_sender executable not found`

- `zabbix_sender` がインストールされていない or パスが異なります
- ローカルテスト時はこのエラーは無視されます（Zabbix送信がスキップされるため）

### 8.2 DBのリセット

```bash
# Windows
Remove-Item .\data\wasabi_monitor.db -Force

# Linux/Mac
rm -f ./data/wasabi_monitor.db
```

次回実行時に自動的にテーブルが再作成されます。

### 8.3 ログの確認

```bash
# アプリケーションログ確認
# Windows
type .\logs\wasabi_monitor.log
# Linux/Mac
tail -f ./logs/wasabi_monitor.log
```

---

## 9. 運用手順書

### 9.1 日次確認事項

1. `output.txt` の最新メトリクスを確認
2. 以下のメトリクスが異常値でないことを確認:
   - `wasabi.upl.scheduled.status` が 1（バックアップ正常）
   - `wasabi.sec.403_error.count` が閾値以下
   - `wasabi.ops.log_delay.seconds` が 1800秒以下

### 9.2 config.yaml 変更時の手順

1. `config.yaml` を編集
2. 実行中のプロセスを `Ctrl+C` で停止
3. `python main.py` で再起動

### 9.3 本番への切り替え手順

```yaml
# config.yaml を以下のように変更

audit_log:
  source: "bucket"             # ← "local" から "bucket" に変更
  bucket_prefix: "audit-logs/"

bucket_log:
  source: "bucket"             # ← "local" から "bucket" に変更

wasabi:
  access_key: "YOUR_REAL_KEY"  # ← 実際のアクセスキー
  secret_key: "YOUR_REAL_KEY"  # ← 実際のシークレットキー
  log_bucket: "your-log-bucket"
```

### 9.4 テストデータの更新

新しいテストログを追加した場合:

1. ファイルを `test/bucket_logs/` または `test/audit_logs/` に配置
2. DB をリセット: `rm ./data/wasabi_monitor.db`
3. `python main.py` を再実行

### 9.5 プロセスの自動起動（systemd 例）

```ini
# /etc/systemd/system/wasabi-monitor.service
[Unit]
Description=Wasabi Log Monitor
After=network.target

[Service]
Type=simple
User=monitor
WorkingDirectory=/opt/kanshi-main
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable wasabi-monitor
sudo systemctl start wasabi-monitor
sudo systemctl status wasabi-monitor
```
