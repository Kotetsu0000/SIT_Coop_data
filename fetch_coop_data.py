"""芝浦工業大学生協の営業時間PDFを取得し、JSONデータに変換するスクリプト

使い方:
    python fetch_coop_data.py          # 生協サイトから新しいPDFを取得した上で全データを再生成
    python fetch_coop_data.py --local  # ダウンロードせず、pdf/ 内のPDFから全データを再生成

抽出方式:
    pdfplumberのテーブル抽出でセル単位に値を取得する。
    結合セル(pdfplumberではNone)は「左隣 → 上の行」の順に値を継承して解決する。
    注釈テキストや空セルなど解決できないセルは overrides.json の定義で補完し、
    それでも解決できない日付は errors/YYYY_MM_DD.json に保存して出力から除外する。
"""
import argparse
import json
import os
import pathlib
import re
import unicodedata
from datetime import datetime

import pdfplumber
import requests
from bs4 import BeautifulSoup

try:
    from discord_webhook import DiscordWebhook
except ImportError:
    DiscordWebhook = None

COOP_URL = 'https://www.univcoop.jp/sit/time/'
PDF_DIR = pathlib.Path('pdf')
DATA_DIR = pathlib.Path('data')
ERROR_DIR = pathlib.Path('errors')
OVERRIDE_FILE = pathlib.Path('overrides.json')
# 生協サイトに現在掲載されているPDFの一覧。coop_data.json(公開ページが参照)は
# このPDFの月のデータだけで構成する(容量を抑えるため全期間は含めない)。
# --local 実行時の再現性のためにファイルとして永続化する。
CURRENT_PDFS_FILE = pathlib.Path('current_pdfs.json')

# 公開データのカラム(この順でPDFテーブルの列と対応する)
TIME_COLUMNS = [
    'shop_self',           # ショップ セルフ
    'shop_counter',        # ショップ カウンター
    'cafeteria',           # カフェテリア(豊洲)
    'coop_plaza_self',     # コーププラザ セルフ
    'coop_plaza_counter',  # コーププラザ カウンター
    'dining_hall',         # 食堂(大宮カフェテリア)
    'shibaura_bakery',     # 芝浦ベーカリー 大学会館1階
    'office',              # 事務室
    'realtor',             # お部屋探し
]

WEEK_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
JAP2ENG = {
    '月': 'Monday', '火': 'Tuesday', '水': 'Wednesday', '木': 'Thursday',
    '金': 'Friday', '土': 'Saturday', '日': 'Sunday',
}

DATE_CELL_RE = re.compile(r'(1[0-2]|[1-9])月\s*(\d{1,2})日\s*\(([日月火水木金土])\)')
TIME_RE = re.compile(r'\d{1,2}:\d{2}-\d{1,2}:\d{2}')
# PDF中に現れるダッシュ・チルダの異体字(時間の区切りとして正規化する)
DASH_VARIANTS = ('−', '‐', '‑', '‒', '–', '—', '―', '~', '〜')


class DummyDiscordWebhook:
    def send(self, text: str):
        print(text)


def get_bot():
    url = os.environ.get('WEBHOOK_URL')
    if url and DiscordWebhook is not None:
        return DiscordWebhook(webhook_url=url)
    print('WEBHOOK_URL is not defined. Using stdout.')
    return DummyDiscordWebhook()


def extract_year_month(file_name: str) -> tuple:
    """ファイル名から (年, 月) を抽出する。該当しなければ (0, 0)。"""
    match = re.search(r'(\d{4})_(\d{1,2})月', file_name)
    if match:
        return int(match.group(1)), int(match.group(2))
    return 0, 0


def extract_version(file_name: str) -> int:
    """ファイル名からバージョン番号を抽出する。「Ver」なしは0。"""
    match = re.search(r'Ver(\d+)', file_name)
    return int(match.group(1)) if match else 0


def norm_cell(cell):
    """セル文字列を正規化する。None(結合セル継続)はNoneのまま返す。"""
    if cell is None:
        return None
    text = unicodedata.normalize('NFKC', cell).replace('\n', '').replace(' ', '')
    for dash in DASH_VARIANTS:
        text = text.replace(dash, '-')
    return text.replace('::', ':')


def parse_time_cell(text):
    """正規化済みセル文字列を時間値に変換する。解釈できなければNone。"""
    if text is None:
        return None
    times = TIME_RE.findall(text)
    if len(times) == 1:
        return times[0]
    if len(times) > 1:
        return '/'.join(times)
    if '休業' in text:
        return '休業'
    if '24時間' in text:
        return '24時間'
    return None


def extract_pdf(pdf_path: str) -> dict:
    """PDFのテーブルから日付ごとの営業時間を抽出する。

    Returns:
        dict: {date_key: {week_day, values(9要素・未解決はNone), raw_cells}}
    """
    year, file_month = extract_year_month(str(pdf_path))
    with pdfplumber.open(pdf_path) as pdf:
        table = pdf.pages[0].extract_tables()[0]

    # COOP-SMART(24時間営業)の列はヘッダから位置を特定して除外する
    # (公開スキーマは従来の9店舗。スキーマ拡張する場合はここを変更)
    smart_col = None
    for row in table[:6]:
        for i, cell in enumerate(row):
            if cell and 'COOP-SMART' in cell.replace('\n', ''):
                smart_col = i

    result = {}
    prev_values = None  # 直前の日付行の解決済み値(縦結合セルの継承元)
    for row in table:
        first = norm_cell(row[0])
        if not first:
            continue
        date_match = DATE_CELL_RE.search(first)
        if not date_match:
            continue
        month = int(date_match.group(1))
        day = int(date_match.group(2))
        week = date_match.group(3)
        # 12月のPDFに含まれる1月の日付は翌年扱い
        y = year + 1 if (file_month == 12 and month == 1) else year
        key = f'{y}_{month:02d}_{day:02d}'

        # 曜日は日付から計算する(PDFの曜日表記には誤植があるため照合のみ行う)
        week_day = WEEK_DAYS[datetime(y, month, day).weekday()]
        if JAP2ENG[week] != week_day:
            print(f'曜日表記の不一致(PDFの誤植?): {key} PDF={JAP2ENG[week]} 実際={week_day}')

        cells = list(row)
        if smart_col is not None:
            cells = cells[:smart_col] + cells[smart_col + 1:]
        body = cells[1:-1]  # 先頭・末尾の日付列を除去

        # None=結合セルの継続(値の継承可)。空文字や注釈テキストは継承不可(override対象)
        values = []
        mergeable = []
        for cell in body:
            text = norm_cell(cell)
            if text is None:
                values.append(None)
                mergeable.append(True)
            else:
                values.append(parse_time_cell(text))
                mergeable.append(False)

        # 結合セルの解決: まず左方向の充填をfixpointまで行い、その後に上の行から継承する
        changed = True
        while changed:
            changed = False
            for i in range(len(values)):
                if values[i] is None and mergeable[i] and i > 0 and values[i - 1] is not None:
                    values[i] = values[i - 1]
                    changed = True
        for i in range(len(values)):
            if values[i] is None and mergeable[i] and prev_values is not None and prev_values[i] is not None:
                values[i] = prev_values[i]

        result[key] = {
            'week_day': week_day,
            'values': values,
            'raw_cells': [norm_cell(c) for c in body],
            'ncols': len(body),
        }
        prev_values = values
    return result


def load_overrides() -> dict:
    if OVERRIDE_FILE.exists():
        with open(OVERRIDE_FILE, encoding='UTF-8') as f:
            return json.load(f)
    return {}


def apply_override(values: list, override: dict) -> list:
    """抽出が不完全な日付にoverrideを適用する。

    actionの種類:
        close_all: 9項目すべて休業
        set:       values(9要素リスト)をそのまま採用
        cells:     未解決(None)のカラムのみ指定値で補完(抽出済みの値は上書きしない)
    """
    action = override.get('action')
    if action == 'close_all':
        return ['休業'] * len(TIME_COLUMNS)
    if action == 'set':
        return list(override['values'])
    if action == 'cells':
        filled = list(values)
        for column, value in override['cells'].items():
            i = TIME_COLUMNS.index(column)
            if filled[i] is None:
                filled[i] = value
        return filled
    raise ValueError(f'Unknown override action: {action}')


def save_json(data: dict, path) -> None:
    with open(path, 'w', encoding='UTF-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def download_coop_pdfs() -> None:
    """生協サイトに掲載されているPDFのうち未取得のものを保存し、
    現在掲載中のPDF一覧を current_pdfs.json に記録する。"""
    PDF_DIR.mkdir(exist_ok=True)
    response = requests.get(COOP_URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    current = []
    for link in soup.find_all('a', href=True):
        if not link['href'].endswith('.pdf'):
            continue
        pdf_url = link['href']
        pdf_path = PDF_DIR / pdf_url.split('/')[-1]
        if extract_year_month(pdf_path.name) == (0, 0):
            print(f'Skip (no year/month in name): {pdf_url}')
            continue
        if not pdf_path.exists():
            print(f'Download: {pdf_url}')
            pdf_response = requests.get(pdf_url)
            with open(pdf_path, 'wb') as f:
                f.write(pdf_response.content)
        current.append(pdf_path.name)
    if current:
        save_json(sorted(set(current)), CURRENT_PDFS_FILE)
    else:
        # サイト側の一時的な問題で一覧が空の場合は既存の一覧を維持する
        print('掲載中のPDFが見つかりません。current_pdfs.json は更新しません。')


def load_current_months() -> set:
    """current_pdfs.json から、coop_data.json に含める月の集合を返す。"""
    if not CURRENT_PDFS_FILE.exists():
        raise FileNotFoundError(
            f'{CURRENT_PDFS_FILE} がありません。--local の前に一度通常実行するか、'
            'リポジトリのファイルを取得してください。'
        )
    with open(CURRENT_PDFS_FILE, encoding='UTF-8') as f:
        names = json.load(f)
    return {extract_year_month(name) for name in names} - {(0, 0)}


def process_all() -> list:
    """pdf/ 内の全PDFからデータを再生成する。

    同月に複数バージョンがある場合は最新バージョンのみを採用する。
    抽出が解決できなかった日付は errors/YYYY_MM_DD.json に保存し、出力から除外する。
    coop_data.json には current_pdfs.json に掲載中の月のデータのみを含める。

    Returns:
        list: 未解決の日付情報(エラーアーティファクトと同形式)のリスト
    """
    DATA_DIR.mkdir(exist_ok=True)
    ERROR_DIR.mkdir(exist_ok=True)
    overrides = load_overrides()
    current_months = load_current_months()

    # 月ごとに最新バージョンのPDFを選ぶ
    latest_by_month = {}
    for name in os.listdir(PDF_DIR):
        if not name.endswith('.pdf'):
            continue
        ym = extract_year_month(name)
        if ym == (0, 0):
            continue
        if ym not in latest_by_month or extract_version(name) > extract_version(latest_by_month[ym]):
            latest_by_month[ym] = name

    coop_data = {}
    unresolved = []
    for (year, month), name in sorted(latest_by_month.items()):
        pdf_path = PDF_DIR / name
        extracted = extract_pdf(str(pdf_path))
        month_data = {}
        for key, info in sorted(extracted.items()):
            values = info['values']
            if None in values and key in overrides:
                values = apply_override(values, overrides[key])
            if len(values) != len(TIME_COLUMNS) or None in values:
                unresolved.append({
                    'date': key,
                    'week_day': info['week_day'],
                    'pdf': str(pdf_path),
                    'raw_cells': info['raw_cells'],
                    'extracted_values': info['values'],
                    'columns': TIME_COLUMNS,
                })
                continue
            month_data[key] = {'week_day': info['week_day']}
            month_data[key].update(zip(TIME_COLUMNS, values))
        save_json(month_data, DATA_DIR / f'{year}_{month}.json')
        if (year, month) in current_months:
            coop_data.update(month_data)

    save_json(dict(sorted(coop_data.items())), DATA_DIR / 'coop_data.json')
    return unresolved


def write_error_artifacts(unresolved: list, bot) -> None:
    """未解決日付のアーティファクトを errors/ に保存し、解消済みのものを削除する。"""
    current = {f'{info["date"]}.json' for info in unresolved}
    for path in ERROR_DIR.glob('*.json'):
        if path.name not in current and path.name != 'validation_report.json':
            path.unlink()
    for info in unresolved:
        save_json(info, ERROR_DIR / f'{info["date"]}.json')
        missing = [
            TIME_COLUMNS[i]
            for i, v in enumerate(info['extracted_values'])
            if v is None
        ]
        bot.send(
            f'抽出失敗: {info["date"]} ({info["week_day"]})\n'
            f'PDF: {info["pdf"]}\n'
            f'未解決カラム: {missing}\n'
            f'セル内容: {info["raw_cells"]}'
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--local', action='store_true',
        help='PDFをダウンロードせず、pdf/ 内のファイルからデータを再生成する',
    )
    args = parser.parse_args()

    bot = get_bot()
    if not args.local:
        download_coop_pdfs()
    unresolved = process_all()
    write_error_artifacts(unresolved, bot)
    if unresolved:
        dates = [info['date'] for info in unresolved]
        print(f'未解決の日付があります(overrides.jsonで補完してください): {dates}')
    else:
        print('全日付の抽出に成功しました。')


if __name__ == '__main__':
    main()
