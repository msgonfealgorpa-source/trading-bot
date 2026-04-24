import time, pandas as pd, ta, requests, datetime, os, sys, numpy as np
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class QuotexProSignals:
    """
    بوت الإشارات السريع (Stochastic Edition)
    ==========================================
    - استراتيجية واحدة فقط: تقاطع الستوكاستك (Stochastic Cross).
    - هدف الإشارة: 1 دقيقة.
    - سرعة فحص عالية جداً لتوليد إشارات متكررة.
    """
    
    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')
        
        if not self.tg_token or not self.tg_chat:
            print("[FATAL ERROR] Missing TELEGRAM_TOKEN or CHAT_ID!")
            return
        
        self.TZ = ZoneInfo("Africa/Tripoli")
        
        # قائمة كوتكس الرسمية (كريبتو + OTC)
        self.QUOTEX_WHITELIST = {
            # ======= الكريبتو =======
            'BTC/USDT': 'BTCUSD(t)', 'ETH/USDT': 'ETHUSD(t)', 
            'BNB/USDT': 'BNBUSD(t)', 'SOL/USDT': 'SOLUSD(t)',
            'XRP/USDT': 'XRPUSD(t)', 'DOGE/USDT': 'DOGEUSD(t)',
            'LTC/USDT': 'LTCUSD(t)', 'ADA/USDT': 'ADAUSD(t)',
            'MATIC/USDT': 'MATICUSD(t)', 'AVAX/USDT': 'AVAXUSD(t)',
            'DOT/USDT': 'DOTUSD(t)', 'LINK/USDT': 'LINKUSD(t)',
            
            # ======= أزواج الـ OTC (تعمل في العطلات وتعطي حركة سريعة جداً) =======
            'EUR/USD': 'EUR/USD OTC', 'GBP/USD': 'GBP/USD OTC', 
            'USD/JPY': 'USD/JPY OTC', 'AUD/USD': 'AUD/USD OTC', 
            'USD/CAD': 'USD/CAD OTC', 'EUR/GBP': 'EUR/GBP OTC', 
            'NZD/USD': 'NZD/USD OTC', 'EUR/JPY': 'EUR/JPY OTC',
            'GBP/JPY': 'GBP/JPY OTC', 'AUD/CAD': 'AUD/CAD OTC'
        }
        
        # متغير لمنع إرسال إشارتين لنفس الزوج في نفس الدقيقة
        self.last_signal_time = {}
        self.stats = {'signals_sent': 0, 'scanned': 0}
        self.report_time = time.time()
        
        msg  = "⚡ *بوت الإشارات السريع*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"🕐 التوقيت: ليبيا (GMT+2)\n"
        msg += f"📋 مراقبة {len(self.QUOTEX_WHITELIST)} زوج (كريبتو + OTC)\n"
        msg += "🎯 الاستراتيجية: `Stochastic Cross (14,3,3)`\n"
        msg += "⏱️ المدة: `1 دقيقة` لجميع الإشارات\n"
        msg += "🚀 جاهز لاصطياد الإشارات..."
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

    def log(self, msg):
        ts = self._get_time()
        print(f"[{ts}] {msg}") 

    # ================================================================
    #                         جلب البيانات
    # ================================================================
    
    def _fetch_ohlcv(self, sym, limit=60):
        base, quote = sym.split('/')
        url = "https://min-api.cryptocompare.com/data/v2/histominute"
        params = {'fsym': base, 'tsym': quote, 'limit': limit}
        try:
            r = requests.get(url, params=params, timeout=5)
            d = r.json()
            if d.get('Response') == 'Success':
                raw = d.get('Data', {}).get('Data', [])
                formatted = [[c['time']*1000, c['open'], c['high'], c['low'], c['close'], c['volumeto']] for c in raw]
                df = pd.DataFrame(formatted, columns=['t','o','h','l','c','v'])
                if len(df) >= limit: return df
        except: pass
        return None

    # ================================================================
    #       🎯 الاستراتيجية: تقاطع الستوكاستك (Stochastic)
    # ================================================================
    
    def _check_stochastic(self, sym):
        df = self._fetch_ohlcv(sym, 60)
        if df is None: return None
        
        # حساب مؤشر الستوكاستك
        stoch = ta.momentum.StochasticOscillator(
            high=df['h'], low=df['l'], close=df['c'], 
            window=14, smooth_window=3
        )
        df['k'] = stoch.stoch()
        df['d'] = stoch.stoch_signal()
        
        cur_k = df['k'].iloc[-1]
        cur_d = df['d'].iloc[-1]
        prev_k = df['k'].iloc[-2]
        prev_d = df['d'].iloc[-2]
        
        if pd.isna(cur_k) or pd.isna(cur_d) or pd.isna(prev_k) or pd.isna(prev_d):
            return None
            
        # 🟢 إشارة شراء (CALL): تقاطع K للأعلى فوق D في منطقة التشبع البيعي (أقل من 30)
        if prev_k <= prev_d and cur_k > cur_d and cur_k < 30:
            return 'CALL'
            
        # 🔴 إشارة بيع (PUT): تقاطع K للأسفل تحت D في منطقة التشبع الشرائي (أعلى من 70)
        if prev_k >= prev_d and cur_k < cur_d and cur_k > 70:
            return 'PUT'
            
        return None

    # ================================================================
    #                      إرسال الإشارة
    # ================================================================

    def _send_signal(self, b_sym, q_sym, direction):
        # جلب السعر الحالي
        base, quote = b_sym.split('/')
        try:
            r = requests.get(f"https://min-api.cryptocompare.com/data/price?fsym={base}&tsyms={quote}", timeout=5)
            price = r.json().get(quote, 0)
        except: price = 0
        
        self.stats['signals_sent'] += 1
        self.last_signal_time[b_sym] = time.time()
        
        icon = "🟢" if direction == 'CALL' else "🔴"
        now_libya = datetime.datetime.now(self.TZ)
        expiry_time = now_libya + datetime.timedelta(minutes=1)
        
        msg  = f"🚀 *إشارة دقيقة*\n"
        msg += f"🪙 الزوج: *{q_sym}*\n"
        msg += f"📊 الاتجاه: *{direction}* {icon}\n"
        msg += f"⏱️ الانتهاء: *{expiry_time.strftime('%H:%M:%S')}* (1 دقيقة)\n"
        msg += f"💵 السعر: `{price}`\n"
        msg += f"🧠 الاستراتيجية: `Stochastic Cross`"
        
        self.tg(msg)
        self.log(f"SIGNAL: {q_sym} {direction} @ {price}")

    # ================================================================
    #                         التشغيل
    # ================================================================
    
    def run(self):
        self.log("HUNTER STARTED - Scanning fast...")
        
        while True:
            try:
                for b_sym, q_sym in self.QUOTEX_WHITELIST.items():
                    self.stats['scanned'] += 1
                    
                    # منع إرسال إشارتين لنفس الزوج في أقل من 120 ثانية (2 دقيقة)
                    if b_sym in self.last_signal_time:
                        if time.time() - self.last_signal_time[b_sym] < 120:
                            continue
                    
                    direction = self._check_stochastic(b_sym)
                    
                    if direction:
                        self._send_signal(b_sym, q_sym, direction)
                    
                    # سرعة فائقة للفحص (نصف ثانية بين كل زوج)
                    time.sleep(0.5) 
                
                # تقرير صامت كل نصف ساعة لمعرفة أن البوت يعمل
                if time.time() - self.report_time >= 1800:
                    self.tg(f"📊 البوت يعمل | إشارات اليوم: {self.stats['signals_sent']}")
                    self.report_time = time.time()
                    
            except Exception as e: 
                self.log(f"ERR: {e}")
                time.sleep(10)
            
            # إعادة تشغيل الدورة فوراً
            time.sleep(5) 

if __name__ == "__main__":
    bot = QuotexProSignals()
    if bot.tg_token:
        bot.run()
