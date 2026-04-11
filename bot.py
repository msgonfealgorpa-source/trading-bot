import ccxt, time, pandas as pd, ta, requests, datetime, os, warnings

# لإخفاء التحذيرات الصفراء التي تلوث الشاشة
warnings.filterwarnings("ignore", category=DeprecationWarning)

class Tracker:
    def __init__(self, t, c, ex): self.log, self.T, self.C, self.ex = [], t, c, ex
    def send(self, m):
        try: requests.post(f"https://api.telegram.org/bot{self.T}/sendMessage", data={'chat_id': self.C, 'text': m, 'parse_mode': 'Markdown'})
        except: pass
    def add(self, s, d, ep, xp, q, p, r):
        self.log.append({'t': datetime.now(datetime.timezone.utc), 's': s, 'd': d, 'ep': ep, 'xp': xp, 'q': float(self.ex.amount_to_precision(s, q)), 'p': p, 'r': r})
    def report(self):
        if not self.log: return
        w = [t for t in self.log if t['p'] > 0]
        m = f"📊 *تقرير الوحش V6.1*\nالصفقات: {len(self.log)}\nالفوز: {(len(w)/len(self.log))*100:.1f}%\nالربح: {sum(t['p'] for t in self.log):.2f}%"
        self.send(m); self.log = [t for t in self.log if t['t'].date() == datetime.now().date()]

class FuturesBot:
    def __init__(self):
        self.K = os.environ.get('API_KEY')
        self.S = os.environ.get('API_SECRET')
        self.TT = os.environ.get('TELEGRAM_TOKEN')
        self.CH = os.environ.get('CHAT_ID')
        
        if not self.K or not self.S or not self.TT: 
            print("❌ خطأ: المفاتيح غير موجودة!")
            return

        self.ex = ccxt.bingx({'apiKey': self.K, 'secret': self.S, 'enableRateLimit': True, 'options': {'defaultType': 'swap'}, 'rateLimit': 2000})
        self.trk = Tracker(self.TT, self.CH, self.ex)
        self.trade = None; self.losses = 0; self.dloss = 0.0; self.date = None; self.rtime = datetime.now()
        self.LEVERAGE = 10 
        
        self.NY_EMA_FILTER = True    
        self.NY_RSI_FILTER = True    
        self.NY_VOL_FILTER = True    
        self.NY_CANDLE_FILTER = True 
        self.NY_RISK_PCT = 5.0      

        self.send("🔄 جاري التحقق من الصفقات المفتوحة...")
        self.trade = self.load_state_from_exchange()
        
        msg = "🗽 *بوت الوحش V6.1 (مثالي)*\n"
        msg += "⚡ 1: بولينجر/ماكدي (8% مخاطرة)\n"
        msg += "🚀 2: كسر دونشين (8% مخاطرة)\n"
        msg += "🗽 3: حيلة نيويورك (5% مخاطرة + توقيت تلقائي)\n"
        msg += "📋 الرافعة: 10X"
        self.send(msg)
        print("جاري تحميل أسواق العقود...")
        self.ex.load_markets(); print("✅ تم التحميل!")
        
        if self.trade: self.send(f"🧠 *تم استئناف صفقة: {self.trade['d']} {self.trade['s']}*")
        
        check_bal = self.bal()
        print(f"🔍 تشخيص: الرصيد المتاح في USDT-M = {check_bal} USDT")
        self.send(f"📊 *تشخيص الحساب*\n💰 الرصيد في (USDT-M): {check_bal} USDT")

    def send(self, m): self.trk.send(m)
    def retry(self, fn, *a, **k):
        for i in range(5):
            try:
                r = getattr(self.ex, fn)(*a, **k)
                return r if r is not None else None
            except Exception as e:
                print(f"Err {fn}: {e}"); time.sleep(5 * (i + 1))
        return None
    def ohlcv(self, s, tf, l): return self.retry('fetch_ohlcv', s, tf, limit=l)
    def tick(self, s): return self.retry('fetch_ticker', s)
    def bal(self): 
        b = self.retry('fetch_balance', {'type': 'swap'})
        return float(b.get('USDT', {}).get('free', 0))
    def ticks(self): return self.retry('fetch_tickers')
    
    def setup_futures(self, s, d):
        try: self.ex.set_leverage(self.LEVERAGE, s, params={'marginMode': 'isolated'})
        except: pass

    def order(self, t, s, q):
        o = self.retry(f'create_market_{t}_order', s, q)
        return o if o and o.get('id') else None

    def load_state_from_exchange(self):
        try:
            positions = self.retry('fetch_positions')
            if positions:
                for pos in positions:
                    qty = float(pos.get('position', pos.get('contracts', 0)))
                    if qty > 0:
                        sym = pos['symbol']; entry = float(pos['entryPrice'])
                        side = pos.get('side', 'long').lower()
                        d = 'short' if 'short' in side else 'long'
                        return {'s': sym, 'd': d, 'e': entry, 'sl': entry*(0.97 if d=='long' else 1.03), 'isl': entry*(0.97 if d=='long' else 1.03), 'hp': entry, 'lp': entry, 'time': time.time(), 'q': qty, 'pyramided': True, 'partial_closed': True, 'strategy': "استئناف"}
        except Exception as e: print(f"Err load state: {e}")
        return None

    def get_btc_rsi(self):
        b = self.ohlcv('BTC/USDT:USDT', '15m', 15)
        if not b: return 50
        return ta.momentum.rsi(pd.DataFrame(b, columns=['t','o','h','l','c','v'])['c'], window=14).iloc[-1]

    def regime(self, s):
        b = self.ohlcv(s, '1h', 100)
        if not b: return "neutral"
        df = pd.DataFrame(b, columns=['t','o','h','l','c','v'])
        df['e1'] = ta.trend.ema_indicator(df['c'], 100); df['e2'] = ta.trend.ema_indicator(df['c'], 200)
        l = df.iloc[-1]; p = df.iloc[-2]
        if l['c'] > l['e1'] and l['e1'] > l['e2'] and l['e1'] > p['e1']: return "uptrend"
        if l['c'] < l['e1'] and l['e1'] < l['e2'] and l['e1'] < p['e1']: return "downtrend"
        return "neutral"

    def analyze_old_strategy(self, s, tf, reg):
        b = self.ohlcv(s, tf, 200)
        if not b: return False, 0, 0, 0, 0
        df = pd.DataFrame(b, columns=['t','o','h','l','c','v'])
        df['e2'] = ta.trend.ema_indicator(df['c'], 200); df['rsi'] = ta.momentum.rsi(df['c'], 14)
        df['macd'] = ta.trend.macd_diff(df['c']); df['vm'] = df['v'].rolling(20).mean()
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
        bb = ta.volatility.BollingerBands(df['c'], 20, 2)
        df['bbl'] = bb.bollinger_lband(); df['bbh'] = bollinger_hband()
        l = df.iloc[-1]; p = df.iloc[-2]
        if tf == '15m':
            if l['atr'] is None: return False, 0, 0, 0, 0
            vs = l['v'] > (l['vm'] * 1.5)
            prev_body = abs(p['o'] - p['c'])
            if reg == "uptrend":
                prev_wick_low = min(p['o'], p['c']) - p['l']
                is_grab = (prev_wick_low > prev_body * 1.5) and (p['l'] < p['bbl'])
                cond = l['c'] > l['e2'] and is_grab and (l['c'] > l['bbl']) and 35 < l['rsi'] < 55 and l['macd'] > p['macd'] and vs and (l['c'] > l['o'])
                if cond: return True, l['c'], l['rsi'], l['bbl'], l['bbh']
            elif reg == "downtrend":
                prev_wick_high = p['h'] - max(p['o'], p['c'])
                is_grab = (prev_wick_high > prev_body * 1.5) and (p['h'] > p['bbh'])
                cond = l['c'] < l['e2'] and is_grab and (l['c'] < l['bbh']) and 45 < l['rsi'] < 65 and l['macd'] < p['macd'] and vs and (l['c'] < p['o'])
                if cond: return True, l['c'], l['rsi'], l['bbl'], l['bbh']
        return False, 0, 0, 0, 0

    def analyze_donchian_strategy(self, s, tf):
        b = self.ohlcv(s, tf, 50)
        if not b or len(b) < 50: return None, 0, 0
        df = pd.DataFrame(b, columns=['t','o','h','l','c','v'])
        df['e2'] = ta.trend.ema_indicator(df['c'], 200)
        df['dc_upper'] = df['h'].rolling(20).max()
        df['dc_lower'] = df['l'].rolling(20).min()
        df['vm'] = df['v'].rolling(20).mean()
        df['rsi'] = ta.momentum.rsi(df['c'], 14)
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
        l = df.iloc[-1]; p = df.iloc[-2]
        if pd.isna(l['atr']) or pd.isna(l['dc_upper']): return None, 0, 0
        vs = l['v'] > l['vm']
        long_cond = (l['c'] > l['e2']) and (l['c'] > l['dc_upper']) and (p['c'] <= p['dc_upper']) and vs and (l['rsi'] > 50)
        short_cond = (l['c'] < l['e2']) and (l['c'] < l['dc_lower']) and (p['c'] >= p['dc_lower']) and vs and (l['rsi'] < 50)
        if long_cond: return 'long', l['c'], l['atr']
        if short_cond: return 'short', l['c'], l['atr']
        return None, 0, 0

    def _get_ny_open_hour_utc(self):
        now = datetime.now(datetime.timezone.utc)
        year = now.year
        dst_start = datetime.datetime(year, 3, 14)
        dst_end = datetime.datetime(year, 11, 7)
        if dst_start <= now <= dst_end:
            return 13 
        else:
            return 14

    def analyze_ny_breakout(self, s):
        now_utc = datetime.now(datetime.timezone.utc)
        ny_hour = self._get_ny_open_hour_utc()
        ny_open_time = now_utc.replace(hour=ny_hour, minute=30, second=0, microsecond=0)
        
        if now_utc < ny_open_time: return None, 0, 0
        
        bars = self.ohlcv(s, '15m', 40)
        if not bars or len(bars) < 10: return None, 0, 0
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        df['time'] = pd.to_datetime(df['t'], unit='ms')
        
        ref_mask = (df['time'].dt.hour == ny_hour) & (df['time'].dt.minute == 30) & (df['time'].dt.date == now_utc.date())
        ref_candles = df[ref_mask]
        if ref_candles.empty: return None, 0, 0
        
        ref_high = ref_candles.iloc[0]['h']
        ref_low = ref_candles.iloc[0]['l']
        
        future_bars = df[df['time'] > ref_candles.iloc[0]['time']]
        
        # ✅ أخذ آخر 5 شموع فقط للـ Retest السريع
        recent_bars = future_bars.tail(5)
        if len(recent_bars) < 3: return None, 0, 0 
        
        l = recent_bars.iloc[-1] 
        p = recent_bars.iloc[-2] 
        
        df['e2'] = ta.trend.ema_indicator(df['c'], window=200)
        df['rsi'] = ta.momentum.rsi(df['c'], window=14)
        
        # ✅ حل مشكلة 'vm': نأخذ المتوسط من الداتا الكاملة لأن الـ 5 شموع لا تحتوي عليه
        df['vm'] = df['v'].rolling(20).mean()
        vm_current = df['vm'].iloc[-1] 
        
        vs = (l['v'] > vm_current * 1.2) if self.NY_VOL_FILTER else True
        
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], window=14).average_true_range()
        if pd.isna(l['e2']) or pd.isna(l['rsi']) or pd.isna(l['atr']) or pd.isna(vm_current): return None, 0, 0
        
        body = abs(l['c'] - l['o'])
        upper_wick = l['h'] - max(l['c'], l['o'])
        lower_wick = min(l['c'], l['o']) - l['l']
        is_strong_candle = (body > (upper_wick + lower_wick)) if self.NY_CANDLE_FILTER else True
        
        long_break = any(recent_bars['c'] > ref_high) 
        if long_break:
            long_retest = p['l'] <= ref_high 
            long_entry = l['c'] > ref_high 
            
            if long_retest and long_entry and is_strong_candle and vs:
                if not self.NY_EMA_FILTER or l['c'] > l['e2']:
                    if not self.NY_RSI_FILTER or l['rsi'] > 50:
                        return 'long', l['c'], l['atr'] * 1.5

        short_break = any(recent_bars['c'] < ref_low) 
        if short_break:
            short_retest = p['h'] >= ref_low
            short_entry = l['c'] < ref_low
            
            if short_retest and short_entry and is_strong_candle and vs:
                if not self.NY_EMA_FILTER or l['c'] < l['e2']:
                    if not self.NY_RISK_PCT or l['rsi'] < 50:
                        return 'short', l['c'], l['atr'] * 1.5
                            
        return None, 0, 0

    def calc_qty(self, s, p, risk_override=None):
        b = self.bal()
        if b == 0: return 0
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
        s = self.trade['s']; d = self.trade['d']
        q = float(self.trade['q'])
        if partial: q = q / 2.0
        close_type = 'sell' if d == 'long' else 'buy'
        fq = float(self.ex.amount_to_precision(s, q))
        if fq <= 0: return
        t = self.tick(s); xp = self.trade['e'] if not t else t['last']
        if not self.order(close_type, s, fq): self.send(f"🚨 فشل إغلاق {d} {s}"); return
        if partial:
            self.trade['q'] = str(float(self.trade['q']) - fq)
            self.trade['partial_closed'] = True
            self.trade['sl'] = self.trade['e']
            self.send(f"⚡ *إغلاق جزئي (50%)*\n🪙 {s} ({d})\n💰 secured: {pct:.2f}%\n🛑 SL للدخول")
            return
        self.trk.add(s, d, self.trade['e'], xp, q, pct, reason)
        if loss:
            self.losses += 1; tb = self.bal()
            self.dloss += (abs(pct)/100)*tb if tb > 0 else abs(pct)
            self.send(f"📉 خسارة {d} {s}: {pct:.2f}%")
        else:
            self.losses = 0; self.send(f"🏆 ربح {d} {s}: {pct:.2f}% | {reason}")
        self.trade = None

    def run(self):
        self.send("🚀 *الوحش V6.1 (مثالي) جاهز!*")
        print("\n🚀 بدء المحرك الثلاثي...")
        while True:
            if self.date != datetime.now().date(): self.dloss = 0.0; self.date = datetime.now().date()
            try:
                if self.dloss >= 20.0: self.send("🛑 حد خسارة يومي 20%"); time.sleep(3600); continue
                
                if not self.trade:
                    print("🔍 جاري الفحص...", end='\r')
                    btc_rsi = self.get_btc_rsi()
                    if btc_rsi < 40 or btc_rsi > 60: 
                        print(f"⚠️ BTC متطرف (RSI: {btc_rsi:.1f}). تجاهل.", end='\r'); time.sleep(60); continue
                    
                    tk = self.ticks()
                    if not tk: time.sleep(30); continue
                    syms = [s for s, i in tk.items() if s.endswith('/USDT:USDT') and i.get('quoteVolume') and i.get('last') and (i['quoteVolume']*i['last'] > 1000000)][:100]
                    if not syms: time.sleep(60); continue
                    
                    for s in syms:
                        rg = self.regime(s)
                        entered = False; strategy_used = ""; direction = None; price = 0; sl_dist = 0
                        
                        if rg in ["uptrend", "downtrend"]:
                            ok, p, rsi, bbl, bbh = self.analyze_old_strategy(s, '15m', rg)
                            if ok:
                                direction = 'long' if rg == "uptrend" else 'short'
                                price = p
                                bars = self.ohlcv(s, '15m', 19)
                                df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
                                atr = ta.volatility.AverageTrueRange(high=df['h'], low=df['l'], close=df['c'], window=14).average_true_range().iloc[-1]
                                sl_dist = 2.5 * atr if not pd.isna(atr) else p * 0.025
                                strategy_used = "[استراتيجية 1] بولينجر/ماكدي"
                                entered = True
                                
                        if not entered:
                            donch_dir, donch_p, donch_atr = self.analyze_donchian_strategy(s, '15m')
                            if donch_dir:
                                direction = donch_dir; price = donch_p; sl_dist = 1.5 * donch_atr 
                                strategy_used = "[استراتيجية 2] كسر دونشين"
                                entered = True

                        if not entered:
                            ny_dir, ny_p, ny_sl = self.analyze_ny_breakout(s)
                            if ny_dir:
                                direction = ny_dir; price = ny_p; sl_dist = ny_sl
                                strategy_used = "🗽 [استراتيجية 3] NY Retest (مخاطر منخفضة)"
                                entered = True

                        if entered and direction and price > 0 and sl_dist > 0:
                            risk_val = self.NY_RISK_PCT if "نيويورك" in strategy_used or "NY" in strategy_used else None
                            q = self.calc_qty(s, price, risk_override=risk_val)
                            if q <= 0: continue
                            
                            self.setup_futures(s, direction)
                            if self.order('buy' if direction == 'long' else 'sell', s, q):
                                if direction == 'long': sl = price - sl_dist
                                else: sl = price + sl_dist
                                
                                self.trade = {
                                    's': s, 'd': direction, 'e': price, 'sl': sl, 'isl': sl, 
                                    'hp': price, 'lp': price, 'time': time.time(), 'q': q, 
                                    'pyramided': False, 'partial_closed': False,
                                    'strategy': strategy_used
                                }
                                emoji = "🟢LONG" if direction == 'long' else "🔴SHORT"
                                self.send(f"{emoji} *عقد جديد*\n{strategy_used}\n🪙 {s}\n💵 {price:.4f}\n⚖️ {q:.4f}\n🛑 SL: {sl:.4f}")
                                print(f"\n🎯 تم فتح {emoji} ({strategy_used}) على {s}!\n")
                                self.losses = 0; break
                
                else:
                    s = self.trade['s']; d = self.trade['d']; t = self.tick(s)
                    if not t: time.sleep(15); continue
                    cp = t['last']; ep = self.trade['e']
                    pp = ((cp - ep) / ep * 100) if d == 'long' else ((ep - cp) / ep * 100)
                    if d == 'long' and cp > self.trade['hp']: self.trade['hp'] = cp
                    if d == 'short' and cp < self.trade['lp']: self.trade['lp'] = cp
                    hpp = ((self.trade['hp'] - ep) / ep * 100) if d == 'long' else ((ep - self.trade['lp']) / ep * 100)
                    
                    strat_name = self.trade.get('strategy', "")
                    print(f"⏱️ {d} {s} | {strat_name} | ربح: {pp:.2f}%     ", end='\r')
                    
                    ssl = self.trade['sl']
                    if d == 'long' and cp <= ssl: self.close("🛑 SL Long", pp, True); continue
                    if d == 'short' and cp >= ssl: self.close("🛑 SL Short", pp, True); continue
                    
                    bars = self.ohlcv(s, '15m', 20)
                    if bars:
                        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
                        vol_ma = df['v'].rolling(20).mean().iloc[-1]
                        if df.iloc[-1]['v'] > (vol_ma * 4): self.close("🔥 انفجار فوليوم", pp, False); continue

                    if time.time() - self.trade['time'] > 3600 and abs(pp) < 1.0: self.close("⏳ انتهاء الوقت", pp, pp<0); continue
                    if pp >= 3.0 and not self.trade.get('partial_closed'): self.close("⚡ جزئي 50%", pp, partial=True); continue
                    
                    if pp >= 2.0 and not self.trade.get('pyramided'):
                        add_q = self.calc_qty(s, cp)
                        if add_q > 0:
                            o_type = 'buy' if d == 'long' else 'sell'
                            if self.order(o_type, s, add_q):
                                self.trade['pyramided'] = True
                                self.trade['q'] = str(float(self.trade['q']) + add_q)
                                self.send(f"🚀 *تعزيز!* {s}\nمضاعفة العقد: {self.trade['q']}")
                                time.sleep(2); continue

                    if pp >= 10.0: self.close("🎯 الهدف 10%", pp, False); continue
                    
                    if hpp >= 2.5:
                        if d == 'long':
                            nsl = self.trade['hp'] * (1 - 0.5 / 100)
                            if nsl > self.trade['sl']: self.trade['sl'] = nsl
                        elif d == 'short':
                            nsl = self.trade['lp'] * (1 + 0.5 / 100)
                            if nsl < self.trade['sl']: self.trade['sl'] = nsl
                            
            except Exception as e: print(f"\n⚠️ Err: {e}"); time.sleep(15)
            time.sleep(15)
            if (datetime.now() - self.rtime).total_seconds() >= 86400: self.trk.report(); self.rtime = datetime.now()

if __name__ == "__main__": FuturesBot().run()
