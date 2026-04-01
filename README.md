# Wasabi ログ監視システム POC

Wasabiクラウドストレージのバケットログ（アクセスログ）および監査ログ（管理操作ログ）を自動収集し、不正アクセスやデータ漏洩の兆候を検知、Zabbixへアラートメトリクスとして連携するPythonベースのアナライザ（POC版）です。

## 主な機能

1. **バケットログ収集・分析**
   - S3互換アクセスログのパース
   - 未認証アクセス、大量ダウンロード、異常なUserAgentなどの検知（SEC-*）
   - 定期アップロードの成功・失敗確認（UPL-*）
   - 意図しない外部へのオブジェクト公開の検知（PUB-*）

2. **監査ログ収集・分析**
   - 管理コンソール操作のCSVログのパース
   - バケットポリシー・パブリックアクセス設定の変更検知
   - 管理ユーザーの認証失敗やrootユーザーによる操作検知

3. **Zabbix 連携**
   - 抽出した各種メトリクス・障害カウントを `zabbix_sender` コマンドを通じてZabbix Serverのトラッパーアイテムへ送信

## ディレクトリ構成

- `main.py`: スケジューラとメインプロセス
- `config.yaml`: 監視設定・システム設定
- `collectors/`: Wasabiバケットからのログ収集・ファイル読み取り
- `parsers/`: ログ形式別のパースロジック
- `storage/`: SQLite DBの管理クラス
- `analyzers/`: カテゴリ別のセキュリティ分析ルール判定
- `alerting/`: Zabbix送信モジュール
- `tools/`: テスト・動作確認用ツール（ダミーデータ生成など）

## セットアップ手順

1. Python 3.9以上を用意
2. 依存パッケージのインストール:
   ```bash
   pip3 install -r requirements.txt
   ```
3. 環境変数の設定（必要に応じてconfig.yamlを直書きに変更）:
   - `WASABI_ACCESS_KEY`
   - `WASABI_SECRET_KEY`
4. `config.yaml` 内のIPホワイトリストやZabbix情報の書き換え
5. Zabbixに同名のトラッパーアイテムを作成する

## 実行

```bash
python3 main.py
```
起動時の1回実行後、設定間隔（デフォルト300秒）で自動的に監視ループに入ります。

## POC動作確認方法

AWS認証情報が無くてもロジックを確認できるよう、ダミーログジェネレータを用意しています。

```bash
# 1. データベースを初期化（テスト実行モード）
python3 tools/test_run.py

# 2. 不正アクセスのダミーログをDBに挿入
python3 tools/generate_dummy_logs.py

# 3. 再度実行し、Zabbixに飛ぶべきメトリクスがログに出力されるのを確認
python3 tools/test_run.py
```
