from datetime import datetime, timedelta
import json
import os

from fetch_coop_data import text_extract

CURRENT_ERROR_DATE_LIST = [
    '2024_06_25',
    '2024_07_06',
    '2024_08_03',
    '2024_08_04',
    '2024_08_24',
    '2024_08_25',
    '2024_10_31',
    '2024_11_02',
    '2025_01_18',
    '2025_01_19',
    '2025_02_01',
    '2025_02_02',
    '2025_02_03',
    '2025_02_04',
    '2025_02_21'
]

def load_json(json_path:str) -> dict:
    with open(json_path, 'r') as f:
        return json.load(f)

def extract_error_date(date_dict:dict) -> dict:
    for key, value in date_dict.items():
        if len(value["time"]) != 9:
            if key not in CURRENT_ERROR_DATE_LIST:
                raise Exception(f'Error date: {key}')
            year, month, day = key.split('_')
            year, month, day = int(year), int(month), int(day)
    print('All date is correct.')

def extract_nonexistent_date() -> list:
    '''JSONに存在しない日付を抽出する

    期間の開始日と終了日を指定することで、その期間内に存在しない日付を抽出する
    日付のフォーマットについては、以下のように指定する
    - 2024年度6月25日 -> 2024_06_25
    '''
    coop_data = load_json('data/coop_data.json')
    # このデータの最も古い日付と新しい日付を取得する
    start_date = min(coop_data.keys())
    end_date = max(coop_data.keys())
    print(f'Start date: {start_date}, End date: {end_date}')
    check_date = datetime.strptime(start_date, '%Y_%m_%d')
    while check_date <= datetime.strptime(end_date, '%Y_%m_%d'):
        check_date_str = check_date.strftime('%Y_%m_%d')
        if check_date_str not in coop_data:
            print(f'Nonexistent date: {check_date_str}')
        check_date += timedelta(days=1)
    print('All date is checked.')

def test():
    pdf_paths = [f'pdf/{i}' for i in os.listdir('pdf') if i.endswith('.pdf')]
    for pdf_path in pdf_paths:
        print(f'PDF path: {pdf_path}')
        date_dict = text_extract(pdf_path)
        extract_error_date(date_dict)
    extract_nonexistent_date()


if __name__ == '__main__':
    test()
