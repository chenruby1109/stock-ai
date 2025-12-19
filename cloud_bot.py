import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import sys
import os
from datetime import datetime, timedelta

# ================= 參數設定區 =================
TELEGRAM_TOKEN = os.environ.get("TG_TOKEN", "你的TOKEN_測試用")
TELEGRAM_CHAT_ID = os.environ.get("TG_CHAT_ID", "你的ID_測試用")

# 監控名單
WATCH_LIST = {
    "2454": "聯發科", "2324": "仁寶", "4927": "泰鼎-KY", "8299": "群聯",
    "3017": "奇鋐", "6805": "富世達", "3661": "世芯-KY", "6770": "力積電"
}
# ===========================================

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload)
    except Exception as e:
        print(f"❌ 發送失敗：{e}")

# --- 智能抓取 (自動判斷上市上櫃) ---
def get_data(symbol):
    try:
        # 1. 先試上市 (.TW)
        ticker = yf.Ticker(symbol + ".TW")
        df = ticker.history(period="1y")
        
        # 2. 如果沒資料，改試上櫃 (.TWO)
        if df.empty:
            ticker = yf.Ticker(symbol + ".TWO")
            df = ticker.history(period="1y")
            
        return df
    except: return None

# --- 技術指標與 ATR 目標運算 ---
def calc_indicators(df):
    if df is None or df.empty: return df
    
    # 均線
    for ma in [5, 10, 20, 60]:
        df[f'MA{ma}'] = df['Close'].rolling(ma).mean()
    df['SMA22'] = df['Close'].rolling(22).mean() # SOP用
    
    # KD
    df['9_High'] = df['High'].rolling(9).max()
    df['9_Low'] = df['Low'].rolling(9).min()
    df['RSV'] = (df['Close'] - df['9_Low']) / (df['9_High'] - df['9_Low']) * 100
    k, d = [50], [50]
    for rsv in df['RSV'].fillna(50):
        k.append(k[-1]*2/3 + rsv*1/3)
        d.append(d[-1]*2/3 + k[-1]*1/3)
    df['K'] = k[1:]
    df['D'] = d[1:]
    
    # MACD
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['MACD']
    
    # 成交量均線
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    
    # ATR (真實波動幅度) - 用來算目標價
    df['TR'] = np.maximum(df['High'] - df['Low'], np.abs(df['High'] - df['Close'].shift(1)))
    df['ATR'] = df['TR'].rolling(14).mean()
    
    return df

# --- 產生 AI 建議 (買點/目標/勝率) ---
def generate_trade_setup(df):
    today = df.iloc[-1]
    close = today['Close']
    atr = today['ATR']
    ma5 = today['MA5']
    ma20 = today['MA20']
    
    # 1. 建議買點
    buy_aggressive = f"{max(ma5, close * 0.99):.1f}" # 沿5日線或現價微回檔
    buy_conservative = f"{max(ma20, close * 0.95):.1f}" # 月線支撐
    
    # 2. 目標價與勝率 (基於 ATR 波動統計)
    # 邏輯：漲 1個 ATR 通常機率高(80%)，漲 2個 ATR 屬於波段(60%)，3個 ATR 屬於長線(40%)
    t1 = close + (atr * 1.5)
    t2 = close + (atr * 3.0)
    
    setup_msg = f"💰 **AI 建議佈局**\n"
    setup_msg += f"🦁 激進買點: {buy_aggressive} (沿5日線)\n"
    setup_msg += f"🐢 保守買點: {buy_conservative} (月線支撐)\n"
    setup_msg += f"🎯 **目標預測**:\n"
    setup_msg += f"   1️⃣ 短線: {t1:.1f} (
