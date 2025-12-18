def check_miniko_strategy(stock_id, df):
    """
    Miniko AI 綜合選股策略 (V25.0 咕嚕咕嚕版)
    """
    # 取得最近幾天的數據
    today = df.iloc[-1]
    prev = df.iloc[-2]     # 昨天
    prev_2 = df.iloc[-3]   # 前天 (用來確認趨勢)

    # -----------------------------------------------------------
    # 先決條件檢查：成交量濾網 (Volume Filter)
    # -----------------------------------------------------------
    # 計算 5 日均量
    vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
    
    # 判定是否為「爆量股」：今天量 > 5日均量的 1.5 倍 (數值可調整)
    is_volume_surge = today['Volume'] > (vol_ma5 * 1.5)
    
    # 如果這檔股票既不在前100大，也沒有爆量，這裡可以直接過濾 (視您的資料源而定)
    # 但因為您說「都要抓進來分析」，我們繼續往下跑策略
    
    # -----------------------------------------------------------
    # 條件一：Miniko 的盤感 (底部咕嚕咕嚕 OR 高檔強勢整理)
    # -----------------------------------------------------------
    condition_a = False
    reason_a = ""

    # A-1: 底部咕嚕咕嚕 (蓄勢待發)
    # 邏輯：K值在低檔(<40)，且股價變動不大(收盤價在 5日均線附近震盪)，看似平靜其實在冒泡
    is_low_kd = today['K'] < 40 and today['D'] < 40
    # 判斷股價是否有撐 (今天收盤 沒有跌破 過去5天最低點)
    recent_low = df['Close'].rolling(5).min().iloc[-1]
    is_supported = today['Close'] >= recent_low 
    
    if is_low_kd and is_supported:
        condition_a = True
        reason_a = "底部咕嚕咕嚕 (KD低檔蓄勢)"

    # A-2: 高檔盤整 (KD回落但價穩)
    # 邏輯：前幾天K值很高(>70)，現在回落到(30-55)，但股價跌幅很小
    # 找過去10天K值的最高點
    max_k_recent = df['K'].rolling(10).max().iloc[-1]
    # 價格變動率 (現在價格 vs 5天前價格)
    price_change_5d = (today['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]
    
    if (max_k_recent > 70) and (30 <= today['K'] <= 58) and (price_change_5d > -0.04):
        # K值從高點下來了，現在在中位數，且股價跌幅小於 4% (強勢整理)
        condition_a = True
        reason_a = "高檔強勢整理 (指標修正價不跌)"

    # -----------------------------------------------------------
    # 條件二：標準 SOP (MACD + SAR + KD金叉)
    # -----------------------------------------------------------
    condition_b = False
    
    # 1. MACD OSC (柱狀體) 由負轉正 (翻紅)
    # DIF = EMA12 - EMA26, MACD = EMA9(DIF), OSC = DIF - MACD
    macd_flip = (prev['MACD_Hist'] < 0) and (today['MACD_Hist'] > 0)
    
    # 2. SAR 多方 (收盤價 > SAR值)
    sar_bull = today['Close'] > today['SAR']
    
    # 3. KD 黃金交叉 (K 突破 D)
    # 允許今天或昨天發生交叉都算 (避免太嚴苛)
    kd_cross_today = (prev['K'] < prev['D']) and (today['K'] > today['D'])
    kd_cross_yest = (df.iloc[-3]['K'] < df.iloc[-3]['D']) and (prev['K'] > prev['D'])
    kd_gold = kd_cross_today or kd_cross_yest

    if macd_flip and sar_bull and kd_gold:
        condition_b = True

    # -----------------------------------------------------------
    # 最終判斷 (二擇一)
    # -----------------------------------------------------------
    final_reasons = []
    
    if condition_a:
        final_reasons.append(f"【型態符合】{reason_a}")
    if condition_b:
        final_reasons.append("【訊號符合】MACD翻紅+SAR多方+KD金叉")
    
    # 只要有爆量，我們也把它標記出來，當作加分項
    if is_volume_surge:
         final_reasons.append("【資金湧入】成交量爆量突增")

    # 決策：(條件A OR 條件B) 成立即可
    # 補充：如果只是單純爆量但型態不對，通常不視為買點，但您可以決定是否要看
    if (condition_a or condition_b):
        return True, " + ".join(final_reasons)
    else:
        return False, ""

# -----------------------------------------------------------
# 執行掃描 (模擬)
# -----------------------------------------------------------
print("Miniko AI 全力掃描中...")
# 這裡放入您的股票池 (前100大 + 爆量股)
# for stock in stock_list:
#     hit, reason = check_miniko_strategy(stock, data)
#     if hit:
#         print(f"抓到！{stock} : {reason}")
