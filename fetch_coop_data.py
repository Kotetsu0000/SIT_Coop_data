import json
import pathlib
import re
import unicodedata

from bs4 import BeautifulSoup
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
    'date_text': r"\d{1,2}月\d{1,2}日\([日月火水木金土]\)",
    'time_text': r"(?:\d{1,2}[:]\d{2}-\d{1,2}[:]\d{2}|休業)"
}

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
    return save_pdf_path_list

def date_str_proc(date_str:str) -> str:
    """日付の文字列を整形する関数
    
    Args:
        date_str (str): 整形する日付の文字列

    Returns:
        str: 整形後の日付の文字列
    """
    month_day = re.findall(r'\d{1,2}', date_str)
    month = month_day[0]
    day = month_day[1]
    week = re.findall(r'\([日月火水木金土]\)', date_str)[0].replace('(', '').replace(')', '')
    return f'{int(month):02d}_{int(day):02d}', JAP2ENG[week]

def data_extract(pdf_path:str):
    DICT_FOLDER = './data/'
    reader = PdfReader(pdf_path)
    pages = reader.pages[0]
    current_date = None
    day_info = {}
    year = pdf_path.split('/')[-1].split('_')[0]

    for i in pages.extract_text().split('\n'):
        text = convert_to_halfwidth(i).replace(' ', '')
        date_text = re.findall(pattern_dict['date_text'], text)
        if len(date_text) == 2:# 通常の場合
            proc_date = date_str_proc(date_text[0])
            current_date = year + '_' + proc_date[0]
            day_info[current_date] = [proc_date[1]]
            time_list = re.findall(pattern_dict['time_text'], text)
            if len(time_list) == 1:# 学生大会の日対応
                day_info[current_date] += ['休業' for _ in range(9)]
            else:
                day_info[current_date] += re.findall(pattern_dict['time_text'], text)
            current_date = None
        if len(date_text) == 4:
            time_list = re.findall(pattern_dict['time_text'], text)

            proc_date = date_str_proc(date_text[0])
            current_date = year + '_' + proc_date[0]
            day_info_list = [proc_date[1]]# Weekday
            day_info[current_date] = day_info_list + time_list[:9]

            proc_date = date_str_proc(date_text[2])
            current_date = year + '_' + proc_date[0]
            day_info_list = [proc_date[1]]# Weekday
            day_info[current_date] = day_info_list + time_list[9:]            
        else:#特殊状態
            if current_date is None:
                if len(date_text) == 1:# 日付(最初)
                    proc_date = date_str_proc(date_text[0])
                    current_date = year + '_' + proc_date[0]
                    day_info_list = [proc_date[1]]
                    day_info_list += re.findall(pattern_dict['time_text'], text)
                else:
                    Exception("Error")
            else:
                if len(date_text) == 0:# 日付の途中
                    day_info_list += re.findall(pattern_dict['time_text'], text)
                elif len(date_text) == 1 and current_date == date_text[0]:# 日付の最後
                    day_info_list += re.findall(pattern_dict['time_text'], text)
                    day_info[current_date] = day_info_list
                    current_date = None
                    del day_info_list
                else:
                    Exception("Error")

    save_dict = {}
    for key, value in day_info.items():
        day_dict = {}
        for column_name, time in zip(TIME_COLMUN_NAME, value):
            day_dict[column_name] = time
        save_dict[key] = day_dict

    pattern = r'\d{4}_\d{1,2}'
    dict_name = re.search(pattern, pdf_path)[0] + '.json'
    save_json(save_dict, DICT_FOLDER + dict_name)
    return save_dict

if __name__ == '__main__':
    all_data = {}
    for pdf_path in download_coopPDF():
        all_data.update(data_extract(pdf_path))
    all_data = dict(sorted(all_data.items()))
    save_json(all_data, './data/coop_data.json')