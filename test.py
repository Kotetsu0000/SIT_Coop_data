"""データの完全性チェック

ハードコードされた日付リストを使わず、生成済みデータだけを検証する。

検証項目:
    1. 月次完全性: 月次ファイル(data/YYYY_M.json)が存在する月の全日付が、
       いずれかの月次ファイルに存在すること(月境界の日付は隣月のPDFが
       カバーすることがあるため、全月次ファイルの結合に対して検証する)。
       どのPDFにも掲載されない日付(年末年始など)は known_gaps.json に
       理由付きで記録することで許容される。
    2. スキーマ: 全エントリが10カラムを過不足なく持ち、値が正規の形式であること
    3. 曜日整合: week_day が日付から計算した実際の曜日と一致すること
    4. 結合整合: 月次ファイルの全日付が coop_data.json に存在し、
       coop_data.json に月次ファイル由来でない日付が無いこと
    5. 抽出エラーの不在: errors/ に未解決の抽出エラー(YYYY_MM_DD.json)が
       残っていないこと(隣月PDFのスピルオーバーで日付がカバーされていても、
       抽出失敗は修正されるべきものとして検出する)

失敗時は全違反を列挙して errors/validation_report.json に書き出し、exit code 1 で終了する。
成功時は validation_report.json を削除して exit code 0 で終了する。

使い方:
    python test.py
"""
import calendar
import json
import pathlib
import re
import sys
from datetime import datetime

DATA_DIR = pathlib.Path('data')
ERROR_DIR = pathlib.Path('errors')
REPORT_FILE = ERROR_DIR / 'validation_report.json'
KNOWN_GAPS_FILE = pathlib.Path('known_gaps.json')

COLUMNS = [
    'week_day', 'shop_self', 'shop_counter', 'cafeteria', 'coop_plaza_self',
    'coop_plaza_counter', 'dining_hall', 'shibaura_bakery', 'office', 'realtor',
]
WEEK_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
TIME_RANGE = r'\d{1,2}:\d{2}-\d{1,2}:\d{2}'
VALUE_RE = re.compile(rf'^(休業|不明|24時間|{TIME_RANGE}(/{TIME_RANGE})*)$')
DATE_KEY_RE = re.compile(r'^\d{4}_\d{2}_\d{2}$')
MONTH_FILE_RE = re.compile(r'^(\d{4})_(\d{1,2})\.json$')


def load_json(path):
    with open(path, encoding='UTF-8') as f:
        return json.load(f)


def check_entry(file_name: str, key: str, entry: dict, report: dict) -> None:
    """1日付分のエントリのスキーマと曜日整合を検証する。"""
    if not DATE_KEY_RE.match(key):
        report['schema_violations'].append({
            'file': file_name, 'date': key, 'problem': '日付キーの形式が不正',
        })
        return
    if not isinstance(entry, dict) or sorted(entry.keys()) != sorted(COLUMNS):
        report['schema_violations'].append({
            'file': file_name, 'date': key,
            'problem': f'カラム不一致: {sorted(entry.keys()) if isinstance(entry, dict) else type(entry).__name__}',
        })
        return
    actual_week = WEEK_DAYS[datetime.strptime(key, '%Y_%m_%d').weekday()]
    if entry['week_day'] != actual_week:
        report['schema_violations'].append({
            'file': file_name, 'date': key,
            'problem': f'曜日不一致: 記載={entry["week_day"]}, 実際={actual_week}',
        })
    for column in COLUMNS[1:]:
        if not VALUE_RE.match(entry[column]):
            report['schema_violations'].append({
                'file': file_name, 'date': key,
                'problem': f'値の形式が不正: {column}={entry[column]!r}',
            })


def main() -> int:
    report = {
        'missing_dates': [],
        'schema_violations': [],
        'consistency_errors': [],
        'extraction_errors': [],
    }

    # fetch_coop_data.py が残した未解決の抽出エラー
    for path in sorted(ERROR_DIR.glob('*.json')):
        if path == REPORT_FILE:
            continue
        artifact = load_json(path)
        report['extraction_errors'].append({
            'date': artifact.get('date', path.stem),
            'file': str(path),
            'pdf': artifact.get('pdf'),
        })

    month_files = sorted(
        (p for p in DATA_DIR.glob('*.json') if MONTH_FILE_RE.match(p.name)),
        key=lambda p: tuple(map(int, MONTH_FILE_RE.match(p.name).groups())),
    )
    if not month_files:
        report['consistency_errors'].append({'problem': f'{DATA_DIR}/ に月次ファイルがありません'})

    known_gaps = load_json(KNOWN_GAPS_FILE) if KNOWN_GAPS_FILE.exists() else {}

    monthly_data = {path: load_json(path) for path in month_files}
    all_monthly_keys = set()
    for data in monthly_data.values():
        all_monthly_keys.update(data.keys())

    for path, data in monthly_data.items():
        year, month = map(int, MONTH_FILE_RE.match(path.name).groups())

        # 月次完全性: ファイル名の月の全日付が結合データのどこかに存在すること
        days_in_month = calendar.monthrange(year, month)[1]
        for day in range(1, days_in_month + 1):
            key = f'{year}_{month:02d}_{day:02d}'
            if key not in all_monthly_keys and key not in known_gaps:
                report['missing_dates'].append({'date': key, 'file': str(path)})

        # スキーマ・曜日(前後月のスピルオーバー日付も対象)
        for key, entry in data.items():
            check_entry(str(path), key, entry, report)

    # 結合データ: 月次ファイルの全日付を含み、それ以外を含まないこと
    coop_path = DATA_DIR / 'coop_data.json'
    if coop_path.exists():
        coop_data = load_json(coop_path)
        for key in sorted(all_monthly_keys - set(coop_data.keys())):
            report['consistency_errors'].append({
                'date': key, 'problem': 'coop_data.json に存在しない',
            })
        for key in sorted(set(coop_data.keys()) - all_monthly_keys):
            report['consistency_errors'].append({
                'date': key, 'problem': 'どの月次ファイルにも存在しない日付が coop_data.json にある',
            })
        for key, entry in coop_data.items():
            check_entry(str(coop_path), key, entry, report)
    else:
        report['consistency_errors'].append({'problem': f'{coop_path} がありません'})

    violations = sum(len(v) for v in report.values())
    if violations == 0:
        if REPORT_FILE.exists():
            REPORT_FILE.unlink()
        print(f'All checks passed. ({len(month_files)} files, {len(all_monthly_keys)} dates)')
        return 0

    for item in report['missing_dates']:
        print(f'欠落日付: {item["date"]} ({item["file"]})')
    for item in report['schema_violations']:
        print(f'スキーマ違反: {item.get("date", "-")} ({item["file"]}) {item["problem"]}')
    for item in report['consistency_errors']:
        print(f'整合性エラー: {item.get("date", "-")} {item["problem"]}')
    for item in report['extraction_errors']:
        print(f'抽出エラー: {item["date"]} ({item["file"]}) PDF: {item["pdf"]}')
    print(f'\n{violations} violations found.')

    ERROR_DIR.mkdir(exist_ok=True)
    with open(REPORT_FILE, 'w', encoding='UTF-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=4)
    print(f'Report written to {REPORT_FILE}')
    return 1


if __name__ == '__main__':
    sys.exit(main())
