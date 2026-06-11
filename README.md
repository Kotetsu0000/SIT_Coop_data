# SIT_Coop_data

芝浦工業大学生協の営業時間を確認できるページ:
<a href="https://kotetsu0000.github.io/SIT_Coop_data/" target="_blank">https://kotetsu0000.github.io/SIT_Coop_data/</a>

生協公式サイトの営業案内PDFを定期取得し、JSONデータに変換してGitHub Pagesで公開しています。

## システム構成

```
生協サイトのPDF
   │  (1日2回 GitHub Actions: fetch_coop_data.yml)
   ▼
fetch_coop_data.py ── pdfplumberのテーブル抽出 + overrides.json による補完
   │
   ├─ 成功 → data/YYYY_M.json, data/coop_data.json を更新してコミット
   │          (coop_data.json を docs/ のページが参照)
   │
   └─ 失敗 → errors/YYYY_MM_DD.json を保存してコミット
               │
               ▼
        test.py が検証失敗 → Issue自動作成(ラベル: extraction-error)
               │
               ▼
        claude_auto_fix.yml ── Claude Code (Sonnet) が overrides.json を修正
               │
               ▼
        Pull Request 自動作成 → CI(test.yml)通過を確認して人間がマージ → 解消
```

### ファイル構成

| パス | 役割 |
|---|---|
| `fetch_coop_data.py` | PDF取得・テーブル抽出・JSON生成 |
| `test.py` | データの完全性チェック(月次全日付・スキーマ・曜日・整合性) |
| `overrides.json` | 抽出できないセルの補完定義(日付単位) |
| `known_gaps.json` | PDF自体に掲載がない日付の記録(年末年始など) |
| `data/YYYY_M.json` | 月ごとの営業時間データ |
| `data/coop_data.json` | 全期間の結合データ(公開ページが参照) |
| `errors/` | 未解決の抽出エラーのアーティファクト |
| `pdf/` | 取得したPDFのアーカイブ |
| `docs/` | GitHub Pages(公開ページ) |

## データ抽出の仕組み

PDFの営業時間表を `pdfplumber` でテーブルとして抽出し、セル単位で値を取得します。

- 結合セル(連続する休業など)は「左隣 → 上の行」の順で値を継承して解決
- `week_day` はPDFの曜日表記ではなく日付から計算(PDF側の誤植対策)
- COOP-SMART(24時間営業)の列はヘッダから検出して除外(現行スキーマは9店舗)
- 注釈テキストが書かれたセルなど解決できないものは `overrides.json` で補完

### overrides.json の書式

抽出が不完全な日付(`null` のカラムが残る日付)にのみ適用されます。
PDFの版が更新されて正常に抽出できるようになった場合は自動的に無視されるため、
古いエントリが残っていても安全です。

```json
{
    "2025_02_01": {"action": "close_all", "note": "入試期間"},
    "2024_08_03": {"action": "cells", "cells": {"coop_plaza_counter": "不明"}, "note": "オープンキャンパス営業"},
    "2099_01_01": {"action": "set", "values": ["休業", "休業", "休業", "休業", "休業", "休業", "休業", "休業", "休業"], "note": "setの例"}
}
```

- `close_all`: 9カラムすべて休業
- `cells`: 指定カラムのみ補完(抽出済みの値は上書きしない)
- `set`: 9カラムを丸ごと指定(`shop_self` 〜 `realtor` の順)
- 値は `H:MM-H:MM` 形式・`休業`・`不明` のいずれか

### known_gaps.json の書式

その月のPDFにも前後の月のPDFにも掲載されていない日付(例: 年末年始)を記録します。
ここに記録された日付は `test.py` の月次完全性チェックから除外されます。

```json
{
    "2024_12_31": "年末年始のためPDFに掲載なし"
}
```

## GitHub Actions ワークフロー

| ワークフロー | トリガー | 役割 |
|---|---|---|
| `fetch_coop_data.yml` | 毎日 5:00/17:00 UTC + 手動 | PDF取得→データ生成→検証→コミット。検証失敗時はIssue作成+自動修正を起動 |
| `claude_auto_fix.yml` | fetchからのdispatch / `extraction-error` ラベル付与 | Claude Code (Sonnet) がoverrides.jsonを修正してPR作成 |
| `test.yml` | main向けPR / developへのpush | データ再現性(`--local` 再生成で差分なし)と完全性を検証 |

運用は `main` ブランチで行われます(データのコミット・Issue作成はmainのみ)。

## セットアップ(リポジトリSecrets)

| Secret | 必須 | 説明 |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | 自動修正に必要 | ローカルで `claude setup-token` を実行して生成したトークンを登録(Claude Pro/Maxサブスクリプションで利用可能) |
| `WEBHOOK_URL` | 任意 | 抽出失敗時のDiscord通知用Webhook URL(未設定でも動作する) |

また、自動修正ワークフローには [Claude GitHub App](https://github.com/apps/claude) の
このリポジトリへのインストールが必要です(`claude` CLIの `/install-github-app` でも設定可能)。

## ローカルでの実行

[uv](https://docs.astral.sh/uv/) を使用します。

```sh
uv sync                                    # 依存関係のインストール
uv run python fetch_coop_data.py --local   # pdf/ からデータを再生成(ダウンロードなし)
uv run python fetch_coop_data.py           # PDFのダウンロードを含む実行
uv run python test.py                      # データの完全性チェック
```

抽出エラーが出た場合は `errors/YYYY_MM_DD.json` の内容を確認し、
`overrides.json` にエントリを追加 → `--local` で再生成 → `test.py` で確認、の順で修正します。
