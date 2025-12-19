import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import sys
import os
from datetime import datetime, timedelta

# ================= 參數設定區 =================
# ⚠️ 請記得填入您的 Token (在 GitHub Secrets 中設定，或暫時填入)
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
        if df.empty: return None
        return df
    except: return None

def calc_indicators(df):
    if df is None or df.empty: return df
    for ma in [5, 10, 20, 60, 120]:
        df[f'MA{ma}'] = df['Close'].rolling(ma).mean()
    df['SMA22'] = df['Close'].rolling(22).mean() 
    
    df['9_High'] = df['High'].rolling(9).max()
    df['9_Low'] = df['Low'].rolling(9).min()
    df['RSV'] = (df['Close'] - df['9_Low']) / (df['9_High'] - df['9_Low']) * 100
    k, d = [50], [50]
    for rsv in df['RSV'].fillna(50):
        k.append(k[-1]*2/3 + rsv*1/3)
        d.append(d[-1]*2/3 + k[-1]*1/3)
    df['K'] = k[1:]
    df['D'] = d[1:]
    
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['MACD']
    
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['TR'] = np.maximum(df['High'] - df['Low'], np.abs(df['High'] - df['Close'].shift(1)))
    df['ATR'] = df['TR'].rolling(14).mean()
    return df

def get_fibonacci(df):
    high = df['High'].iloc[-120:].max()
    low = df['Low'].iloc[-120:].min()
    diff = high - low
    return {
        "0.200": high - (diff * 0.2),
        "0.382": high - (diff * 0.382),
        "0.618": high - (diff * 0.618)
    }

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

def analyze_strategy(df):
    today = df.iloc[-1]
    fib = get_fibonacci(df)
    atr = today['ATR'] if not pd.isna(today['ATR']) else today['Close'] * 0.02
    
    buy_aggressive = max(today['MA5'], fib['0.200']) 
    buy_conservative = max(today['MA20'], fib['0.382']) 
    
    score = 50
    if today['Close'] > today['MA20']: score += 10
    if today['MA20'] > today['MA60']: score += 10 
    if today['MACD_Hist'] > 0: score += 10
    if today['K'] < 80 and today['K'] > today['D']: score += 10 
    if today['Volume'] > today['Vol_MA5']: score += 5
    win_rate = min(score, 85) 
    
    target_price = today['Close'] + (atr * 3) 
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
    # 修正：使用台灣時間
    today_str = (datetime.now() + timedelta(hours=8)).strftime('%Y-%m-%d')
    report = f"📅 <b>Miniko 戰情室 - {today_str} 盤後報告</b>\n"
    report += "-------------------------\n"
    
    for code, name in WATCH_LIST.items():
        try:
            df = get_data(code)
            if df is None: continue
            df = calc_indicators(df)
            today = df.iloc[-1]
            prev = df.iloc[-2]
            chg = today['Close'] - prev['Close']
            pct = (chg / prev['Close']) * 100
            icon = "🔺" if pct > 0 else "💚" if pct < 0 else "➖"
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
        except: pass

    report += "\n<i>(Miniko AI 自動生成)</i>"
    send_telegram(report)

# --- 模式 B: 盤中監控 (含定時策略報告) ---
def run_monitor():
    print("👀 盤中哨兵模式啟動 (已校正台灣時間 +8)...")
    
    alert_history = {} 
    
    # 測試時間：您可以把現在的「台灣時間」分鐘數加進去測試
    # 例如現在台灣是 04:30，您可以填 "04:31"
    test_times = [f"04:{i:02d}" for i in range(15, 60)] + [f"05:{i:02d}" for i in range(0, 60)]
    
    target_times = ["10:20", "12:00"] + test_times
    scheduled_report_sent = {t: False for t in target_times}

    while True: 
        # ⚠️ 關鍵修正：轉成台灣時間
        now_tw = datetime.now() + timedelta(hours=8)
        now_str = now_tw.strftime('%H:%M')
        
        # 讓您在 Log 看到現在系統認知的「台灣時間」
        print(f"\r🔄 台灣時間: {now_tw.strftime('%H:%M:%S')} | 掃描中...", end="")
        
        # --- 🕒 定時策略報告觸發區 ---
        for t_time in target_times:
            if t_time == now_str and not scheduled_report_sent[t_time]:
                print(f"\n⏰ 時間到 ({t_time})！觸發定時策略報告...")
                
                strategy_msg = f"🔔 <b>Miniko {t_time} 策略推演</b> 🔔\n\n"
                has_data = False

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
                        has_data = True
                    except: pass
                
                if has_data:
                    send_telegram(strategy_msg)
                
                scheduled_report_sent[t_time] = True 

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
                        # 60分鐘冷卻
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
                    
                    print(f"\n🚀 發送 {name} 快報！")
                    send_telegram(msg)
                    alert_history[code] = datetime.now()
            except: pass
            
        # 敏捷測試：只休息 5 秒
        time.sleep(5)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        # 預設模式，您也可以改成 "monitor"
        mode = "report" 

    if mode == "report":
        run_daily_report()
    elif mode == "monitor":
        run_monitor()
    else:
        print("請指定模式: python cloud_bot.py [monitor|report]")
