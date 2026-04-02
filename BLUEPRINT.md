# Wasabi Log Monitor — システム設計書 (Blueprint)

> **文書バージョン:** 1.0  
> **最終更新日:** 2026-04-02  
> **ステータス:** POC (Proof of Concept)

---

## 1. 概要

### 1.1 目的

Wasabi クラウドストレージに対する **バケットアクセスログ** および **管理監査ログ** を自動収集・分析し、  
セキュリティ脅威の検知、バックアップ健全性の確認、意図しないデータ公開の監視を行うシステムである。  
分析結果はメトリクスとして Zabbix へ送信し、既存の統合監視基盤に統合する。

### 1.2 スコープ

| 項目 | 内容 |
|------|------|
| 対象環境 | Wasabi Cloud Storage (ap-northeast-1) |
| ログ種別 | S3バケットアクセスログ (txt)、管理監査ログ (CSV) |
| アラート連携先 | Zabbix Server (zabbix_sender 経由) |
| データベース | SQLite (POC)、PostgreSQL (本番拡張予定) |
| 実行形態 | Linux/macOS 上の常駐 Python プロセス |

---

## 2. アーキテクチャ

### 2.1 全体構成図

```
┌─────────────────────────────────────────────────────────────┐
│                    Wasabi Cloud Storage                      │
│  ┌─────────────────┐       ┌──────────────────────┐         │
│  │ log-storage-bucket│       │ audit-logs/ (CSV)    │         │
│  │ (アクセスログ)     │       │ (管理監査ログ)        │         │
│  └────────┬────────┘       └──────────┬───────────┘         │
└───────────┼────────────────────────────┼────────────────────┘
            │ boto3 (S3 API)             │ boto3 / ローカル読込
            ▼                            ▼
┌─────────────────────────────────────────────────────────────┐
│             Wasabi Log Monitor (Python)                      │
│                                                             │
│  ┌────────────────┐   ┌─────────────────┐                   │
│  │ BucketLog       │   │ AuditLog         │   Collectors     │
│  │ Collector       │   │ Collector        │   (収集層)       │
│  └───────┬────────┘   └────────┬────────┘                   │
│          │                     │                            │
│          ▼                     ▼                            │
│  ┌────────────────┐   ┌─────────────────┐                   │
│  │ BucketLog       │   │ AuditLog         │   Parsers        │
│  │ Parser          │   │ Parser (CSV)     │   (解析層)       │
│  └───────┬────────┘   └────────┬────────┘                   │
│          │                     │                            │
│          ▼                     ▼                            │
│  ┌──────────────────────────────────────┐                   │
│  │         SQLite Database              │   Storage          │
│  │  bucket_logs │ audit_logs │ files    │   (永続化層)       │
│  └──────────────────┬───────────────────┘                   │
│                     │ analyzed = 0 のみ抽出                  │
│                     ▼                                       │
│  ┌──────────────────────────────────────┐                   │
│  │           Analyzers (分析層)          │                   │
│  │  Security │ Upload │ Public │ Ops    │                   │
│  └──────────────────┬───────────────────┘                   │
│                     │ メトリクス                              │
│                     ▼                                       │
│  ┌──────────────────────────────────────┐                   │
│  │       ZabbixSenderWrapper            │   Alerting         │
│  │       (zabbix_sender -i -)           │   (通知層)         │
│  └──────────────────┬───────────────────┘                   │
└─────────────────────┼───────────────────────────────────────┘
                      │
                      ▼
               ┌──────────────┐
               │ Zabbix Server │
               └──────────────┘
```

### 2.2 処理フロー

```
スケジューラ起動 (APScheduler: 300秒間隔)
    │
    ├── 1. collect_logs()
    │       ├── BucketLogCollector.collect()
    │       │     └── S3からログファイル取得 → パース → DB INSERT (analyzed=0)
    │       └── AuditLogCollector.collect()
    │             └── S3/ローカルCSV取得 → パース → DB INSERT (analyzed=0)
    │
    └── 2. analyze_and_alert()
            ├── SecurityAnalyzer.analyze()      ─┐
            ├── UploadAnalyzer.analyze()         │ WHERE analyzed = 0
            ├── PublicAccessAnalyzer.analyze()    │ のデータのみ対象
            ├── OpsAnalyzer.analyze()            ─┘
            │
            ├── ZabbixSenderWrapper.send_metrics()
            │
            └── DBManager.mark_logs_as_analyzed()
                  └── UPDATE ... SET analyzed = 1 WHERE analyzed = 0
```

### 2.3 差分駆動型アーキテクチャ

本システムは「**未分析データ駆動型 (Analyzed-Flag Paradigm)**」を採用している。

| 従来方式 (時間窓) | 現行方式 (差分フラグ) |
|---|---|
| `WHERE request_time >= now()-5min` | `WHERE analyzed = 0` |
| ログ到着遅延があると取りこぼす | 取り込まれたログは必ず1回処理される |
| 大ファイル転送中のログが漏れる | 処理順序に依存しない |
| 時計同期の問題に弱い | タイムスタンプに依存しない |

> **例外:** `UploadAnalyzer` のスケジュール監視 (UPL-01) のみ、「システムが稼働しているか」を判定する目的で過去24時間の絶対時間を参照する。

---

## 3. ディレクトリ構成

```
wasabi-log-monitor/
├── main.py                          # エントリポイント・スケジューラ
├── config.yaml                      # 全体設定ファイル
├── requirements.txt                 # Python 依存パッケージ
│
├── collectors/                      # ログ収集レイヤー
│   ├── bucket_log_collector.py      #   S3バケットログ収集
│   └── audit_log_collector.py       #   管理監査ログ収集 (S3/ローカル)
│
├── parsers/                         # ログ解析レイヤー
│   ├── bucket_log_parser.py         #   S3アクセスログ正規表現パーサ
│   └── audit_log_parser.py          #   監査CSV柔軟マッピングパーサ
│
├── storage/                         # データ永続化レイヤー
│   ├── models.py                    #   データクラス (BucketLog, AuditLog)
│   └── db_manager.py                #   SQLite管理・マイグレーション
│
├── analyzers/                       # 分析ルールエンジン
│   ├── security_analyzer.py         #   SEC-01〜SEC-10
│   ├── upload_analyzer.py           #   UPL-01〜UPL-06
│   ├── public_access_analyzer.py    #   PUB-01〜PUB-07
│   └── ops_analyzer.py              #   OPS-01〜OPS-04
│
├── alerting/                        # 外部通知レイヤー
│   └── zabbix_sender.py             #   Zabbix Sender ラッパー
│
├── tools/                           # 開発・テストユーティリティ
│   ├── import_sample.py             #   サンプルデータインポート
│   ├── test_analyze_all.py          #   全量分析テスト
│   ├── test_run.py                  #   統合テスト実行
│   ├── print_metrics.py             #   メトリクス表示
│   └── generate_dummy_logs.py       #   ダミーログ生成
│
├── data/                            # SQLite DB 格納先
│   └── wasabi_monitor.db
│
└── logs/                            # アプリケーションログ
    └── wasabi_monitor.log
```

---

## 4. データベース設計

### 4.1 bucket_logs テーブル

| カラム名 | 型 | 説明 |
|---|---|---|
| `id` | INTEGER (PK) | 自動採番 |
| `log_file_name` | TEXT | ソースのログファイル名 |
| `bucket_owner` | TEXT | バケットオーナーID |
| `bucket` | TEXT | バケット名 |
| `request_time` | TIMESTAMP | リクエスト発生時刻 |
| `remote_ip` | TEXT | クライアントIPアドレス |
| `requester` | TEXT | IAMユーザー (`-` は匿名) |
| `request_id` | TEXT (UNIQUE) | リクエスト固有ID（重複排除キー） |
| `operation` | TEXT | S3 API操作名 (例: `REST.PUT.OBJECT`) |
| `key` | TEXT | オブジェクトキー |
| `request_uri` | TEXT | HTTPリクエストURI |
| `http_status` | INTEGER | HTTPステータスコード |
| `error_code` | TEXT | S3エラーコード |
| `bytes_sent` | INTEGER | 送信バイト数 |
| `object_size` | INTEGER | オブジェクトサイズ |
| `total_time` | INTEGER | 総処理時間 (ms) |
| `turn_around_time` | INTEGER | ターンアラウンド時間 (ms) |
| `referer` | TEXT | Refererヘッダー |
| `user_agent` | TEXT | User-Agentヘッダー |
| `version_id` | TEXT | バージョンID |
| `host_id` | TEXT | ホストID |
| `signature_version` | TEXT | 署名バージョン |
| `cipher_suite` | TEXT | 暗号スイート |
| `authentication_type` | TEXT | 認証タイプ |
| `host_header` | TEXT | ホストヘッダー |
| `tls_version` | TEXT | TLSバージョン |
| `created_at` | TIMESTAMP | レコード作成日時 |
| `analyzed` | BOOLEAN | 分析済みフラグ (0=未分析, 1=分析済) |

**インデックス:**
- `idx_bucket_req_id` — `request_id` (重複排除の高速化)
- `idx_bucket_time` — `request_time` (時系列クエリ)
- `idx_bucket_op` — `operation` (操作種別フィルタ)
- `idx_bucket_status` — `http_status` (ステータスフィルタ)
- `idx_bucket_analyzed` — `analyzed` (差分抽出の高速化)

### 4.2 audit_logs テーブル

| カラム名 | 型 | 説明 |
|---|---|---|
| `id` | INTEGER (PK) | 自動採番 |
| `timestamp` | TIMESTAMP | イベント発生時刻 |
| `user` | TEXT | 操作ユーザー |
| `action` | TEXT | 操作内容 |
| `resource` | TEXT | 対象リソース |
| `result` | TEXT | 操作結果 (Success/Fail) |
| `source_ip` | TEXT | 操作元IP |
| `raw_data` | TEXT | 生データ (JSON文字列) |
| `created_at` | TIMESTAMP | レコード作成日時 |
| `analyzed` | BOOLEAN | 分析済みフラグ |

**インデックス:**
- `idx_audit_time` — `timestamp`
- `idx_audit_user` — `user`
- `idx_audit_action` — `action`
- `idx_audit_analyzed` — `analyzed`

### 4.3 processed_files テーブル

| カラム名 | 型 | 説明 |
|---|---|---|
| `file_name` | TEXT (PK) | 処理済みファイル名（S3キーまたはローカルパス） |
| `processed_at` | TIMESTAMP | 処理日時 |

---

## 5. 監視ルール定義

### 5.1 セキュリティ監視 (SEC)

| ID | ルール名 | Zabbixキー | データソース | 検知ロジック |
|---|---|---|---|---|
| SEC-01 | 未認証アクセス検知 | `wasabi.sec.unauth_access.count` | bucket_logs | `requester = '-'` のログ件数 |
| SEC-02 | 403エラー急増 | `wasabi.sec.403_error.count` | bucket_logs | `http_status = 403` の件数 |
| SEC-03 | 未知IPからのアクセス | `wasabi.sec.unknown_ip.count` | bucket_logs | IPホワイトリスト外からのアクセス件数 |
| SEC-04 | 大量データダウンロード | `wasabi.sec.data_exfil.bytes` | bucket_logs | `REST.GET.OBJECT` の `bytes_sent` 合計 |
| SEC-05 | 不審なUserAgent | `wasabi.sec.suspicious_ua.count` | bucket_logs | UAブラックリストにマッチする件数 |
| SEC-06 | 大量DELETE操作 | `wasabi.sec.delete_ops.count` | bucket_logs | `REST.DELETE.OBJECT` の件数 |
| SEC-07 | 業務時間外アクセス | `wasabi.sec.off_hours.count` | bucket_logs | 設定された業務時間帯外のアクセス件数 |
| SEC-10 | 弱いTLS使用 | `wasabi.sec.weak_tls.count` | bucket_logs | 許可TLSバージョン以外の件数 |
| SEC-08 | 管理操作の認証失敗 | `wasabi.sec.admin_fail.count` | audit_logs | `result LIKE '%fail%'` の件数 |
| SEC-09 | rootアカウント使用 | `wasabi.sec.root_usage.count` | audit_logs | `user = 'root'` の件数 |

### 5.2 アップロード監視 (UPL)

| ID | ルール名 | Zabbixキー | 検知ロジック |
|---|---|---|---|
| UPL-01 | 定期アップロード完了確認 | `wasabi.upl.scheduled.status` | 過去24時間のPUT成功ログとスケジュールパターンの照合 (1=正常, 0=異常) |
| UPL-02 | アップロードサイズ | `wasabi.upl.upload.bytes` | `REST.PUT.OBJECT` 成功の `object_size` 合計 |
| UPL-03 | アップロード失敗 | `wasabi.upl.upload_failure.count` | `REST.PUT.OBJECT` で `http_status != 200` の件数 |
| UPL-04 | 未知IPからのアップロード | `wasabi.upl.unknown_ip.count` | バックアップサーバーIP以外からのPUT操作数 |
| UPL-05 | マルチパート未完了 | `wasabi.upl.multipart_uncompleted.count` | `POST.UPLOADS` - `POST.UPLOAD` の差分 |
| UPL-06 | アップロード件数 | `wasabi.upl.daily_upload.count` | `REST.PUT.OBJECT` 成功件数 |

### 5.3 外部公開監視 (PUB)

| ID | ルール名 | Zabbixキー | 検知ロジック |
|---|---|---|---|
| PUB-01 | 匿名GETアクセス | `wasabi.pub.anon_get.count` | 匿名ユーザーによるGETオブジェクト成功件数 |
| PUB-02 | バケットポリシー変更 | `wasabi.pub.policy_change.count` | 監査ログ中の `bucketpolicy` 関連操作件数 |
| PUB-03 | ACL変更検知 | `wasabi.pub.acl_change.count` | `PUT.OBJECT_ACL` / `PUT.BUCKET_ACL` 件数 |
| PUB-04 | パブリックアクセス設定変更 | `wasabi.pub.public_config_change.count` | 監査ログ中の `publicaccess` 関連操作件数 |
| PUB-05 | 外部リファラー | `wasabi.pub.external_referer.count` | 許可ドメイン以外からのReferer件数 |
| PUB-06 | 匿名バケットリスト | `wasabi.pub.anon_list.count` | 匿名ユーザーによるGET BUCKET成功件数 |
| PUB-07 | ブラウザ直接アクセス | `wasabi.pub.browser_access.count` | ブラウザ系UAでのGETオブジェクト件数 |

### 5.4 運用監視 (OPS)

| ID | ルール名 | Zabbixキー | 検知ロジック |
|---|---|---|---|
| OPS-01 | ログ配送遅延 | `wasabi.ops.log_delay.seconds` | DB上の最新ログ時刻と現在時刻の差分（秒） |
| OPS-02 | APIスロットリング | `wasabi.ops.throttle.count` | `http_status IN (429, 503)` の件数 |
| OPS-03 | レプリケーション正常性 | `wasabi.ops.replication.status` | POCでは常に1（正常） |
| OPS-04 | ストレージ使用量急増 | `wasabi.ops.storage_increase.bytes` | 処理バッチ内のPUT成功の `object_size` 合計 |

---

## 6. 設定ファイル仕様 (config.yaml)

### 6.1 セクション一覧

| セクション | 説明 |
|---|---|
| `wasabi` | S3接続情報（エンドポイント、リージョン、認証キー、ログバケット名） |
| `audit_log` | 監査ログ取得元 (`bucket` or `local`)、パス設定 |
| `database` | DB種別 (`sqlite`/`postgresql`)、接続情報 |
| `zabbix` | Zabbixサーバー接続情報、`zabbix_sender` バイナリパス |
| `scheduler` | ログ収集間隔・分析間隔（秒） |
| `monitoring.security` | セキュリティルールの閾値、業務時間帯、許可TLSバージョン |
| `monitoring.upload` | バックアップスケジュール定義、サイズ偏差許容%、マルチパートタイムアウト |
| `monitoring.public_access` | 許可リファラードメインリスト |
| `monitoring.ops` | ログ遅延閾値、ストレージ増分閾値 |
| `ip_whitelist` | 正規アクセス元IP (CIDRサポート)、バックアップサーバーIP |
| `ua_blacklist` | 不審UserAgentのパターンリスト |
| `logging` | ログレベル、ファイルパス、ローテーション設定 |

### 6.2 環境変数展開

POC段階では未実装。本番では `${WASABI_ACCESS_KEY}` 等の環境変数を展開する機構が必要。

---

## 7. 外部インターフェース

### 7.1 Wasabi S3 API

- **プロトコル:** HTTPS (boto3)
- **エンドポイント:** `https://s3.ap-northeast-1.wasabisys.com`
- **認証:** Access Key / Secret Key
- **使用API:** `ListObjectsV2`, `GetObject`

### 7.2 Zabbix連携

- **プロトコル:** Zabbix Sender Protocol (TCP)
- **送信形式:** 標準入力パイプ (`zabbix_sender -i -`)
- **データ形式:** `"<hostname>" "<key>" "<value>"` (1行1メトリクス)
- **送信タイミング:** 各分析サイクル完了時

---

## 8. 重要な設計判断

### 8.1 差分フラグ vs 時間窓

**判断:** `analyzed` フラグ方式を採用  
**理由:** 時間窓方式では、大容量ファイルの長時間アップロードやログ配送遅延によりデータの取りこぼしが発生するリスクがあった。フラグ方式はログの到着時刻に依存せず、DBに挿入されたすべてのログを確実に1回だけ処理する。

### 8.2 SQLite vs PostgreSQL

**判断:** POC段階ではSQLiteを使用  
**理由:** デプロイの簡易性と開発速度を優先。本番環境では同時書き込み耐性や運用管理の観点からPostgreSQLへの切り替えを推奨する。

### 8.3 request_id によるべき等性

**判断:** `bucket_logs.request_id` にUNIQUE制約を設定  
**理由:** 同一ログファイルの再取り込み時にデータが二重登録されることを防止する。`IntegrityError` は黙殺し処理を続行する。

### 8.4 処理済みファイル管理

**判断:** `processed_files` テーブルで管理  
**理由:** S3上のログファイルを2回取得・パースする無駄を防止する。一度処理が完了したファイルは以降のサイクルでスキップされる。

---

## 9. 今後の拡張ポイント

| 項目 | 優先度 | 概要 |
|---|---|---|
| PostgreSQL対応 | 高 | `db_manager.py` のバックエンド切り替え |
| 環境変数展開 | 高 | `config.yaml` 内の `${VAR}` を自動展開 |
| ログローテーション | 中 | `RotatingFileHandler` への切り替え |
| アラート閾値の動的判定 | 中 | 過去の統計値に基づく異常検知 |
| 複数バケット対応 | 中 | 設定ファイルにバケットリストを定義 |
| Webhook通知 | 低 | Slack/Teams等への直接通知 |
| WebダッシュボードUI | 低 | Flaskベースのステータス確認画面 |
