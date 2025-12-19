# -*- coding: utf-8 -*-
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import sys
import os
from datetime import datetime, timedelta

# ================= ⚙️ 參數設定區 =================
# 在雲端環境請使用環境變數，本地測試可直接填入字串
TELEGRAM_TOKEN = os.environ.get("TG_TOKEN", "你的_TOKEN_填在這裡")
TELEGRAM_CHAT_ID = os.environ.get("TG_CHAT_ID", "你的_ID_填在這裡")

# 監控名單
WATCH_LIST = {
    "2454": "聯發科", "2324": "仁寶", "4927": "泰鼎-KY", "8299": "群聯",
    "3017": "奇鋐", "6805": "富世達", "3661": "世芯-KY", "6770": "力積電"
}
# ===============================================

def send_telegram(message):
    """發送 Telegram 訊息 (HTML 格式)"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID, 
            "text": message, 
            "parse_mode": "HTML", 
            "disable_web_page_preview": True
        }
        requests.post(url, json=payload)
        # print(f"✅ 訊息已發送") 
    except Exception as e:
        print(f"❌ Telegram 發送失敗：{e}")

def get_data(symbol):
    """自動判斷上市(.TW)或上櫃(.TWO)並獲取數據"""
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
    """計算技術指標：均線、KD、MACD、布林、ATR (保留原邏輯)"""
    if df is None or df.empty: return df
    
    # 均線
    for ma in [5, 10, 20, 60, 120]:
        df[f'MA{ma}'] = df['Close'].rolling(ma).mean()
    df['SMA22'] = df['Close'].rolling(22).mean() # SOP 攻擊線
    
    # KD (9,3,3)
    df['9_High'] = df['High'].rolling(9).max()
    df['9_Low'] = df['Low'].rolling(9).min()
    df['RSV'] = (df['Close'] - df['9_Low']) / (df['9_High'] - df['9_Low']) * 100
    k, d = [50], [50]
    for rsv in df['RSV'].fillna(50):
        k.append(k[-1]*2/3 + rsv*1/3)
        d.append(d[-1]*2/3 + k[-1]*1/3)
    df['K'] = k[1:]
    df['D'] = d[1:]
    
    # MACD (12,26,9)
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['MACD']
    
    # 量能與 ATR
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['TR'] = np.maximum(df['High'] - df['Low'], np.abs(df['High'] - df['Close'].shift(1)))
    df['ATR'] = df['TR'].rolling(14).mean()
    
    return df

def get_fibonacci(df):
    """計算費波那契回檔位"""
    high = df['High'].iloc[-120:].max()
    low = df['Low'].iloc[-120:].min()
    diff = high - low
    return {
        "0.200": high - (diff * 0.2),
        "0.382": high - (diff * 0.382),
        "0.618": high - (diff * 0.618)
    }

def check_conditions(df, symbol, name):
    """檢核 6 大核心訊號 (保留原邏輯)"""
    today = df.iloc[-1]
    prev = df.iloc[-2]
    signals = []
    
    # 1. 主力權證大單 (>3000萬 & 漲)
    turnover = today['Close'] * today['Volume']
    if turnover > 30000000 and today['Close'] > prev['Close']:
        signals.append(f"🔥 <b>主力權證大單</b>")

    # 2. SOP 起漲 (MACD翻紅 + 站上SMA22 + KD金叉)
    is_sop = (prev['MACD_Hist'] <= 0 and today['MACD_Hist'] > 0) and \
             (today['Close'] > today['SMA22']) and \
             (today['K'] > today['D'])
    if is_sop:
        signals.append(f"✅ <b>SOP 起漲訊號</b>")

    # 3. High C 高檔整理
    k_max_10 = df['K'].rolling(10).max().iloc[-1]
    if (k_max_10 > 70) and (40 <= today['K'] <= 60) and (today['Close'] > today['MA20']):
         signals.append(f"☕ <b>High C 高檔整理</b>")

    # 4. 底部咕嚕咕嚕 (低檔金叉)
    if today['K'] < 40 and today['K'] > prev['K'] and today['K'] > today['D']:
        signals.append(f"💧 <b>底部咕嚕咕嚕</b>")
        
    # 5. 出量突破
    if (today['Volume'] > today['Vol_MA5'] * 1.5) and (today['Close'] > prev['Close'] * 1.03):
        signals.append(f"🚀 <b>出量突破</b>")

    # 6. 主力連買 (3~10天)
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
    """計算策略數據：買點、勝率、目標價"""
    today = df.iloc[-1]
    fib = get_fibonacci(df)
    atr = today['ATR'] if not pd.isna(today['ATR']) else today['Close'] * 0.02
    
    # 買點計算 (激進 vs 保守)
    buy_aggressive = max(today['MA5'], fib['0.200']) 
    buy_conservative = max(today['MA20'], fib['0.382']) 
    
    # 勝率評分模型 (簡單權重)
    score = 50
    if today['Close'] > today['MA20']: score += 10    # 站上月線
    if today['MA20'] > today['MA60']: score += 10     # 均線多排
    if today['MACD_Hist'] > 0: score += 10            # 動能翻紅
    if today['K'] < 80 and today['K'] > today['D']: score += 10 # 金叉且不熱
    if today['Volume'] > today['Vol_MA5']: score += 5 # 有量
    win_rate = min(score, 90) # 上限 90%
    
    # 目標價與達標機率
    target_price = today['Close'] + (atr * 3) # 目標 3倍 ATR
    prob_target = int(win_rate * 0.8)         # 達標率約為勝率的 8折
    
    return {
        "buy_agg": buy_aggressive,
        "buy_con": buy_conservative,
        "win_rate": win_rate,
        "target": target_price,
        "prob_target": prob_target
    }

# ==========================================
# 🅰️ 模式 A: 盤後報告 (Daily Report)
# ==========================================
def run_daily_report():
    print("📊 生成盤後報告中...")
    # 台灣時間校正
    today_str = (datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d')
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
        except: pass

    report += "\n<i>(Miniko AI 自動生成)</i>"
    send_telegram(report)
    print("✅ 盤後報告已發送")

# ==========================================
# 🅱️ 模式 B: 盤中哨兵 (Intraday Monitor)
# ==========================================
def run_monitor():
    print("👀 Miniko 盤中哨兵模式啟動 (已校正 UTC+8)...")
    print("🚀 功能: [即時訊號快報] + [10:20/12:00 戰略報告]")
    
    alert_history = {} # 記錄即時訊號發送時間 (冷卻用)
    
    # 定時報告時間點
    target_times = ["10:20", "12:00"]
    scheduled_report_sent = {t: False for t in target_times}

    while True: 
        # 1. 取得準確的台灣時間
        now_tw = datetime.utcnow() + timedelta(hours=8)
        now_str = now_tw.strftime('%H:%M')
        
        # Log 顯示 (每 30 秒跳一次)
        print(f"\r🔄 [{now_str}] 戰情掃描中...", end="")
        
        # --- 🕒 [定時] 策略報告觸發區 (10:20 & 12:00) ---
        for t_time in target_times:
            if t_time == now_str and not scheduled_report_sent[t_time]:
                print(f"\n⏰ 時間到 ({t_time})！正在發送戰略報告...")
                
                strategy_msg = f"🔔 <b>Miniko {t_time} 盤中戰略推演</b> 🔔\n\n"
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
                        strategy_msg += f"🎯 目標: {strat['target']:.1f} (達標率{strat['prob_target']}%)\n"
                        strategy_msg += f"------------------\n"
                        has_data = True
                    except: pass
                
                if has_data:
                    send_telegram(strategy_msg)
                
                scheduled_report_sent[t_time] = True 
        
        # 跨日/跨時段重置 Flags (讓程式可以長期掛機)
        if now_str == "13:00": scheduled_report_sent["10:20"] = False
        if now_str == "00:00": scheduled_report_sent["12:00"] = False

        # --- 🔥 [即時] 訊號監控邏輯 ---
        for code, name in WATCH_LIST.items():
            try:
                df = get_data(code)
                if df is None: continue
                df = calc_indicators(df)
                
                # 檢查是否有訊號
                signals = check_conditions(df, code, name)
                
                if signals:
                    # 冷卻機制: 同一檔股票 60 分鐘內不重複發通知
                    last_sent_time = alert_history.get(code)
                    if last_sent_time:
                        if (datetime.utcnow() - last_sent_time).seconds < 3600:
                            continue

                    today = df.iloc[-1]
                    prev = df.iloc[-2]
                    chg = today['Close'] - prev['Close']
                    pct = (chg / prev['Close']) * 100
                    icon = "🔺" if pct > 0 else "💚" if pct < 0 else "➖"
                    
                    msg = f"🚨 <b>Miniko 盤中訊號快報</b> 🚨\n\n"
                    msg += f"<b>{name} ({code})</b> 觸發條件！\n"
                    msg += f"💰 現價: {today['Close']} {icon} ({pct:+.2f}%)\n"
                    msg += f"📊 量能: {int(today['Volume']/1000)} 張\n"
                    msg += f"---------------------\n"
                    msg += f"<b>💡 訊號內容：</b>\n"
                    msg += "\n".join([f"{s}" for s in signals])
                    msg += f"\n---------------------\n"
                    msg += f"<i>(觸發時間: {now_str})</i>"
                    
                    print(f"\n🚀 {name} 出現訊號，立即發送！")
                    send_telegram(msg)
                    alert_history[code] = datetime.utcnow() # 更新發送時間
            except: pass
            
        # 休息 30 秒 (兼顧即時性與 API 限制)
        time.sleep(30)

if __name__ == "__main__":
    # 預設執行 Monitor 模式 (適合掛在伺服器)
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        mode = "monitor" 

    if mode == "report":
        run_daily_report()
    elif mode == "monitor":
        run_monitor()
    else:
        print("請指定模式: python cloud_bot.py [monitor|report]")
