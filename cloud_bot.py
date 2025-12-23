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
    except Exception as e:
        print(f"❌ Telegram 發送失敗：{e}")

def get_data(symbol, period="1y", interval="1d"):
    """
    獲取指定時間頻率的K線數據 (支援多週期)
    """
    try:
        # 嘗試上市
        ticker = yf.Ticker(symbol + ".TW")
        df = ticker.history(period=period, interval=interval)
        
        # 如果上市抓不到，嘗試上櫃
        if df.empty:
            ticker = yf.Ticker(symbol + ".TWO")
            df = ticker.history(period=period, interval=interval)
        
        if df.empty: return None
        return df
    except: return None

def calc_indicators(df):
    """計算技術指標"""
    if df is None or df.empty: return df
    
    # 均線
    for ma in [5, 10, 20, 60, 120]:
        df[f'MA{ma}'] = df['Close'].rolling(ma).mean()
    df['SMA22'] = df['Close'].rolling(22).mean() 
    
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
    """檢核 6 大核心訊號"""
    today = df.iloc[-1]
    prev = df.iloc[-2]
    signals = []
    
    # 1. 主力權證大單 (>3000萬 & 漲)
    turnover = today['Close'] * today['Volume']
    if turnover > 30000000 and today['Close'] > prev['Close']:
        signals.append(f"🔥 <b>主力權證大單</b>")

    # 2. SOP 起漲
    is_sop = (prev['MACD_Hist'] <= 0 and today['MACD_Hist'] > 0) and \
             (today['Close'] > today['SMA22']) and \
             (today['K'] > today['D'])
    if is_sop:
        signals.append(f"✅ <b>SOP 起漲訊號</b>")

    # 3. High C 高檔整理
    k_max_10 = df['K'].rolling(10).max().iloc[-1]
    if (k_max_10 > 70) and (40 <= today['K'] <= 60) and (today['Close'] > today['MA20']):
         signals.append(f"☕ <b>High C 高檔整理</b>")

    # 4. 底部咕嚕咕嚕
    if today['K'] < 40 and today['K'] > prev['K'] and today['K'] > today['D']:
        signals.append(f"💧 <b>底部咕嚕咕嚕</b>")
        
    # 5. 出量突破
    if (today['Volume'] > today['Vol_MA5'] * 1.5) and (today['Close'] > prev['Close'] * 1.03):
        signals.append(f"🚀 <b>出量突破</b>")

    # 6. 主力連買
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
    """計算策略數據"""
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
    win_rate = min(score, 90)
    
    target_price = today['Close'] + (atr * 3)
    prob_target = int(win_rate * 0.8)
    
    return {
        "buy_agg": buy_aggressive,
        "buy_con": buy_conservative,
        "win_rate": win_rate,
        "target": target_price,
        "prob_target": prob_target
    }

# ==========================================
# 🅱️ 模式 B: 盤中哨兵 (終極戰略版 - 含開機測試)
# ==========================================
def run_monitor():
    print("👀 Miniko 盤中哨兵模式啟動 (已校正 UTC+8)...")
    print("🚀 功能更新: [09:30 開盤] + [10:20/12:00 戰報] + [13:36 收盤] + [18:40 總結]")
    
    # 🔥🔥🔥 測試通知 🔥🔥🔥
    send_telegram("🚀 Miniko 系統連線測試成功！已更新時刻表：\n1. 09:30 開盤衝鋒掃描\n2. 13:36 收盤定心丸\n3. 18:40 盤後籌碼AI總結")
    
    alert_history = {} 
    
    # ⏰ 設定排程時間表
    schedule_tasks = {
        "09:30": "morning_scan",   # ✨ 新增：早上開盤全部訊號
        "10:20": "strategy",
        "12:00": "strategy",
        "13:36": "closing",        # ✨ 修改：改成 13:36 抓最新收盤價
        "17:01": "chips_mtf",      # 原有的多週期分析
        "18:40": "evening_summary" # ✨ 新增：盤後關鍵籌碼與AI總建議
    }
    # 初始化發送狀態
    scheduled_report_sent = {t: False for t in schedule_tasks}

    while True: 
        # 1. 取得準確的台灣時間 (UTC+8)
        now_tw = datetime.utcnow() + timedelta(hours=8)
        now_str = now_tw.strftime('%H:%M')
        weekday = now_tw.weekday() # 0=週一 ~ 6=週日

        # 2. 定義時段狀態
        is_working_day = (0 <= weekday <= 4)
        
        # 機器人清醒時間 (08:50 ~ 19:00) -> 延長到 19:00 以包含 18:40 的報告
        is_active_hours = is_working_day and (8 <= now_tw.hour <= 19)
        
        # 盤中交易時間 (09:00 ~ 13:30) - 只有這時候會掃描突發訊號
        is_trading_hours = is_working_day and (
            (now_tw.hour == 9) or 
            (now_tw.hour > 9 and now_tw.hour < 13) or 
            (now_tw.hour == 13 and now_tw.minute <= 30)
        )

        # 3. 休眠判斷
        if not is_active_hours:
            print(f"\r💤 [{now_str}] 休市中 (Miniko 下班)...", end="")
            # 每日 00:00 重置報告發送狀態
            if now_str == "00:00":
                for t in schedule_tasks: scheduled_report_sent[t] = False
            time.sleep(60) 
            continue 

        # ================= 工作時段邏輯 =================
        status_msg = "交易中" if is_trading_hours else "盤後待命"
        print(f"\r🔄 [{now_str}] {status_msg} - 監控掃描中...", end="")
        
        # --- 🕒 定時報告處理 ---
        if now_str in schedule_tasks and not scheduled_report_sent[now_str]:
            report_type = schedule_tasks[now_str]
            print(f"\n⏰ 時間到 ({now_str})！正在生成 {report_type} 報告...")
            
            report_content = ""
            # 設定標題
            if report_type == "morning_scan":
                report_content = f"🌅 <b>Miniko 09:30 開盤衝鋒掃描</b> 🌅\n<i>(早盤多空力道確認)</i>\n\n"
            elif report_type == "strategy":
                report_content = f"🔔 <b>Miniko {now_str} 盤中戰略推演</b> 🔔\n\n"
            elif report_type == "closing":
                report_content = f"🌇 <b>Miniko 13:36 收盤定心丸</b> 🌇\n<i>(收盤價已確認更新)</i>\n\n"
            elif report_type == "chips_mtf":
                report_content = f"🥡 <b>Miniko 17:01 多週期結構戰報</b> 🥡\n\n"
            elif report_type == "evening_summary":
                report_content = f"🌙 <b>Miniko 18:40 盤後籌碼與AI總建議</b> 🌙\n<i>(主力動向與隔日戰略)</i>\n\n"

            has_data = False

            for code, name in WATCH_LIST.items():
                try:
                    # 基礎日線
                    df_day = get_data(code, period="1y", interval="1d")
                    if df_day is None: continue
                    df_day = calc_indicators(df_day)
                    today = df_day.iloc[-1]
                    prev = df_day.iloc[-2]
                    
                    # 判斷漲跌符號
                    pct = ((today['Close'] - prev['Close']) / prev['Close']) * 100
                    icon = "🔺" if pct > 0 else "💚" if pct < 0 else "➖"
                    
                    report_content += f"<b>📌 {name} ({code})</b> {icon} {today['Close']}\n"
                    
                    # === 09:30 開盤掃描 (看即時訊號 + 量能) ===
                    if report_type == "morning_scan":
                        signals = check_conditions(df_day, code, name)
                        vol_ratio = today['Volume'] / prev['Volume'] if prev['Volume'] > 0 else 0
                        
                        report_content += f"📊 早盤量能: 昨日的 {vol_ratio*100:.1f}%\n"
                        if signals:
                            report_content += f"⚡ 觸發訊號: {' '.join(signals)}\n"
                        else:
                            report_content += f"⚡ 狀態: 觀察中，無特殊訊號\n"

                    # === 10:20 & 12:00 盤中戰略 ===
                    elif report_type == "strategy":
                        strat = analyze_strategy(df_day)
                        report_content += f"🛒 建議買點: {strat['buy_agg']:.1f}(激) / {strat['buy_con']:.1f}(穩)\n"
                        report_content += f"🎲 預估勝率: {strat['win_rate']}%\n"
                        report_content += f"🌊 目前趨勢: {'多頭' if today['Close']>today['MA20'] else '整理/空頭'}\n"

                    # === 13:36 收盤建議 (修正時間版) ===
                    elif report_type == "closing":
                        strat = analyze_strategy(df_day)
                        report_content += f"💰 <b>最終收盤: {today['Close']} ({pct:+.2f}%)</b>\n"
                        report_content += f"🎯 明日佈局: 若回測 {strat['buy_con']:.1f} 可低接\n"
                        report_content += f"📊 停損建議: 跌破 {today['MA20']:.1f} 減碼\n"

                    # === 17:01 多週期 ===
                    elif report_type == "chips_mtf":
                        df_60m = get_data(code, period="1mo", interval="60m")
                        df_60m = calc_indicators(df_60m)
                        k60 = df_60m.iloc[-1]['K'] if df_60m is not None else 50
                        report_content += f"🔸 60分K: KD值 {int(k60)} ({'過熱' if k60>80 else '低檔' if k60<20 else '中性'})\n"
                        report_content += f"🔹 日線趨勢: {'多頭排列' if today['MA20']>today['MA60'] else '整理'}\n"

                    # === 18:40 盤後籌碼與AI總建議 ===
                    elif report_type == "evening_summary":
                        # 1. 籌碼推估 (因為無法抓分點，用價量結構推估主力)
                        vol_status = "量增價漲(主力進場)" if (today['Volume'] > today['Vol_MA5'] and today['Close'] > prev['Close']) else \
                                     "量縮整理(主力惜售)" if (today['Volume'] < today['Vol_MA5'] and abs(pct) < 1) else \
                                     "出貨跡象" if (today['Volume'] > today['Vol_MA5'] and pct < -1) else "中性"
                        
                        # 2. 週線趨勢 (大戶方向)
                        df_week = get_data(code, period="2y", interval="1wk")
                        df_week = calc_indicators(df_week)
                        wk_trend = "長線多頭" if df_week.iloc[-1]['Close'] > df_week.iloc[-1]['MA20'] else "長線保守"

                        # 3. 綜合 AI 建議
                        strat = analyze_strategy(df_day)
                        signals = check_conditions(df_day, code, name)
                        
                        report_content += f"🛡️ <b>籌碼動向(推估)</b>: {vol_status}\n"
                        report_content += f"📅 <b>長線格局</b>: {wk_trend}\n"
                        if signals:
                            report_content += f"🚨 <b>今日訊號總結</b>: {' | '.join(signals)}\n"
                        
                        # 最終一句話
                        ai_msg = "🔥 積極操作" if (strat['win_rate'] >= 80) else \
                                 "✅ 拉回買進" if (strat['win_rate'] >= 60) else \
                                 "⚠️ 觀望/減碼"
                        report_content += f"💡 <b>AI總結</b>: 勝率{strat['win_rate']}% -> {ai_msg}\n"

                    report_content += f"------------------\n"
                    has_data = True
                except Exception as e:
                    # print(f"Error: {e}") 
                    pass
            
            if has_data:
                send_telegram(report_content)
            
            scheduled_report_sent[now_str] = True 
        
        # 每日 08:00 重置所有旗標 (跨日保護)
        if now_str == "08:00": 
            for t in schedule_tasks: scheduled_report_sent[t] = False

        # --- 🔥 [即時] 訊號監控 (限交易時段) ---
        if is_trading_hours:
            for code, name in WATCH_LIST.items():
                try:
                    # 冷卻檢查 (避免一直叫)
                    last_sent_time = alert_history.get(code)
                    if last_sent_time and (datetime.utcnow() - last_sent_time).seconds < 3600:
                        continue

                    df = get_data(code)
                    if df is None: continue
                    df = calc_indicators(df)
                    signals = check_conditions(df, code, name)
                    
                    if signals:
                        today = df.iloc[-1]
                        prev = df.iloc[-2]
                        pct = ((today['Close'] - prev['Close']) / prev['Close']) * 100
                        icon = "🔺" if pct > 0 else "💚" if pct < 0 else "➖"
                        
                        msg = f"🚨 <b>Miniko 盤中訊號快報</b> 🚨\n\n"
                        msg += f"<b>{name} ({code})</b> 觸發條件！\n"
                        msg += f"💰 現價: {today['Close']} {icon} ({pct:+.2f}%)\n"
                        msg += f"📊 量能: {int(today['Volume']/1000)} 張\n"
                        msg += f"---------------------\n"
                        msg += "\n".join([f"{s}" for s in signals])
                        msg += f"\n---------------------\n"
                        msg += f"<i>(觸發時間: {now_str})</i>"
                        
                        send_telegram(msg)
                        alert_history[code] = datetime.utcnow()
                except: pass
            
        time.sleep(30)

if __name__ == "__main__":
    run_monitor()
