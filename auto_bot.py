import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timedelta

# ================= 參數設定區 (請修改這裡) =================
TELEGRAM_TOKEN = "8444206711:AAFX9ExxgkhvT1Fn0wHJXBy1Ixk5xK1WoSw"
TELEGRAM_CHAT_ID = "8185905217"

# 監控名單：代號對應名稱
WATCH_LIST = {
    "2454": "聯發科",
    "2324": "仁寶",
    "4927": "泰鼎-KY",
    "8299": "群聯",
    "3017": "奇鋐",
    "6805": "富世達",
    "3661": "世芯-KY",
    "6770": "力積電"
}
# ========================================================

# --- Telegram 發送函式 ---
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown" # 支援粗體與格式
        }
        requests.post(url, json=payload)
        print(f"✅ 訊息已發送：{message[:20]}...")
    except Exception as e:
        print(f"❌ 發送失敗：{e}")

# --- 技術指標計算 (沿用你的邏輯) ---
def calc_indicators(df):
    if df is None or df.empty: return df
    
    # 均線
    for ma in [5, 10, 20, 60]:
        df[f'MA{ma}'] = df['Close'].rolling(ma).mean()
    
    # 特攻隊均線 (SOP用)
    df['SMA22'] = df['Close'].rolling(22).mean()

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
    
    return df

# --- 核心訊號檢查 ---
def check_signals(symbol, name):
    print(f"🔍 正在掃描：{symbol} {name} ...")
    
    # 為了模擬盤中，我們抓取資料 (Yahoo Finance 盤中會更新最後一筆 row)
    ticker_symbol = symbol + ".TW"
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="1y") # 抓一年算指標比較準
        
        if df.empty:
            return None
        
        # 計算指標
        df = calc_indicators(df)
        
        # 取得最後兩筆資料 (Today & Yesterday)
        today = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 訊號搜集箱
        signals = []
        
        # 1. 權證大量買入 (模擬：總成交金額大且上漲)
        # 註：Yahoo無法直接抓權證，我們用「成交金額爆量」作為法人大戶進場的替代訊號
        turnover = today['Close'] * today['Volume']
        if turnover > 50000000 and today['Close'] > prev['Close']: # 設定5000萬台幣比較保險，避免小單亂叫
             signals.append("🔥 **疑似權證/主力大單進駐** (成交額爆發)")

        # 2. SOP 訊號 (MACD翻紅 + 站上SMA22 + KD金叉)
        is_sop = (prev['MACD_Hist'] <= 0 and today['MACD_Hist'] > 0) and \
                 (today['Close'] > today['SMA22']) and \
                 (prev['K'] < prev['D'] and today['K'] > today['D'])
        if is_sop:
            signals.append("✅ **SOP 起漲訊號** (三線合一：MACD翻紅+KD金叉+站上月線)")

        # 3. 高檔盤整 (High C) - 價格沒掉下來，KD回落到40-60
        # 邏輯：過去10天K值曾>70 (高檔)，但現在K值回到40-60之間 (整理)，且股價守在月線上
        k_max_10 = df['K'].rolling(10).max().iloc[-1]
        if (k_max_10 > 70) and (40 <= today['K'] <= 60) and (today['Close'] > today['MA20']):
            signals.append("☕ **High C 高檔整理** (KD回落40-60，蓄勢待發)")

        # 4. 底部咕嚕咕嚕 (Gulu) - KD小於40且勾起來
        kd_low = today['K'] < 40
        k_hook = (today['K'] > prev['K']) and (today['K'] > today['D'])
        if kd_low and k_hook:
            signals.append("💧 **底部咕嚕咕嚕** (低檔KD金叉勾起)")

        # 5. 大量突破 (成交量 > 5日均量 1.5倍 且 長紅)
        vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
        if (today['Volume'] > vol_ma5 * 1.5) and (today['Close'] > prev['Close'] * 1.02):
            signals.append("🚀 **出量攻擊** (量能 > 1.5倍均量)")

        # --- 若有訊號，組裝報告 ---
        if signals:
            price_info = f"💰 現價：{today['Close']:.1f} (漲跌 {today['Close']-prev['Close']:.1f})"
            report = f"🚨 **Miniko 戰情室警報：{name} ({symbol})**\n"
            report += f"{price_info}\n\n"
            report += "\n".join(signals)
            report += f"\n\n⏳ 時間：{datetime.now().strftime('%H:%M:%S')}"
            return report
        
        return None

    except Exception as e:
        print(f"Error checking {symbol}: {e}")
        return None

# --- 主程式迴圈 ---
def main():
    print("🤖 Miniko AI 盤中哨兵已啟動...")
    print(f"📋 監控名單：{list(WATCH_LIST.values())}")
    send_telegram("⚡ Miniko AI 盤中哨兵已上線！開始監控股票...")
    
    # 記錄今天是否已經發送過該股票的訊號，避免一分鐘發一次轟炸
    # 格式： {'2454': ['SOP', 'High C'], ...}
    sent_history = {code: [] for code in WATCH_LIST} 

    while True:
        now = datetime.now()
        
        # 設定監控時間 (例如 09:00 ~ 13:30)
        # 如果你想全天測試，可以先把這行註解掉
        if not (datetime(now.year, now.month, now.day, 9, 0) <= now <= datetime(now.year, now.month, now.day, 13, 35)):
            print("💤 非盤中時間，休息中...")
            time.sleep(300) # 休息5分鐘
            continue

        for code, name in WATCH_LIST.items():
            report = check_signals(code, name)
            
            if report:
                # 簡單去重邏輯：如果這個股票今天還沒發過報告，或者隔了很久(這裡簡化為只要有訊號就發，但實務上建議加冷卻時間)
                # 這裡示範：只要有訊號就發送 (Yahoo Finance更新較慢，通常幾分鐘變動一次)
                
                # 為了避免同一分鐘重複發送，我們可以檢查內容雜湊，或是簡單地直接發
                send_telegram(report)
                
            # 休息一下，避免被 Yahoo 封鎖 IP
            time.sleep(10) 

        print("✅ 掃描一輪完成，休息 60 秒...")
        time.sleep(60)

if __name__ == "__main__":
    main()