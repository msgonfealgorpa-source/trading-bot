import ccxt, time, pandas as pd, ta, requests, datetime, os, sys, threading

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class SmartBot:
    """
    بوت الوحش V11.1 (Fast Entry Edition)
    =======================================
    التحديثات:
    - دخول سريع: رصد الحركة أثناء الشمعة وليس بعدها
    - Trailing Stop محسن: أبطأ وأذكى
    - أولوية للحيتان: فحصهم أولاً
    """
    
    def __init__(self):
        self.api_key = os.environ.get('API_KEY')
        self.api_secret = os.environ.get('API_SECRET')
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')
        
        if not all([self.api_key, self.api_secret, self.tg_token]):
            print("[FATAL ERROR] Missing API Keys!")
            return
        
        self.exchange = ccxt.bingx({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
        
        self.trade_lock = threading.Lock()
        self.active_trade = None
        self.day = None
        self.day_trades = 0
        self.day_pnl = 0.0
        self.scan_num = 0
        self.report_time = time.time()
        self.last_scan_summary = time.time()
        
        self.streak_wins = 0
        self.streak_losses = 0
        self.tilt_until = 0
        self.is_aggressive = False
        
        # ذاكرة مؤقتة للعملات المرشحة
        self.hot_pairs = {}  # {sym: {'score': x, 'dir': 'long', 'time': t}}
        self.whale_alerts = {}  # {sym: {'time': t, 'dir': 'long'}}
        
        self.stats = {
            'wins': 0, 'losses': 0, 'timeouts': 0, 
            'scanned': 0, 'no_score': 0, 'qty_zero': 0, 
            'order_fail': 0, 'tilt_triggered': 0, 'slippage_blocked': 0,
            'whale_spotted': 0,
            'fast_entries': 0,  # دخول سريع
            'trail_adjustments': 0  # تعديلات التتبع
        }
        
        self.CFG = {
            'max_daily': 10,
            'leverage': 10,
            'base_risk_pct': 5.0,
            'sl_mult': 1.5,
            'tp_mult': 2.5,
            'min_score': 4,
            'score_gap': 2,
            'cooldown_sec': 300,
            'partial_at': 1.5,
            'trail_after': 2.0,  # ✅ تم التعديل من 1.0 إلى 2.0
            'max_hold_min': 120,
            'vol_filter': 500000,
            'max_scan': 40,
            'loop_sec': 10,  # ✅ تم التسريع من 20 إلى 10 ثواني
            'summary_every': 1800,
            # ======= إعدادات التطور والحماية =======
            'tilt_after_losses': 2,
            'tilt_duration_min': 60,
            'aggression_after_wins': 3,
            'aggression_risk_boost': 2.0,
            'vol_multiplier_danger': 2.0,
            'max_slippage_pct': 0.5,
            # ======= إعدادات رادار الحيتان =======
            'whale_level_1': 1.5,
            'whale_level_2': 3.0,
            'whale_level_3': 5.0,
            # ======= ✅ إعدادات جديدة للدخول السريع =======
            'hot_pair_expire': 120,  # مدة بقاء الزوج الساخن (ثانية)
            'whale_priority': True,  # أولوية الحيتان
            'early_entry_pct': 0.3,  # الدخول بعد 30% من الشمعة
            'trail_step': 0.15,  # ✅ خطوة التتبع 0.15% بدلاً من 0.01
            'trail_min_move': 0.5,  # ✅ أقل حركة لتعديل SL
        }
        
        self.tg("🔄 جاري التشغيل...")
        self.active_trade = self._load_position()
        self.exchange.load_markets()
        
        bal = self._balance()
        msg  = "🐋 *بوت الوحش V11.1 (Fast Entry)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "⚡ دخول سريع (أثناء الشمعة)\n"
        msg += "🐢 Trailing محسن (أبطأ)\n"
        msg += "🐋 أولوية الحيتان\n"
        msg += "🛡️ حماية من الانزلاق\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"💳 رصيد: {bal} USDT"
        self.tg(msg)
        
        if self.active_trade:
            self.tg(f"🧠 استئناف: {self.active_trade['dir']} {self.active_trade['sym']}")

    def tg(self, msg):
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'}
            )
        except: pass

    def log(self, msg_en, notify=False, msg_ar=None):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg_en}") 
        if notify:
            self.tg(msg_ar if msg_ar else msg_en)
    
    def fmt(self, val, decimals=6):
        if val == 0: return "0"
        return f"{val:.{decimals}g}"
    
    # ================================================================
    #                         API & ORDERS
    # ================================================================
    
    def _api(self, method, *args, **kwargs):
        for i in range(3):
            try: return getattr(self.exchange, method)(*args, **kwargs)
            except Exception as e:
                self.log(f"API Retry {method}: {str(e)[:50]}")
                time.sleep(3 * (i + 1))
        return None
    
    def _balance(self):
        b = self._api('fetch_balance', {'type': 'swap'})
        return float(b.get('USDT', {}).get('free', 0)) if b else 0
    
    def _tickers(self): return self._api('fetch_tickers')
    def _ticker(self, sym): return self._api('fetch_ticker', sym)
    def _ohlcv(self, sym, tf, limit=60): return self._api('fetch_ohlcv', sym, tf, limit=limit)
    
    def _df(self, sym, tf, limit=60):
        data = self._ohlcv(sym, tf, limit)
        if not data or len(data) < limit: return None
        return pd.DataFrame(data, columns=['t','o','h','l','c','v'])
    
    def _set_lev(self, sym, pos_side='LONG'):
        try:
            self.exchange.set_leverage(self.CFG['leverage'], sym, params={'marginMode': 'isolated', 'positionSide': pos_side})
        except: pass

    def _order(self, side, sym, qty, pos_side=None):
        fn = f'create_market_{side}_order'
        params = {'positionSide': pos_side} if pos_side else {}
        try:
            o = getattr(self.exchange, fn)(sym, qty, params=params)
            if o and o.get('id'):
                self.log(f"ORDER OK: {o['id']}", notify=True, msg_ar=f"✅ تنفيذ: {o['id']}")
                return o
        except ccxt.errors.InsufficientFunds:
            self.log("ORDER FAIL: No Funds", notify=True, msg_ar="❌ رصيد غير كافي!")
            self.stats['order_fail'] += 1
            return None
        except ccxt.errors.ExchangeError as e:
            self.log(f"ORDER FAIL: {str(e)[:60]}", notify=True, msg_ar=f"❌ خطأ منصة")
            self.stats['order_fail'] += 1
            return None
        except Exception as e:
            self.log(f"ORDER FAIL: {str(e)[:60]}")
            self.stats['order_fail'] += 1
            return None
        self.stats['order_fail'] += 1
        return None
    
    def _load_position(self):
        try:
            positions = self._api('fetch_positions')
            if positions:
                for p in positions:
                    qty = float(p.get('position', p.get('contracts', 0)))
                    if qty > 0:
                        sym = p['symbol']; entry = float(p['entryPrice'])
                        d = 'short' if p.get('positionSide', '').lower() == 'short' else 'long'
                        return {'sym': sym, 'dir': d, 'entry': entry, 'qty': qty, 'time': time.time(), 'strategy': 'استئناف', 'partial': True, 'sl': entry * (0.97 if d == 'long' else 1.03), 'tp': 0, 'trail_active': False, 'highest_pct': 0}
        except: pass
        return None

    # ================================================================
    #               🚫 حماية الانزلاق والتطور
    # ================================================================

    def _check_slippage(self, sym, signal_price):
        ticker = self._ticker(sym)
        if not ticker: return True
        diff_pct = abs(ticker['last'] - signal_price) / signal_price * 100
        if diff_pct > self.CFG['max_slippage_pct']:
            self.stats['slippage_blocked'] += 1
            self.log(f"SLIPPAGE BLOCKED: {diff_pct:.2f}%", notify=True, msg_ar=f"🚫 انزلاق محظور! فرق {diff_pct:.2f}%")
            return False
        return True

    def _evolve_after_close(self, is_win):
        if is_win:
            self.streak_wins += 1; self.streak_losses = 0
            if self.streak_wins >= self.CFG['aggression_after_wins'] and not self.is_aggressive:
                self.is_aggressive = True
                self.tg(f"⚡ *وضع الاستغلال!* مخاطرة {self.CFG['base_risk_pct'] + self.CFG['aggression_risk_boost']}%")
        else:
            self.streak_losses += 1; self.streak_wins = 0
            if self.is_aggressive: self.is_aggressive = False
            if self.streak_losses >= self.CFG['tilt_after_losses']:
                self.tilt_until = time.time() + (self.CFG['tilt_duration_min'] * 60)
                self.stats['tilt_triggered'] += 1
                self.tg(f"🛡️ *Anti-Tilt* إيقاف {self.CFG['tilt_duration_min']} دقيقة")

    def _get_dynamic_risk(self, sym, atr):
        risk = self.CFG['base_risk_pct']
        if self.is_aggressive: risk += self.CFG['aggression_risk_boost']
        try:
            df = self._df(sym, '1h', 50)
            if df is not None:
                atr_s = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
                if not pd.isna(atr_s.iloc[-1]) and not pd.isna(atr_s.iloc[-20:].mean()) and atr_s.iloc[-20:].mean() > 0:
                    if (atr_s.iloc[-1] / atr_s.iloc[-20:].mean()) >= self.CFG['vol_multiplier_danger']: risk *= 0.6
        except: pass
        return risk

    def _calc_qty(self, sym, price, atr):
        bal = self._balance()
        if bal <= 0: return 0
        sl_dist = self.CFG['sl_mult'] * atr
        if sl_dist <= 0: return 0
        qty = (bal * (self._get_dynamic_risk(sym, atr) / 100)) / sl_dist
        try:
            fq = self.exchange.amount_to_precision(sym, qty)
            mn = self.exchange.market(sym).get('limits', {}).get('amount', {}).get('min')
            if mn and float(fq) < float(mn): fq = self.exchange.amount_to_precision(sym, float(mn) * 1.1)
            return float(fq) if float(fq) > 0 else 0
        except: return 0
    
    def _pnl_pct(self, entry, current, direction):
        return ((current - entry) / entry) * 100 if direction == 'long' else ((entry - current) / entry) * 100

    # ================================================================
    #     ⚡ الدخول السريع: رصد أثناء الشمعة بدلاً من بعدها
    # ================================================================
    
    def _candle_progress(self, sym, tf='15m'):
        """حساب نسبة اكتمال الشمعة الحالية"""
        try:
            tf_minutes = {'1m': 1, '5m': 5, '15m': 15, '1h': 60, '4h': 240}
            minutes = tf_minutes.get(tf, 15)
            now = datetime.datetime.now()
            elapsed = now.minute % minutes + now.second / 60
            return elapsed / minutes
        except:
            return 1.0
    
    def _is_whale_realtime(self, sym):
        """✅ فحص الحوت في الوقت الحقيقي (أثناء الشمعة)"""
        try:
            ticker = self._ticker(sym)
            if not ticker: return None, 0, 0, "No Ticker"
            
            df = self._df(sym, '15m', 60)
            df_h = self._df(sym, '1h', 50)
            if df is None or df_h is None: return None, 0, 0, "No Data"
            
            df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
            df['vm'] = df['v'].rolling(20).mean()
            
            cur = df.iloc[-1]
            atr = cur['atr']
            if pd.isna(atr) or atr <= 0: return None, 0, 0, "ATR N/A"
            
            # ✅ الحجم الحالي من التicker (أثناء الشمعة)
            current_vol = ticker.get('baseVolume', 0)
            if current_vol <= 0: return None, 0, 0, "No Vol"
            
            avg_vol = cur['vm'] if not pd.isna(cur['vm']) and cur['vm'] > 0 else 0
            if avg_vol <= 0: return None, 0, 0, "No Avg Vol"
            
            vol_ratio = current_vol / avg_vol
            
            # ✅ فقط إذا كان الحجم مرتفعاً بشكل واضح
            if vol_ratio < self.CFG['whale_level_1']:
                return None, 0, 0, f"VOL_{vol_ratio:.1f}x"
            
            # ✅ تحديد الاتجاه من حركة السعر الحالية
            price = ticker['last']
            candle_open = cur['o']
            price_move = (price - candle_open) / candle_open * 100
            
            # ✅ الحد الأدنى للحركة (0.2% على الأقل)
            if abs(price_move) < 0.2:
                return None, 0, 0, f"NO_MOVE_{price_move:.2f}%"
            
            # ✅ تحديد الاتجاه
            direction = 'long' if price_move > 0 else 'short'
            
            # ✅ تقييم قوة الحوت
            if vol_ratio >= self.CFG['whale_level_3']:
                reason = f"🐋MEGA_{vol_ratio:.0f}x|{price_move:+.2f}%"
                self.stats['whale_spotted'] += 1
                return direction, price, atr, reason
            elif vol_ratio >= self.CFG['whale_level_2']:
                reason = f"🐋WHALE_{vol_ratio:.0f}x|{price_move:+.2f}%"
                self.stats['whale_spotted'] += 1
                return direction, price, atr, reason
            elif vol_ratio >= self.CFG['whale_level_1'] * 1.2:  # 1.8x للحجم العادي
                reason = f"🐋FLOW_{vol_ratio:.1f}x|{price_move:+.2f}%"
                self.stats['whale_spotted'] += 1
                return direction, price, atr, reason
            
            return None, 0, 0, f"VOL_{vol_ratio:.1f}x"
            
        except Exception as e:
            self.log(f"Realtime whale check err: {str(e)[:40]}")
            return None, 0, 0, "Error"

    # ================================================================
    #          🐋 الاستراتيجية: نظام النقاط + رادار الحيتان
    # ================================================================
    
    def _score(self, sym):
        df = self._df(sym, '15m', 60)
        df_h = self._df(sym, '1h', 50)
        if df is None or df_h is None: return None, 0, 0, "Data N/A"
        
        df['ema9'] = ta.trend.ema_indicator(df['c'], 9)
        df['ema21'] = ta.trend.ema_indicator(df['c'], 21)
        df['rsi'] = ta.momentum.rsi(df['c'], 14)
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
        df['vm'] = df['v'].rolling(20).mean()
        df['macd'] = ta.trend.macd_diff(df['c'])
        df_h['ema50'] = ta.trend.ema_indicator(df_h['c'], 50)
        
        cur = df.iloc[-1]; prev = df.iloc[-2]; cur_h = df_h.iloc[-1]
        atr = cur['atr']
        if pd.isna(atr) or atr <= 0: return None, 0, 0, "ATR N/A"
        
        L, S = 0, 0; LR, SR = [], []
        
        # 1. اتجاه الساعة
        if not pd.isna(cur_h['ema50']):
            if cur_h['c'] > cur_h['ema50']: L += 2; LR.append("1H_UP")
            else: S += 2; SR.append("1H_DN")
        
        # 2. تقاطع EMA
        ema_ok = all(not pd.isna(x) for x in [cur['ema9'], cur['ema21'], prev['ema9'], prev['ema21']])
        if ema_ok:
            if prev['ema9'] <= prev['ema21'] and cur['ema9'] > cur['ema21']: L += 2; LR.append("CROSS_UP")
            elif prev['ema9'] >= prev['ema21'] and cur['ema9'] < cur['ema21']: S += 2; SR.append("CROSS_DN")
            elif cur['ema9'] > cur['ema21']: L += 1
            else: S += 1
        
        # 3. RSI
        if not pd.isna(cur['rsi']):
            if cur['rsi'] < 35: L += 2; LR.append(f"RSI_{cur['rsi']:.0f}")
            elif cur['rsi'] > 65: S += 2; SR.append(f"RSI_{cur['rsi']:.0f}")
            elif 40 <= cur['rsi'] < 50: L += 1
            elif 50 < cur['rsi'] <= 60: S += 1
        
        # 4. MACD
        if not pd.isna(cur['macd']) and not pd.isna(prev['macd']):
            if cur['macd'] > 0 and cur['macd'] > prev['macd']: L += 1
            elif cur['macd'] < 0 and cur['macd'] < prev['macd']: S += 1
        
        # 5. شمعة قوية
        body = abs(cur['c'] - cur['o']); rng = cur['h'] - cur['l']
        if rng > 0 and (body / rng) > 0.5:
            if cur['c'] > cur['o']: L += 1; LR.append("BULL_CAND")
            else: S += 1; SR.append("BEAR_CAND")
        
        # ===== 🐋 6. رادار الحيتان =====
        is_whale = False
        if not pd.isna(cur['vm']) and cur['vm'] > 0:
            vol_ratio = cur['v'] / cur['vm']
            
            if vol_ratio >= self.CFG['whale_level_3']:
                is_whale = True
                if cur['c'] > cur['o']: L += 4; LR.append(f"🐋WHALE_{vol_ratio:.0f}x")
                else: S += 4; SR.append(f"🐋WHALE_{vol_ratio:.0f}x")
            elif vol_ratio >= self.CFG['whale_level_2']:
                is_whale = True
                if cur['c'] > cur['o']: L += 3; LR.append(f"🐋WHALE_{vol_ratio:.0f}x")
                else: S += 3; SR.append(f"🐋WHALE_{vol_ratio:.0f}x")
            elif vol_ratio >= self.CFG['whale_level_1']:
                if cur['c'] > cur['o']: L += 1; LR.append(f"VOL_{vol_ratio:.1f}x")
                else: S += 1; SR.append(f"VOL_{vol_ratio:.1f}x")
        
        if is_whale:
            self.stats['whale_spotted'] += 1
        
        min_pts = self.CFG['min_score']; gap = self.CFG['score_gap']
        
        if L >= min_pts and (L - S) >= gap: return 'long', cur['c'], atr, f"L:{L} S:{S} | " + "+".join(LR[:3]), is_whale
        elif S >= min_pts and (S - L) >= gap: return 'short', cur['c'], atr, f"L:{L} S:{S} | " + "+".join(SR[:3]), is_whale
        
        self.stats['no_score'] += 1
        return None, 0, 0, f"L:{L} S:{S}", False
    
    def _ny_signal(self, sym):
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        ny_h = 13 if datetime.datetime(now.year, 3, 14) <= now <= datetime.datetime(now.year, 11, 7) else 14
        ny_time = now.replace(hour=ny_h, minute=30, second=0, microsecond=0)
        if now < ny_time: return None, 0, 0, "Pre-NY", False
        if (now - ny_time).total_seconds() > 10800: return None, 0, 0, "Post-NY", False
        
        df = self._df(sym, '15m', 30)
        if df is None: return None, 0, 0, "No Data", False
        df['ts'] = pd.to_datetime(df['t'], unit='ms')
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
        mask = (df['ts'].dt.hour == ny_h) & (df['ts'].dt.minute == 30) & (df['ts'].dt.date == now.date())
        ref = df[mask]
        if ref.empty: return None, 0, 0, "No NY", False
        
        ref_h, ref_l = ref.iloc[0]['h'], ref.iloc[0]['l']
        cur = df.iloc[-1]; atr = cur['atr']
        if pd.isna(atr) or atr <= 0: return None, 0, 0, "ATR N/A", False
        if cur['c'] > ref_h: return 'long', cur['c'], atr, "NY_UP", False
        elif cur['c'] < ref_l: return 'short', cur['c'], atr, "NY_DN", False
        return None, 0, 0, "No Break", False
    
    # ================================================================
    #                     TRADE MANAGEMENT
    # ================================================================
    
    def _open(self, direction, sym, price, atr, strategy, reason, is_whale=False):
        if not self._check_slippage(sym, price): return False
            
        sl_dist = self.CFG['sl_mult'] * atr
        tp_dist = self.CFG['tp_mult'] * atr
        sl = price - sl_dist if direction == 'long' else price + sl_dist
        tp = price + tp_dist if direction == 'long' else price - tp_dist
        
        qty = self._calc_qty(sym, price, atr)
        if qty <= 0: self.stats['qty_zero'] += 1; return False
        
        side = 'buy' if direction == 'long' else 'sell'
        pos_side = 'LONG' if direction == 'long' else 'SHORT'
        
        self._set_lev(sym, pos_side)
        time.sleep(0.5)  # ✅ تقليل الانتظار
        
        order = self._order(side, sym, qty, pos_side=pos_side)
        
        if order:
            with self.trade_lock:
                self.active_trade = {
                    'sym': sym, 'dir': direction, 'entry': price, 'sl': sl, 'tp': tp, 
                    'qty': qty, 'strategy': strategy, 'reason': reason, 'time': time.time(), 
                    'partial': False,
                    'trail_active': False,  # ✅ متابعة حالة التتبع
                    'highest_pct': 0  # ✅ أعلى ربح وصل له
                }
                self.day_trades += 1
            
            icon = "🟢" if direction == 'long' else "🔴"
            whale_tag = "\n🐋 دخول مدعوم بحوت!" if is_whale else ""
            fast_tag = "\n⚡ دخول سريع!" if 'Realtime' in strategy else ""
            mode = "⚡AGG" if self.is_aggressive else "🛡️NORM"
            
            msg  = f"{icon} *صفقة #{self.day_trades}*\n"
            msg += f"📊 {strategy}\n🪙 {sym}\n"
            msg += f"💵 {self.fmt(price)} | ⚖️ {self.fmt(qty, 4)}\n"
            msg += f"🛑 {self.fmt(sl)} | 🎯 {self.fmt(tp)}\n"
            msg += f"🧠 {mode}{whale_tag}{fast_tag}\n🆔 {order.get('id', '?')}"
            self.tg(msg)
            
            if is_whale or 'Realtime' in strategy:
                self.stats['fast_entries'] += 1
            return True
        
        # محاولة بالحد الأدنى
        try:
            mn = float(self.exchange.market(sym).get('limits', {}).get('amount', {}).get('min', 0))
            if mn > 0:
                order2 = self._order(side, sym, mn * 1.1, pos_side=pos_side)
                if order2:
                    with self.trade_lock:
                        self.active_trade = {
                            'sym': sym, 'dir': direction, 'entry': price, 'sl': sl, 'tp': tp, 
                            'qty': mn * 1.1, 'strategy': strategy+"(MIN)", 'reason': reason, 
                            'time': time.time(), 'partial': False, 'trail_active': False, 'highest_pct': 0
                        }
                        self.day_trades += 1
                    self.tg(f"🟢 صفقة (حد أدنى) {sym}\n🆔 {order2.get('id')}")
                    return True
        except: pass
        return False
    
    def _close(self, reason, pct, partial=False):
        with self.trade_lock:
            if not self.active_trade: return
            t = self.active_trade.copy()
            sym, d = t['sym'], t['dir']
            qty = float(t['qty'])
            if partial:
                qty = qty / 2
                t['partial'] = True
                t['sl'] = t['entry']
                self.active_trade = t
        
        pos_side = 'LONG' if d == 'long' else 'SHORT'
        try: fq = float(self.exchange.amount_to_precision(sym, qty))
        except: fq = qty
        if fq <= 0: return
        
        order = self._order('sell' if d == 'long' else 'buy', sym, fq, pos_side=pos_side)
        if not order: self.tg(f"🚨 فشل إغلاق {d} {sym}"); return
        
        is_loss = pct < 0
        if partial:
            self.tg(f"⚡ جزئي 50% {sym} | {pct:+.2f}%\n🆔 {order.get('id')}"); return
        
        with self.trade_lock:
            self._evolve_after_close(not is_loss)
            self.day_pnl += pct
            if is_loss: self.stats['losses'] += 1
            else: self.stats['wins'] += 1
            self.active_trade = None
        
        icon = "🏆" if not is_loss else "📉"
        self.tg(f"{icon} {sym} ({d}) | {pct:+.2f}%\n📝 {reason} | صافي: {self.day_pnl:+.2f}%\n🆔 {order.get('id')}")
    
    def _manage(self):
        with self.trade_lock:
            if not self.active_trade: return
            t = self.active_trade.copy()
        
        sym, d = t['sym'], t['dir']
        ticker = self._ticker(sym)
        if not ticker: return
        
        cp = ticker['last']; ep = t['entry']
        pct = self._pnl_pct(ep, cp, d)
        
        # ✅ تحديث أعلى ربح وصلت له الصفقة
        with self.trade_lock:
            if self.active_trade and pct > self.active_trade.get('highest_pct', 0):
                self.active_trade['highest_pct'] = pct
        
        self.log(f"GUARD: {d} {sym} | {pct:+.2f}% | Trail: {'ON' if t.get('trail_active') else 'OFF'}")
        
        # ✅ فحص وقف الخسارة
        if d == 'long' and cp <= t['sl']: self._close("🛑 SL", pct); return
        if d == 'short' and cp >= t['sl']: self._close("🛑 SL", pct); return
        
        # ✅ فحص الهدف
        tp = t.get('tp', 0)
        if tp > 0:
            if d == 'long' and cp >= tp: self._close("🎯 TP", pct); return
            if d == 'short' and cp <= tp: self._close("🎯 TP", pct); return
        
        with self.trade_lock:
            if not self.active_trade: return
            
            # ✅ الخروج الجزئي
            if pct >= self.CFG['partial_at'] and not self.active_trade.get('partial'):
                self.active_trade['partial'] = True
                self.active_trade['sl'] = self.active_trade['entry']
                self._close(f"⚡ جزئي", pct, partial=True)
                if tp > 0 and ep > 0:
                    if d == 'long': self.active_trade['tp'] = ep + (tp - ep) * 0.6
                    else: self.active_trade['tp'] = ep - (ep - tp) * 0.6
                return
            
            # ✅ Trailing Stop محسن (أبطأ وأذكى)
            highest = self.active_trade.get('highest_pct', 0)
            
            # ✅ تفعيل التتبع فقط بعد الوصول لـ trail_after
            if pct >= self.CFG['trail_after']:
                if not self.active_trade.get('trail_active'):
                    self.active_trade['trail_active'] = True
                    self.log(f"TRAIL ACTIVATED at {pct:.2f}%", notify=True, msg_ar=f"🐢 تفعيل التتبع عند {pct:.2f}%")
                
                # ✅ حساب المسافة التي تراجع منها من الأعلى
                drawdown_from_high = highest - pct
                
                # ✅ تعديل SL فقط إذا تراجع أكثر من trail_min_move من الأعلى
                if drawdown_from_high >= self.CFG['trail_min_move']:
                    trail_step = self.CFG['trail_step']  # 0.15%
                    
                    if d == 'long':
                        # ✅ SL الجديد = السعر الحالي - خطوة التتبع
                        new_sl = cp * (1 - trail_step / 100)
                        # ✅ تعديل فقط إذا كان SL الجديد أعلى من القديم
                        if new_sl > self.active_trade['sl']:
                            self.active_trade['sl'] = new_sl
                            self.stats['trail_adjustments'] += 1
                            self.log(f"TRAIL UP: SL -> {new_sl:.6f} (from high {highest:.2f}%)")
                    else:
                        # ✅ SL الجديد = السعر الحالي + خطوة التتبع
                        new_sl = cp * (1 + trail_step / 100)
                        # ✅ تعديل فقط إذا كان SL الجديد أقل من القديم
                        if new_sl < self.active_trade['sl']:
                            self.active_trade['sl'] = new_sl
                            self.stats['trail_adjustments'] += 1
                            self.log(f"TRAIL DN: SL -> {new_sl:.6f} (from high {highest:.2f}%)")
            
            # ✅ انتهاء الوقت
            elapsed = (time.time() - self.active_trade['time']) / 60
            if elapsed >= self.CFG['max_hold_min']:
                self._close(f"⏳ انتهاء {elapsed:.0f}د", pct)
                self.stats['timeouts'] += 1

    # ================================================================
    #                    ⚡ فحص سريع للحيتان
    # ================================================================
    
    def _fast_whale_scan(self, tickers):
        """✅ فحص سريع للحيتان في الوقت الحقيقي - أولوية قصوى"""
        now = time.time()
        
        # تنظيف التنبيهات القديمة
        self.whale_alerts = {k: v for k, v in self.whale_alerts.items() if now - v['time'] < 60}
        
        # ترتيب العملات حسب الحجم (الأعلى أولاً)
        vol_sorted = sorted(
            [s for s, t in tickers.items() if s.endswith('/USDT:USDT')],
            key=lambda s: tickers[s].get('quoteVolume', 0),
            reverse=True
        )[:20]  # ✅ فحص أعلى 20 عملة فقط للحيتان
        
        for sym in vol_sorted:
            # ✅ تخطي إذا كان هناك تنبيه حديث لنفس الزوج
            if sym in self.whale_alerts:
                continue
                
            d, p, atr, reason = self._is_whale_realtime(sym)
            
            if d and p > 0 and atr > 0:
                self.whale_alerts[sym] = {'time': now, 'dir': d}
                self.log(f"⚡ FAST WHALE: {sym} {d.upper()} | {reason}", notify=True, 
                        msg_ar=f"⚡ *حوت فوري!*\n🪙 {sym} {d.upper()}\n📝 {reason}")
                return sym, d, p, atr, reason, True
        
        return None

    # ================================================================
    #                         THREADS & LOOPS
    # ================================================================
    
    def _guard_loop(self):
        self.log("GUARD THREAD STARTED", notify=True, msg_ar="🛡️ تفعيل حارس الصفقات!")
        while True:
            try: self._manage()
            except Exception as e: self.log(f"GUARD ERR: {e}")
            time.sleep(1)
            
    def _report(self):
        total = self.stats['wins'] + self.stats['losses']
        wr = (self.stats['wins'] / total * 100) if total > 0 else 0
        msg  = "🐋 *تقرير V11.1 (Fast Entry)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"📋 صفقات: {self.day_trades}/{self.CFG['max_daily']} | {wr:.1f}%\n"
        msg += f"💰 صافي: {self.day_pnl:+.2f}%\n"
        msg += f"🐋 حيتان رصدت: {self.stats['whale_spotted']}\n"
        msg += f"⚡ دخول سريع: {self.stats['fast_entries']}\n"
        msg += f"🐢 تعديلات تتبع: {self.stats['trail_adjustments']}\n"
        msg += f"🛡️ وقاية: {self.stats['tilt_triggered']}"
        self.tg(msg)
    
    def _summary(self):
        mode = "⚡استغلال" if self.is_aggressive else "🛡️عادي"
        self.tg(f"📊 {self.day_trades}/{self.CFG['max_daily']} | صافي: {self.day_pnl:+.2f}% | 🐋{self.stats['whale_spotted']} | ⚡{self.stats['fast_entries']} | {mode}")
    
    def run(self):
        self.tg("🐋 *الوحش V11.1 يعمل!*")
        threading.Thread(target=self._guard_loop, daemon=True).start()
        self.log("HUNTER STARTED", notify=True, msg_ar="🏹 تفعيل مسار الصيد!")
        
        while True:
            try:
                today = datetime.date.today()
                if self.day != today:
                    if self.day is not None and self.day_trades > 0: self._report()
                    with self.trade_lock:
                        self.day = today; self.day_trades = 0; self.day_pnl = 0.0
                        self.stats = {k: 0 for k in self.stats}
                        self.streak_wins = 0; self.streak_losses = 0; self.tilt_until = 0; self.is_aggressive = False
                        self.hot_pairs = {}; self.whale_alerts = {}
                    self.log("NEW DAY RESET", notify=True, msg_ar="📅 يوم جديد!")
                
                with self.trade_lock: has_trade = self.active_trade is not None
                
                if has_trade or self.day_trades >= self.CFG['max_daily']:
                    time.sleep(600 if self.day_trades >= self.CFG['max_daily'] else self.CFG['loop_sec'])
                    continue
                
                if time.time() < self.tilt_until: time.sleep(60); continue
                
                self.scan_num += 1
                tickers = self._tickers()
                if not tickers: time.sleep(30); continue
                
                syms = [s for s, t in tickers.items() if s.endswith('/USDT:USDT') and t.get('quoteVolume') and t.get('last') and t['quoteVolume'] * t['last'] > self.CFG['vol_filter']][:100]
                if not syms: time.sleep(60); continue
                
                self.log(f"SCAN #{self.scan_num} | 🐋{self.stats['whale_spotted']} | ⚡{self.stats['fast_entries']}")
                
                # ✅ الخطوة 1: فحص سريع للحيتان (أولوية)
                whale_result = self._fast_whale_scan(tickers)
                
                if whale_result:
                    sym, d, p, atr, reason, is_whale = whale_result
                    with self.trade_lock: can_open = self.active_trade is None
                    if can_open and self._open(d, sym, p, atr, "⚡Realtime حوت", reason, is_whale):
                        continue
                
                # ✅ الخطوة 2: الفحص العادي
                found = False
                for sym in syms[:self.CFG['max_scan']]:
                    self.stats['scanned'] += 1
                    
                    d, p, atr, reason, is_whale = self._score(sym)
                    strat = "🐋 حوت" if is_whale else "نقاط ذكية"
                    
                    if not d:
                        d, p, atr, reason, _ = self._ny_signal(sym)
                        strat = "نيويورك"
                    
                    if d and p > 0 and atr > 0:
                        if is_whale:
                            self.log(f"🐋 WHALE SIGNAL: {sym} {d.upper()} | {reason}", notify=True, msg_ar=f"🐋 *بصمة حوت!*\n🪙 {sym} {d.upper()}\n📝 {reason}")
                        
                        with self.trade_lock: can_open = self.active_trade is None
                        
                        if can_open and self._open(d, sym, p, atr, strat, reason, is_whale):
                            found = True
                            break
                
                if not found: self.log("NO SIGNALS")
                if time.time() - self.last_scan_summary >= self.CFG['summary_every']:
                    self._summary(); self.last_scan_summary = time.time()
                    
            except Exception as e: self.log(f"HUNTER ERR: {e}"); time.sleep(15)
            time.sleep(self.CFG['loop_sec'])

if __name__ == "__main__":
    bot = SmartBot()
    if bot.api_key:
        bot.run()
