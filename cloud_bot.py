import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import sys
import os
from datetime import datetime, timedelta

# ================= 參數設定區 =================
# 在 GitHub Actions 中，這些會從環境變數讀取
# 如果你在本機測試，請暫時填入你的 Token
TELEGRAM_TOKEN = os.environ.get("TG_TOKEN", "你的_TOKEN_填在這裡")
TELEGRAM_CHAT_ID = os.environ.get("TG_CHAT_ID", "你的_ID_填在這裡")

# 監控名單
WATCH_LIST = {
    "2454": "聯發科", "2324": "仁寶", "4927": "泰鼎-KY", "8299": "群聯",
    "3017": "奇鋐", "6805": "富世達", "3661": "世芯-KY", "6770": "力積電"
}
# ===========================================

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID, 
            "text": message, 
            "parse_mode": "HTML", # 改用 HTML 支援更多格式
            "disable_web_page_preview": True
        }
        requests.post(url, json=payload)
        print(f"✅ 訊息已發送")
    except Exception as e:
        print(f"❌ 發送失敗：{e}")

def get_data(symbol):
    """
    自動判斷上市(.TW)或上櫃(.TWO)
    """
    try:
        # 1. 先嘗試上市代號 (.TW)
        ticker = yf.Ticker(symbol + ".TW")
        df = ticker.history(period="1y")
        
        # 2. 如果抓不到資料 (DataFrame 為空)，嘗試上櫃代號 (.TWO)
        if df.empty:
            # print(f"⚠️ {symbol}.TW 無資料，嘗試 .TWO...")
            ticker = yf.Ticker(symbol + ".TWO")
            df = ticker.history(period="1y")
        
        # 3. 如果還是空的，回傳 None
        if df.empty:
            print(f"❌ 無法獲取 {symbol} 資料")
            return None
            
        return df
    except Exception as e: 
        print(f"❌ 獲取資料錯誤 {symbol}: {e}")
        return None

def calc_indicators(df):
    if df is None or df.empty: return df
    
    # 均線
    for ma in [5, 10, 20, 60, 120]:
        df[f'MA{ma}'] = df['Close'].rolling(ma).mean()
    df['SMA22'] = df['Close'].rolling(22).mean() # SOP用
    
    # KD (參數 9, 3, 3)
    df['9_High'] = df['High'].rolling(9).max()
    df['9_Low'] = df['Low'].rolling(9).min()
    df['RSV'] = (df['Close'] - df['9_Low']) / (df['9_High'] - df['9_Low']) * 100
    k, d = [50], [50]
    for rsv in df['RSV'].fillna(50):
        k.append(k[-1]*2/3 + rsv*1/3)
        d.append(d[-1]*2/3 + k[-1]*1/3)
    df['K'] = k[1:]
    df['D'] = d[1:]
    
    # MACD (參數 12, 26, 9)
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['MACD']
    
    # 量能與布林通道
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['BB_Mid'] = df['Close'].rolling(20).mean()
    df['BB_Std'] = df['Close'].rolling(20).std()
    df['BB_Up'] = df['BB_Mid'] + 2 * df['BB_Std']
    df['BB_Low'] = df['BB_Mid'] - 2 * df['BB_Std']
    df['BB_Pct'] = (df['Close'] - df['BB_Low']) / (df['BB_Up'] - df['BB_Low'])
    
    return df

# 檢查所有條件 (回傳觸發的訊號列表)
def check_conditions(df, symbol, name):
    today = df.iloc[-1]
    prev = df.iloc[-2]
    signals = []
    
    # 1. 權證/大單 (成交額 > 3000萬 且 漲) - 修改門檻為 3000萬 符合您之前的邏輯
    turnover = today['Close'] * today['Volume']
    if turnover > 30000000 and today['Close'] > prev['Close']:
        signals.append(f"🔥 <b>主力權證大單</b>")

    # 2. SOP 訊號 (MACD翻紅 + 站上SMA22 + KD金叉)
    is_sop = (prev['MACD_Hist'] <= 0 and today['MACD_Hist'] > 0) and \
             (today['Close'] > today['SMA22']) and \
             (today['K'] > today['D'])
    if is_sop:
        signals.append(f"✅ <b>SOP 起漲訊號</b>")

    # 3. High C 高檔整理 (K值回落40-60，股價守月線)
    k_max_10 = df['K'].rolling(10).max().iloc[-1]
    if (k_max_10 > 70) and (40 <= today['K'] <= 60) and (today['Close'] > today['MA20']):
         signals.append(f"☕ <b>High C 高檔整理</b>")

    # 4. 底部咕嚕咕嚕 (低檔金叉)
    if today['K'] < 40 and today['K'] > prev['K'] and today['K'] > today['D']:
        signals.append(f"💧 <b>底部咕嚕咕嚕</b>")
        
    # 5. 大量突破 (量增 + 長紅)
    if (today['Volume'] > today['Vol_MA5'] * 1.5) and (today['Close'] > prev['Close'] * 1.03):
        signals.append(f"🚀 <b>出量突破</b>")

    # 6. 主力連買 (連3紅K 或 收漲)
    recent = df.iloc[-10:]
    is_strong = (recent['Close'] >= recent['Open']) | (recent['Close'] > recent['Close'].shift(1))
    consecutive = 0
    for x in reversed(is_strong.values):
        if x: consecutive += 1
        else: break
    if 3 <= consecutive <= 10:
        signals.append(f"🛡️ <b>主力連買({consecutive}天)</b>")
        
    return signals

# --- 模式 A: 盤後報告 (Daily Report) ---
def run_daily_report():
    print("📊 生成盤後報告中...")
    today_str = datetime.now().strftime('%Y-%m-%d')
    report = f"📅 <b>Miniko 戰情室 - {today_str} 盤後報告</b>\n"
    report += "-------------------------\n"
    
    for code, name in WATCH_LIST.items():
        print(f"分析中: {code} {name}...") # Debug 用
        try:
            df = get_data(code)
            if df is None: 
                print(f"跳過 {code} (無資料)")
                continue
            
            df = calc_indicators(df)
            today = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 漲跌圖示
            chg = today['Close'] - prev['Close']
            pct = (chg / prev['Close']) * 100
            
            if pct > 0: icon = "🔺"
            elif pct < 0: icon = "💚"
            else: icon = "➖"
            
            # 判斷趨勢
            trend = "盤整"
            if today['Close'] > today['MA20'] and today['MA20'] > today['MA60']: trend = "多頭"
            if today['Close'] < today['MA20'] and today['MA20'] < today['MA60']: trend = "空頭"
            
            # 組合訊息
            report += f"<b>{name} ({code})</b> {icon} {today['Close']} ({pct:+.2f}%)\n"
            report += f"🌊 趨勢: {trend} | KD: {int(today['K'])}/{int(today['D'])}\n"
            
            # 檢查是否有特殊訊號
            signals = check_conditions(df, code, name)
            if signals:
                report += f"💡 訊號: {', '.join(signals)}\n"
            else:
                report += f"💤 狀態: 無特殊訊號\n"
            
            report += "---------------\n"
            time.sleep(1) # 避免請求過快
        except Exception as e:
            print(f"Error {code}: {e}")

    report += "\n<i>(Miniko AI 自動生成)</i>"
    send_telegram(report)

# --- 模式 B: 盤中監控 (Intraday Monitor) ---
def run_monitor():
    print("👀 盤中哨兵啟動...")
    # 設定掃描時間限制 (例如跑 10 分鐘)
    start_time = datetime.now()
    
    while (datetime.now() - start_time).seconds < 600: 
        print(f"正在掃描... {datetime.now().strftime('%H:%M:%S')}")
        
        for code, name in WATCH_LIST.items():
            try:
                df = get_data(code)
                if df is None: continue
                df = calc_indicators(df)
                signals = check_conditions(df, code, name)
                
                # 只有當有訊號時才發送
                if signals:
                    msg = f"🚨 <b>{name} ({code}) 盤中快報</b> 🚨\n"
                    msg += f"現價: {df.iloc[-1]['Close']}\n"
                    msg += "\n".join([f"✅ {s}" for s in signals])
                    send_telegram(msg)
                    # 實務上這裡建議加上一個機制，避免同一天重複發送同一支股票
            except: pass
            time.sleep(1)
        
        # 休息 60 秒再掃描下一輪
        time.sleep(60) 

if __name__ == "__main__":
    # 如果沒有參數，預設跑 daily report 測試
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        mode = "report" # 預設模式

    if mode == "report":
        run_daily_report()
    elif mode == "monitor":
        run_monitor()
    else:
        print("請指定模式: python cloud_bot.py [monitor|report]")
