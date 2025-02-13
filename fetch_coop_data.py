import json
import pathlib
import os
import re
import unicodedata

from bs4 import BeautifulSoup
from discord_webhook import DiscordWebhook
from pypdf import PdfReader
import requests

TIME_COLMUN_NAME = [
    'week_day',#'曜日',
    'shop_self',#'ショップ セルフ',
    'shop_counter',#'ショップ カウンター',
    'cafeteria',#'カフェテリア',
    'coop_plaza_self',#'コーププラザ セルフ',
    'coop_plaza_counter',#'コーププラザ カウンター',
    'dining_hall',#'食堂',
    'shibaura_bakery',#'芝浦ベーカリー 大学会館１階',
    'office',#'事務室',
    'realtor',#'お部屋探し',
]

ENG2JAP = {
    'Monday': '月',
    'Tuesday': '火',
    'Wednesday': '水',
    'Thursday': '木',
    'Friday': '金',
    'Saturday': '土',
    'Sunday': '日',
}

JAP2ENG = {
    '月': 'Monday',
    '火': 'Tuesday',
    '水': 'Wednesday',
    '木': 'Thursday',
    '金': 'Friday',
    '土': 'Saturday',
    '日': 'Sunday',
}

pattern_dict = {
    'date_text': r"(1[0-2]|[1-9])月\d{1,2}日\([日月火水木金土]\)",
    'time_text': r"(?:\d{1,2}[:]\d{2}-\d{1,2}[:]\d{2}|休業)"
}

# ファイルのソートに使用する。月のマッピング
month_mapping = {
    "1月": 1, "2月": 2, "3月": 3, "4月": 4, "5月": 5, "6月": 6,
    "7月": 7, "8月": 8, "9月": 9, "10月": 10, "11月": 11, "12月": 12
}

def extract_date(file_name:str) -> tuple:
    """ファイル名から年と月を抽出する関数

    Args:
        file_name (str): ファイル名

    Returns:
        year (int): 年
        month (int): 月
    """
    match = re.search(r'(\d{4})_(\d{1,2}月)', file_name)
    if match:
        year = int(match.group(1))
        month = month_mapping[match.group(2)]
        return year, month
    return 0, 0  # 日付がない場合のデフォルト値

def save_pdf(url:str, path:str) -> None:
    """PDFファイルを保存する関数
    
    Args:
        url (str): PDFファイルのURL
        path (str): 保存するパス
    """
    response = requests.get(url)
    with open(path, 'wb') as file:
        file.write(response.content)

def save_json(data:dict, path:str) -> None:
    """JSONファイルを保存する関数
    
    Args:
        data (dict): 保存するデータ
        path (str): 保存するパス
    """
    with open(path, 'w', encoding='UTF-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

def make_path(path:str) -> None:
    """ディレクトリの作成を行う関数
    
    Args:
        path (str): 作成するフォルダのパス
    """
    p = pathlib.Path(path)
    if not p.exists():
        p.mkdir(parents=True)

def file_exists(path:str) -> bool:
    """ファイルが存在するか確認する関数
    
    Args:
        path (str): ファイルのパス

    Returns:
        bool: ファイルが存在するかどうか
    """
    return pathlib.Path(path).exists()

def convert_to_halfwidth(text:str) -> str:
    """全角文字を半角文字に変換

    Args:
        text (str): 変換前の文字列

    Returns:
        str: 変換後の文字列
    """
    return unicodedata.normalize('NFKC', text)

def download_coopPDF() -> list:
    """芝浦工業大学の生協のPDFをダウンロードする関数
    
    Returns:
        list: 保存したPDFのパスのリスト
    """
    URL = 'https://www.univcoop.jp/sit/time/'
    PDF_FOLDER = './pdf/'

    response = requests.get(URL)
    soup = BeautifulSoup(response.text, 'html.parser')

    save_pdf_path_list = []
    for link in soup.find_all('a', href=True):
        if link['href'].endswith('.pdf'):
            print(link['href'])
            pdf_url = link['href']
            pdf_path = PDF_FOLDER + pdf_url.split('/')[-1]
            if not file_exists(pdf_path):
                save_pdf(pdf_url, pdf_path)
            save_pdf_path_list.append(pdf_path)
    save_pdf_path_list = sorted(save_pdf_path_list, key=extract_date)
    return save_pdf_path_list

def date_str_proc(date_str:str, year:str, last_month_flag:bool) -> tuple:
    """日付の文字列を整形する関数
    
    Args:
        date_str (str): 整形する日付の文字列
        year (str): 年
        last_month_flag (bool): 12月かどうか

    Returns:
        str: 整形後の日付の文字列
        str: 曜日の文字列
        bool: 12月から1月になる場合
    """
    month_day = re.findall(r'\d{1,2}', date_str)
    month = month_day[0]
    day = month_day[1]
    week = re.findall(r'\([日月火水木金土]\)', date_str)[0].replace('(', '').replace(')', '')
    if last_month_flag and int(month) == 1:# ファイルが12月のもので1月になる場合
        return f'{int(year)+1}_{int(month):02d}_{int(day):02d}', JAP2ENG[week], True
    elif int(month) == 12:# ファイルが12月のものの場合
        return f'{int(year)}_{int(month):02d}_{int(day):02d}', JAP2ENG[week], True
    else:
        return f'{int(year)}_{int(month):02d}_{int(day):02d}', JAP2ENG[week], False

def data_extract(pdf_path:str):
    DICT_FOLDER = './data/'
    save_dict = date_dict_proc(text_extract(pdf_path))

    pattern = r'\d{4}_\d{1,2}'
    dict_name = re.search(pattern, pdf_path)[0] + '.json'
    save_json(save_dict, DICT_FOLDER + dict_name)
    return save_dict

def date_dict_proc(date_dict:dict):
    return_dict = {}
    for key, value in date_dict.items():
        if len(value["time"]) != 9:
            year, month, day = key.split('_')
            year, month, day = int(year), int(month), int(day)

            if month == 1 and day > 17 and day < 20:# 共通テスト期間
                """
                対応する日付
                - 2025年1月18日
                - 2025年1月19日
                """
                date_dict[key]["time"] = ['休業' for _ in range(9)]
            elif month == 2 and day < 5:# 入試期間(前期日程)
                """
                対応する日付
                - 2025年2月1日
                - 2025年2月2日
                - 2025年2月3日
                - 2025年2月4日
                """
                date_dict[key]["time"] = ['休業' for _ in range(9)]
            elif month == 2 and day > 20:# 入試期間(後期日程)
                """
                対応する日付
                - 2025年2月21日
                """
                date_dict[key]["time"] = ['休業' for _ in range(9)]
            elif month == 6:# 学生大会?
                """
                対応する日付
                - 2024年6月25日
                """
                date_dict[key]["time"] = ['休業' for _ in range(9)]
            elif month == 7 and day == 6:# 体験授業特別営業?
                """
                対応する日付
                - 2024年7月6日
                """
                date_dict[key]["time"].insert(1, '休業')# 6月PDF参照
            elif (month == 7 and day > 20) or (month == 8 and day < 15):#大宮オープンキャンパス?
                """
                対応する日付
                - 2024年8月3日
                - 2024年8月4日
                """
                date_dict[key]["time"].insert(4, '不明')
            elif month == 8 and day > 15: # 豊洲オープンキャンパス?
                """
                対応する日付
                - 2024年8月24日
                - 2024年8月25日
                """
                date_dict[key]["time"].insert(1, '不明')
            elif (month == 10 and day > 30) or (month==11 and day < 7): # 芝浦祭期間?
                """
                対応する日付
                - 2024年10月31日
                - 2024年11月2日
                """
                date_dict[key]["time"] = ['休業' for _ in range(9)]

        if len(value["time"]) == 9:# 修正できたもの
            return_dict[key] = {}
            for colmun in TIME_COLMUN_NAME:
                if colmun == 'week_day':
                    return_dict[key][colmun] = date_dict[key][colmun]
                else:
                    return_dict[key][colmun] = date_dict[key]["time"].pop(0)
        else:
            print(f'{year}年{month}月{day}日')
            print(key, value["time"], len(value["time"]))
            print(f'-> {value["text"]}')
            send_text = f'{year}年{month}月{day}日\n{key} {value["week_day"]}\n{value["text"]}\n{value["time"]}'
            bot.send(send_text)
        
    return return_dict

def text_extract(pdf_path:str) -> dict:
    reader = PdfReader(pdf_path)
    pages = reader.pages[0]
    year = pdf_path.split('/')[-1].split('_')[0]

    text = pages.extract_text().replace('\n', '').replace(' ', '')
    text = convert_to_halfwidth(text)

    finditer = list(re.finditer(pattern_dict['date_text'], text))

    current_date = ''
    date_num = 0
    text_dict = {}
    last_month_flag = False
    for i in finditer:
        group_text = i.group()
        if current_date != group_text:#一つ目の日付
            current_date = group_text#日付を更新
            date_num += 1 #日付の数をカウント
            text_start = i.end()#日付の間のテキストの開始位置
            continue
        else:
            text_end = i.start()#日付の間のテキストの終了位置
            key, week, last_month_flag = date_str_proc(group_text, year, last_month_flag)

            aa = re.findall(pattern_dict['time_text'], text[text_start:text_end])
            text_dict[key] = {}
            text_dict[key]['week_day'] = week
            text_dict[key]['text'] = text[text_start:text_end]
            text_dict[key]['time'] = aa
    return text_dict

def check_all_data():
    pdf_paths = [f'pdf/{i}' for i in os.listdir('pdf') if i.endswith('.pdf')]
    for pdf_path in pdf_paths:
        data_extract(pdf_path)

if __name__ == '__main__':
    try:
        WEBHOOK_URL = os.environ['WEBHOOK_URL']
        bot = DiscordWebhook(webhook_url=WEBHOOK_URL)
    except:
        print('WEBHOOK_URL is not defined.')
    all_data = {}
    for pdf_path in download_coopPDF():
        all_data.update(data_extract(pdf_path))
    all_data = dict(sorted(all_data.items()))
    save_json(all_data, './data/coop_data.json')
    