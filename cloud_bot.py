import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import sys
import os
from datetime import datetime, timedelta

# ================= 參數設定區 =================
# ⚠️ 請記得填入您的 Token
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
            "parse_mode": "HTML", 
            "disable_web_page_preview": True
        }
        requests.post(url, json=payload)
        print(f"✅ 訊息已發送")
    except Exception as e:
        print(f"❌ 發送失敗：{e}")

def get_data(symbol):
    try:
        ticker = yf.Ticker(symbol + ".TW")
        df = ticker.history(period="1y")
        if df.empty:
            ticker = yf.Ticker(symbol + ".TWO")
            df = ticker.history(period="1y")
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
    
    # ATR & Bollinger
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['BB_Mid'] = df['Close'].rolling(20).mean()
    df['BB_Std'] = df['Close'].rolling(20).std()
    df['BB_Up'] = df['BB_Mid'] + 2 * df['BB_Std']
    df['BB_Low'] = df['BB_Mid'] - 2 * df['BB_Std']
    df['TR'] = np.maximum(df['High'] - df['Low'], np.abs(df['High'] - df['Close'].shift(1)))
    df['ATR'] = df['TR'].rolling(14).mean()
    
    return df

# 費波那契計算
def get_fibonacci(df):
    high = df['High'].iloc[-120:].max()
    low = df['Low'].iloc[-120:].min()
    diff = high - low
    return {
        "0.200": high - (diff * 0.2),
        "0.382": high - (diff * 0.382),
        "0.618": high - (diff * 0.618)
    }

# 檢查所有條件
def check_conditions(df, symbol, name):
    today = df.iloc[-1]
    prev = df.iloc[-2]
    signals = []
    
    turnover = today['Close'] * today['Volume']
    if turnover > 30000000 and today['Close'] > prev['Close']:
        signals.append(f"🔥 <b>主力權證大單</b>")

    is_sop = (prev['MACD_Hist'] <= 0 and today['MACD_Hist'] > 0) and \
             (today['Close'] > today['SMA22']) and \
             (today['K'] > today['D'])
    if is_sop:
        signals.append(f"✅ <b>SOP 起漲訊號</b>")

    k_max_10 = df['K'].rolling(10).max().iloc[-1]
    if (k_max_10 > 70) and (40 <= today['K'] <= 60) and (today['Close'] > today['MA20']):
         signals.append(f"☕ <b>High C 高檔整理</b>")

    if today['K'] < 40 and today['K'] > prev['K'] and today['K'] > today['D']:
        signals.append(f"💧 <b>底部咕嚕咕嚕</b>")
        
    if (today['Volume'] > today['Vol_MA5'] * 1.5) and (today['Close'] > prev['Close'] * 1.03):
        signals.append(f"🚀 <b>出量突破</b>")

    recent = df.iloc[-10:]
    is_strong = (recent['Close'] >= recent['Open']) | (recent['Close'] > recent['Close'].shift(1))
    consecutive = 0
    for x in reversed(is_strong.values):
        if x: consecutive += 1
        else: break
    if 3 <= consecutive <= 10:
        signals.append(f"🛡️ <b>主力連買({consecutive}天)</b>")
        
    return signals

# 新增：計算策略分析 (買點、目標、機率)
def analyze_strategy(df):
    today = df.iloc[-1]
    fib = get_fibonacci(df)
    atr = today['ATR'] if not pd.isna(today['ATR']) else today['Close'] * 0.02
    
    # 1. 建議買點
    buy_aggressive = max(today['MA5'], fib['0.200']) 
    buy_conservative = max(today['MA20'], fib['0.382']) 
    
    # 2. 勝率模擬 
    score = 50
    if today['Close'] > today['MA20']: score += 10
    if today['MA20'] > today['MA60']: score += 10 
    if today['MACD_Hist'] > 0: score += 10
    if today['K'] < 80 and today['K'] > today['D']: score += 10 
    if today['Volume'] > today['Vol_MA5']: score += 5
    win_rate = min(score, 85) 
    
    # 3. 目標價計算
    target_price = today['Close'] + (atr * 3) 
    
    # 4. 達標機率
    prob_target = int(win_rate * 0.8) 
    
    return {
        "buy_agg": buy_aggressive,
        "buy_con": buy_conservative,
        "win_rate": win_rate,
        "target": target_price,
        "prob_target": prob_target
    }

# --- 模式 A: 盤後報告 ---
def run_daily_report():
    print("📊 生成盤後報告中...")
    today_str = datetime.now().strftime('%Y-%m-%d')
    report = f"📅 <b>Miniko 戰情室 - {today_str} 盤後報告</b>\n"
    report += "-------------------------\n"
    
    for code, name in WATCH_LIST.items():
        print(f"分析中: {code} {name}...") 
        try:
            df = get_data(code)
            if df is None: continue
            
            df = calc_indicators(df)
            today = df.iloc[-1]
            prev = df.iloc[-2]
            
            chg = today['Close'] - prev['Close']
            pct = (chg / prev['Close']) * 100
            
            if pct > 0: icon = "🔺"
            elif pct < 0: icon = "💚"
            else: icon = "➖"
            
            trend = "盤整"
            if today['Close'] > today['MA20'] and today['MA20'] > today['MA60']: trend = "多頭"
            if today['Close'] < today['MA20'] and today['MA20'] < today['MA60']: trend = "空頭"
            
            report += f"<b>{name} ({code})</b> {icon} {today['Close']} ({pct:+.2f}%)\n"
            report += f"🌊 趨勢: {trend} | KD: {int(today['K'])}/{int(today['D'])}\n"
            
            signals = check_conditions(df, code, name)
            if signals:
                report += f"💡 訊號: {', '.join(signals)}\n"
            else:
                report += f"💤 狀態: 無特殊訊號\n"
            
            report += "---------------\n"
            time.sleep(1) 
        except Exception as e:
            print(f"Error {code}: {e}")

    report += "\n<i>(Miniko AI 自動生成)</i>"
    send_telegram(report)

# --- 模式 B: 盤中監控 (含定時策略報告) ---
def run_monitor():
    print("👀 盤中哨兵模式啟動 (每 5 分鐘掃描 + 定時報告)...")
    
    alert_history = {} 
    
    # ⚠️ 為了讓您測試，我加了 04:11 ~ 04:15，請趕快執行！
    scheduled_report_sent = {
        "10:20": False, 
        "12:00": False, 
        "04:11": False, 
        "04:12": False,
        "04:13": False,
        "04:14": False,
        "04:15": False
    }

    while True: 
        now = datetime.now()
        now_str = now.strftime('%H:%M')
        print(f"\n🔄 [{now_str}] 掃描中...")
        
        # --- 🕒 定時策略報告觸發區 (含測試時間) ---
        target_times = ["10:20", "12:00", "04:11", "04:12", "04:13", "04:14", "04:15"]
        
        for t_time in target_times:
            if t_time == now_str and not scheduled_report_sent[t_time]:
                print(f"⏰ 觸發 {t_time} 定時策略報告！")
                
                strategy_msg = f"🔔 <b>Miniko {t_time} 策略推演 (測試)</b> 🔔\n\n"
                
                for code, name in WATCH_LIST.items():
                    try:
                        df = get_data(code)
                        if df is None: continue
                        df = calc_indicators(df)
                        strat = analyze_strategy(df)
                        
                        strategy_msg += f"<b>📌 {name} ({code})</b>\n"
                        strategy_msg += f"🛒 買點: {strat['buy_agg']:.1f}(激) / {strat['buy_con']:.1f}(穩)\n"
                        strategy_msg += f"🎲 勝率: {strat['win_rate']}%\n"
                        strategy_msg += f"🎯 目標: {strat['target']:.1f} (機率{strat['prob_target']}%)\n"
                        strategy_msg += f"------------------\n"
                    except: pass
                    
                send_telegram(strategy_msg)
                scheduled_report_sent[t_time] = True 
        
        # 重置邏輯 (測試用不到，但保留)
        if now_str == "12:05": scheduled_report_sent["10:20"] = False
        if now_str == "13:30": scheduled_report_sent["12:00"] = False

        # --- 原有監控邏輯 ---
        for code, name in WATCH_LIST.items():
            try:
                df = get_data(code)
                if df is None: continue
                df = calc_indicators(df)
                
                signals = check_conditions(df, code, name)
                
                if signals:
                    last_sent_time = alert_history.get(code)
                    if last_sent_time:
                        if (datetime.now() - last_sent_time).seconds < 3600:
                            continue

                    today = df.iloc[-1]
                    prev = df.iloc[-2]
                    chg = today['Close'] - prev['Close']
                    pct = (chg / prev['Close']) * 100
                    icon = "🔺" if pct > 0 else "💚" if pct < 0 else "➖"
                    
                    msg = f"🚨 <b>Miniko 盤中快報</b> 🚨\n\n"
                    msg += f"<b>{name} ({code})</b> 出現訊號！\n"
                    msg += f"💰 現價: {today['Close']} {icon} ({pct:+.2f}%)\n"
                    msg += f"📊 量能: {int(today['Volume']/1000)} 張\n"
                    msg += f"---------------------\n"
                    msg += f"<b>💡 觸發條件：</b>\n"
                    msg += "\n".join([f"{s}" for s in signals])
                    msg += f"\n---------------------\n"
                    msg += f"<i>(時間: {now_str})</i>"
                    
                    print(f"🚀 發送 {name} 快報！")
                    send_telegram(msg)
                    alert_history[code] = datetime.now()
                    
            except Exception as e:
                print(f"❌ 監控錯誤 {code}: {e}")
            
            time.sleep(1) 
        
        print("💤 休息 60 秒後繼續 (為了測試改快一點)...")
        time.sleep(60) # 測試時改成 60 秒掃一次比較快

if __name__ == "__main__":
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        mode = "report" 

    if mode == "report":
        run_daily_report()
    elif mode == "monitor":
        run_monitor()
    else:
        print("請指定模式: python cloud_bot.py [monitor|report]")
