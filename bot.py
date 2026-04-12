import ccxt, time, pandas as pd, ta, requests, datetime, os, sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class SmartBot:
    """
    بوت الوحش V9.0 (النظام التطوري الديناميكي)
    ==========================================
    الميزات الجديدة:
    1. Anti-Tilt: وقف ذكي بعد خسائر متتالية
    2. Aggression Mode: استغلال عنيف للترندات القوية
    3. Volatility Shift: تقليل الحجم في العواصف
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
        
        self.active_trade = None
        self.day = None
        self.day_trades = 0
        self.day_pnl = 0.0
        self.scan_num = 0
        self.report_time = time.time()
        self.last_scan_summary = time.time()
        
        # ======= المتغيرات التطورية الجديدة =======
        self.streak_wins = 0      # عدد الأرباح المتتالية
        self.streak_losses = 0    # عدد الخسائر المتتالية
        self.tilt_until = 0       # وقت نهاية وضع "الوقاية" (الإيقاف المؤقت)
        self.is_aggressive = False # هل نحن في وضع "الاستغلال"؟
        
        self.stats = {
            'wins': 0, 'losses': 0, 'timeouts': 0, 
            'scanned': 0, 'no_score': 0, 'qty_zero': 0, 
            'order_fail': 0, 'tilt_triggered': 0
        }
        
        self.CFG = {
            'max_daily': 10,
            'leverage': 10,
            'base_risk_pct': 5.0,   # المخاطرة الأساسية 5%
            'sl_mult': 1.5,
            'tp_mult': 2.5,
            'min_score': 4,
            'score_gap': 2,
            'cooldown_sec': 300,
            'partial_at': 1.5,
            'trail_after': 1.0,
            'max_hold_min': 120,
            'vol_filter': 500000,
            'max_scan': 40,
            'loop_sec': 20,
            'summary_every': 1800,
            # ======= إعدادات التطور =======
            'tilt_after_losses': 2,      # إيقاف مؤقت بعد خسارتين متتاليتين
            'tilt_duration_min': 60,     # مدة الإيقاف ساعة
            'aggression_after_wins': 3,  # تفعيل الاستغلال بعد 3 أرباح متتالية
            'aggression_risk_boost': 2.0,# زيادة المخاطرة بـ 2% في وضع الاستغلال
            'vol_multiplier_danger': 2.0,# إذا كان التقلب ضعف المتوسط = خطر
        }
        
        self.tg("🔄 جاري الفحص...")
        self.active_trade = self._load_position()
        self.exchange.load_markets()
        
        bal = self._balance()
        msg  = "🧠 *بوت الوحش V9.0 (التطوري)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "🛡️ وقف ذكي (Anti-Tilt)\n"
        msg += "⚡ وضع الاستغلال (Aggression)\n"
        msg += "🌊 حماية من التقلبات (Volatility)\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"💵 رصيد: {bal} USDT"
        self.tg(msg)
        
        if self.active_trade:
            self.tg(f"🧠 استئناف: {self.active_trade['dir']} {self.active_trade['sym']}")

    def tg(self, msg):
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'}
            )
        except Exception as e:
            print(f"[TG ERROR] {e}")

    def log(self, msg_en, notify=False, msg_ar=None):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg_en}") 
        if notify:
            self.tg(msg_ar if msg_ar else msg_en)
    
    def fmt(self, val, decimals=6):
        if val == 0: return "0"
        return f"{val:.{decimals}g}"
    
    # ================================================================
    #                         API CALLS
    # ================================================================
    
    def _api(self, method, *args, **kwargs):
        for i in range(3):
            try:
                return getattr(self.exchange, method)(*args, **kwargs)
            except Exception as e:
                self.log(f"API Retry {method}: {e}")
                time.sleep(3 * (i + 1))
        return None
    
    def _balance(self):
        b = self._api('fetch_balance', {'type': 'swap'})
        return float(b.get('USDT', {}).get('free', 0)) if b else 0
    
    def _tickers(self): return self._api('fetch_tickers')
    def _ticker(self, sym): return self._api('fetch_ticker', sym)
    
    def _ohlcv(self, sym, tf, limit=60):
        return self._api('fetch_ohlcv', sym, tf, limit=limit)
    
    def _df(self, sym, tf, limit=60):
        data = self._ohlcv(sym, tf, limit)
        if not data or len(data) < limit:
            return None
        return pd.DataFrame(data, columns=['t','o','h','l','c','v'])
    
    def _set_lev(self, sym, pos_side='LONG'):
        try:
            self.exchange.set_leverage(
                self.CFG['leverage'], sym, 
                params={'marginMode': 'isolated', 'positionSide': pos_side}
            )
        except Exception as e:
            self.log(f"LEVERAGE WARNING: {e}")

    def _order(self, side, sym, qty, pos_side=None):
        fn = f'create_market_{side}_order'
        params = {}
        if pos_side:
            params['positionSide'] = pos_side
            
        try:
            o = getattr(self.exchange, fn)(sym, qty, params=params)
            if o and o.get('id'):
                self.log(f"ORDER SUCCESS: ID={o['id']}", notify=True, msg_ar=f"✅ تنفيذ: {o['id']}")
                return o
            else:
                self.log(f"ORDER NO ID: {o}")
                
        except ccxt.errors.InsufficientFunds as e:
            self.log(f"ORDER FAILED: Insufficient Funds", notify=True, msg_ar=f"❌ رصيد غير كافي!")
            self.stats['order_fail'] += 1
            return None
        except ccxt.errors.ExchangeError as e:
            self.log(f"ORDER FAILED: Exchange - {e}", notify=True, msg_ar=f"❌ خطأ منصة: {e}")
            self.stats['order_fail'] += 1
            return None
        except ccxt.errors.NetworkError as e:
            self.log(f"ORDER FAILED: Network - {e}", notify=True, msg_ar=f"❌ خطأ شبكة: {e}")
            time.sleep(5)
            try:
                o = getattr(self.exchange, fn)(sym, qty, params=params)
                if o and o.get('id'): return o
            except: pass
        except Exception as e:
            self.log(f"ORDER FAILED: {e}", notify=True, msg_ar=f"❌ خطأ: {e}")
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
                        sym = p['symbol']
                        entry = float(p['entryPrice'])
                        pos_side = p.get('positionSide', '').lower()
                        d = 'short' if pos_side == 'short' else 'long'
                        self.log(f"RESUMING: {d} {sym}", notify=True, msg_ar=f"🔄 استئناف: {d} {sym}")
                        return {
                            'sym': sym, 'dir': d, 'entry': entry,
                            'qty': qty, 'time': time.time(),
                            'strategy': 'استئناف', 'partial': True,
                            'sl': entry * (0.97 if d == 'long' else 1.03), 'tp': 0
                        }
        except Exception as e:
            self.log(f"LOAD POS ERROR: {e}")
        return None

    # ================================================================
    #               🧠 النظام التطوري (الذكاء الديناميكي)
    # ================================================================

    def _evolve_after_close(self, is_win):
        """
        هذه الدالة هي قلب النظام التطوري.
        تُستدعى فور إغلاق أي صفقة لتعديل سلوك البوت.
        """
        if is_win:
            self.streak_wins += 1
            self.streak_losses = 0
            
            # 🚀 تفعيل وضع الاستغلال (Aggression Mode)
            if self.streak_wins >= self.CFG['aggression_after_wins'] and not self.is_aggressive:
                self.is_aggressive = True
                msg = f"⚡ *وضع الاستغلال مفعّل!*\n"
                msg += f"📊 {self.streak_wins} أرباح متتالية\n"
                msg += f"📈 تم رفع المخاطرة إلى {self.CFG['base_risk_pct'] + self.CFG['aggression_risk_boost']}%"
                self.tg(msg)
        else:
            self.streak_losses += 1
            self.streak_wins = 0
            
            # إلغاء الاستغلال فور الخسارة
            if self.is_aggressive:
                self.is_aggressive = False
                self.log("AGGRESSION MODE OFF", notify=True, msg_ar="🛑 تم إلغاء وضع الاستغلال")
            
            # 🛡️ تفعيل الوقاية (Anti-Tilt)
            if self.streak_losses >= self.CFG['tilt_after_losses']:
                self.tilt_until = time.time() + (self.CFG['tilt_duration_min'] * 60)
                self.stats['tilt_triggered'] += 1
                msg = f"🛡️ *وضع الوقاية مفعّل (Anti-Tilt)*\n"
                msg += f"❌ {self.streak_losses} خسائر متتالية\n"
                msg += f"⏸️ إيقاف تام لمدة {self.CFG['tilt_duration_min']} دقيقة\n"
                msg += f"💡 السوق غير واضح أو متقلب، الانتظار أكثر أماناً."
                self.tg(msg)

    def _get_dynamic_risk(self, sym, atr):
        """
        حساب المخاطرة ديناميكياً حسب:
        1. الوضع الأساسي / وضع الاستغلال
        2. التقلبات الحالية للسوق (Volatility)
        """
        risk = self.CFG['base_risk_pct']
        
        # 1. زيادة المخاطرة إذا كنا في وضع الاستغلال
        if self.is_aggressive:
            risk += self.CFG['aggression_risk_boost']
        
        # 2. فحص التقلبات (هل السوق في عاصفة؟)
        try:
            df = self._df(sym, '1h', 50)
            if df is not None:
                atr_series = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
                cur_atr = atr_series.iloc[-1]
                avg_atr = atr_series.iloc[-20:].mean() # متوسط آخر 20 ساعة
                
                if not pd.isna(cur_atr) and not pd.isna(avg_atr) and avg_atr > 0:
                    vol_ratio = cur_atr / avg_atr
                    
                    # إذا التقلب ضعف المتوسط -> خطر انزلاق عالي -> قلل المخاطرة بنسبة 40%
                    if vol_ratio >= self.CFG['vol_multiplier_danger']:
                        risk *= 0.6
                        self.log(f"VOLATILITY ALERT: {vol_ratio:.1f}x Avg. Risk reduced to {risk:.1f}%")
        except Exception as e:
            pass # لا نوقف البوت بسبب خطأ في حساب التقلب
            
        return risk

    # ================================================================
    #                        CALCULATIONS
    # ================================================================
    
    def _calc_qty(self, sym, price, atr):
        bal = self._balance()
        if bal <= 0:
            self.log("BALANCE IS ZERO!", notify=True, msg_ar="❌ الرصيد صفر!")
            return 0
        
        sl_dist = self.CFG['sl_mult'] * atr
        if sl_dist <= 0: return 0
        
        # استخدام المخاطرة الديناميكية بدل الثابتة
        risk_pct = self._get_dynamic_risk(sym, atr)
        risk_amount = bal * (risk_pct / 100)
        qty = risk_amount / sl_dist
        
        try:
            market = self.exchange.market(sym)
            fq = self.exchange.amount_to_precision(sym, qty)
            mn = market.get('limits', {}).get('amount', {}).get('min')
            
            if mn and float(fq) < float(mn):
                fq = self.exchange.amount_to_precision(sym, float(mn) * 1.1)
            
            result = float(fq)
            return result if result > 0 else 0
        except Exception as e:
            self.log(f"QTY CALC ERROR: {e}")
            return 0
    
    def _pnl_pct(self, entry, current, direction):
        if direction == 'long':
            return ((current - entry) / entry) * 100
        return ((entry - current) / entry) * 100
    
    # ================================================================
    #                    STRATEGY: SCORING SYSTEM
    # ================================================================
    
    def _score(self, sym):
        df = self._df(sym, '15m', 60)
        df_h = self._df(sym, '1h', 50)
        
        if df is None or df_h is None:
            return None, 0, 0, "Data N/A"
        
        df['ema9'] = ta.trend.ema_indicator(df['c'], 9)
        df['ema21'] = ta.trend.ema_indicator(df['c'], 21)
        df['rsi'] = ta.momentum.rsi(df['c'], 14)
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
        df['vm'] = df['v'].rolling(20).mean()
        df['macd'] = ta.trend.macd_diff(df['c'])
        df_h['ema50'] = ta.trend.ema_indicator(df_h['c'], 50)
        
        cur = df.iloc[-1]; prev = df.iloc[-2]; cur_h = df_h.iloc[-1]
        atr = cur['atr']
        if pd.isna(atr) or atr <= 0:
            return None, 0, 0, "ATR N/A"
        
        L, S = 0, 0
        LR, SR = [], []
        
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
            if cur['c'] > cur['o']: L += 1; LR.append("BULL_CANDLE")
            else: S += 1; SR.append("BEAR_CANDLE")
        
        if not pd.isna(cur['vm']) and cur['v'] > cur['vm']:
            if cur['c'] > cur['o']: L += 1
            else: S += 1
        
        min_pts = self.CFG['min_score']; gap = self.CFG['score_gap']
        
        if L >= min_pts and (L - S) >= gap:
            return 'long', cur['c'], atr, f"L:{L} S:{S} | " + "+".join(LR[:3])
        elif S >= min_pts and (S - L) >= gap:
            return 'short', cur['c'], atr, f"L:{L} S:{S} | " + "+".join(SR[:3])
        
        self.stats['no_score'] += 1
        return None, 0, 0, f"L:{L} S:{S}"
    
    def _ny_signal(self, sym):
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        ny_h = 13 if datetime.datetime(now.year, 3, 14) <= now <= datetime.datetime(now.year, 11, 7) else 14
        ny_time = now.replace(hour=ny_h, minute=30, second=0, microsecond=0)
        if now < ny_time: return None, 0, 0, "Pre-NY"
        if (now - ny_time).total_seconds() > 10800: return None, 0, 0, "Post-NY"
        
        df = self._df(sym, '15m', 30)
        if df is None: return None, 0, 0, "No Data"
        df['ts'] = pd.to_datetime(df['t'], unit='ms')
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
        mask = (df['ts'].dt.hour == ny_h) & (df['ts'].dt.minute == 30) & (df['ts'].dt.date == now.date())
        ref = df[mask]
        if ref.empty: return None, 0, 0, "No NY Candle"
        
        ref_h, ref_l = ref.iloc[0]['h'], ref.iloc[0]['l']
        cur = df.iloc[-1]; atr = cur['atr']
        if pd.isna(atr) or atr <= 0: return None, 0, 0, "ATR N/A"
        
        if cur['c'] > ref_h: return 'long', cur['c'], atr, "NY_UP"
        elif cur['c'] < ref_l: return 'short', cur['c'], atr, "NY_DN"
        return None, 0, 0, "No Break"
    
    # ================================================================
    #                     TRADE MANAGEMENT
    # ================================================================
    
    def _open(self, direction, sym, price, atr, strategy, reason):
        sl_dist = self.CFG['sl_mult'] * atr
        tp_dist = self.CFG['tp_mult'] * atr
        sl = price - sl_dist if direction == 'long' else price + sl_dist
        tp = price + tp_dist if direction == 'long' else price - tp_dist
        
        qty = self._calc_qty(sym, price, atr)
        if qty <= 0:
            self.stats['qty_zero'] += 1
            return False
        
        side = 'buy' if direction == 'long' else 'sell'
        pos_side = 'LONG' if direction == 'long' else 'SHORT'
        
        self._set_lev(sym, pos_side)
        time.sleep(1)
        
        order = self._order(side, sym, qty, pos_side=pos_side)
        
        if order:
            self.active_trade = {
                'sym': sym, 'dir': direction, 'entry': price,
                'sl': sl, 'tp': tp, 'qty': qty,
                'strategy': strategy, 'reason': reason,
                'time': time.time(), 'partial': False
            }
            
            self.day_trades += 1
            icon = "🟢" if direction == 'long' else "🔴"
            mode = "⚡AGGRESSIVE" if self.is_aggressive else "🛡️NORMAL"
            
            msg  = f"{icon} *صفقة #{self.day_trades}*\n"
            msg += "━━━━━━━━━━━━━━━━\n"
            msg += f"📊 {strategy}\n"
            msg += f"🪙 {sym}\n"
            msg += f"💵 دخول: {self.fmt(price)}\n"
            msg += f"⚖️ كمية: {self.fmt(qty, 4)}\n"
            msg += f"🛑 SL: {self.fmt(sl)}\n"
            msg += f"🎯 TP: {self.fmt(tp)}\n"
            msg += f"📝 {reason}\n"
            msg += f"🧠 الوضع: {mode}\n"
            msg += f"🆔 {order.get('id', '?')}"
            self.tg(msg)
            return True
        
        # محاولة إنقاذ بالحد الأدنى
        try:
            market = self.exchange.market(sym)
            mn = float(market.get('limits', {}).get('amount', {}).get('min', 0))
            if mn > 0:
                self._set_lev(sym, pos_side)
                time.sleep(1)
                order2 = self._order(side, sym, mn * 1.1, pos_side=pos_side)
                if order2:
                    self.active_trade = {
                        'sym': sym, 'dir': direction, 'entry': price,
                        'sl': sl, 'tp': tp, 'qty': mn * 1.1,
                        'strategy': strategy + " (MIN)", 'reason': reason,
                        'time': time.time(), 'partial': False
                    }
                    self.day_trades += 1
                    self.tg(f"🟢 *صفقة (حد أدنى)*\n🪙 {sym}\n🆔 {order2.get('id')}")
                    return True
        except Exception as e:
            self.log(f"MIN QTY RETRY FAILED: {e}")
        
        return False
    
    def _close(self, reason, pct, partial=False):
        if not self.active_trade: return
        t = self.active_trade
        sym, d = t['sym'], t['dir']
        qty = float(t['qty'])
        
        if partial:
            qty = qty / 2
            t['partial'] = True
            t['sl'] = t['entry']
        
        close_side = 'sell' if d == 'long' else 'buy'
        pos_side = 'LONG' if d == 'long' else 'SHORT'
        
        try:
            fq = float(self.exchange.amount_to_precision(sym, qty))
        except:
            fq = qty
        
        if fq <= 0: return
        
        order = self._order(close_side, sym, fq, pos_side=pos_side)
        if not order:
            self.tg(f"🚨 فشل إغلاق {d} {sym}")
            return
        
        oid = order.get('id', '?')
        is_loss = pct < 0
        self.day_pnl += pct
        
        if partial:
            msg  = "⚡ *إغلاق جزئي 50%*\n"
            msg += f"🪙 {sym} ({d})\n"
            msg += f"💰 {pct:+.2f}%\n"
            msg += f"🛑 SL نقل للدخول\n"
            msg += f"🆔 {oid}"
            self.tg(msg)
            return
        
        # 🧠 استدعاء النظام التطوري بعد الإغلاق الكامل
        self._evolve_after_close(not is_loss)
        
        if is_loss:
            self.stats['losses'] += 1
            icon = "📉"
        else:
            self.stats['wins'] += 1
            icon = "🏆"
        
        msg  = f"{icon} *إغلاق صفقة*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"🪙 {sym} ({d})\n"
        msg += f"{'💔' if is_loss else '💰'} النتيجة: {pct:+.2f}%\n"
        msg += f"📝 السبب: {reason}\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"📊 اليوم: {self.day_trades}/{self.CFG['max_daily']} | صافي: {self.day_pnl:+.2f}%\n"
        msg += f"🧠 سلسلة: W{self.streak_wins} / L{self.streak_losses}\n"
        msg += f"🆔 {oid}"
        self.tg(msg)
        self.active_trade = None
    
    def _manage(self):
        t = self.active_trade
        if not t: return
        sym, d = t['sym'], t['dir']
        ticker = self._ticker(sym)
        if not ticker: return
        
        cp = ticker['last']; ep = t['entry']
        pct = self._pnl_pct(ep, cp, d)
        self.log(f"MANAGING {d} {sym} | PnL: {pct:+.2f}%")
        
        if d == 'long' and cp <= t['sl']:
            self._close("🛑 وقف خسارة", pct); return
        if d == 'short' and cp >= t['sl']:
            self._close("🛑 وقف خسارة", pct); return
        
        tp = t.get('tp', 0)
        if tp > 0:
            if d == 'long' and cp >= tp:
                self._close("🎯 جني أرباح", pct); return
            if d == 'short' and cp <= tp:
                self._close("🎯 جني أرباح", pct); return
        
        if pct >= self.CFG['partial_at'] and not t.get('partial'):
            self._close(f"⚡ جزئي @ {pct:.1f}%", pct, partial=True)
            if tp > 0 and ep > 0:
                if d == 'long': t['tp'] = ep + (tp - ep) * 0.6
                else: t['tp'] = ep - (ep - tp) * 0.6
            return
        
        if pct >= self.CFG['trail_after']:
            mult = self.CFG['sl_mult'] * 0.01
            if d == 'long':
                new_sl = cp * (1 - mult)
                if new_sl > t['sl']: t['sl'] = new_sl
            else:
                new_sl = cp * (1 + mult)
                if new_sl < t['sl']: t['sl'] = new_sl
        
        elapsed = (time.time() - t['time']) / 60
        if elapsed >= self.CFG['max_hold_min']:
            self._close(f"⏳ انتهاء {elapsed:.0f}د", pct)
            self.stats['timeouts'] += 1
            return
    
    # ================================================================
    #                         REPORTS
    # ================================================================
    
    def _report(self):
        total = self.stats['wins'] + self.stats['losses']
        wr = (self.stats['wins'] / total * 100) if total > 0 else 0
        msg  = "🧠 *تقرير النظام التطوري V9.0*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"📋 الصفقات: {self.day_trades}/{self.CFG['max_daily']}\n"
        msg += f"✅ أرباح: {self.stats['wins']}\n"
        msg += f"❌ خسائر: {self.stats['losses']}\n"
        msg += f"📈 نسبة فوز: {wr:.1f}%\n"
        msg += f"💰 صافي: {self.day_pnl:+.2f}%\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"🛡️ مرات الوقاية: {self.stats['tilt_triggered']}\n"
        msg += f"📊 اتجاه مرفوض: {self.stats['no_score']}"
        self.tg(msg)
    
    def _summary(self):
        msg  = f"📊 *ملخص - {self.day_trades}/{self.CFG['max_daily']}*\n"
        msg += f"💰 صافي: {self.day_pnl:+.2f}%\n"
        mode = "⚡ استغلال" if self.is_aggressive else "🛡️ عادي"
        msg += f"🧠 الوضع: {mode} | W{self.streak_wins} L{self.streak_losses}"
        self.tg(msg)
    
    # ================================================================
    #                         MAIN LOOP
    # ================================================================
    
    def run(self):
        self.tg("🧠 *الوحش V9.0 (التطوير الذاتي) يعمل!*")
        self.log("BOT V9.0 EVOLUTIONARY STARTED", notify=True, msg_ar="🚀 تم بدء النظام التطوري!")
        
        while True:
            try:
                today = datetime.date.today()
                if self.day != today:
                    if self.day is not None and self.day_trades > 0:
                        self._report()
                    self.day = today
                    self.day_trades = 0
                    self.day_pnl = 0.0
                    self.stats = {k: 0 for k in self.stats}
                    # إعادة ضبط الحالة الذهنية للبوت يومياً
                    self.streak_wins = 0
                    self.streak_losses = 0
                    self.tilt_until = 0
                    self.is_aggressive = False
                    self.log("NEW DAY RESET", notify=True, msg_ar="📅 يوم جديد - إعادة ضبط العقل!")
                
                if self.day_trades >= self.CFG['max_daily']:
                    self.log(f"DAILY LIMIT ({self.CFG['max_daily']})")
                    time.sleep(600)
                    continue
                
                # 🛡️ فحص وضع الوقاية (Anti-Tilt)
                if time.time() < self.tilt_until:
                    wait = int((self.tilt_until - time.time()) / 60)
                    self.log(f"🛡️ ANTI-TILT ACTIVE: {wait} min left")
                    time.sleep(60)
                    continue
                
                if self.active_trade:
                    self._manage()
                    time.sleep(15)
                    continue
                
                self.scan_num += 1
                self.log(f"SCAN #{self.scan_num}")
                
                tickers = self._tickers()
                if not tickers:
                    time.sleep(30)
                    continue
                
                syms = [
                    s for s, t in tickers.items()
                    if s.endswith('/USDT:USDT')
                    and t.get('quoteVolume')
                    and t.get('last')
                    and t['quoteVolume'] * t['last'] > self.CFG['vol_filter']
                ][:100]
                
                if not syms:
                    time.sleep(60)
                    continue
                
                self.log(f"SCANNING {len(syms)} ASSETS...")
                found = False
                
                for sym in syms[:self.CFG['max_scan']]:
                    self.stats['scanned'] += 1
                    
                    d, p, atr, reason = self._score(sym)
                    strat = "نقاط ذكية"
                    
                    if not d:
                        d, p, atr, reason = self._ny_signal(sym)
                        strat = "نيويورك"
                    
                    if d and p > 0 and atr > 0:
                        self.log(f"SIGNAL: {sym} {d.upper()} | {reason}", 
                                 notify=True, msg_ar=f"✅ فرصة: {sym} {d.upper()}")
                        
                        if self._open(d, sym, p, atr, strat, reason):
                            found = True
                            break
                
                if not found:
                    self.log("NO SIGNALS")
                
                if time.time() - self.last_scan_summary >= self.CFG['summary_every']:
                    self._summary()
                    self.last_scan_summary = time.time()
                
            except Exception as e:
                self.log(f"LOOP ERROR: {e}")
                time.sleep(15)
            
            time.sleep(self.CFG['loop_sec'])

if __name__ == "__main__":
    bot = SmartBot()
    if bot.api_key:
        bot.run()
