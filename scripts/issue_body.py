"""抽出エラーのIssue本文(Markdown)を生成するスクリプト

errors/ 内のアーティファクトと validation_report.json から、
自動修正フロー(Claude Code)が読み取りやすい形式でIssue本文を組み立てて標準出力に出す。
"""
import json
import pathlib

ERROR_DIR = pathlib.Path('errors')
REPORT_FILE = ERROR_DIR / 'validation_report.json'


def main():
    lines = [
        '## データ抽出エラー',
        '',
        '定期実行のデータ検証(`python test.py`)が失敗しました。',
        '以下のエラー内容を確認し、`overrides.json`(抽出できないセルの補完)または',
        '`known_gaps.json`(PDF自体に掲載がない日付)を修正してください。',
        '',
    ]

    artifacts = sorted(p for p in ERROR_DIR.glob('*.json') if p != REPORT_FILE)
    if artifacts:
        lines.append('### 未解決の抽出エラー')
        lines.append('')
        for path in artifacts:
            info = json.loads(path.read_text(encoding='UTF-8'))
            lines.append(f'#### {info["date"]} ({info.get("week_day", "?")})')
            lines.append('')
            lines.append(f'- PDF: `{info.get("pdf")}`')
            lines.append(f'- アーティファクト: `{path}`')
            lines.append('')
            lines.append('```json')
            lines.append(json.dumps(info, ensure_ascii=False, indent=2))
            lines.append('```')
            lines.append('')

    if REPORT_FILE.exists():
        report = json.loads(REPORT_FILE.read_text(encoding='UTF-8'))
        if any(report.get(k) for k in ('missing_dates', 'schema_violations', 'consistency_errors')):
            lines.append('### 検証レポート')
            lines.append('')
            lines.append('```json')
            lines.append(json.dumps(report, ensure_ascii=False, indent=2))
            lines.append('```')
            lines.append('')

    lines += [
        '### 修正手順',
        '',
        '1. 上記アーティファクトの `raw_cells` と `extracted_values` を確認する',
        '   (`null` のカラムが解決できなかったセル。`columns` が対応するカラム名)',
        '2. 必要ならPDF(リポジトリ内のパス)を直接確認する',
        '3. `overrides.json` に該当日付のエントリを追加する',
        '   - 全店休業: `{"action": "close_all", "note": "理由"}`',
        '   - 特定セルのみ補完: `{"action": "cells", "cells": {"カラム名": "値"}, "note": "理由"}`',
        '   - 値は `H:MM-H:MM` 形式・`休業`・`不明` のいずれか。判断できない場合は `不明` を使う',
        '4. PDFにそもそも日付が掲載されていない場合は `known_gaps.json` に日付と理由を追加する',
        '5. `uv run python fetch_coop_data.py --local` でデータを再生成する',
        '6. `uv run python test.py` が成功することを確認する',
    ]
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
