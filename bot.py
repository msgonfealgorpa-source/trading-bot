import ccxt, time, pandas as pd, ta, requests, datetime, json, os

FILE = "bot_state.json"

class Tracker:
    def __init__(self, t, c, ex):
        self.log, self.T, self.C, self.ex = [], t, c, ex
    def send(self, m):
        try: requests.post(f"https://api.telegram.org/bot{self.T}/sendMessage", data={'chat_id': self.C, 'text': m, 'parse_mode': 'Markdown'})
        except: pass
    def add(self, s, ep, xp, q, p, r):
        self.log.append({'t': datetime.datetime.now(), 's': s, 'ep': ep, 'xp': xp, 'q': float(self.ex.amount_to_precision(s, q)), 'p': p, 'r': r})
    def report(self):
        if not self.log: return
        w = [t for t in self.log if t['p'] > 0]
        m = f"📊 *تقرير V3*\nالصفقات: {len(self.log)}\nالفوز: {(len(w)/len(self.log))*100:.1f}%\nالربح: {sum(t['p'] for t in self.log):.2f}%"
        self.send(m); self.log = [t for t in self.log if t['t'].date() == datetime.date.today()]

class KrakenBot:
    def __init__(self):
        self.K = 'egAeFM8kVEn7YRKPIHRpJGpDW4GFuHRDHFnRmRqdEWcZxPRAb0qHbvd6T6X3MC94Ffqfgc4BSv9mxbBPXSQ'
        self.S = 'OC7UgGik9WOSjUI6r4AvbqfZIq9O9BrjzC2LRrott95Ewcu2jQHRnjCNQj8sn9ZdKIsAf9ioAkp89xs1e7g'
        self.TT = '8744586010:AAET91PN6ApW3FiX4WU1nSH_F5xoHuzIQKk'
        self.CH = '7520475220'
        self.ex = ccxt.bingx({'apiKey': self.K, 'secret': self.S, 'enableRateLimit': True, 'options': {'defaultType': 'spot'}, 'rateLimit': 2000})
        self.trk = Tracker(self.TT, self.CH, self.ex)
        self.losses = 0; self.dloss = 0.0; self.date = None; self.rtime = datetime.datetime.now()
        
        print("🛡️ جاري تحميل الذاكرة المحلية...")
        self.trade = self.load_state()
        self.send("✨ *الوحش V3 (The Kraken) استيقظ!*")
        if self.trade: self.send(f"🔄 تم استعادة صفقة مفتوحة: {self.trade['s']}")
        
        print("⏳ جاري تحميل أسواق BingX...")
        self.ex.load_markets()
        print("✅ الجاهزية 100%")

    def send(self, m): self.trk.send(m)
    def save_state(self):
        try:
            with open(FILE, 'w') as f: json.dump(self.trade, f)
        except Exception as e: print(f"Err Save: {e}")
    def load_state(self):
        if os.path.exists(FILE):
            try:
                with open(FILE, 'r') as f: return json.load(f)
            except: return None
        return None

    def retry(self, fn, *a, **k):
        for i in range(5):
            try:
                r = getattr(self.ex, fn)(*a, **k)
                return r if r is not None else None
            except Exception as e:
                print(f"Err {fn}: {e}"); time.sleep(5 * (i + 1))
        return None
    def ohlcv(self, s, tf, l=50): return self.retry('fetch_ohlcv', s, tf, limit=l)
    def tick(self, s): return self.retry('fetch_ticker', s)
    def bal(self): return self.retry('fetch_balance')
    def ticks(self): return self.retry('fetch_tickers')
    def order(self, t, s, q):
        o = self.retry(f'create_market_{t}_order', s, q)
        return o if o and o.get('id') else None

    def get_btc_rsi(self):
        b = self.ohlcv('BTC/USDT', '15m', 15)
        return ta.momentum.rsi(pd.DataFrame(b, columns=['t','o','h','l','c','v'])['c'], 14).iloc[-1] if b else 50

    def check_mtf(self, s):
        # فحص 4h و 1h للتأكد من الاتجاه (استخدام EMA 50 بدل 200 لتوفير الرام)
        d1 = self.ohlcv(s, '1h', 55)
        if not d1: return False
        df1 = pd.DataFrame(d1, columns=['t','o','h','l','c','v'])
        if df1['c'].iloc[-1] < ta.trend.ema_indicator(df1['c'], 50).iloc[-1]: return False
        
        d4 = self.ohlcv(s, '4h', 55)
        if not d4: return False
        df4 = pd.DataFrame(d4, columns=['t','o','h','l','c','v'])
        if df4['c'].iloc[-1] < ta.trend.ema_indicator(df4['c'], 50).iloc[-1]: return False
        return True

    def analyze_15m(self, s):
        b = self.ohlcv(s, '15m', 100)
        if not b: return False, 0, 0, 0
        df = pd.DataFrame(b, columns=['t','o','h','l','c','v'])
        df['rsi'] = ta.momentum.rsi(df['c'], 14); df['macd'] = ta.trend.macd_diff(df['c'])
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
        bb = ta.volatility.BollingerBands(df['c'], 20, 2)
        df['bbl'] = bb.bollinger_lband(); df['bbh'] = bb.bollinger_hband()
        l = df.iloc[-1]; p = df.iloc[-2]
        
        if pd.isna(l['atr']) or l['atr'] <= 0: return False, 0, 0, 0
        
        # 1. صيد الحيتان (Volume Spike): الحجم أعلى من ضعف أعلى حجم في 20 شمعة
        vol_spike = l['v'] > (df['v'].shift(1).rolling(20).max().iloc[-1] * 2)
        
        # 2. الكسر الوهمي (Liquidity Sweep): الفتيل اخترق البولينجر لكن الإغلاق فوقه
        sweep = (l['l'] < l['bbl']) and (l['c'] > l['bbl']) and (p['l'] < p['bbl'])
        
        # 3. الزخم
        rsi_ok = 35 < l['rsi'] < 60
        macd_ok = l['macd'] > p['macd']
        
        if sweep and vol_spike and rsi_ok and macd_ok:
            return True, l['c'], l['atr'], l['bbh']
        return False, 0, 0, 0

    def calc_qty(self, s, p, atr):
        b = float(self.bal().get('USDT', {}).get('free', 0))
        if b == 0: return 0
        risk = b * (0.75 if self.losses >= 3 else 1.5) / 100
        sl_dist = 2.5 * atr
        if p - sl_dist <= 0: return 0
        qty = risk / sl_dist
        try:
            m = self.ex.market(s); fq = self.ex.amount_to_precision(s, qty)
            mn = m.get('limits', {}).get('amount', {}).get('min')
            if mn and float(fq) < mn: fq = self.ex.amount_to_precision(s, mn)
        except: fq = self.ex.amount_to_precision(s, qty)
        return float(fq) if float(fq) > 0 else 0

    def close(self, reason, pct, loss=False):
        if not self.trade: return
        s = self.trade['s']; c = s.split('/')[0]; b = self.bal()
        if not b or c not in b or b[c].get('free', 0) <= 0: 
            self.trade = None; self.save_state(); return
        q = float(self.ex.amount_to_precision(s, b[c]['free']))
        if q <= 0: self.trade = None; self.save_state(); return
        t = self.tick(s); xp = self.trade['e'] if not t else t['last']
        if not self.order('sell', s, q): self.send(f"🚨 فشل إغلاق {s}"); return
        self.trk.add(s, self.trade['e'], xp, q, pct, reason)
        if loss:
            self.losses += 1; tb = float(self.bal().get('USDT', {}).get('free', 0))
            self.dloss += (abs(pct)/100)*tb if tb > 0 else abs(pct)
            self.send(f"📉 خسارة {s}: {pct:.2f}% | {reason}")
        else:
            self.losses = 0; self.send(f"🏆 ربح {s}: {pct:.2f}% | {reason}")
        self.trade = None; self.save_state()

    def run(self):
        print("\n🦑 تم بدء دورة الوحش V3...\n")
        while True:
            if self.date != datetime.date.today(): self.dloss = 0.0; self.date = datetime.date.today()
            try:
                if self.dloss >= 3.0: self.send("🛑 حد الخسارة اليومي"); time.sleep(3600); continue
                
                if not self.trade:
                    print("🔍 [1/4] فحص نبض البيتكوين...")
                    if self.get_btc_rsi() < 40: print("🛑 BTC ينهار. انتظار..."); time.sleep(60); continue
                    
                    print("🌐 [2/4] جلب سيولة السوق...")
                    tk = self.ticks()
                    if not tk: time.sleep(30); continue
                    
                    # فلتر أولي سريع
                    syms = [s for s, i in tk.items() if s.endswith('/USDT') and ':' not in s and i.get('quoteVolume') and i.get('last') and (i['quoteVolume']*i['last'] > 5000000) and abs(i.get('change', 0)) > 1.5][:20]
                    if not syms: print("💤 لا عملات مطابقة."); time.sleep(60); continue
                    
                    print(f"🧠 [3/4] تحليل ذكي لـ {len(syms)} عملة (MTF + Smart Money)...")
                    for s in syms:
                        print(f"-> فحص {s}...", end='\r')
                        # الخطوة الأهم: التأكد من 4h و 1h قبل تحليل 15m
                        if not self.check_mtf(s): continue
                        
                        ok, p, atr, bbh = self.analyze_15m(s)
                        if ok:
                            q = self.calc_qty(s, p, atr)
                            if q <= 0: continue
                            if self.order('buy', s, q):
                                sl = p - (2.5 * atr)
                                self.trade = {'s': s, 'e': p, 'sl': sl, 'isl': sl, 'hp': p, 'time': time.time(), 'bbh': bbh}
                                self.save_state() # حفظ فوري في الذاكرة
                                self.send(f"🎯 *دخول وحش (MTF + Sweep)*\n🪙 {s}\n💵 {p:.4f}\n⚖️ {q:.6f}\n🛑 SL: {sl:.4f}")
                                print(f"\n🦑 🦑 🦑 تم فتح صفقة قاتلة على {s}!\n")
                                self.losses = 0; break
                else:
                    s = self.trade['s']; t = self.tick(s)
                    if not t: time.sleep(15); continue
                    cp = t['last']; ep = self.trade['e']; pp = ((cp - ep) / ep) * 100
                    if cp > self.trade['hp']: self.trade['hp'] = cp
                    hpp = ((self.trade['hp'] - ep) / ep) * 100
                    print(f"⏱️ مراقبة {s} | ربح: {pp:.2f}% | ذروة: {hpp:.2f}% | SL: {self.trade['sl']:.4f}   ", end='\r')
                    
                    ssl = max(self.trade['sl'], self.trade['isl'])
                    if cp <= ssl: self.close("🛑 ضرب وقف الخسارة", pp, True); continue
                    if time.time() - self.trade['time'] > 3600 and pp < 1.0: self.close("⏳ انتهاء الوقت", pp, True); continue
                    
                    # جلب ATR الديناميكي للتريلينغ
                    bars = self.ohlcv(s, '15m', 20)
                    if not bars: continue
                    atr_now = ta.volatility.AverageTrueRange(high=pd.DataFrame(bars, columns=['t','o','h','l','c','v'])['h'], low=pd.DataFrame(bars, columns=['t','o','h','l','c','v'])['l'], close=pd.DataFrame(bars, columns=['t','o','h','l','c','v'])['c'], window=14).average_true_range().iloc[-1]
                    if pd.isna(atr_now): continue
                    
                    # 🌟 التريلينغ الديناميكي (خنق السعر)
                    if hpp > 4.0: nsl = self.trade['hp'] - (atr_now * 1.0)      # خنق شديد جداً
                    elif hpp > 2.0: nsl = self.trade['hp'] - (atr_now * 1.5)    # خنق متوسط
                    else: nsl = self.trade['isl']                                # بدون خنق
                    
                    if nsl > self.trade['sl']:
                        self.trade['sl'] = nsl
                        self.save_state() # تحديث الذاكرة المحلية بالـ SL الجديد
                        self.send(f"⬆️ *خنق ديناميكي لـ {s}:* SL الجديد {nsl:.4f}")
                    
                    # الخروج الذكي من السقف
                    if cp >= self.trade['bbh']: self.close("🎯 ضرب سقف البولينجر", pp, False); continue
                    
                    # خروج RSI القمة
                    if pp > 1.5:
                        rsi = ta.momentum.rsi(pd.DataFrame(bars, columns=['t','o','h','l','c','v'])['c'], 14).iloc[-1]
                        if rsi > 75 and bars[-1]['c'] < bars[-2]['c']: self.close("🧠 خروج ذكي (RSI)", pp, False); continue
            except Exception as e: 
                print(f"\n⚠️ خطأ: {e}\n")
                time.sleep(10)
            time.sleep(15)
            if (datetime.datetime.now() - self.rtime).total_seconds() >= 86400: self.trk.report(); self.rtime = datetime.datetime.now()

if __name__ == "__main__": KrakenBot().run()
