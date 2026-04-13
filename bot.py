import ccxt, time, pandas as pd, ta, requests, datetime, os, sys, threading

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class SmartBot:
    """
    بوت الوحش V12.0 (Reality Sync Edition)
    =========================================
    إصلاح كارثي: البوت الآن يثق بالمنصة فقط!
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
        
        # ✅ لم نعد نحفظ الصفقة محلياً بشكل كامل
        # ✅ نحفظ فقط الإعدادات (SL, TP, استراتيجية)
        self.trade_settings = None  # {sym, dir, sl, tp, strategy, entry, time, partial, trail_active, highest_pct}
        
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
        
        self.whale_alerts = {}
        
        self.stats = {
            'wins': 0, 'losses': 0, 'timeouts': 0, 
            'scanned': 0, 'no_score': 0, 'qty_zero': 0, 
            'order_fail': 0, 'tilt_triggered': 0, 'slippage_blocked': 0,
            'whale_spotted': 0, 'fast_entries': 0, 'trail_adjustments': 0,
            'sync_fixes': 0  # ✅ عدد مرات إصلاح التناقض
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
            'trail_after': 2.0,
            'max_hold_min': 120,
            'vol_filter': 500000,
            'max_scan': 40,
            'loop_sec': 10,
            'summary_every': 1800,
            'tilt_after_losses': 2,
            'tilt_duration_min': 60,
            'aggression_after_wins': 3,
            'aggression_risk_boost': 2.0,
            'vol_multiplier_danger': 2.0,
            'max_slippage_pct': 0.5,
            'whale_level_1': 1.5,
            'whale_level_2': 3.0,
            'whale_level_3': 5.0,
            'hot_pair_expire': 120,
            'whale_priority': True,
            'early_entry_pct': 0.3,
            'trail_step': 0.15,
            'trail_min_move': 0.5,
        }
        
        self.tg("🔄 جاري التشغيل...")
        self.exchange.load_markets()
        
        # ✅ الخطوة الأولى: مزامنة فورية مع المنصة
        self._force_sync()
        
        bal = self._balance()
        msg  = "🐋 *بوت الوحش V12.0 (Reality Sync)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "🔗 مزامنة حقيقية مع المنصة\n"
        msg += "⚡ دخول سريع (أثناء الشمعة)\n"
        msg += "🐢 Trailing محسن (أبطأ)\n"
        msg += "🐋 أولوية الحيتان\n"
        msg += "🛡️ حماية من الانزلاق\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"💳 رصيد: {bal} USDT"
        self.tg(msg)
        
        # ✅ إبلاغ عن الصفقة الحالية إذا وجدت
        if self.trade_settings:
            ts = self.trade_settings
            self.tg(f"🧠 استئناف مراقبة: {ts['dir']} {ts['sym']}")

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

    # ================================================================
    #    🔗 المزامنة الحقيقية - الوظيفة الأهم في V12.0
    # ================================================================
    
    def _get_real_position(self):
        """
        ✅ يسأل المنصة مباشرة: هل يوجد مركز مفتوح؟
        ✅ يرجع الحقيقة من بنج إكس فقط
        """
        try:
            positions = self._api('fetch_positions')
            if not positions:
                return None
            
            for p in positions:
                qty = float(p.get('position', p.get('contracts', 0)))
                if qty > 0:
                    return {
                        'sym': p['symbol'],
                        'dir': 'short' if p.get('positionSide', '').lower() == 'short' else 'long',
                        'entry': float(p['entryPrice']),
                        'qty': qty,
                        'pnl': float(p.get('unrealizedPnl', 0)),
                        'pnl_pct': float(p.get('percentage', 0)),
                        'liquidation': float(p.get('liquidationPrice', 0))
                    }
            return None
        except Exception as e:
            self.log(f"REAL POS ERROR: {str(e)[:50]}")
            return None
    
    def _force_sync(self):
        """
        ✅ مزامنة قسرية: ما في المنصة هو الحقيقة
        ✅ يحذف أي بيانات محلية خاطئة
        """
        real = self._get_real_position()
        
        with self.trade_lock:
            if real:
                sym = real['sym']
                d = real['dir']
                entry = real['entry']
                
                # ✅ إذا كانت الإعدادات المحلية مختلفة = تناقض!
                if self.trade_settings:
                    if self.trade_settings['sym'] != sym or self.trade_settings['dir'] != d:
                        self.tg(
                            f"🚨 *تناقض مكتشف وإصلاحه!*\n"
                            f"━━━━━━━━━━━━━━━━\n"
                            f"البوت كان يرى:\n"
                            f"  {self.trade_settings.get('dir', '?')} {self.trade_settings.get('sym', '?')}\n"
                            f"المنصة (الحقيقة):\n"
                            f"  {d} {sym}\n"
                            f"  دخول: {entry}\n"
                            f"  P&L: {real['pnl_pct']:.2f}%\n"
                            f"━━━━━━━━━━━━━━━━\n"
                            f"🔧 تم تصحيح الحالة"
                        )
                        self.stats['sync_fixes'] += 1
                
                # ✅ حفظ الإعدادات بناءً على الواقع
                self.trade_settings = {
                    'sym': sym,
                    'dir': d,
                    'entry': entry,
                    'qty': real['qty'],
                    'strategy': self.trade_settings.get('strategy', 'مستعادة') if self.trade_settings else 'مستعادة',
                    'reason': 'SYNC',
                    'time': time.time(),
                    'sl': entry * (0.97 if d == 'long' else 1.03),  # SL افتراضي
                    'tp': 0,
                    'partial': False,
                    'trail_active': False,
                    'highest_pct': 0
                }
                
                self.log(f"SYNC: Real position confirmed: {d} {sym} @ {entry} | P&L: {real['pnl_pct']:.2f}%")
                
            else:
                # ✅ لا يوجد مركز في المنصة = مسح المحلي
                if self.trade_settings:
                    self.log(f"SYNC: Cleared ghost position {self.trade_settings['sym']}")
                    self.stats['sync_fixes'] += 1
                self.trade_settings = None

    # ================================================================
    #               حماية الانزلاق والتطور
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
    #              فحص الحوت في الوقت الحقيقي
    # ================================================================
    
    def _is_whale_realtime(self, sym):
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
            
            current_vol = ticker.get('baseVolume', 0)
            if current_vol <= 0: return None, 0, 0, "No Vol"
            
            avg_vol = cur['vm'] if not pd.isna(cur['vm']) and cur['vm'] > 0 else 0
            if avg_vol <= 0: return None, 0, 0, "No Avg Vol"
            
            vol_ratio = current_vol / avg_vol
            
            if vol_ratio < self.CFG['whale_level_1']:
                return None, 0, 0, f"VOL_{vol_ratio:.1f}x"
            
            price = ticker['last']
            candle_open = cur['o']
            price_move = (price - candle_open) / candle_open * 100
            
            if abs(price_move) < 0.2:
                return None, 0, 0, f"NO_MOVE_{price_move:.2f}%"
            
            direction = 'long' if price_move > 0 else 'short'
            
            if vol_ratio >= self.CFG['whale_level_3']:
                self.stats['whale_spotted'] += 1
                return direction, price, atr, f"🐋MEGA_{vol_ratio:.0f}x|{price_move:+.2f}%"
            elif vol_ratio >= self.CFG['whale_level_2']:
                self.stats['whale_spotted'] += 1
                return direction, price, atr, f"🐋WHALE_{vol_ratio:.0f}x|{price_move:+.2f}%"
            elif vol_ratio >= self.CFG['whale_level_1'] * 1.2:
                self.stats['whale_spotted'] += 1
                return direction, price, atr, f"🐋FLOW_{vol_ratio:.1f}x|{price_move:+.2f}%"
            
            return None, 0, 0, f"VOL_{vol_ratio:.1f}x"
        except Exception as e:
            return None, 0, 0, "Error"

    # ================================================================
    #              نظام النقاط + رادار الحيتان
    # ================================================================
    
    def _score(self, sym):
        df = self._df(sym, '15m', 60)
        df_h = self._df(sym, '1h', 50)
        if df is None or df_h is None: return None, 0, 0, "Data N/A", False
        
        df['ema9'] = ta.trend.ema_indicator(df['c'], 9)
        df['ema21'] = ta.trend.ema_indicator(df['c'], 21)
        df['rsi'] = ta.momentum.rsi(df['c'], 14)
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
        df['vm'] = df['v'].rolling(20).mean()
        df['macd'] = ta.trend.macd_diff(df['c'])
        df_h['ema50'] = ta.trend.ema_indicator(df_h['c'], 50)
        
        cur = df.iloc[-1]; prev = df.iloc[-2]; cur_h = df_h.iloc[-1]
        atr = cur['atr']
        if pd.isna(atr) or atr <= 0: return None, 0, 0, "ATR N/A", False
        
        L, S = 0, 0; LR, SR = [], []
        
        if not pd.isna(cur_h['ema50']):
            if cur_h['c'] > cur_h['ema50']: L += 2; LR.append("1H_UP")
            else: S += 2; SR.append("1H_DN")
        
        ema_ok = all(not pd.isna(x) for x in [cur['ema9'], cur['ema21'], prev['ema9'], prev['ema21']])
        if ema_ok:
            if prev['ema9'] <= prev['ema21'] and cur['ema9'] > cur['ema21']: L += 2; LR.append("CROSS_UP")
            elif prev['ema9'] >= prev['ema21'] and cur['ema9'] < cur['ema21']: S += 2; SR.append("CROSS_DN")
            elif cur['ema9'] > cur['ema21']: L += 1
            else: S += 1
        
        if not pd.isna(cur['rsi']):
            if cur['rsi'] < 35: L += 2; LR.append(f"RSI_{cur['rsi']:.0f}")
            elif cur['rsi'] > 65: S += 2; SR.append(f"RSI_{cur['rsi']:.0f}")
            elif 40 <= cur['rsi'] < 50: L += 1
            elif 50 < cur['rsi'] <= 60: S += 1
        
        if not pd.isna(cur['macd']) and not pd.isna(prev['macd']):
            if cur['macd'] > 0 and cur['macd'] > prev['macd']: L += 1
            elif cur['macd'] < 0 and cur['macd'] < prev['macd']: S += 1
        
        body = abs(cur['c'] - cur['o']); rng = cur['h'] - cur['l']
        if rng > 0 and (body / rng) > 0.5:
            if cur['c'] > cur['o']: L += 1; LR.append("BULL_CAND")
            else: S += 1; SR.append("BEAR_CAND")
        
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
        
        if is_whale: self.stats['whale_spotted'] += 1
        
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
        
        # ✅ تحقق أخير: لا توجد صفقة فعلية
        real_check = self._get_real_position()
        if real_check:
            self.log(f"BLOCKED: Real position exists {real_check['sym']}")
            return False
            
        sl_dist = self.CFG['sl_mult'] * atr
        tp_dist = self.CFG['tp_mult'] * atr
        sl = price - sl_dist if direction == 'long' else price + sl_dist
        tp = price + tp_dist if direction == 'long' else price - tp_dist
        
        qty = self._calc_qty(sym, price, atr)
        if qty <= 0: self.stats['qty_zero'] += 1; return False
        
        side = 'buy' if direction == 'long' else 'sell'
        pos_side = 'LONG' if direction == 'long' else 'SHORT'
        
        self._set_lev(sym, pos_side)
        time.sleep(0.5)
        
        order = self._order(side, sym, qty, pos_side=pos_side)
        
        if order:
            # ✅ تحقق حقيقي بعد الأمر
            time.sleep(2)
            real = self._get_real_position()
            
            if not real:
                self.tg(f"🚨 *أمر وهمي!*\nالأمر نجح لكن لا مركز فعلي\n🪙 {sym}")
                self.stats['order_fail'] += 1
                return False
            
            if real['dir'] != direction:
                self.tg(f"🚨 *اتجاه خاطئ!*\nطلب: {direction}\nفعلي: {real['dir']}\n🪙 {sym}")
                # ✅ إغلاق فوري
                self._force_close_position(sym, "اتجاه خاطئ")
                return False
            
            with self.trade_lock:
                self.trade_settings = {
                    'sym': sym, 'dir': direction, 'entry': real['entry'], 
                    'qty': real['qty'], 'sl': sl, 'tp': tp,
                    'strategy': strategy, 'reason': reason, 'time': time.time(),
                    'partial': False, 'trail_active': False, 'highest_pct': 0
                }
                self.day_trades += 1
            
            icon = "🟢" if direction == 'long' else "🔴"
            whale_tag = "\n🐋 دخول مدعوم بحوت!" if is_whale else ""
            fast_tag = "\n⚡ دخول سريع!" if 'Realtime' in strategy else ""
            mode = "⚡AGG" if self.is_aggressive else "🛡️NORM"
            
            msg  = f"{icon} *صفقة #{self.day_trades}* ✅\n"
            msg += f"📊 {strategy}\n🪙 {sym}\n"
            msg += f"💵 {self.fmt(real['entry'])} | ⚖️ {self.fmt(real['qty'], 4)}\n"
            msg += f"🛑 {self.fmt(sl)} | 🎯 {self.fmt(tp)}\n"
            msg += f"🧠 {mode}{whale_tag}{fast_tag}\n🆔 {order.get('id', '?')}"
            self.tg(msg)
            
            if is_whale or 'Realtime' in strategy:
                self.stats['fast_entries'] += 1
            return True
        
        return False
    
    def _force_close_position(self, sym, reason=""):
        """✅ إغلاق قسري من المنصة بغض النظر عن الحالة المحلية"""
        try:
            real = self._get_real_position()
            if not real: return
            
            d = real['dir']
            pos_side = 'LONG' if d == 'long' else 'SHORT'
            qty = real['qty']
            
            self.log(f"FORCE CLOSE: {d} {sym} | Reason: {reason}")
            
            fq = float(self.exchange.amount_to_precision(sym, qty))
            if fq <= 0: return
            
            self._order('sell' if d == 'long' else 'buy', sym, fq, pos_side=pos_side)
            
            with self.trade_lock:
                self.trade_settings = None
                
        except Exception as e:
            self.log(f"FORCE CLOSE ERR: {str(e)[:60]}")
    
    def _close(self, reason, pct, partial=False):
        with self.trade_lock:
            if not self.trade_settings: return
            t = self.trade_settings.copy()
            sym, d = t['sym'], t['dir']
            qty = float(t['qty'])
            if partial:
                qty = qty / 2
                t['partial'] = True
                t['sl'] = t['entry']
                self.trade_settings = t
        
        pos_side = 'LONG' if d == 'long' else 'SHORT'
        try: fq = float(self.exchange.amount_to_precision(sym, qty))
        except: fq = qty
        if fq <= 0: return
        
        order = self._order('sell' if d == 'long' else 'buy', sym, fq, pos_side=pos_side)
        if not order:
            self.tg(f"🚨 فشل إغلاق {d} {sym}")
            return
        
        is_loss = pct < 0
        if partial:
            self.tg(f"⚡ جزئي 50% {sym} | {pct:+.2f}%\n🆔 {order.get('id')}")
            return
        
        with self.trade_lock:
            self._evolve_after_close(not is_loss)
            self.day_pnl += pct
            if is_loss: self.stats['losses'] += 1
            else: self.stats['wins'] += 1
            self.trade_settings = None
        
        icon = "🏆" if not is_loss else "📉"
        self.tg(f"{icon} {sym} ({d}) | {pct:+.2f}%\n📝 {reason} | صافي: {self.day_pnl:+.2f}%\n🆔 {order.get('id')}")
    
    def _manage(self):
        """
        ✅ إدارة الصفقة: يسأل المنصة كل ثانية
        """
        # ✅ الخطوة 1: اسأل المنصة ماذا يوجد فعلاً
        real = self._get_real_position()
        
        with self.trade_lock:
            settings = self.trade_settings.copy() if self.trade_settings else None
        
        # ✅ الحالة 1: لا يوجد شيء في المنصة
        if not real:
            if settings:
                self.log(f"SYNC: Position gone from exchange, clearing local", notify=True, 
                        msg_ar=f"🔗 *مزامنة:* الصفقة أُغلقت من المنصة\n🪙 {settings['sym']}")
                self.stats['sync_fixes'] += 1
                with self.trade_lock:
                    self.trade_settings = None
            return
        
        sym = real['sym']
        d = real['dir']
        entry = real['entry']
        pnl_pct = real['pnl_pct']  # ✅ نسبة الربح/الخسارة من المنصة مباشرة!
        
        # ✅ الحالة 2: تناقض في الاتجاه!
        if settings and (settings['sym'] != sym or settings['dir'] != d):
            self.tg(
                f"🚨 *تناقض حرج!*\n"
                f"المحلي: {settings.get('dir','?')} {settings.get('sym','?')}\n"
                f"المنصة: {d} {sym} | {pnl_pct:+.2f}%\n"
                f"🔧 تصحيح فوري"
            )
            self.stats['sync_fixes'] += 1
            with self.trade_lock:
                self.trade_settings = {
                    'sym': sym, 'dir': d, 'entry': entry, 'qty': real['qty'],
                    'sl': entry * (0.97 if d == 'long' else 1.03),
                    'tp': 0, 'strategy': 'مصححة', 'reason': 'SYNC_FIX',
                    'time': time.time(), 'partial': False, 'trail_active': False, 'highest_pct': 0
                }
            settings = self.trade_settings.copy()
        
        # ✅ الحالة 3: لا توجد إعدادات محلية = صفقة منسية
        if not settings:
            self.tg(f"🔗 *صفقة مستعادة!*\n{d} {sym} | {pnl_pct:+.2f}%")
            with self.trade_lock:
                self.trade_settings = {
                    'sym': sym, 'dir': d, 'entry': entry, 'qty': real['qty'],
                    'sl': entry * (0.97 if d == 'long' else 1.03),
                    'tp': 0, 'strategy': 'مستعادة', 'reason': 'AUTO_SYNC',
                    'time': time.time(), 'partial': False, 'trail_active': False, 'highest_pct': 0
                }
            settings = self.trade_settings.copy()
        
        # ✅ الآن نحن متأكدين: الإعدادات = المنصة
        ticker = self._ticker(sym)
        if not ticker: return
        cp = ticker['last']
        
        # ✅ طباعة الحقيقة من المنصة
        self.log(f"GUARD: {d} {sym} | {pnl_pct:+.2f}% (REAL) | Trail: {'ON' if settings.get('trail_active') else 'OFF'}")
        
        # ✅ فحص SL
        sl = settings['sl']
        if d == 'long' and cp <= sl: self._close("🛑 SL", pnl_pct); return
        if d == 'short' and cp >= sl: self._close("🛑 SL", pnl_pct); return
        
        # ✅ فحص TP
        tp = settings.get('tp', 0)
        if tp > 0:
            if d == 'long' and cp >= tp: self._close("🎯 TP", pnl_pct); return
            if d == 'short' and cp <= tp: self._close("🎯 TP", pnl_pct); return
        
        # ✅ تحديث أعلى ربح
        with self.trade_lock:
            if self.trade_settings and pnl_pct > self.trade_settings.get('highest_pct', 0):
                self.trade_settings['highest_pct'] = pnl_pct
        
        with self.trade_lock:
            if not self.trade_settings: return
            
            # ✅ خروج جزئي
            if pnl_pct >= self.CFG['partial_at'] and not self.trade_settings.get('partial'):
                self.trade_settings['partial'] = True
                self.trade_settings['sl'] = self.trade_settings['entry']
                self._close("⚡ جزئي", pnl_pct, partial=True)
                if tp > 0 and entry > 0:
                    if d == 'long': self.trade_settings['tp'] = entry + (tp - entry) * 0.6
                    else: self.trade_settings['tp'] = entry - (entry - tp) * 0.6
                return
            
            # ✅ Trailing Stop محسن
            highest = self.trade_settings.get('highest_pct', 0)
            
            if pnl_pct >= self.CFG['trail_after']:
                if not self.trade_settings.get('trail_active'):
                    self.trade_settings['trail_active'] = True
                    self.log(f"TRAIL ACTIVATED at {pnl_pct:.2f}%", notify=True, 
                            msg_ar=f"🐢 تفعيل التتبع عند {pnl_pct:.2f}%")
                
                drawdown_from_high = highest - pnl_pct
                
                if drawdown_from_high >= self.CFG['trail_min_move']:
                    trail_step = self.CFG['trail_step']
                    
                    if d == 'long':
                        new_sl = cp * (1 - trail_step / 100)
                        if new_sl > self.trade_settings['sl']:
                            self.trade_settings['sl'] = new_sl
                            self.stats['trail_adjustments'] += 1
                    else:
                        new_sl = cp * (1 + trail_step / 100)
                        if new_sl < self.trade_settings['sl']:
                            self.trade_settings['sl'] = new_sl
                            self.stats['trail_adjustments'] += 1
            
            # ✅ انتهاء الوقت
            elapsed = (time.time() - self.trade_settings['time']) / 60
            if elapsed >= self.CFG['max_hold_min']:
                self._close(f"⏳ انتهاء {elapsed:.0f}د", pnl_pct)
                self.stats['timeouts'] += 1

    # ================================================================
    #                    فحص سريع للحيتان
    # ================================================================
    
    def _fast_whale_scan(self, tickers):
        now = time.time()
        self.whale_alerts = {k: v for k, v in self.whale_alerts.items() if now - v['time'] < 60}
        
        vol_sorted = sorted(
            [s for s, t in tickers.items() if s.endswith('/USDT:USDT')],
            key=lambda s: tickers[s].get('quoteVolume', 0),
            reverse=True
        )[:20]
        
        for sym in vol_sorted:
            if sym in self.whale_alerts: continue
            
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
        self.log("GUARD THREAD STARTED (Reality Sync)", notify=True, msg_ar="🛡️ حارس الصفقات مع مزامنة حقيقية!")
        sync_counter = 0
        while True:
            try:
                sync_counter += 1
                # ✅ مزامنة كاملة كل 15 ثانية
                if sync_counter >= 15:
                    self._force_sync()
                    sync_counter = 0
                self._manage()
            except Exception as e: self.log(f"GUARD ERR: {e}")
            time.sleep(1)
            
    def _report(self):
        total = self.stats['wins'] + self.stats['losses']
        wr = (self.stats['wins'] / total * 100) if total > 0 else 0
        msg  = "🐋 *تقرير V12.0 (Reality Sync)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"📋 صفقات: {self.day_trades}/{self.CFG['max_daily']} | {wr:.1f}%\n"
        msg += f"💰 صافي: {self.day_pnl:+.2f}%\n"
        msg += f"🐋 حيتان: {self.stats['whale_spotted']}\n"
        msg += f"⚡ دخول سريع: {self.stats['fast_entries']}\n"
        msg += f"🔗 مزامنة: {self.stats['sync_fixes']} إصلاح\n"
        msg += f"🛡️ وقاية: {self.stats['tilt_triggered']}"
        self.tg(msg)
    
    def _summary(self):
        mode = "⚡استغلال" if self.is_aggressive else "🛡️عادي"
        self.tg(f"📊 {self.day_trades}/{self.CFG['max_daily']} | صافي: {self.day_pnl:+.2f}% | 🐋{self.stats['whale_spotted']} | 🔗{self.stats['sync_fixes']} | {mode}")
    
    def run(self):
        self.tg("🐋 *الوحش V12.0 يعمل!*")
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
                        self.whale_alerts = {}
                    self.log("NEW DAY RESET", notify=True, msg_ar="📅 يوم جديد!")
                
                with self.trade_lock: has_settings = self.trade_settings is not None
                
                if has_settings or self.day_trades >= self.CFG['max_daily']:
                    time.sleep(600 if self.day_trades >= self.CFG['max_daily'] else self.CFG['loop_sec'])
                    continue
                
                if time.time() < self.tilt_until: time.sleep(60); continue
                
                self.scan_num += 1
                tickers = self._tickers()
                if not tickers: time.sleep(30); continue
                
                syms = [s for s, t in tickers.items() if s.endswith('/USDT:USDT') and t.get('quoteVolume') and t.get('last') and t['quoteVolume'] * t['last'] > self.CFG['vol_filter']][:100]
                if not syms: time.sleep(60); continue
                
                self.log(f"SCAN #{self.scan_num} | 🐋{self.stats['whale_spotted']} | 🔗{self.stats['sync_fixes']}")
                
                # ✅ أولوية الحيتان
                whale_result = self._fast_whale_scan(tickers)
                if whale_result:
                    sym, d, p, atr, reason, is_whale = whale_result
                    with self.trade_lock: can_open = self.trade_settings is None
                    if can_open and self._open(d, sym, p, atr, "⚡Realtime حوت", reason, is_whale):
                        continue
                
                # ✅ الفحص العادي
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
                            self.log(f"🐋 WHALE: {sym} {d.upper()} | {reason}", notify=True,
                                    msg_ar=f"🐋 *بصمة حوت!*\n🪙 {sym} {d.upper()}\n📝 {reason}")
                        
                        with self.trade_lock: can_open = self.trade_settings is None
                        
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
