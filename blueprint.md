# Wasabi ログ監視システム — 設計ブループリント

> **バージョン**: 1.1（POC）  
> **最終更新日**: 2026-04-06  
> **ステータス**: POC（Proof of Concept）

---

## 1. システム概要

### 1.1 目的

Wasabi クラウドストレージの **バケットログ**（S3アクセスログ）と **監査ログ**（管理コンソール操作ログ）を自動収集し、セキュリティ・運用上の異常を検知して Zabbix へメトリクスとして連携する Python ベースの監視システムです。

### 1.2 解決する課題

| 課題 | 本システムによる対応 |
|---|---|
| 不正アクセスの検知が手動 | 403エラー急増、未知IP、不審UA等の自動検知 |
| データ漏洩リスクの可視化不足 | 大量ダウンロード、匿名GETアクセスの計測 |
| バックアップ正常性確認の手間 | 定期アップロードの自動確認・失敗検知 |
| 監査ログの活用不足 | ポリシー変更、root使用、認証失敗の自動監視 |
| 統合監視への未連携 | Zabbix トラッパーアイテム経由でメトリクス送信 |

### 1.3 システム全体像

```
┌─────────────────────────────────────────────────────────────┐
│                    Wasabi Cloud Storage                      │
│  ┌──────────────────┐  ┌──────────────────────────────────┐ │
│  │  ログ保管バケット    │  │  Wasabi 管理コンソール (監査ログ) │ │
│  │  (S3アクセスログ)   │  │  (CSV形式)                      │ │
│  └────────┬─────────┘  └───────────────┬──────────────────┘ │
└───────────┼────────────────────────────┼────────────────────┘
            │                            │
            ▼                            ▼
┌───────────────────────────────────────────────────────────┐
│              Wasabi Log Monitor (本システム)                │
│                                                           │
│  ┌─────────────┐  ┌─────────────┐                         │
│  │ BucketLog    │  │ AuditLog    │   ← Collectors         │
│  │ Collector    │  │ Collector   │     (S3 or ローカル)     │
│  └──────┬──────┘  └──────┬──────┘                         │
│         │                │                                │
│         ▼                ▼                                │
│  ┌─────────────┐  ┌─────────────┐                         │
│  │ BucketLog    │  │ AuditLog    │   ← Parsers            │
│  │ Parser       │  │ Parser      │     (正規表現 / CSV)     │
│  └──────┬──────┘  └──────┬──────┘                         │
│         │                │                                │
│         ▼                ▼                                │
│  ┌──────────────────────────────┐                         │
│  │       SQLite Database        │   ← Storage             │
│  │  (bucket_logs, audit_logs,   │     (永続化・重複排除)     │
│  │   processed_files)           │                         │
│  └──────────────┬───────────────┘                         │
│                 │                                         │
│                 ▼                                         │
│  ┌────────────────────────────────────────────────┐       │
│  │              Analyzers (分析エンジン)             │       │
│  │  ┌────────────┐ ┌───────────┐ ┌─────────────┐  │       │
│  │  │ Security   │ │ Upload    │ │ PublicAccess │  │       │
│  │  │ Analyzer   │ │ Analyzer  │ │ Analyzer    │  │       │
│  │  │ (SEC-*)    │ │ (UPL-*)   │ │ (PUB-*)     │  │       │
│  │  └────────────┘ └───────────┘ └─────────────┘  │       │
│  │  ┌────────────┐                                │       │
│  │  │ Ops        │                                │       │
│  │  │ Analyzer   │                                │       │
│  │  │ (OPS-*)    │                                │       │
│  │  └────────────┘                                │       │
│  └──────────────────────┬─────────────────────────┘       │
│                         │                                 │
│                         ▼                                 │
│  ┌──────────────┐  ┌──────────────┐                       │
│  │ output.txt   │  │ Zabbix       │   ← Alerting          │
│  │ (ローカル)    │  │ Sender       │     (メトリクス送信)    │
│  └──────────────┘  └──────┬───────┘                       │
└────────────────────────────┼───────────────────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   Zabbix Server   │
                    │  (統合監視基盤)     │
                    └──────────────────┘
```

---

## 2. ディレクトリ構成

```
kanshi-main/
├── main.py                     # エントリーポイント・スケジューラ
├── config.yaml                 # 全体設定ファイル
├── requirements.txt            # Python依存パッケージ
├── blueprint.md                # 本ドキュメント（設計書）
├── manual.md                   # 運用マニュアル
├── README.md                   # プロジェクト概要
├── output.txt                  # 分析結果出力ファイル
│
├── collectors/                 # ログ収集モジュール
│   ├── __init__.py
│   ├── bucket_log_collector.py # バケットログ収集（S3/ローカル対応）
│   └── audit_log_collector.py  # 監査ログ収集（S3/ローカル対応）
│
├── parsers/                    # ログパースモジュール
│   ├── __init__.py
│   ├── bucket_log_parser.py    # S3アクセスログ正規表現パーサー
│   └── audit_log_parser.py     # 監査ログCSVパーサー
│
├── analyzers/                  # 分析エンジン
│   ├── __init__.py
│   ├── security_analyzer.py    # セキュリティ分析（SEC-01〜10）
│   ├── upload_analyzer.py      # アップロード監視（UPL-01〜06）
│   ├── public_access_analyzer.py # 外部公開監視（PUB-01〜07）
│   └── ops_analyzer.py         # 運用監視（OPS-01〜04）
│
├── alerting/                   # アラート送信モジュール
│   ├── __init__.py
│   └── zabbix_sender.py        # Zabbix Sender ラッパー
│
├── storage/                    # データ永続化モジュール
│   ├── __init__.py
│   ├── models.py               # データモデル定義（BucketLog, AuditLog）
│   └── db_manager.py           # SQLite DB管理クラス
│
├── tools/                      # ユーティリティ
│   ├── test_run.py             # スケジューラなしテスト実行
│   ├── generate_dummy_logs.py  # ダミーログ生成
│   └── print_metrics.py        # メトリクス単独出力
│
├── test/                       # テストデータ
│   ├── audit_logs/             # 監査ログサンプル（CSV, 6ファイル）
│   └── bucket_logs/            # バケットログサンプル（53ファイル）
│
├── data/                       # ランタイムデータ
│   └── wasabi_monitor.db       # SQLiteデータベース（自動生成）
│
└── logs/                       # アプリケーションログ
    └── wasabi_monitor.log      # 実行ログ（自動生成）
```

---

## 3. コンポーネント詳細

### 3.1 Collectors（収集層）

ログソースからデータを取得し、Parser に渡してパース済みデータを DB に保存します。

#### BucketLogCollector

| 項目 | 内容 |
|---|---|
| ファイル | `collectors/bucket_log_collector.py` |
| 入力 | S3アクセスログファイル（テキスト形式、1行1リクエスト） |
| 動作モード | `bucket`（S3から取得）/ `local`（ローカルファイルから取得） |
| 重複排除 | `processed_files` テーブルでファイル単位の処理済み管理 |
| 設定 | `config.yaml` → `bucket_log.source`, `bucket_log.local_path` |

#### AuditLogCollector

| 項目 | 内容 |
|---|---|
| ファイル | `collectors/audit_log_collector.py` |
| 入力 | 監査ログCSVファイル（ヘッダー付き） |
| 動作モード | `bucket`（S3から取得）/ `local`（ローカルファイルから取得） |
| 重複排除 | `processed_files` テーブルでファイル単位の処理済み管理 |
| 設定 | `config.yaml` → `audit_log.source`, `audit_log.local_path` |

### 3.2 Parsers（パース層）

#### BucketLogParser

S3アクセスログの1行を正規表現でパースし、`BucketLog` データクラスに変換します。

**対応フィールド（24項目）:**

| フィールド | 説明 | 例 |
|---|---|---|
| `bucket_owner` | バケットオーナーのハッシュ | `04F56E04B2D1...` |
| `bucket` | バケット名 | `shunki-test-01` |
| `request_time` | リクエスト日時（UTC） | `04/Mar/2026:15:00:08 +0000` |
| `remote_ip` | アクセス元IP | `220.158.16.201` |
| `requester` | リクエスタ（`-`=匿名） | `J2WUS0Y5LEGM...` |
| `operation` | S3操作名 | `REST.PUT.OBJECT` |
| `key` | オブジェクトキー | `backup/daily/db.bak` |
| `http_status` | HTTPステータスコード | `200`, `403`, `404` |
| `bytes_sent` | 送信バイト数 | `1024` |
| `object_size` | オブジェクトサイズ | `5000000` |
| `user_agent` | ユーザーエージェント | `aws-cli/2.34.0...` |
| `tls_version` | TLSバージョン | `TLSv1.3` |

#### AuditLogParser

CSV形式の監査ログを `csv.DictReader` で読み込み、`AuditLog` データクラスに変換します。ヘッダー名の揺れに対応するため、部分一致ベースの柔軟なキーマッピングを実装しています。

**監査ログCSVヘッダー例:**
```
Method,Path,QueryString,Body,UserNum,RemoteAddr,StatusCode,TimeStamp,SessionName,RoleName
```

### 3.3 Storage（永続化層）

#### DBManager

SQLite データベースを管理するクラスです。

**テーブル構成:**

```
┌─────────────────┐  ┌──────────────────┐  ┌─────────────────┐
│   bucket_logs    │  │   audit_logs      │  │ processed_files  │
├─────────────────┤  ├──────────────────┤  ├─────────────────┤
│ id (PK, AI)     │  │ id (PK, AI)      │  │ file_name (PK)  │
│ log_file_name   │  │ timestamp        │  │ processed_at    │
│ bucket_owner    │  │ user             │  └─────────────────┘
│ bucket          │  │ action           │
│ request_time    │  │ resource         │
│ remote_ip       │  │ result           │
│ requester       │  │ source_ip        │
│ request_id (UQ) │  │ raw_data         │
│ operation       │  │ created_at       │
│ key             │  └──────────────────┘
│ request_uri     │
│ http_status     │
│ error_code      │
│ bytes_sent      │
│ object_size     │
│ total_time      │
│ turn_around_time│
│ referer         │
│ user_agent      │
│ version_id      │
│ host_id         │
│ signature_ver   │
│ cipher_suite    │
│ auth_type       │
│ host_header     │
│ tls_version     │
│ created_at      │
└─────────────────┘
```

**タイムゾーン対応:**
- カスタム SQLite Adapter/Converter を登録し、`datetime` オブジェクトを ISO8601 形式で保存・復元
- タイムゾーン情報（`+00:00`）を含む日時の正確な取り扱いを保証

### 3.4 Analyzers（分析層）

DB に蓄積されたログデータに対して SQL クエリで分析を行い、`(メトリクス名, 値)` のタプルリストを返します。

#### SecurityAnalyzer（SEC-01〜10）

| ID | メトリクス名 | 検知内容 | ソース |
|---|---|---|---|
| SEC-01 | `wasabi.sec.unauth_access.count` | 未認証アクセス（requester='-'） | バケットログ |
| SEC-02 | `wasabi.sec.403_error.count` | 403エラー件数 | バケットログ |
| SEC-03 | `wasabi.sec.unknown_ip.count` | 未知IPからのアクセス | バケットログ |
| SEC-04 | `wasabi.sec.data_exfil.bytes` | GET操作の総送信バイト数 | バケットログ |
| SEC-05 | `wasabi.sec.suspicious_ua.count` | 不審UserAgent検知数 | バケットログ |
| SEC-06 | `wasabi.sec.delete_ops.count` | DELETE操作件数 | バケットログ |
| SEC-07 | `wasabi.sec.off_hours.count` | 業務時間外アクセス数 | バケットログ |
| SEC-08 | `wasabi.sec.admin_fail.count` | 管理操作認証失敗数 | 監査ログ |
| SEC-09 | `wasabi.sec.root_usage.count` | rootアカウント使用数 | 監査ログ |
| SEC-10 | `wasabi.sec.weak_tls.count` | 弱いTLS使用数 | バケットログ |

#### UploadAnalyzer（UPL-01〜06）

| ID | メトリクス名 | 検知内容 | ソース |
|---|---|---|---|
| UPL-01 | `wasabi.upl.scheduled.status` | 定期バックアップ状態（1=OK/0=NG） | バケットログ |
| UPL-02 | `wasabi.upl.upload.bytes` | アップロード総バイト数 | バケットログ |
| UPL-03 | `wasabi.upl.upload_failure.count` | アップロード失敗件数 | バケットログ |
| UPL-04 | `wasabi.upl.unknown_ip.count` | 未知IPからのアップロード数 | バケットログ |
| UPL-05 | `wasabi.upl.multipart_uncompleted.count` | マルチパート未完了数 | バケットログ |
| UPL-06 | `wasabi.upl.daily_upload.count` | 日次アップロード件数 | バケットログ |

#### PublicAccessAnalyzer（PUB-01〜07）

| ID | メトリクス名 | 検知内容 | ソース |
|---|---|---|---|
| PUB-01 | `wasabi.pub.anon_get.count` | 匿名GETアクセス数 | バケットログ |
| PUB-02 | `wasabi.pub.policy_change.count` | バケットポリシー変更数 | 監査ログ |
| PUB-03 | `wasabi.pub.acl_change.count` | ACL変更操作数 | バケットログ |
| PUB-04 | `wasabi.pub.public_config_change.count` | パブリックアクセス設定変更数 | 監査ログ |
| PUB-05 | `wasabi.pub.external_referer.count` | 外部リファラーアクセス数 | バケットログ |
| PUB-06 | `wasabi.pub.anon_list.count` | 匿名バケットリスト操作数 | バケットログ |
| PUB-07 | `wasabi.pub.browser_access.count` | ブラウザ直接アクセス数 | バケットログ |

#### OpsAnalyzer（OPS-01〜04）

| ID | メトリクス名 | 検知内容 | ソース |
|---|---|---|---|
| OPS-01 | `wasabi.ops.log_delay.seconds` | ログ配送遅延（秒） | バケットログ |
| OPS-02 | `wasabi.ops.throttle.count` | APIスロットリング数（429/503） | バケットログ |
| OPS-03 | `wasabi.ops.replication.status` | レプリケーション状態（常時1） | 固定値 |
| OPS-04 | `wasabi.ops.storage_increase.bytes` | ストレージ増加量（バイト） | バケットログ |

### 3.5 Alerting（通知層）

#### ZabbixSenderWrapper

`zabbix_sender` コマンドを呼び出し、メトリクスを Zabbix Server のトラッパーアイテムへ送信します。

- **送信形式**: 標準入力経由（`-i -` オプション）
- **データ形式**: `"hostname" "key" "value"` の1行1メトリクス
- **エラーハンドリング**: `zabbix_sender` 未インストール時はエラーログ出力のみ（POCのため）

---

## 4. 動作モード

### 4.1 本番モード（`source: "bucket"`）

```
Wasabi S3 → Collector → Parser → SQLite → Analyzer → Zabbix
                                                   ↘ output.txt
```

- S3 バケットからログを定期取得（`boto3` 使用）
- `APScheduler` によるスケジューラで一定間隔（デフォルト 300秒）で自動実行
- メトリクスを Zabbix Server へ送信

### 4.2 ローカルテストモード（`source: "local"`）

```
test/bucket_logs/ → Collector → Parser → SQLite → Analyzer → output.txt
test/audit_logs/  ↗                                        ↘ コンソール
```

- ローカルファイルからログを読み込み（S3接続不要）
- **DB内の全データ**を分析対象とする（時間窓を 2020-01-01〜現在に拡大）
- Zabbix 送信は **スキップ**
- **一度実行して自動終了**（スケジューラは起動しない）
- 結果は `output.txt` とコンソールに出力

---

## 5. データフロー

```
[ログファイル]
     │
     ▼
[Collector] ─── is_file_processed? ──→ スキップ（処理済み）
     │                  │
     │（未処理）          │
     ▼                  │
[Parser] ─── パース成功? ──→ スキップ（パースエラー行）
     │                  │
     │（成功）           │
     ▼                  │
[DBManager.insert_*] ──→ 重複チェック（request_id UNIQUE制約）
     │                  │
     │（挿入成功）        │
     ▼                  │
[mark_file_processed] ──→ processed_files テーブルに記録
     │
     ▼
[Analyzer.analyze()] ─── SQLクエリでメトリクス算出
     │
     ▼
[output.txt / Zabbix] ─── 結果出力・送信
```

---

## 6. 設定ファイル構成（config.yaml）

| セクション | 用途 | 主要設定項目 |
|---|---|---|
| `wasabi` | S3接続情報 | `endpoint_url`, `access_key`, `secret_key`, `log_bucket` |
| `audit_log` | 監査ログ収集設定 | `source`（bucket/local）, `local_path` |
| `bucket_log` | バケットログ収集設定 | `source`（bucket/local）, `local_path` |
| `database` | DB設定 | `type`（sqlite/postgresql）, `sqlite.path` |
| `zabbix` | Zabbix連携設定 | `server`, `port`, `hostname`, `sender_path` |
| `scheduler` | スケジューラ | `collection_interval`, `analysis_interval` |
| `monitoring` | 監視ルール | `security`, `upload`, `public_access`, `ops` |
| `ip_whitelist` | IP許可リスト | `allowed_ips`, `backup_server_ips` |
| `ua_blacklist` | UA拒否リスト | `patterns` |
| `logging` | ログ設定 | `level`, `file`, `max_bytes` |

---

## 7. 技術スタック

| カテゴリ | 技術 | バージョン要件 |
|---|---|---|
| 言語 | Python | 3.9以上 |
| S3クライアント | boto3 | >= 1.28.0 |
| YAML | PyYAML | >= 6.0 |
| スケジューラ | APScheduler | >= 3.10.0 |
| データベース | SQLite3 | Python標準ライブラリ |
| 監視連携 | zabbix_sender | 外部コマンド |

---

## 8. 今後の拡張ポイント

| 項目 | 現状（POC） | 将来の拡張案 |
|---|---|---|
| DB | SQLite（単一ファイル） | PostgreSQL 対応（config.yaml に設定枠あり） |
| 環境変数展開 | 未実装 | `${VAR}` の自動展開実装 |
| ログローテーション | ファイルサイズ制限なし | `RotatingFileHandler` 適用 |
| 分析ルール | ハードコーディング | ルールエンジン化・プラグイン化 |
| アラート通知先 | Zabbix のみ | Slack, Teams, Email 対応 |
| ダッシュボード | なし | Grafana 連携 |
| テスト | 手動テスト | pytest ユニットテスト |
