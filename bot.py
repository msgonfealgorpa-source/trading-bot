import ccxt, time, pandas as pd, ta, requests, datetime, os, random

class Tracker:
    def __init__(self, t, c, ex): 
        self.log, self.T, self.C, self.ex = [], t, c, ex
        self.no_signal_counter = 0
        self.last_signal_time = time.time()

    def send(self, m):
        try: 
            requests.post(f"https://api.telegram.org/bot{self.T}/sendMessage", 
                         data={'chat_id': self.C, 'text': m, 'parse_mode': 'Markdown'}, timeout=10)
        except Exception as e: 
            pass

    def debug(self, msg: str, force_tg: bool = False):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}")
        if force_tg and ("❌" in msg or "✅" in msg or "🎯" in msg or "⚠️" in msg or "📊" in msg):
            try: self.send(msg)
            except: pass

    def add(self, s, d, ep, xp, q, p, r):
        self.log.append({'t': datetime.datetime.now(), 's': s, 'd': d, 'ep': ep, 'xp': xp, 
                        'q': float(self.ex.amount_to_precision(s, q)), 'p': p, 'r': r})

    def report(self):
        if not self.log: 
            self.send("📊 لا توجد صفقات في التقرير اليومي")
            return
        w = [t for t in self.log if t['p'] > 0]
        m = f"📊 *تقرير الوحش V7.1*\n📋 الصفقات: {len(self.log)}\n✅ الفوز: {(len(w)/len(self.log))*100:.1f}%\n💰 الربح: {sum(t['p'] for t in self.log):.2f}%"
        self.send(m)
        self.log = [t for t in self.log if t['t'].date() == datetime.date.today()]

    def check_no_signal_alert(self):
        if time.time() - self.last_signal_time > 5400:  # 1.5 ساعة
            self.send("⚠️ *تنبيه*\nلم يتم فتح صفقات منذ 1.5 ساعة")
            self.last_signal_time = time.time() # منع التكرار


class FuturesBot:
    def __init__(self):
        self.K = os.environ.get('API_KEY')
        self.S = os.environ.get('API_SECRET')
        self.TT = os.environ.get('TELEGRAM_TOKEN')
        self.CH = os.environ.get('CHAT_ID')
        
        if not self.K or not self.S or not self.TT:   
            print("❌ خطأ: المفاتيح غير موجودة!"); return  

        self.ex = ccxt.bingx({'apiKey': self.K, 'secret': self.S, 'enableRateLimit': True, 'options': {'defaultType': 'swap'}, 'rateLimit': 1500})  
        self.trk = Tracker(self.TT, self.CH, self.ex)  
        self.trade = None; self.losses = 0; self.dloss = 0.0; self.date = None; self.rtime = datetime.datetime.now(); self.scan_count = 0
        
        self.LEVERAGE = 10   
        self.NY_RISK_PCT = 5.0
        self.LIQUIDITY_MIN = 200000  # تم التخفيض لـ 200K
        
        # فلاتر مستبعدة تماماً لتعظيم الفرص
        self.BTC_RSI_FILTER_ENABLED = False  
        
        self.send("🔄 جاري التحقق...")  
        self.trade = self.load_state_from_exchange()  
          
        msg = "🚀 *بوت الوحش V7.1 (وضع التنفيذ الفوري)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "⚙️ *تعديلات جذرية:*\n"
        msg += "• إلغاء فلتر الاتجاه (Range/Neutral يدخل)\n"
        msg += "• دونشian كسر صرف (بدون شروط)\n"
        msg += "• سيولة 200K فقط\n"
        msg += "• فحص 100 عملة عشوائياً\n"
        msg += "━━━━━━━━━━━━━━━━"
        self.send(msg)  
        
        self.ex.load_markets()
        if self.trade: self.send(f"🧠 استئناف: {self.trade['d']} {self.trade['s']}")
        self.send(f"💰 الرصيد: {self.bal()} USDT")

    def send(self, m): self.trk.send(m)

    def retry(self, fn, *a, **k):  
        for i in range(3):  
            try: return getattr(self.ex, fn)(*a, **k)  
            except Exception as e: time.sleep(5 * (i + 1))  
        return None  

    def ohlcv(self, s, tf, l): return self.retry('fetch_ohlcv', s, tf, limit=l)  
    def tick(self, s): return self.retry('fetch_ticker', s)  
    def bal(self):   
        b = self.retry('fetch_balance', {'type': 'swap'})  
        return float(b.get('USDT', {}).get('free', 0)) if b else 0  
    def ticks(self): return self.retry('fetch_tickers')  
      
    def setup_futures(self, s, d):  
        try: self.ex.set_leverage(self.LEVERAGE, s, params={'marginMode': 'isolated'})
        except: pass  

    def order(self, t, s, q):  
        o = self.retry(f'create_market_{t}_order', s, q)
        if o and o.get('id'): return o
        return None  

    def load_state_from_exchange(self):  
        try:  
            positions = self.retry('fetch_positions')  
            if positions:  
                for pos in positions:  
                    qty = float(pos.get('position', pos.get('contracts', 0)))  
                    if qty > 0:  
                        sym = pos['symbol']; entry = float(pos['entryPrice'])  
                        d = 'short' if 'short' in pos.get('side', 'long').lower() else 'long'  
                        return {'s': sym, 'd': d, 'e': entry, 'sl': entry*(0.97 if d=='long' else 1.03), 'isl': entry*(0.97 if d=='long' else 1.03), 'hp': entry, 'lp': entry, 'time': time.time(), 'q': qty, 'pyramided': True, 'partial_closed': True, 'strategy': "استئناف"}  
        except: pass  
        return None  

    def analyze_old_strategy(self, s, tf):  
        """استراتيجية بولينجر - تعمل في أي اتجاه (صاعد، هابط، نيترال)"""
        b = self.ohlcv(s, tf, 200)  
        if not b: return False, 0, 0, 0, 0, "لا بيانات", None
        df = pd.DataFrame(b, columns=['t','o','h','l','c','v'])  
        df['rsi'] = ta.momentum.rsi(df['c'], 14)  
        df['macd'] = ta.trend.macd_diff(df['c'])
        df['vm'] = df['v'].rolling(20).mean()  
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()  
        bb = ta.volatility.BollingerBands(df['c'], 20, 2)  
        df['bbl'] = bb.bollinger_lband(); df['bbh'] = bb.bollinger_hband()  
        l = df.iloc[-1]; p = df.iloc[-2]
        
        if pd.isna(l['atr']) or l['atr'] == 0: return False, 0, 0, 0, 0, "ATR صفر", None
        vs = l['v'] > (l['vm'] * 1.1) # خففنا الفوليوم أكثر
        prev_body = abs(p['o'] - p['c'])
        if prev_body == 0: prev_body = 0.0001
        
        # فحص Grab صاعد (يعمل حتى في النيترال)
        prev_wick_low = min(p['o'], p['c']) - p['l']
        if prev_wick_low > prev_body and p['l'] < p['bbl'] and l['c'] > l['bbl'] and 30 < l['rsi'] < 60 and l['macd'] > p['macd'] and (l['c'] > l['o']):
            return True, l['c'], l['rsi'], l['bbl'], l['bbh'], "OK", 'long'
            
        # فحص Grab هابط (يعمل حتى في النيترال)
        prev_wick_high = p['h'] - max(p['o'], p['c'])
        if prev_wick_high > prev_body and p['h'] > p['bbh'] and l['c'] < l['bbh'] and 40 < l['rsi'] < 70 and l['macd'] < p['macd'] and (l['c'] < p['o']):
            return True, l['c'], l['rsi'], l['bbl'], l['bbh'], "OK", 'short'
            
        return False, 0, 0, 0, 0, "لا توجد صفقة بولينجر", None

    def analyze_donchian_strategy(self, s, tf):  
        """استراتيجية دونشيان - كسر صرف 100% بدون أي شروط إضافية"""
        b = self.ohlcv(s, tf, 50)  
        if not b or len(b) < 50: return None, 0, 0, "بيانات ناقصة"
        
        df = pd.DataFrame(b, columns=['t','o','h','l','c','v'])  
        df['dc_upper'] = df['h'].rolling(20).max()  
        df['dc_lower'] = df['l'].rolling(20).min()  
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()  
        
        l = df.iloc[-1]; p = df.iloc[-2]
        if pd.isna(l['atr']) or pd.isna(l['dc_upper']): return None, 0, 0, "DC غير جاهز"
        
        # شروط الكسر النقي فقط (الشمعة الحالية تكسر، السابقة لم تكسر)
        if (l['c'] > l['dc_upper']) and (p['c'] <= p['dc_upper']): 
            return 'long', l['c'], l['atr'], "OK"
            
        if (l['c'] < l['dc_lower']) and (p['c'] >= p['dc_lower']): 
            return 'short', l['c'], l['atr'], "OK"
            
        return None, 0, 0, "لا يوجد كسر جديد"

    def _get_ny_open_hour_utc(self):  
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)  
        dst_start = datetime.datetime(now.year, 3, 14); dst_end = datetime.datetime(now.year, 11, 7)  
        return 13 if dst_start <= now <= dst_end else 14

    def analyze_ny_breakout(self, s):  
        """استراتيجية نيويورك - تعمل في أي اتجاه"""
        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        ny_hour = self._get_ny_open_hour_utc()
        ny_open_time = now_utc.replace(hour=ny_hour, minute=30, second=0, microsecond=0)
        
        if now_utc < ny_open_time or (now_utc - ny_open_time).total_seconds() > 14400:
            return None, 0, 0, "خارج توقيت نيويورك"
        
        bars = self.ohlcv(s, '15m', 40)
        if not bars or len(bars) < 10: return None, 0, 0, "بيانات ناقصة"
        
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        df['time'] = pd.to_datetime(df['t'], unit='ms')
        ref_candles = df[(df['time'].dt.hour == ny_hour) & (df['time'].dt.minute == 30) & (df['time'].dt.date == now_utc.date())]
        
        if ref_candles.empty: return None, 0, 0, "لا شمعة افتتاح"
        ref_high = ref_candles.iloc[0]['h']; ref_low = ref_candles.iloc[0]['l']
        
        recent_bars = df[df['time'] > ref_candles.iloc[0]['time']].tail(3)
        if len(recent_bars) < 2: return None, 0, 0, "شمور قليلة"
        
        l = recent_bars.iloc[-1]; df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
        if pd.isna(l['atr']) or l['atr'] <= 0: return None, 0, 0, "ATR صفر"
        
        if l['c'] > ref_high: return 'long', l['c'], l['atr'] * 1.5, "OK"
        if l['c'] < ref_low: return 'short', l['c'], l['atr'] * 1.5, "OK"
        
        return None, 0, 0, "لم يكسر نطاق نيويورك"

    def calc_qty(self, s, p, risk_override=None):  
        b = self.bal()  
        if b <= 0: return 0
        bars = self.ohlcv(s, '15m', 19)
        if not bars: return 0
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        atr = ta.volatility.AverageTrueRange(high=df['h'], low=df['l'], close=df['c'], window=14).average_true_range().iloc[-1]
        if pd.isna(atr) or atr <= 0: return 0
        
        risk_pct = risk_override if risk_override is not None else (0.75 if self.losses >= 3 else 8.0)
        risk = b * (risk_pct / 100)
        sl_dist = 2.5 * atr
        if sl_dist <= 0: return 0
        qty = risk / sl_dist
        
        try:
            m = self.ex.market(s); fq = self.ex.amount_to_precision(s, qty)
            mn = m.get('limits', {}).get('amount', {}).get('min')
            if mn and float(fq) < mn: fq = self.ex.amount_to_precision(s, mn)
        except: fq = self.ex.amount_to_precision(s, qty)
        return float(fq) if float(fq) > 0 else 0

    def close(self, reason, pct, loss=False, partial=False):
        if not self.trade: return
        s, d, q = self.trade['s'], self.trade['d'], float(self.trade['q'])
        if partial: q = q / 2.0
        close_type = 'sell' if d == 'long' else 'buy'
        fq = float(self.ex.amount_to_precision(s, q))
        if fq <= 0: return
        
        o = self.order(close_type, s, fq)
        if not o: self.send(f"🚨 فشل إغلاق {d} {s}"); return
        
        oid = o.get('id', '?')
        if partial:
            self.trade['q'] = str(float(self.trade['q']) - fq)
            self.trade['partial_closed'] = True; self.trade['sl'] = self.trade['e']
            self.send(f"⚡ *إغلاق جزئي 50%*\n🪙 {s}\n💰 مؤمن: {pct:.2f}%\n🆔 {oid}")
            return
            
        self.trk.add(s, d, self.trade['e'], self.tick(s)['last'] if self.tick(s) else self.trade['e'], q, pct, reason)
        if loss:
            self.losses += 1; tb = self.bal(); self.dloss += (abs(pct)/100)*tb if tb > 0 else abs(pct)
            self.send(f"📉 *خسارة*\n🪙 {s} ({d})\n💔 {pct:.2f}%\n❌ {reason}\n🆔 {oid}")
        else:
            self.losses = 0
            self.send(f"🏆 *ربح*\n🪙 {s} ({d})\n💰 {pct:.2f}%\n✅ {reason}\n🆔 {oid}")
        self.trade = None

    def run(self):
        self.send("🚀 *الوحش V7.1 بدأ العمل!*")
        print("\n🚀 بدء التشغيل - فحص 100 عملة عشوائياً كل 45 ثانية...")
        
        while True:
            if self.date != datetime.date.today(): self.dloss = 0.0; self.date = datetime.date.today()
            try:
                if self.dloss >= 20.0: self.send("🛑 حد خسارة 20%"); time.sleep(3600); continue
                
                if not self.trade:
                    self.scan_count += 1
                    self.trk.debug(f"🔍 دورة فحص #{self.scan_count}")
                    
                    tk = self.ticks()
                    if not tk: time.sleep(45); continue
                    
                    # 1. فلتر سيولة 200,000 فقط
                    syms = [s for s, i in tk.items() if s.endswith('/USDT:USDT') and i.get('quoteVolume') and i.get('last') and (i['quoteVolume'] * i['last'] > self.LIQUIDITY_MIN)]
                    
                    if not syms: self.trk.debug("⚠️ لا توجد عملات"); time.sleep(45); continue
                    
                    # 2. خلط عشوائي وأخذ 100 عملة
                    random.shuffle(syms)
                    scan_list = syms[:100]
                    
                    self.trk.debug(f"📊 جاري فحص {len(scan_list)} عملة...", force_tg=(self.scan_count % 5 == 0))
                    
                    found = False
                    for s in scan_list:
                        entered = False; direction = None; price = 0; sl_dist = 0; strategy_used = ""
                        
                        # أ. بولينجر (بدون النظر للاتجاه)
                        ok, p, rsi, bbl, bbh, status, strat_dir = self.analyze_old_strategy(s, '15m')
                        if ok:
                            direction, price, strategy_used = strat_dir, p, "[1] بولينجر"
                            bars = self.ohlcv(s, '15m', 19)
                            df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
                            atr = ta.volatility.AverageTrueRange(high=df['h'], low=df['l'], close=df['c'], 14).average_true_range().iloc[-1]
                            sl_dist = 2.5 * atr if not pd.isna(atr) else p * 0.02
                            entered = True
                        
                        # ب. دونشيان (كسر صرف بدون أي شروط)
                        if not entered:
                            donch_dir, donch_p, donch_atr, _ = self.analyze_donchian_strategy(s, '15m')
                            if donch_dir:
                                direction, price, sl_dist, strategy_used = donch_dir, donch_p, 1.5 * donch_atr, "[2] دونشيان"
                                entered = True
                        
                        # ج. نيويورك (بدون النظر للاتجاه)
                        if not entered:
                            ny_dir, ny_p, ny_sl, _ = self.analyze_ny_breakout(s)
                            if ny_dir:
                                direction, price, sl_dist, strategy_used = ny_dir, ny_p, ny_sl, "🗽 [3] نيويورك"
                                entered = True
                        
                        # تنفيذ
                        if entered and direction and price > 0 and sl_dist > 0:
                            risk_val = self.NY_RISK_PCT if "نيويورك" in strategy_used else None
                            q = self.calc_qty(s, price, risk_override=risk_val)
                            if q <= 0: continue
                            
                            self.setup_futures(s, direction)
                            o = self.order('buy' if direction == 'long' else 'sell', s, q)
                            
                            if o:
                                sl = (price - sl_dist) if direction == 'long' else (price + sl_dist)
                                self.trade = {'s': s, 'd': direction, 'e': price, 'sl': sl, 'isl': sl, 'hp': price, 'lp': price, 'time': time.time(), 'q': q, 'pyramided': False, 'partial_closed': False, 'strategy': strategy_used}
                                
                                emoji = "🟢LONG" if direction == 'long' else "🔴SHORT"
                                msg = f"{emoji} *صفقة جديدة*\n🪙 {s}\n📊 {strategy_used}\n💵 {price:.4f}\n⚖️ {q:.4f}\n🛑 {sl:.4f}\n🆔 {o.get('id')}"
                                self.send(msg)
                                self.trk.debug(f"✅ تم الدخول: {s} {direction}")
                                self.losses = 0; self.trk.last_signal_time = time.time()
                                found = True; break
                    
                    if not found: self.trk.check_no_signal_alert()
                
                else:
                    s, d = self.trade['s'], self.trade['d']
                    t = self.tick(s)
                    if not t: time.sleep(30); continue
                    cp = t['last']; ep = self.trade['e']
                    pp = ((cp - ep) / ep * 100) if d == 'long' else ((ep - cp) / ep * 100)
                    
                    if d == 'long' and cp > self.trade['hp']: self.trade['hp'] = cp
                    if d == 'short' and cp < self.trade['lp']: self.trade['lp'] = cp
                    hpp = ((self.trade['hp'] - ep) / ep * 100) if d == 'long' else ((ep - self.trade['lp']) / ep * 100)
                    
                    self.trk.debug(f"⏱️ {s} | {pp:.2f}%")
                    
                    if (d == 'long' and cp <= self.trade['sl']) or (d == 'short' and cp >= self.trade['sl']): 
                        self.close("🛑 SL", pp, True); continue
                        
                    bars = self.ohlcv(s, '15m', 20)
                    if bars:
                        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
                        if df.iloc[-1]['v'] > (df['v'].rolling(20).mean().iloc[-1] * 4): 
                            self.close("🔥 انفجار فوليوم", pp); continue

                    if time.time() - self.trade['time'] > 3600 and abs(pp) < 1.0: self.close("⏳ انتهاء الوقت", pp, pp<0); continue
                    if pp >= 3.0 and not self.trade.get('partial_closed'): self.close("⚡ جزئي", pp, partial=True); continue
                    
                    if pp >= 2.0 and not self.trade.get('pyramided'):
                        add_q = self.calc_qty(s, cp)
                        if add_q > 0 and self.order('buy' if d == 'long' else 'sell', s, add_q):
                            self.trade['pyramided'] = True; self.trade['q'] = str(float(self.trade['q']) + add_q)
                            self.send(f"🚀 تعزيز {s}")

                    if pp >= 10.0: self.close("🎯 الهدف", pp); continue
                    
                    if hpp >= 2.5:
                        nsl = self.trade['hp'] * 0.995 if d == 'long' else self.trade['lp'] * 1.005
                        if (d == 'long' and nsl > self.trade['sl']) or (d == 'short' and nsl < self.trade['sl']): self.trade['sl'] = nsl
                            
            except Exception as e: 
                self.trk.debug(f"⚠️ خطأ: {e}")
                time.sleep(30)
            
            # 3. التأخير 45 ثانية
            time.sleep(45)
            if (datetime.datetime.now() - self.rtime).total_seconds() >= 86400: self.trk.report(); self.rtime = datetime.datetime.now()

if __name__ == "__main__":
    bot = FuturesBot()
    if bot.K: bot.run()
