import time, pandas as pd, ta, requests, datetime, os, sys, numpy as np
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class QuotexSniperBot:
    """
    بوت القناص V12.0 (5-Min Triple Confirmation)
    =============================================
    - مصدر البيانات: CryptoCompare (مستقر، لا يسبب Crash).
    - الاستراتيجية: EMA 200 + Bollinger Bands + Stochastic.
    - الفريم الزمني: 5 دقائق (مصنوع بدقة باستخدام Pandas).
    - التوقيت: إفريقيا/طرابلس (ليبيا).
    """
    
    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')
        
        if not self.tg_token or not self.tg_chat:
            print("[FATAL ERROR] Missing TELEGRAM_TOKEN or CHAT_ID!")
            return
        
        self.TZ = ZoneInfo("Africa/Tripoli")
        
        # قاموس الرموز (متوافق مع CryptoCompare)
        self.SYMBOLS_MAP = {
            # ======= الكريبتو =======
            'BTC/USDT': 'BTCUSD(t)', 
            'ETH/USDT': 'ETHUSD(t)', 
            'BNB/USDT': 'BNBUSD(t)', 
            'SOL/USDT': 'SOLUSD(t)',
            'XRP/USDT': 'XRPUSD(t)', 
            'DOGE/USDT': 'DOGEUSD(t)',
            'ADA/USDT': 'ADAUSD(t)',
            # ======= أزواج الفوركس / OTC =======
            'EUR/USD': 'EUR/USD OTC', 
            'GBP/USD': 'GBP/USD OTC', 
            'USD/JPY': 'USD/JPY OTC', 
            'AUD/USD': 'AUD/USD OTC', 
            'USD/CAD': 'USD/CAD OTC', 
            'EUR/GBP': 'EUR/GBP OTC', 
            'NZD/USD': 'NZD/USD OTC', 
            'EUR/JPY': 'EUR/JPY OTC'
        }
        
        self.last_signal_time = {}
        self.stats = {'signals_sent': 0, 'scans': 0}
        self.report_time = time.time()
        self.COOLDOWN_SEC = 300 # 5 دقائق مهلة بين الإشارات لنفس الزوج
        
        msg  = "🎯 *بوت القناص (5 دقائق)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "🕐 التوقيت: ليبيا (GMT+2)\n"
        msg += f"📋 مراقبة {len(self.SYMBOLS_MAP)} زوج\n"
        msg += "🧠 الاستراتيجية 3 أبعاد:\n"
        msg += "1️⃣ `EMA 200` (للترند)\n"
        msg += "2️⃣ `Bollinger Bands` (للتشبع)\n"
        msg += "3️⃣ `Stochastic` (للزناد)\n"
        msg += "🚀 جاهز للعمل باحترافية..."
        self.tg(msg)

    def _get_time(self):
        return datetime.datetime.now(self.TZ).strftime("%H:%M:%S")

    def tg(self, msg):
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'},
                timeout=5
            )
        except Exception as e:
            print(f"[{self._get_time()}] TG Error: {e}")

    def log(self, msg):
        ts = self._get_time()
        print(f"[{ts}] {msg}") 

    # ================================================================
    #                   جلب البيانات وتصنيع الفريم 5 دقائق
    # ================================================================
    
    def _get_5m_data(self, sym):
        """يجلب بيانات الدقيقة ويحولها لفريم 5 دقائق بدون أي ضغط على الذاكرة"""
        base, quote = sym.split('/')
        url = "https://min-api.cryptocompare.com/data/v2/histominute"
        # نجلب 1500 شمعة دقيقة (حوالي يوم ونصف) لنضمن تكوين 200 شمعة 5 دقائق
        params = {'fsym': base, 'tsym': quote, 'limit': 1500}
        
        try:
            r = requests.get(url, params=params, timeout=10)
            d = r.json()
            if d.get('Response') == 'Success':
                raw = d.get('Data', {}).get('Data', [])
                if not raw: return None
                
                df = pd.DataFrame(raw, columns=['time', 'open', 'high', 'low', 'close', 'volumeto'])
                df['time'] = pd.to_datetime(df['time'], unit='ms')
                
                # تحويل البيانات الخام إلى شموع 5 دقائق حقيقية
                df_5m = df.set_index('time').resample('5min').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volumeto': 'sum'
                }).dropna().reset_index()
                
                # نأخذ آخر 210 شمعة لحساب EMA 200 بدقة
                return df_5m.tail(210)
        except Exception as e:
            self.log(f"Data Err {sym}: {str(e)[:30]}")
        return None

    # ================================================================
    #         🎯 استراتيجية القناص (Triple Confirmation)
    # ================================================================
    
    def _analyze_symbol(self, df_5m):
        if df_5m is None or len(df_5m) < 200:
            return None, 0
            
        try:
            # توحيد أسماء الأعمدة لتتناسب مع مكتبة ta
            df = df_5m.rename(columns={
                'open': 'Open', 'high': 'High', 
                'low': 'Low', 'close': 'Close'
            }).copy()
            
            # 1. حساب EMA 200
            df['ema200'] = ta.trend.ema_indicator(df['Close'], window=200)
            
            # 2. حساب Bollinger Bands (20, 2)
            bb = ta.volatility.BollingerBands(close=df['Close'], window=20, window_dev=2)
            df['bb_upper'] = bb.bollinger_hband()
            df['bb_lower'] = bb.bollinger_lband()
            
            # 3. حساب Stochastic (14, 3, 3)
            stoch = ta.momentum.StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'], window=14, smooth_window=3)
            df['stoch_k'] = stoch.stoch()
            df['stoch_d'] = stoch.stoch_signal()
            
            cur = df.iloc[-1]
            prev = df.iloc[-2]
            price = cur['Close']
            
            # التحقق من عدم وجود قيم فارغة (NaN) في الشمعة الحالية
            if pd.isna(cur['ema200']) or pd.isna(cur['bb_upper']) or pd.isna(cur['stoch_k']):
                return None, price

            # ==========================================
            # 🟢 شرط الشراء (CALL)
            # ==========================================
            uptrend = price > cur['ema200']
            bb_touch_lower = cur['Low'] <= cur['bb_lower'] or prev['Low'] <= prev['bb_lower']
            stoch_cross_up = (prev['stoch_k'] <= prev['stoch_d']) and (cur['stoch_k'] > cur['stoch_d']) and (cur['stoch_k'] < 20)
            
            if uptrend and bb_touch_lower and stoch_cross_up:
                return 'CALL', price
                
            # ==========================================
            # 🔴 شرط البيع (PUT)
            # ==========================================
            downtrend = price < cur['ema200']
            bb_touch_upper = cur['High'] >= cur['bb_upper'] or prev['High'] >= prev['bb_upper']
            stoch_cross_down = (prev['stoch_k'] >= prev['stoch_d']) and (cur['stoch_k'] < cur['stoch_d']) and (cur['stoch_k'] > 80)
            
            if downtrend and bb_touch_upper and stoch_cross_down:
                return 'PUT', price
                
        except Exception as e:
            return None, 0
            
        return None, 0

    # ================================================================
    #                            إرسال الإشارة
    # ================================================================

    def _send_signal(self, api_sym, qx_sym, direction, price):
        self.stats['signals_sent'] += 1
        self.last_signal_time[api_sym] = time.time()
        
        icon = "🟢" if direction == 'CALL' else "🔴"
        now_libya = datetime.datetime.now(self.TZ)
        expiry_time = now_libya + datetime.timedelta(minutes=5)
        
        # تحديد عدد الخانات العشرية حسب نوع الزوج
        decimals = 5 if 'USD' in api_sym and 'USDT' not in api_sym else 2
        
        msg  = f"🎯 *إشارة قنص مؤكدة*\n"
        msg += f"━━━━━━━━━━━━━━━━\n"
        msg += f"🪙 الزوج: *{qx_sym}*\n"
        msg += f"📊 الاتجاه: *{direction}* {icon}\n"
        msg += f"⏱️ الانتهاء: *{expiry_time.strftime('%H:%M:%S')}* (5 دقائق)\n"
        msg += f"💵 السعر: `{price:.{decimals}f}`\n"
        msg += f"🧠 الاستراتيجية: `EMA200 + BB + Stoch`\n"
        msg += f"━━━━━━━━━━━━━━━━"
        
        self.tg(msg)
        self.log(f"SIGNAL FIRED: {qx_sym} {direction} @ {price:.{decimals}f}")

    # ================================================================
    #                            التشغيل الرئيسي
    # ================================================================
    
    def run(self):
        self.log("SNIPER STARTED - Analyzing 5m charts...")
        
        while True:
            try:
                self.stats['scans'] += 1
                
                # فحص الأزواج واحداً تلو الآخر (هذا يمنع الكرش تماماً)
                for api_sym, qx_sym in self.SYMBOLS_MAP.items():
                    
                    # حماية الـ Cooldown 
                    if api_sym in self.last_signal_time:
                        if time.time() - self.last_signal_time[api_sym] < self.COOLDOWN_SEC:
                            continue
                    
                    # 1. جلب البيانات وتصنيع الفريم
                    df_5m = self._get_5m_data(api_sym)
                    
                    # 2. تحليل الاستراتيجية
                    direction, price = self._analyze_symbol(df_5m)
                    
                    # 3. إطلاق الإشارة
                    if direction and price > 0:
                        self._send_signal(api_sym, qx_sym, direction, price)
                    
                    # مهلة ثانية واحدة فقط بين كل زوج لتجنب الضغط على الإنترنت
                    time.sleep(1)

                # تقرير صامت كل ساعة
                if time.time() - self.report_time >= 3600:
                    self.tg(f"📊 القناص يعمل | إشارات اليوم: {self.stats['signals_sent']}")
                    self.report_time = time.time()
                    
            except Exception as e: 
                self.log(f"MAIN LOOP ERR: {e}")
                time.sleep(10)
            
            # انتظار دقيقة كاملة (لأن الفريم 5 دقائق، لا حاجة للفحص أسرع من ذلك)
            self.log("Cycle complete. Waiting 60 seconds...")
            time.sleep(60) 

if __name__ == "__main__":
    bot = QuotexSniperBot()
    if bot.tg_token:
        bot.run()
