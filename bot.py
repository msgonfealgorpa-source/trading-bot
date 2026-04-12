انظر هل تم

import ccxt, time, pandas as pd, ta, requests, datetime, os
from typing import Optional, Tuple, List

class Tracker:
def init(self, t, c, ex):
self.log, self.T, self.C, self.ex = [], t, c, ex
self.debug_enabled = True
self.no_signal_counter = 0
self.last_signal_time = time.time()

def send(self, m):  
    try:   
        requests.post(f"https://api.telegram.org/bot{self.T}/sendMessage",   
                     data={'chat_id': self.C, 'text': m, 'parse_mode': 'Markdown'})  
    except Exception as e:   
        print(f"TG Error: {e}")  

def debug(self, msg: str, send_to_tg: bool = False):  
    """طباعة رسائل Debug مفصلة"""  
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")  
    full_msg = f"[{timestamp}] {msg}"  
    print(full_msg)  
    if send_to_tg and self.debug_enabled:  
        # إرسال فقط الرسائل المهمة  
        if "❌" in msg or "✅" in msg or "🎯" in msg or "⚠️" in msg:  
            self.send(msg)  

def add(self, s, d, ep, xp, q, p, r):  
    self.log.append({'t': datetime.datetime.now(), 's': s, 'd': d, 'ep': ep, 'xp': xp,   
                    'q': float(self.ex.amount_to_precision(s, q)), 'p': p, 'r': r})  

def report(self):  
    if not self.log:   
        self.send("📊 لا توجد صفقات اليوم")  
        return  
    w = [t for t in self.log if t['p'] > 0]  
    total_profit = sum(t['p'] for t in self.log)  
    m = f"📊 *تقرير الوحش V7.0*\n"  
    m += f"📋 الصفقات: {len(self.log)}\n"  
    m += f"✅ الفوز: {(len(w)/len(self.log))*100:.1f}%\n"  
    m += f"💰 الربح الإجمالي: {total_profit:.2f}%\n"  
    m += f"💵 أفضل صفقة: {max(t['p'] for t in self.log):.2f}%\n"  
    m += f"📉 أسوأ صفقة: {min(t['p'] for t in self.log):.2f}%"  
    self.send(m)  
    self.log = [t for t in self.log if t['t'].date() == datetime.date.today()]  

def check_no_signal_alert(self):  
    """تنبيه عند عدم وجود فرص لفترة طويلة"""  
    if time.time() - self.last_signal_time > 7200:  # ساعتين  
        self.no_signal_counter += 1  
        if self.no_signal_counter >= 1:  
            self.send(f"⚠️ *تنبيه*\nلم يتم فتح صفقات منذ ساعتين\n🔍 قد تكون الشروط صارمة جداً")  
            self.no_signal_counter = 0

class FuturesBot:
def init(self):
self.K = os.environ.get('API_KEY')
self.S = os.environ.get('API_SECRET')
self.TT = os.environ.get('TELEGRAM_TOKEN')
self.CH = os.environ.get('CHAT_ID')

if not self.K or not self.S or not self.TT:     
        print("❌ خطأ: المفاتيح غير موجودة!")    
        return    

    self.ex = ccxt.bingx({  
        'apiKey': self.K, 'secret': self.S,   
        'enableRateLimit': True,   
        'options': {'defaultType': 'swap'},   
        'rateLimit': 1500  
    })    
    self.trk = Tracker(self.TT, self.CH, self.ex)    
    self.trade = None  
    self.losses = 0  
    self.dloss = 0.0  
    self.date = None  
    self.rtime = datetime.datetime.now()  
    self.scan_count = 0  
    self.rejected_stats = {  
        'no_trend': 0, 'rsi_fail': 0, 'volume_fail': 0,   
        'macd_fail': 0, 'bollinger_fail': 0, 'donchian_fail': 0,  
        'ny_fail': 0, 'qty_fail': 0, 'order_fail': 0  
    }  
      
    # ⚙️ إعدادات مرنة  
    self.LEVERAGE = 10     
      
    # فلاتر الاستراتيجيات - تخفيف الشروط  
    self.OLD_VOL_MULTIPLIER = 1.2      # كان 1.5  
    self.DONCHIAN_VOL_REQUIRED = False  # إزالة شرط الفوليوم  
    self.DONCHIAN_EMA_REQUIRED = False  # إزالة شرط EMA  
      
    # فلاتر نيويورك - أكثر مرونة  
    self.NY_EMA_FILTER = False         # تعطيل فلتر EMA  
    self.NY_RSI_FILTER = False         # تعطيل فلتر RSI  
    self.NY_VOL_FILTER = False         # تعطيل فلتر الفوليوم  
    self.NY_CANDLE_FILTER = False      # تعطيل فلتر الشمعة  
    self.NY_RISK_PCT = 5.0  
      
    # فلتر BTC RSI - جعله ثانوي فقط  
    self.BTC_RSI_FILTER_ENABLED = False  # تعطيل مؤقتاً  
    self.BTC_RSI_WARNING_ONLY = True     # تحذير فقط  
    self.BTC_RSI_RANGE = (20, 80)        # نطاق موسع  
      
    self.send("🔄 جاري التحقق من الصفقات المفتوحة...")    
    self.trade = self.load_state_from_exchange()    
        
    msg = "🗽 *بوت الوحش V7.0 (المنفذ الذكي)*\n"  
    msg += "━━━━━━━━━━━━━━━━\n"  
    msg += "⚙️ *التغييرات:*\n"  
    msg += "• فلتر BTC RSI: معطل\n"  
    msg += "• شروط مرنة أكثر\n"  
    msg += "• Debug كامل لكل عملية\n"  
    msg += "━━━━━━━━━━━━━━━━\n"  
    msg += "⚡ 1: بولينجر/ماكدي (8%)\n"  
    msg += "🚀 2: كسر دونشين (8%)\n"  
    msg += "🗽 3: نيويورك (5%)\n"  
    msg += "📋 الرافعة: 10X"  
    self.send(msg)    
      
    print("جاري تحميل أسواق العقود...")    
    self.ex.load_markets()  
    print("✅ تم التحميل!")  
      
    if self.trade:   
        self.send(f"🧠 *تم استئناف صفقة: {self.trade['d']} {self.trade['s']}*")  
        
    check_bal = self.bal()    
    self.trk.debug(f"💰 الرصيد المتاح: {check_bal} USDT", send_to_tg=True)  
    self.send(f"📊 *تشخيص الحساب*\n💰 الرصيد: {check_bal} USDT")  

def send(self, m):   
    self.trk.send(m)  

def retry(self, fn, *a, **k):    
    for i in range(5):    
        try:    
            r = getattr(self.ex, fn)(*a, **k)    
            return r if r is not None else None    
        except Exception as e:    
            self.trk.debug(f"🔄 محاولة {i+1} لـ {fn}: {e}")  
            time.sleep(3 * (i + 1))    
    return None    

def ohlcv(self, s, tf, l):   
    return self.retry('fetch_ohlcv', s, tf, limit=l)    

def tick(self, s):   
    return self.retry('fetch_ticker', s)    

def bal(self):     
    b = self.retry('fetch_balance', {'type': 'swap'})    
    return float(b.get('USDT', {}).get('free', 0)) if b else 0    

def ticks(self):   
    return self.retry('fetch_tickers')    
    
def setup_futures(self, s, d):    
    try:   
        self.ex.set_leverage(self.LEVERAGE, s, params={'marginMode': 'isolated'})  
        self.trk.debug(f"⚙️ تم ضبط الرافعة {self.LEVERAGE}X لـ {s}")  
    except Exception as e:  
        self.trk.debug(f"⚠️ فشل ضبط الرافعة: {e}")  
        pass    

def order(self, t, s, q):    
    o = self.retry(f'create_market_{t}_order', s, q)  
    if o and o.get('id'):  
        self.trk.debug(f"✅ تم تنفيذ الأمر | Order ID: {o['id']}", send_to_tg=True)  
        return o  
    else:  
        self.rejected_stats['order_fail'] += 1  
        self.trk.debug(f"❌ فشل تنفيذ الأمر على {s}")  
    return None    

def load_state_from_exchange(self):    
    try:    
        positions = self.retry('fetch_positions')    
        if positions:    
            for pos in positions:    
                qty = float(pos.get('position', pos.get('contracts', 0)))    
                if qty > 0:    
                    sym = pos['symbol']  
                    entry = float(pos['entryPrice'])    
                    side = pos.get('side', 'long').lower()    
                    d = 'short' if 'short' in side else 'long'    
                    self.trk.debug(f"🔄 استئناف صفقة: {d} {sym}", send_to_tg=True)  
                    return {  
                        's': sym, 'd': d, 'e': entry,   
                        'sl': entry*(0.97 if d=='long' else 1.03),   
                        'isl': entry*(0.97 if d=='long' else 1.03),   
                        'hp': entry, 'lp': entry, 'time': time.time(),   
                        'q': qty, 'pyramided': True, 'partial_closed': True,   
                        'strategy': "استئناف"  
                    }    
    except Exception as e:   
        self.trk.debug(f"❌ خطأ في تحميل الحالة: {e}")  
    return None    

def get_btc_rsi(self):    
    b = self.ohlcv('BTC/USDT:USDT', '15m', 15)    
    if not b: return 50    
    rsi = ta.momentum.rsi(pd.DataFrame(b, columns=['t','o','h','l','c','v'])['c'], window=14).iloc[-1]  
    return rsi  

def check_btc_rsi_filter(self) -> Tuple[bool, str]:  
    """فحص فلتر BTC RSI - الآن ثانوي فقط"""  
    btc_rsi = self.get_btc_rsi()  
    low, high = self.BTC_RSI_RANGE  
      
    if not self.BTC_RSI_FILTER_ENABLED:  
        self.trk.debug(f"📊 BTC RSI: {btc_rsi:.1f} (فلتر معطل)")  
        return True, ""  
      
    if btc_rsi < low or btc_rsi > high:  
        reason = f"BTC RSI {btc_rsi:.1f} خارج النطاق ({low}-{high})"  
        if self.BTC_RSI_WARNING_ONLY:  
            self.trk.debug(f"⚠️ {reason} - تحذير فقط، سيتم المتابعة")  
            return True, reason  
        else:  
            self.trk.debug(f"❌ {reason} - تم الرفض")  
            self.rejected_stats['rsi_fail'] += 1  
            return False, reason  
      
    self.trk.debug(f"📊 BTC RSI: {btc_rsi:.1f} ✓")  
    return True, ""  

def regime(self, s) -> str:  
    b = self.ohlcv(s, '1h', 100)    
    if not b: return "neutral"    
    df = pd.DataFrame(b, columns=['t','o','h','l','c','v'])    
    df['e1'] = ta.trend.ema_indicator(df['c'], 100)  
    df['e2'] = ta.trend.ema_indicator(df['c'], 200)    
    l = df.iloc[-1]  
    p = df.iloc[-2]  
      
    if l['c'] > l['e1'] and l['e1'] > l['e2'] and l['e1'] > p['e1']:  
        return "uptrend"    
    if l['c'] < l['e1'] and l['e1'] < l['e2'] and l['e1'] < p['e1']:  
        return "downtrend"    
    return "neutral"  

def analyze_old_strategy(self, s, tf, reg) -> Tuple[bool, float, float, float, float, str]:  
    """استراتيجية بولينجر/ماكدي مع debug كامل"""  
    b = self.ohlcv(s, tf, 200)    
    if not b:   
        return False, 0, 0, 0, 0, "لا توجد بيانات"  
      
    df = pd.DataFrame(b, columns=['t','o','h','l','c','v'])    
    df['e2'] = ta.trend.ema_indicator(df['c'], 200)  
    df['rsi'] = ta.momentum.rsi(df['c'], 14)    
    df['macd'] = ta.trend.macd_diff(df['c'])  
    df['vm'] = df['v'].rolling(20).mean()    
    df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()    
    bb = ta.volatility.BollingerBands(df['c'], 20, 2)    
    df['bbl'] = bb.bollinger_lband()  
    df['bbh'] = bb.bollinger_hband()    
      
    l = df.iloc[-1]  
    p = df.iloc[-2]  
      
    if tf == '15m':    
        if l['atr'] is None or pd.isna(l['atr']):  
            return False, 0, 0, 0, 0, "ATR غير متوفر"  
          
        vs = l['v'] > (l['vm'] * self.OLD_VOL_MULTIPLIER)  
        prev_body = abs(p['o'] - p['c'])  
          
        if reg == "uptrend":  
            # فحص كل شرط مع تحديد سبب الفشل  
            checks = []  
              
            if l['c'] <= l['e2']:  
                checks.append("السعر تحت EMA200")  
            if prev_body == 0 or (min(p['o'], p['c']) - p['l']) <= prev_body * 1.5:  
                checks.append("لا يوجد ظل سفلي قوي")  
            if p['l'] >= p['bbl']:  
                checks.append("الشمعة لم تلمس البولينجر السفلي")  
            if not (35 < l['rsi'] < 55):  
                checks.append(f"RSI={l['rsi']:.1f} خارج 35-55")  
            if l['macd'] <= p['macd']:  
                checks.append("MACD لا يرتفع")  
            if not vs:  
                checks.append(f"فوليوم ضعيف ({l['v']:.0f} < {l['vm']*self.OLD_VOL_MULTIPLIER:.0f})")  
            if l['c'] <= l['o']:  
                checks.append("شمعة هابطة")  
              
            if checks:  
                self.rejected_stats['bollinger_fail'] += 1  
                return False, 0, 0, 0, 0, f"Long: {', '.join(checks[:3])}"  
              
            return True, l['c'], l['rsi'], l['bbl'], l['bbh'], "OK"  
              
        elif reg == "downtrend":  
            checks = []  
              
            if l['c'] >= l['e2']:  
                checks.append("السعر فوق EMA200")  
            if prev_body == 0 or (p['h'] - max(p['o'], p['c'])) <= prev_body * 1.5:  
                checks.append("لا يوجد ظل علوي قوي")  
            if p['h'] <= p['bbh']:  
                checks.append("الشمعة لم تلمس البولينجر العلوي")  
            if not (45 < l['rsi'] < 65):  
                checks.append(f"RSI={l['rsi']:.1f} خارج 45-65")  
            if l['macd'] >= p['macd']:  
                checks.append("MACD لا ينخفض")  
            if not vs:  
                checks.append(f"فوليوم ضعيف ({l['v']:.0f} < {l['vm']*self.OLD_VOL_MULTIPLIER:.0f})")  
            if l['c'] >= p['o']:  
                checks.append("شمعة صاعدة")  
              
            if checks:  
                self.rejected_stats['bollinger_fail'] += 1  
                return False, 0, 0, 0, 0, f"Short: {', '.join(checks[:3])}"  
              
            return True, l['c'], l['rsi'], l['bbl'], l['bbh'], "OK"  
      
    return False, 0, 0, 0, 0, "الإطار الزمني غير 15m"  

def analyze_donchian_strategy(self, s, tf) -> Tuple[Optional[str], float, float, str]:  
    """استراتيجية دونشين مع debug كامل وشروط مرنة"""  
    b = self.ohlcv(s, tf, 50)    
    if not b or len(b) < 50:  
        return None, 0, 0, "بيانات غير كافية"  
      
    df = pd.DataFrame(b, columns=['t','o','h','l','c','v'])    
    df['e2'] = ta.trend.ema_indicator(df['c'], 200)    
    df['dc_upper'] = df['h'].rolling(20).max()    
    df['dc_lower'] = df['l'].rolling(20).min()    
    df['vm'] = df['v'].rolling(20).mean()    
    df['rsi'] = ta.momentum.rsi(df['c'], 14)    
    df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()    
      
    l = df.iloc[-1]  
    p = df.iloc[-2]  
      
    if pd.isna(l['atr']) or pd.isna(l['dc_upper']):  
        return None, 0, 0, "ATR أو DC غير متوفر"  
      
    vs = l['v'] > l['vm'] if not self.DONCHIAN_VOL_REQUIRED else True  
      
    # فحص Long  
    long_checks = []  
    if self.DONCHIAN_EMA_REQUIRED and l['c'] <= l['e2']:  
        long_checks.append("تحت EMA200")  
    if not (l['c'] > l['dc_upper']):  
        long_checks.append("لم يكسر العلوي")  
    if not (p['c'] <= p['dc_upper']):  
        long_checks.append("السابق كان فوق العلوي")  
    if self.DONCHIAN_VOL_REQUIRED and not vs:  
        long_checks.append("فوليوم ضعيف")  
    if l['rsi'] <= 50:  
        long_checks.append(f"RSI={l['rsi']:.1f} < 50")  
      
    if not long_checks:  
        return 'long', l['c'], l['atr'], "OK"  
      
    # فحص Short  
    short_checks = []  
    if self.DONCHIAN_EMA_REQUIRED and l['c'] >= l['e2']:  
        short_checks.append("فوق EMA200")  
    if not (l['c'] < l['dc_lower']):  
        short_checks.append("لم يكسر السفلي")  
    if not (p['c'] >= p['dc_lower']):  
        short_checks.append("السابق كان تحت السفلي")  
    if self.DONCHIAN_VOL_REQUIRED and not vs:  
        short_checks.append("فوليوم ضعيف")  
    if l['rsi'] >= 50:  
        short_checks.append(f"RSI={l['rsi']:.1f} > 50")  
      
    if not short_checks:  
        return 'short', l['c'], l['atr'], "OK"  
      
    self.rejected_stats['donchian_fail'] += 1  
    reason = f"L:{long_checks[0] if long_checks else '-'} | S:{short_checks[0] if short_checks else '-'}"  
    return None, 0, 0, reason  

def _get_ny_open_hour_utc(self):    
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)    
    year = now.year    
    dst_start = datetime.datetime(year, 3, 14)    
    dst_end = datetime.datetime(year, 11, 7)    
    return 13 if dst_start <= now <= dst_end else 14  

def analyze_ny_breakout(self, s) -> Tuple[Optional[str], float, float, str]:  
    """استراتيجية نيويورك مع شروط مرنة جداً وdebug"""  
    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)  
    ny_hour = self._get_ny_open_hour_utc()  
    ny_open_time = now_utc.replace(hour=ny_hour, minute=30, second=0, microsecond=0)  
      
    # فحص التوقيت  
    if now_utc < ny_open_time:  
        return None, 0, 0, "قبل موعد نيويورك"  
      
    # فحص مهلة الفرصة (4 ساعات بعد الافتتاح)  
    if (now_utc - ny_open_time).total_seconds() > 14400:  
        return None, 0, 0, "انتهت مهلة نيويورك (4س)"  
      
    bars = self.ohlcv(s, '15m', 40)  
    if not bars or len(bars) < 10:  
        return None, 0, 0, "بيانات غير كافية"  
      
    df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])  
    df['time'] = pd.to_datetime(df['t'], unit='ms')  
      
    # البحث عن شمعة الافتتاح  
    ref_mask = (df['time'].dt.hour == ny_hour) & (df['time'].dt.minute == 30) & (df['time'].dt.date == now_utc.date())  
    ref_candles = df[ref_mask]  
      
    if ref_candles.empty:  
        return None, 0, 0, "لم يتم العثور على شمعة الافتتاح"  
      
    ref_high = ref_candles.iloc[0]['h']  
    ref_low = ref_candles.iloc[0]['l']  
      
    future_bars = df[df['time'] > ref_candles.iloc[0]['time']]  
    recent_bars = future_bars.tail(5)  
      
    if len(recent_bars) < 2:  
        return None, 0, 0, "شموع قليلة بعد الافتتاح"  
      
    l = recent_bars.iloc[-1]  
    p = recent_bars.iloc[-2]  
      
    df['e2'] = ta.trend.ema_indicator(df['c'], window=200)  
    df['rsi'] = ta.momentum.rsi(df['c'], window=14)  
    df['vm'] = df['v'].rolling(20).mean()  
    df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], window=14).average_true_range()  
      
    if pd.isna(l['atr']) or l['atr'] <= 0:  
        return None, 0, 0, "ATR غير متوفر"  
      
    # فحص الكسر - الشروط مخففة  
    long_break = l['c'] > ref_high  # فقط آخر شمعة  
    short_break = l['c'] < ref_low  
      
    ny_checks = []  
      
    if long_break:  
        # فحصات Long - معظمها معطل  
        if self.NY_EMA_FILTER and l['c'] <= l['e2']:  
            ny_checks.append("تحت EMA200")  
        if self.NY_RSI_FILTER and l['rsi'] <= 50:  
            ny_checks.append(f"RSI={l['rsi']:.1f}")  
          
        if not ny_checks:  
            self.trk.debug(f"🗽 NY Long مؤكد: {s} عند {l['c']:.4f}")  
            return 'long', l['c'], l['atr'] * 1.5, "OK"  
      
    ny_checks = []  
      
    if short_break:  
        if self.NY_EMA_FILTER and l['c'] >= l['e2']:  
            ny_checks.append("فوق EMA200")  
        if self.NY_RSI_FILTER and l['rsi'] >= 50:  
            ny_checks.append(f"RSI={l['rsi']:.1f}")  
          
        if not ny_checks:  
            self.trk.debug(f"🗽 NY Short مؤكد: {s} عند {l['c']:.4f}")  
            return 'short', l['c'], l['atr'] * 1.5, "OK"  
      
    self.rejected_stats['ny_fail'] += 1  
    reason = "لم يحدث كسر" if not (long_break or short_break) else f"فلاتر: {ny_checks[0] if ny_checks else '?'}"  
    return None, 0, 0, reason  

def calc_qty(self, s, p, risk_override=None) -> float:    
    b = self.bal()    
    if b == 0:   
        self.trk.debug("❌ الرصيد صفر!")  
        return 0  
      
    bars = self.ohlcv(s, '15m', 19)  
    if not bars:  
        return 0  
      
    df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])  
    atr = ta.volatility.AverageTrueRange(high=df['h'], low=df['l'], close=df['c'], window=14).average_true_range().iloc[-1]  
      
    if pd.isna(atr) or atr <= 0:  
        return 0  
      
    risk_pct = risk_override if risk_override is not None else (0.75 if self.losses >= 3 else 8.0)  
    risk = b * (risk_pct / 100)  
    sl_dist = 2.5 * atr  
      
    if sl_dist <= 0:  
        return 0  
      
    qty = risk / sl_dist  
      
    try:  
        m = self.ex.market(s)  
        fq = self.ex.amount_to_precision(s, qty)  
        mn = m.get('limits', {}).get('amount', {}).get('min')  
        if mn and float(fq) < mn:  
            fq = self.ex.amount_to_precision(s, mn)  
    except:  
        fq = self.ex.amount_to_precision(s, qty)  
      
    return float(fq) if float(fq) > 0 else 0  

def close(self, reason: str, pct: float, loss: bool = False, partial: bool = False):  
    """إغلاق الصفقة مع إشعار مفصل"""  
    if not self.trade:  
        return  
      
    s = self.trade['s']  
    d = self.trade['d']  
    q = float(self.trade['q'])  
      
    if partial:  
        q = q / 2.0  
      
    close_type = 'sell' if d == 'long' else 'buy'  
    fq = float(self.ex.amount_to_precision(s, q))  
      
    if fq <= 0:  
        self.trk.debug("❌ الكمية صفر للإغلاق")  
        return  
      
    t = self.tick(s)  
    xp = self.trade['e'] if not t else t['last']  
      
    o = self.order(close_type, s, fq)  
    if not o:  
        self.send(f"🚨 *فشل إغلاق*\n{d} {s}\n🛑 {reason}")  
        return  
      
    order_id = o.get('id', 'N/A')  
    strat = self.trade.get('strategy', '')  
      
    if partial:  
        self.trade['q'] = str(float(self.trade['q']) - fq)  
        self.trade['partial_closed'] = True  
        self.trade['sl'] = self.trade['e']  
          
        msg = f"⚡ *إغلاق جزئي 50%*\n"  
        msg += f"🪙 {s} ({d})\n"  
        msg += f"📊 الاستراتيجية: {strat}\n"  
        msg += f"💰 الربح المؤمن: {pct:.2f}%\n"  
        msg += f"🛑 SL نقل للدخول\n"  
        msg += f"🆔 Order: {order_id}"  
        self.send(msg)  
        return  
      
    self.trk.add(s, d, self.trade['e'], xp, q, pct, reason)  
      
    if loss:  
        self.losses += 1  
        tb = self.bal()  
        self.dloss += (abs(pct)/100)*tb if tb > 0 else abs(pct)  
          
        msg = f"📉 *خسارة*\n"  
        msg += f"🪙 {s} ({d})\n"  
        msg += f"📊 الاستراتيجية: {strat}\n"  
        msg += f"💔 الخسارة: {pct:.2f}%\n"  
        msg += f"❌ السبب: {reason}\n"  
        msg += f"🆔 Order: {order_id}"  
        self.send(msg)  
    else:  
        self.losses = 0  
          
        msg = f"🏆 *ربح*\n"  
        msg += f"🪙 {s} ({d})\n"  
        msg += f"📊 الاستراتيجية: {strat}\n"  
        msg += f"💰 الربح: {pct:.2f}%\n"  
        msg += f"✅ السبب: {reason}\n"  
        msg += f"🆔 Order: {order_id}"  
        self.send(msg)  
      
    self.trade = None  

def get_rejection_summary(self) -> str:  
    """ملخص أسباب الرفض"""  
    total = sum(self.rejected_stats.values())  
    if total == 0:  
        return "لا توجد رفضات بعد"  
      
    summary = "📊 *ملخص الرفضات:*\n"  
    summary += f"├ لا اتجاه واضح: {self.rejected_stats['no_trend']}\n"  
    summary += f"├ RSI فشل: {self.rejected_stats['rsi_fail']}\n"  
    summary += f"├ فوليوم ضعيف: {self.rejected_stats['volume_fail']}\n"  
    summary += f"├ بولينجر: {self.rejected_stats['bollinger_fail']}\n"  
    summary += f"├ دونشين: {self.rejected_stats['donchian_fail']}\n"  
    summary += f"├ نيويورك: {self.rejected_stats['ny_fail']}\n"  
    summary += f"├ كمية صفر: {self.rejected_stats['qty_fail']}\n"  
    summary += f"└ فشل الأمر: {self.rejected_stats['order_fail']}"  
    return summary  

def run(self):  
    """المحرك الرئيسي مع debug كامل"""  
    self.send("🚀 *الوحش V7.0 جاهز!*")  
    self.send("📋 *الوضع: منفذ ذكي*\n⚙️ فلاتر مرنة | Debug مفعل")  
    print("\n🚀 بدء المحرك الثلاثي V7.0...")  
      
    while True:  
        if self.date != datetime.date.today():  
            self.dloss = 0.0  
            self.date = datetime.date.today()  
            self.rejected_stats = {k: 0 for k in self.rejected_stats}  
          
        try:  
            # فحص حد الخسارة اليومي  
            if self.dloss >= 20.0:  
                self.send("🛑 *حد خسارة يومي 20%*")  
                self.trk.debug("⏸️ إيقاف بسبب حد الخسارة")  
                time.sleep(3600)  
                continue  
              
            if not self.trade:  
                self.scan_count += 1  
                self.trk.debug(f"🔍 فحص #{self.scan_count} - جاري البحث عن فرص...")  
                  
                # فحص BTC RSI - الآن ثانوي  
                btc_ok, btc_reason = self.check_btc_rsi_filter()  
                  
                tk = self.ticks()  
                if not tk:  
                    self.trk.debug("⚠️ فشل جلب البيانات")  
                    time.sleep(30)  
                    continue  
                  
                # فلتر السيولة المخفف  
                syms = [  
                    s for s, i in tk.items()   
                    if s.endswith('/USDT:USDT')   
                    and i.get('quoteVolume')   
                    and i.get('last')   
                    and (i['quoteVolume'] * i['last'] > 500000)  # خفض من مليون  
                ][:150]  # زيادة عدد العملات  
                  
                if not syms:  
                    self.trk.debug("⚠️ لا توجد عملات مؤهلة")  
                    time.sleep(60)  
                    continue  
                  
                self.trk.debug(f"📊 فحص {len(syms)} عملة...")  
                  
                found_signal = False  
                  
                for idx, s in enumerate(syms[:50]):  # فحص 50 عملة لكل دورة  
                    rg = self.regime(s)  
                      
                    # Debug للاتجاه  
                    if idx < 5:  # طباعة أول 5 فقط  
                        self.trk.debug(f"  {s}: اتجاه={rg}")  
                      
                    if rg == "neutral":  
                        self.rejected_stats['no_trend'] += 1  
                        continue  
                      
                    entered = False  
                    strategy_used = ""  
                    direction = None  
                    price = 0  
                    sl_dist = 0  
                    reject_reason = ""  
                      
                    # 1️⃣ استراتيجية بولينجر/ماكدي  
                    ok, p, rsi, bbl, bbh, status = self.analyze_old_strategy(s, '15m', rg)  
                    if ok:  
                        direction = 'long' if rg == "uptrend" else 'short'  
                        price = p  
                        bars = self.ohlcv(s, '15m', 19)  
                        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])  
                        atr = ta.volatility.AverageTrueRange(high=df['h'], low=df['l'], close=df['c'], window=14).average_true_range().iloc[-1]  
                        sl_dist = 2.5 * atr if not pd.isna(atr) else p * 0.025  
                        strategy_used = "[1] بولينجر/ماكدي"  
                        entered = True  
                        self.trk.debug(f"✅ فرصة بولينجر: {s} {direction}", send_to_tg=True)  
                    else:  
                        reject_reason = f"بولينجر: {status}"  
                      
                    # 2️⃣ استراتيجية دونشين  
                    if not entered:  
                        donch_dir, donch_p, donch_atr, donch_status = self.analyze_donchian_strategy(s, '15m')  
                        if donch_dir:  
                            direction = donch_dir  
                            price = donch_p  
                            sl_dist = 1.5 * donch_atr  
                            strategy_used = "[2] كسر دونشين"  
                            entered = True  
                            self.trk.debug(f"✅ فرصة دونشين: {s} {direction}", send_to_tg=True)  
                        else:  
                            reject_reason = f"دونشين: {donch_status}"  
                      
                    # 3️⃣ استراتيجية نيويورك  
                    if not entered:  
                        ny_dir, ny_p, ny_sl, ny_status = self.analyze_ny_breakout(s)  
                        if ny_dir:  
                            direction = ny_dir  
                            price = ny_p  
                            sl_dist = ny_sl  
                            strategy_used = "🗽 [3] نيويورك"  
                            entered = True  
                            self.trk.debug(f"✅ فرصة نيويورك: {s} {direction}", send_to_tg=True)  
                        else:  
                            reject_reason = f"نيويورك: {ny_status}"  
                      
                    # محاولة الدخول  
                    if entered and direction and price > 0 and sl_dist > 0:  
                        risk_val = self.NY_RISK_PCT if "نيويورك" in strategy_used or "NY" in strategy_used else None  
                        q = self.calc_qty(s, price, risk_override=risk_val)  
                          
                        if q <= 0:  
                            self.rejected_stats['qty_fail'] += 1  
                            self.trk.debug(f"❌ {s}: كمية صفر")  
                            continue  
                          
                        self.setup_futures(s, direction)  
                          
                        if self.order('buy' if direction == 'long' else 'sell', s, q):  
                            if direction == 'long':  
                                sl = price - sl_dist  
                            else:  
                                sl = price + sl_dist  
                              
                            self.trade = {  
                                's': s, 'd': direction, 'e': price, 'sl': sl, 'isl': sl,  
                                'hp': price, 'lp': price, 'time': time.time(), 'q': q,  
                                'pyramided': False, 'partial_closed': False,  
                                'strategy': strategy_used  
                            }  
                              
                            emoji = "🟢LONG" if direction == 'long' else "🔴SHORT"  
                            msg = f"{emoji} *عقد جديد*\n"  
                            msg += f"━━━━━━━━━━━━━━━━\n"  
                            msg += f"📊 الاستراتيجية: {strategy_used}\n"  
                            msg += f"🪙 العملة: {s}\n"  
                            msg += f"💵 الدخول: {price:.4f}\n"  
                            msg += f"⚖️ الكمية: {q:.4f}\n"  
                            msg += f"🛑 SL: {sl:.4f}\n"  
                            msg += f"━━━━━━━━━━━━━━━━\n"  
                            if btc_reason:  
                                msg += f"⚠️ ملاحظة: {btc_reason}\n"  
                            msg += f"📊 الاتجاه: {rg}"  
                            self.send(msg)  
                              
                            print(f"\n🎯 تم فتح {emoji} ({strategy_used}) على {s}!\n")  
                            self.losses = 0  
                            self.trk.last_signal_time = time.time()  
                            self.trk.no_signal_counter = 0  
                            found_signal = True  
                            break  
                    else:  
                        # طباعة سبب الرفض للعملات المهمة فقط  
                        if "BTC" in s or "ETH" in s or "SOL" in s or "BNB" in s:  
                            self.trk.debug(f"❌ {s}: {reject_reason}")  
                  
                # تنبيه عند عدم وجود فرص  
                if not found_signal:  
                    self.trk.check_no_signal_alert()  
                  
                # إرسال ملخص الرفضات كل 10 فحوصات  
                if self.scan_count % 10 == 0:  
                    self.send(self.get_rejection_summary())  
              
            else:  
                # إدارة الصفقة المفتوحة  
                s = self.trade['s']  
                d = self.trade['d']  
                t = self.tick(s)  
                  
                if not t:  
                    time.sleep(15)  
                    continue  
                  
                cp = t['last']  
                ep = self.trade['e']  
                pp = ((cp - ep) / ep * 100) if d == 'long' else ((ep - cp) / ep * 100)  
                  
                if d == 'long' and cp > self.trade['hp']:  
                    self.trade['hp'] = cp  
                if d == 'short' and cp < self.trade['lp']:  
                    self.trade['lp'] = cp  
                  
                hpp = ((self.trade['hp'] - ep) / ep * 100) if d == 'long' else ((ep - self.trade['lp']) / ep * 100)  
                  
                strat_name = self.trade.get('strategy', "")  
                self.trk.debug(f"⏱️ {d} {s} | {strat_name} | ربح: {pp:.2f}% | أعلى: {hpp:.2f}%")  
                  
                # فحص SL  
                ssl = self.trade['sl']  
                if d == 'long' and cp <= ssl:  
                    self.close("🛑 SL Long", pp, True)  
                    continue  
                if d == 'short' and cp >= ssl:  
                    self.close("🛑 SL Short", pp, True)  
                    continue  
                  
                # فحص انفجار الفوليوم  
                bars = self.ohlcv(s, '15m', 20)  
                if bars:  
                    df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])  
                    vol_ma = df['v'].rolling(20).mean().iloc[-1]  
                    if df.iloc[-1]['v'] > (vol_ma * 4):  
                        self.close("🔥 انفجار فوليوم عكسي", pp, False)  
                        continue  
                  
                # انتهاء الوقت  
                if time.time() - self.trade['time'] > 3600 and abs(pp) < 1.0:  
                    self.close("⏳ انتهاء الوقت (ساعة)", pp, pp < 0)  
                    continue  
                  
                # إغلاق جزئي  
                if pp >= 3.0 and not self.trade.get('partial_closed'):  
                    self.close("⚡ جزئي 50% عند 3%", pp, partial=True)  
                    continue  
                  
                # تعزيز المركز  
                if pp >= 2.0 and not self.trade.get('pyramided'):  
                    add_q = self.calc_qty(s, cp)  
                    if add_q > 0:  
                        o_type = 'buy' if d == 'long' else 'sell'  
                        o = self.order(o_type, s, add_q)  
                        if o:  
                            self.trade['pyramided'] = True  
                            self.trade['q'] = str(float(self.trade['q']) + add_q)  
                            self.send(f"🚀 *تعزيز!* {s}\nمضاعفة العقد: {self.trade['q']}\n🆔 Order: {o.get('id')}")  
                            time.sleep(2)  
                            continue  
                  
                # الهدف  
                if pp >= 10.0:  
                    self.close("🎯 الهدف 10%", pp, False)  
                    continue  
                  
                # Trailing Stop  
                if hpp >= 2.5:  
                    if d == 'long':  
                        nsl = self.trade['hp'] * (1 - 0.5 / 100)  
                        if nsl > self.trade['sl']:  
                            self.trade['sl'] = nsl  
                            self.trk.debug(f"📈 SL متحرك: {nsl:.4f}")  
                    elif d == 'short':  
                        nsl = self.trade['lp'] * (1 + 0.5 / 100)  
                        if nsl < self.trade['sl']:  
                            self.trade['sl'] = nsl  
                            self.trk.debug(f"📉 SL متحرك: {nsl:.4f}")  
              
        except Exception as e:  
            self.trk.debug(f"⚠️ خطأ عام: {e}")  
            time.sleep(15)  
          
        time.sleep(15)  
          
        # تقرير يومي  
        if (datetime.datetime.now() - self.rtime).total_seconds() >= 86400:  
            self.trk.report()  
            self.send(self.get_rejection_summary())  
            self.rtime = datetime.datetime.now()

if name == "main":
bot = FuturesBot()
if bot.K:  # التأكد من وجود المفاتيح
bot.run()
