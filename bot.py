import time, pandas as pd, ta, requests, datetime, os, sys, threading, numpy as np
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class QuotexMonsterBot:
    """
    بوت الوحش V11.0 (Quotex Pro OTC Edition)
    ======================================
    - رادار زخم خاص بالفوركس (يعوض غياب الحجم في OTC)
    - شروط دخول متوازنة للخيارات الثنائية
    """
    
    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')
        
        if not self.tg_token or not self.tg_chat:
            print("[FATAL ERROR] Missing TELEGRAM_TOKEN or CHAT_ID in .env!")
            return
        
        self.TZ = ZoneInfo("Africa/Tripoli")
        
        self.QUOTEX_WHITELIST = {
            # ======= العملات الرقمية =======
            'BTC/USDT': 'BTCUSD(t)', 'ETH/USDT': 'ETHUSD(t)', 
            'BNB/USDT': 'BNBUSD(t)', 'SOL/USDT': 'SOLUSD(t)',
            'XRP/USDT': 'XRPUSD(t)', 'DOGE/USDT': 'DOGEUSD(t)',
            'LTC/USDT': 'LTCUSD(t)', 'ADA/USDT': 'ADAUSD(t)',
            'MATIC/USDT': 'MATICUSD(t)', 'AVAX/USDT': 'AVAXUSD(t)',
            'DOT/USDT': 'DOTUSD(t)', 'LINK/USDT': 'LINKUSD(t)',
            
            # ======= أزواج الفوركس والـ OTC =======
            'EUR/USD': 'EUR/USD OTC', 'GBP/USD': 'GBP/USD OTC', 
            'USD/JPY': 'USD/JPY OTC', 'AUD/USD': 'AUD/USD OTC', 
            'USD/CAD': 'USD/CAD OTC', 'EUR/GBP': 'EUR/GBP OTC', 
            'NZD/USD': 'NZD/USD OTC', 'EUR/JPY': 'EUR/JPY OTC',
            'GBP/JPY': 'GBP/JPY OTC', 'AUD/CAD': 'AUD/CAD OTC'
        }
        
        self.trade_lock = threading.Lock()
        self.day = None
        self.day_signals = 0
        self.day_wins = 0
        self.day_losses = 0
        self.scan_num = 0
        self.report_time = time.time()
        self.last_signal_time = 0
        self.cooldown_sec = 120 
        
        self.streak_losses = 0
        self.tilt_until = 0
        
        self.stats = {
            'signals_sent': 0, 'scanned': 0, 'no_score': 0, 
            'whale_spotted': 0, 'choppy_blocked': 0, 'tilt_triggered': 0
        }
        
        # تم تعديل الإعدادات لتكون مثالية للثنائيات
        self.CFG = {
            'max_daily_signals': 20,
            'min_score': 4,       # تم تخفيضها من 5 لسرعة الاستجابة
            'score_gap': 1,       # تم تخفيضها من 2 (فارق نقطة واحدة يكفي)
            'loop_sec': 25,
            'summary_every': 1800,
            'tilt_after_losses': 3,
            'tilt_duration_min': 45,
            'whale_level_1': 1.2,
            'whale_level_2': 2.5,
            'whale_level_3': 4.0,
            'min_bb_width_pct': 0.03 # تم تخفيضها لتتناسب مع فوركس
        }
        
        self.tg("🔄 جاري التشغيل وضبط التوقيت...")
        self.tg(f"✅ تم الربط بنجاح! التوقيت الحالي: {self._get_time()}")
        
        msg  = "🐋 *بوت الوحش V11.0 (Pro OTC)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"🕐 التوقيت: ليبيا (GMT+2)\n"
        msg += f"📋 مراقبة {len(self.QUOTEX_WHITELIST)} زوج\n"
        msg += "⚡ رادار الزخم (Momentum) مفعّل للـ OTC\n"
        msg += "🚫 فلتر التذبذب مفعّل"
        self.tg(msg)

    def _get_time(self):
        return datetime.datetime.now(self.TZ).strftime("%H:%M:%S")

    def tg(self, msg):
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'}
            )
        except: pass

    def log(self, msg_en, notify=False, msg_ar=None):
        ts = self._get_time()
        print(f"[{ts}] {msg_en}") 
        if notify:
            self.tg(msg_ar if msg_ar else msg_en)

    # ================================================================
    #              API & DATA
    # ================================================================
    
    def _fetch_ticker(self, sym):
        base, quote = sym.split('/')
        url = f"https://min-api.cryptocompare.com/data/price?fsym={base}&tsyms={quote}"
        try:
            r = requests.get(url, timeout=5)
            d = r.json()
            price = d.get(quote, 0)
            if price > 0: return {'last': price}
        except: pass
        return None

    def _fetch_ohlcv(self, sym, limit=300):
        base, quote = sym.split('/')
        url = "https://min-api.cryptocompare.com/data/v2/histominute"
        params = {'fsym': base, 'tsym': quote, 'limit': limit}
        try:
            r = requests.get(url, params=params, timeout=10)
            d = r.json()
            if d.get('Response') == 'Success':
                raw = d.get('Data', {}).get('Data', [])
                formatted = [[c['time']*1000, c['open'], c['high'], c['low'], c['close'], c['volumeto']] for c in raw]
                df = pd.DataFrame(formatted, columns=['t','o','h','l','c','v'])
                if len(df) >= limit: return df
        except: pass
        return None

    def _get_data(self, sym):
        df_raw = self._fetch_ohlcv(sym, 300)
        if df_raw is None: return None, None
        
        df_1m = df_raw.iloc[-60:] 
        
        try:
            df_raw['ts'] = pd.to_datetime(df_raw['t'], unit='ms')
            df_5m = df_raw.set_index('ts').resample('5min').agg({
                'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last', 'v': 'sum'
            }).dropna().reset_index()
            df_5m['t'] = df_5m['index'].astype(np.int64) // 10**6
            df_5m = df_5m.iloc[-60:]
        except:
            df_5m = None
            
        return df_1m, df_5m
    
    # ================================================================
    #     🧠 الاستراتيجية المتطورة (كريبتو + OTC)
    # ================================================================
    
    def _score_binary(self, sym):
        df_1m, df_5m = self._get_data(sym)
        if df_1m is None or df_5m is None: return None, "No Data", 0, False
        
        df_1m['ema9'] = ta.trend.ema_indicator(df_1m['c'], 9)
        df_1m['ema21'] = ta.trend.ema_indicator(df_1m['c'], 21)
        df_1m['rsi'] = ta.momentum.rsi(df_1m['c'], 14)
        df_1m['macd'] = ta.trend.macd_diff(df_1m['c'])
        
        df_5m['ema50'] = ta.trend.ema_indicator(df_5m['c'], 50)
        
        bb = ta.volatility.BollingerBands(df_5m['c'], 20, 2)
        df_5m['bb_width'] = (bb.bollinger_hband() - bb.bollinger_lband()) / bb.bollinger_mavg() * 100
        
        cur = df_1m.iloc[-1]; prev = df_1m.iloc[-2]; cur_5m = df_5m.iloc[-1]
        
        if not pd.isna(cur_5m['bb_width']) and cur_5m['bb_width'] < self.CFG['min_bb_width_pct']:
            self.stats['choppy_blocked'] += 1
            return None, "Choppy Market", 0, False
            
        L, S = 0, 0; LR, SR = [], []
        is_whale = False
        
        # 1. الاتجاه العام
        if not pd.isna(cur_5m['ema50']):
            if cur_5m['c'] > cur_5m['ema50']: L += 2; LR.append("5M_UP")
            else: S += 2; SR.append("5M_DN")
        
        # 2. تقاطع EMA
        ema_ok = all(not pd.isna(x) for x in [cur['ema9'], cur['ema21'], prev['ema9'], prev['ema21']])
        if ema_ok:
            if prev['ema9'] <= prev['ema21'] and cur['ema9'] > cur['ema21']: L += 3; LR.append("CROSS_UP")
            elif prev['ema9'] >= prev['ema21'] and cur['ema9'] < cur['ema21']: S += 3; SR.append("CROSS_DN")
            elif cur['ema9'] > cur['ema21']: L += 1
            else: S += 1
            
        # 3. RSI (تم رفع النقاط في مناطق الاشباع)
        if not pd.isna(cur['rsi']):
            if cur['rsi'] < 25: L += 3; LR.append(f"RSI_{cur['rsi']:.0f}")
            elif cur['rsi'] < 35: L += 2; LR.append(f"RSI_{cur['rsi']:.0f}")
            elif cur['rsi'] > 75: S += 3; SR.append(f"RSI_{cur['rsi']:.0f}")
            elif cur['rsi'] > 65: S += 2; SR.append(f"RSI_{cur['rsi']:.0f}")
            elif 40 <= cur['rsi'] < 50: L += 1
            elif 50 < cur['rsi'] <= 60: S += 1
            
        # 4. MACD
        if not pd.isna(cur['macd']) and not pd.isna(prev['macd']):
            if cur['macd'] > 0 and cur['macd'] > prev['macd']: L += 1
            elif cur['macd'] < 0 and cur['macd'] < prev['macd']: S += 1
            
        # 5. قوة الشمعة (Price Action)
        body = abs(cur['c'] - cur['o']); rng = cur['h'] - cur['l']
        if rng > 0 and (body / rng) > 0.7:
            if cur['c'] > cur['o']: L += 2; LR.append("STRONG_BULL")
            else: S += 2; SR.append("STRONG_BEAR")
        elif rng > 0 and (body / rng) > 0.5:
            if cur['c'] > cur['o']: L += 1; LR.append("BULL_CAND")
            else: S += 1; SR.append("BEAR_CAND")
        
        # ===== ⚡ 6. رادار الزخم / الحيتان (ذكاء مزدوج) =====
        df_1m['vm'] = df_1m['v'].rolling(20).mean()
        if not pd.isna(cur['vm']) and cur['vm'] > 0:
            # للعملات الرقمية (يعتمد على الحجم)
            vol_ratio = cur['v'] / cur['vm']
            if vol_ratio >= self.CFG['whale_level_3']: is_whale = True
            elif vol_ratio >= self.CFG['whale_level_2']: is_whale = True
            elif vol_ratio >= self.CFG['whale_level_1']: pass
            
            if is_whale:
                pts = 4 if vol_ratio >= self.CFG['whale_level_3'] else 3
                if cur['c'] > cur['o']: L += pts; LR.append(f"🐋WHALE_{vol_ratio:.0f}x")
                else: S += pts; SR.append(f"🐋WHALE_{vol_ratio:.0f}x")
        else:
            # للفوركس و OTC (يعتمد على طول الشمعة كزخم حاد)
            df_1m['range'] = df_1m['h'] - df_1m['l']
            avg_range = df_1m['range'].rolling(20).mean()
            cur_range = cur['h'] - cur['l']
            avg_rng_val = avg_range.iloc[-1]
            
            if not pd.isna(avg_rng_val) and avg_rng_val > 0:
                momentum_ratio = cur_range / avg_rng_val
                if momentum_ratio >= 2.5: 
                    is_whale = True
                    if cur['c'] > cur['o']: L += 3; LR.append(f"⚡MOM_{momentum_ratio:.1f}x")
                    else: S += 3; SR.append(f"⚡MOM_{momentum_ratio:.1f}x")
                elif momentum_ratio >= 1.8:
                    if cur['c'] > cur['o']: L += 2; LR.append(f"MOM_{momentum_ratio:.1f}x")
                    else: S += 2; SR.append(f"MOM_{momentum_ratio:.1f}x")
        
        if is_whale: self.stats['whale_spotted'] += 1
        
        min_pts = self.CFG['min_score']; gap = self.CFG['score_gap']
        
        duration = 5
        if is_whale: duration = 1
        if "CROSS" in str(LR) or "CROSS" in str(SR): duration = 3
        
        if L >= min_pts and (L - S) >= gap: 
            return 'CALL', f"L:{L} S:{S} | " + "+".join(LR[:3]), duration, is_whale
        elif S >= min_pts and (S - L) >= gap: 
            return 'PUT', f"L:{L} S:{S} | " + "+".join(SR[:3]), duration, is_whale
            
        self.stats['no_score'] += 1
        return None, f"L:{L} S:{S}", 0, False

    # ================================================================
    #             إدارة الإشارات و التحقق الذاتي
    # ================================================================

    def _send_signal(self, b_sym, q_sym, direction, reason, duration, is_whale):
        price = 0
        ticker = self._fetch_ticker(b_sym)
        if ticker: price = ticker['last']
        
        self.stats['signals_sent'] += 1
        self.last_signal_time = time.time()
        
        with self.trade_lock:
            self.day_signals += 1
            
        icon = "🟢" if direction == 'CALL' else "🔴"
        whale_tag = "\n⚡ زخم حاد / حوت!" if is_whale else ""
        
        now_libya = datetime.datetime.now(self.TZ)
        expiry_time = now_libya + datetime.timedelta(minutes=duration)
        expiry_str = expiry_time.strftime("%H:%M:%S")
        time_now_str = now_libya.strftime("%H:%M:%S")
        
        msg  = f"🚀 *إشارة كوتكس (Quotex)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"🪙 الزوج: *{q_sym}*\n"
        msg += f"📊 الاتجاه: *{direction}* {icon}\n"
        msg += f"⏱️ وقت الإشارة: {time_now_str}\n"
        msg += f"⌛ وقت الانتهاء: *{expiry_str} (توقيت ليبيا)*\n"
        msg += f"💵 سعر الدخول: `{price}`\n"
        msg += f"🧠 الأسباب: `{reason}`{whale_tag}\n"
        msg += "━━━━━━━━━━━━━━━━"
        
        self.tg(msg)
        threading.Thread(target=self._validate_signal_outcome, args=(b_sym, direction, price, duration), daemon=True).start()

    def _validate_signal_outcome(self, sym, direction, entry_price, duration):
        time.sleep(duration * 60)
        ticker = self._fetch_ticker(sym)
        if not ticker or entry_price == 0: return
        
        current_price = ticker['last']
        is_win = False
        if direction == 'CALL' and current_price > entry_price: is_win = True
        if direction == 'PUT' and current_price < entry_price: is_win = True
        
        self.log(f"Validation: {sym} {direction} -> {'WIN ✅' if is_win else 'LOSS ❌'}")
        
        with self.trade_lock:
            if is_win:
                self.day_wins += 1
                self.streak_losses = 0
            else:
                self.day_losses += 1
                self.streak_losses += 1
                
                if self.streak_losses >= self.CFG['tilt_after_losses']:
                    self.tilt_until = time.time() + (self.CFG['tilt_duration_min'] * 60)
                    self.stats['tilt_triggered'] += 1
                    self.tg(f"🛡️ *Anti-Tilt مفعّل!* \nإيقاف الإشارات لمدة {self.CFG['tilt_duration_min']} دقيقة.")

    # ================================================================
    #                         MAIN RUN LOOP
    # ================================================================
    
    def _report(self):
        total = self.day_wins + self.day_losses
        win_rate = (self.day_wins / total * 100) if total > 0 else 0
        msg  = "📊 *تقرير إشارات اليوم (توقيت ليبيا)*\n"
        msg += f"🔍 فحص: {self.stats['scanned']} | مرفوضة (ضعيفة): {self.stats['no_score']}\n"
        msg += f"🚀 إشارات مُرسلة: {self.day_signals}/{self.CFG['max_daily_signals']}\n"
        msg += f"🏆 نسبة الربح: {win_rate:.1f}% ({self.day_wins}W / {self.day_losses}L)\n"
        msg += f"⚡ زخم/حيتان: {self.stats['whale_spotted']} | تذبذب: {self.stats['choppy_blocked']}\n"
        msg += f"🛡️ إيقاف (Tilt): {self.stats['tilt_triggered']}"
        self.tg(msg)

    def run(self):
        self.tg("🐋 *مسار الصيد بدأ!*")
        self.log("HUNTER STARTED", notify=True, msg_ar="🏹 جاري مراقبة الأسواق!")
        
        while True:
            try:
                today = datetime.datetime.now(self.TZ).date()
                if self.day != today:
                    if self.day is not None and self.day_signals > 0: self._report()
                    with self.trade_lock:
                        self.day = today; self.day_signals = 0; self.day_wins = 0; self.day_losses = 0
                        self.stats = {k: 0 for k in self.stats}
                        self.streak_losses = 0; self.tilt_until = 0
                    self.log("NEW DAY RESET", notify=True, msg_ar="📅 يوم جديد، تم تصفير الإحصائيات!")
                
                if self.day_signals >= self.CFG['max_daily_signals']:
                    time.sleep(600); continue
                
                if time.time() < self.tilt_until:
                    time.sleep(60); continue
                
                if time.time() - self.last_signal_time < self.cooldown_sec:
                    time.sleep(10); continue
                
                self.scan_num += 1
                found = False
                
                for b_sym, q_sym in self.QUOTEX_WHITELIST.items():
                    self.stats['scanned'] += 1
                    
                    direction, reason, duration, is_whale = self._score_binary(b_sym)
                    
                    if direction:
                        self.log(f"SIGNAL FOUND: {q_sym} {direction} | {reason}")
                        self._send_signal(b_sym, q_sym, direction, reason, duration, is_whale)
                        found = True
                        break
                    
                    time.sleep(1) 
                
                if not found and self.scan_num % 5 == 0: 
                    self.log(f"SCAN #{self.scan_num} | No Signals | Scanned: {self.stats['scanned']}")
                    
                # إيقاف الرسائل المزعجة: يرسل تقرير فقط إذا كان هناك إشارات، أو رسالة مختصرة
                if time.time() - self.report_time >= self.CFG['summary_every']:
                    if self.day_signals > 0:
                        self._report()
                    else:
                        self.tg(f"📊 يعمل بنشاط | فحص: {self.stats['scanned']} زوج | مرفوضة: {self.stats['no_score']} | تذبذب: {self.stats['choppy_blocked']}")
                    self.report_time = time.time()
                    
            except Exception as e: 
                self.log(f"HUNTER ERR: {e}")
                time.sleep(15)
            
            time.sleep(self.CFG['loop_sec'])

if __name__ == "__main__":
    bot = QuotexMonsterBot()
    if bot.tg_token:
        bot.run()
