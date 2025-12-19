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
# 如果你在本機測試，請暫時填入你的 Token，上傳前記得改回 os.environ.get
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
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload)
        print(f"✅ 訊息已發送")
    except Exception as e:
        print(f"❌ 發送失敗：{e}")

def get_data(symbol):
    try:
        ticker = yf.Ticker(symbol + ".TW")
        # 盤中需要即時數據，Yahoo 有時會有延遲，這是免費源的限制
        df = ticker.history(period="1y") 
        return df
    except: return None

def calc_indicators(df):
    if df is None or df.empty: return df
    
    # 均線
    for ma in [5, 10, 20, 60, 120]:
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
    
    # Vol & BB
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
    
    # 1. 權證/大單 (成交額 > 5000萬 且 漲)
    turnover = today['Close'] * today['Volume']
    if turnover > 50000000 and today['Close'] > prev['Close']:
        signals.append(f"🔥 **主力權證大單** (金額爆發)")

    # 2. SOP 訊號 (MACD翻紅 + 站上SMA22 + KD金叉)
    is_sop = (prev['MACD_Hist'] <= 0 and today['MACD_Hist'] > 0) and \
             (today['Close'] > today['SMA22']) and \
             (today['K'] > today['D'])
    if is_sop:
        signals.append(f"✅ **SOP 起漲訊號** (三線合一)")

    # 3. High C 高檔整理 (K值回落40-60，股價守月線)
    k_max_10 = df['K'].rolling(10).max().iloc[-1]
    if (k_max_10 > 70) and (40 <= today['K'] <= 60) and (today['Close'] > today['MA20']):
         signals.append(f"☕ **High C 高檔整理** (蓄勢待發)")

    # 4. 底部咕嚕咕嚕 (低檔金叉)
    if today['K'] < 40 and today['K'] > prev['K'] and today['K'] > today['D']:
        signals.append(f"💧 **底部咕嚕咕嚕** (低檔佈局)")
        
    # 5. 大量突破 (量增 + 長紅)
    if (today['Volume'] > today['Vol_MA5'] * 1.5) and (today['Close'] > prev['Close'] * 1.03):
        signals.append(f"🚀 **出量突破** (帶量長紅)")
        
    return signals

# --- 模式 A: 盤後報告 (Daily Report) ---
def run_daily_report():
    print("📊 生成盤後報告中...")
    report = f"📅 **Miniko 戰情室 - {datetime.now().strftime('%Y-%m-%d')} 盤後報告**\n"
    report += "-"*25 + "\n"
    
    for code, name in WATCH_LIST.items():
        try:
            df = get_data(code)
            if df is None: continue
            df = calc_indicators(df)
            today = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 漲跌圖示
            chg = today['Close'] - prev['Close']
            pct = (chg / prev['Close']) * 100
            icon = "🔺" if chg > 0 else "💚" if chg < 0 else "➖"
            
            # 判斷趨勢
            trend = "盤整"
            if today['Close'] > today['MA20'] and today['MA20'] > today['MA60']: trend = "多頭"
            if today['Close'] < today['MA20'] and today['MA20'] < today['MA60']: trend = "空頭"
            
            report += f"**{name} ({code})** {icon} {today['Close']} ({pct:.2f}%)\n"
            report += f"🌊 趨勢: {trend} | KD: {int(today['K'])}/{int(today['D'])}\n"
            
            # 檢查是否有特殊訊號
            signals = check_conditions(df, code, name)
            if signals:
                report += f"💡 訊號: {', '.join([s.split(' ')[0]+s.split(' ')[1] for s in signals])}\n"
            else:
                report += f"💤 狀態: 無特殊訊號\n"
            
            report += "-"*15 + "\n"
            time.sleep(1) # 避免請求過快
        except Exception as e:
            print(f"Error {code}: {e}")

    report += "\n🔗 [點此開啟戰略指揮室查看圖表](https://share.streamlit.io/你的帳號/你的專案/app.py)"
    send_telegram(report)

# --- 模式 B: 盤中監控 (Intraday Monitor) ---
def run_monitor():
    print("👀 盤中哨兵啟動...")
    # 為了避免 GitHub Action 超時，我們跑一輪就結束 (透過 Action 的排程每 10-15 分鐘呼叫一次)
    # 或者在這裡跑一個短迴圈 (例如 10 分鐘)
    
    start_time = datetime.now()
    # 每次執行只跑 15 分鐘 (GitHub Action 免費版通常建議短時間多次觸發)
    while (datetime.now() - start_time).seconds < 900: 
        current_time = datetime.now() + timedelta(hours=8) # 轉台灣時間
        print(f"掃描時間: {current_time.strftime('%H:%M')}")
        
        # 簡單判斷盤中時間 (台灣 09:00 - 13:30)
        # 注意：GitHub 伺服器時間是 UTC，所以要自己換算。
        # 這裡簡化邏輯：只要被呼叫就檢查，時間控制交給 GitHub Schedule
        
        for code, name in WATCH_LIST.items():
            try:
                df = get_data(code)
                if df is None: continue
                df = calc_indicators(df)
                signals = check_conditions(df, code, name)
                
                if signals:
                    msg = f"🚨 **{name} ({code}) 盤中快報** 🚨\n"
                    msg += f"現價: {df.iloc[-1]['Close']}\n"
                    msg += "\n".join(signals)
                    send_telegram(msg)
                    # 避免同一分鐘重複發送，實務上可以加個暫存檔記錄已發送的訊號
            except: pass
            time.sleep(2)
        
        time.sleep(60) # 每分鐘掃描一次

if __name__ == "__main__":
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode == "report":
            run_daily_report()
        elif mode == "monitor":
            run_monitor()
    else:
        print("請指定模式: python cloud_bot.py [monitor|report]")
