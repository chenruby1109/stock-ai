import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# 設定頁面標題
st.set_page_config(page_title="Miniko AI 戰情室", page_icon="📈", layout="wide")
st.title("📈 Miniko AI 全台股獵手 (V44.0 多源聚合渦輪版)")

# --- 1. 智慧抓股引擎 (多源頭聚合：HiStock + Yahoo上市 + Yahoo上櫃) ---
@st.cache_data(ttl=1800)
def get_market_stocks():
    # 用於儲存結果的字典 (使用字典可自動去重複: code -> name)
    stock_map = {}
    
    # 偽裝瀏覽器 Header
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7'
    }

    # ------------------------------------------------
    # 來源 A: HiStock (嗨投資) - 通常最穩定
    # ------------------------------------------------
    try:
        url = "https://histock.tw/stock/rank.aspx?p=all" 
        r = requests.get(url, headers=headers, timeout=5)
        dfs = pd.read_html(r.text)
        df = dfs[0]
        
        col_code = [c for c in df.columns if '代號' in str(c)][0]
        col_name = [c for c in df.columns if '股票' in str(c) or '名稱' in str(c)][0]
        
        for index, row in df.iterrows():
            code = ''.join([c for c in str(row[col_code]) if c.isdigit()])
            name = str(row[col_name])
            if len(code) == 4:
                stock_map[f"{code}.TW"] = name # 存入字典
    except Exception as e:
        print(f"HiStock error: {e}")

    # ------------------------------------------------
    # 來源 B: Yahoo 股市 (上市 TAI)
    # ------------------------------------------------
    try:
        url = "https://tw.stock.yahoo.com/rank/volume?exchange=TAI"
        r = requests.get(url, headers=headers, timeout=5)
        if "Table" in r.text or "table" in r.text:
            dfs = pd.read_html(r.text)
            df = dfs[0]
            target_col = [c for c in df.columns if '股號' in c or '名稱' in c][0]
            for item in df[target_col]:
                item_str = str(item)
                code = ''.join([c for c in item_str if c.isdigit()])
                name = item_str.replace(code, '').strip()
                if len(code) == 4:
                    if not name: name = code
                    stock_map[f"{code}.TW"] = name
    except Exception as e:
        print(f"Yahoo TAI error: {e}")

    # ------------------------------------------------
    # 來源 C: Yahoo 股市 (上櫃 TWO) - 抓OTC飆股
    # ------------------------------------------------
    try:
        url = "https://tw.stock.yahoo.com/rank/volume?exchange=TWO"
        r = requests.get(url, headers=headers, timeout=5)
        if "Table" in r.text or "table" in r.text:
            dfs = pd.read_html(r.text)
            df = dfs[0]
            target_col = [c for c in df.columns if '股號' in c or '名稱' in c][0]
            for item in df[target_col]:
                item_str = str(item)
                code = ''.join([c for c in item_str if c.isdigit()])
                name = item_str.replace(code, '').strip()
                if len(code) == 4:
                    # 上櫃股票代號在 yfinance 也是 .TW (大部分) 或 .TWO，這裡統一先試 .TW
                    # 註：yfinance 台股上櫃通常也吃 .TW，若不行可試 .TWO，但在批次下載中混合比較麻煩
                    # 我們這裡先假設 .TW，因為大部份資料源通用
                    if not name: name = code
                    stock_map[f"{code}.TW"] = name
    except Exception as e:
        print(f"Yahoo TWO error: {e}")

    # ------------------------------------------------
    # 備援名單 (如果上面都抓不到，至少要有這些)
    # ------------------------------------------------
    backup_codes = [
        "2330.TW", "2317.TW", "2324.TW", "2603.TW", "2609.TW", "3231.TW", "2357.TW", "3037.TW", "2382.TW", "2303.TW", 
        "2454.TW", "2379.TW", "2356.TW", "2615.TW", "3481.TW", "2409.TW", "2376.TW", "2301.TW", "3035.TW", "3017.TW",
        "1513.TW", "1519.TW", "1605.TW", "1503.TW", "2515.TW", "2501.TW", "2881.TW", "2882.TW", "2891.TW", "5880.TW",
        "2886.TW", "2892.TW", "1319.TW", "1722.TW", "1795.TW", "4763.TW", "4133.TW", "6446.TW", "6472.TW", "3711.TW",
        "2344.TW", "6770.TW", "3529.TW", "6239.TW", "8069.TWO", "3034.TW", "3532.TW", "3008.TW", "3189.TW", "5347.TWO",
        "3260.TWO", "6180.TWO", "8046.TW", "2449.TW", "6189.TW", "6278.TW", "4968.TW", "4961.TW", "2498.TW", "2368.TW",
        "2313.TW", "2312.TW", "2367.TW", "6213.TW", "3044.TW", "3019.TW", "2408.TW", "3443.TW", "3661.TW", "6669.TW",
        "3036.TW", "2383.TW", "2323.TW", "2404.TW", "2455.TW", "3583.TW", "4906.TW", "5269.TW", "5483.TWO", "6488.
