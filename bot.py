import time, pandas as pd, ta, requests, datetime, os, sys
import yfinance as yf
import warnings
from zoneinfo import ZoneInfo

# إخفاء تحذيرات yfinance المزعجة
warnings.filterwarnings("ignore")

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class QuotexSniperBot:
    """
    بوت القناص V12.0 (5-Min Triple Confirmation)
    =============================================
    - مصدر البيانات: Yahoo Finance (فوركس + كريبتو).
    - الاستراتيجية: EMA 200 + Bollinger Bands + Stochastic.
    - الفريم الزمني: 5 دقائق.
    - التوقيت: إفريقيا/طرابلس (ليبيا).
    """
    
    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')
        
        if not self.tg_token or not self.tg_chat:
            print("[FATAL ERROR] Missing TELEGRAM_TOKEN or CHAT_ID in environment variables!")
            return
        
        # التوقيت المحلي لليبيا
        self.TZ = ZoneInfo("Africa/Tripoli")
        
        # القاموس السحري: ربط رموز Yahoo Finance برموز منصة Quotex
        self.SYMBOLS_MAP = {
            # ======= الكريبتو =======
            'BTC-USD': 'BTCUSD(t)', 
            'ETH-USD': 'ETHUSD(t)', 
            'BNB-USD': 'BNBUSD(t)', 
            'SOL-USD': 'SOLUSD(t)',
            'XRP-USD': 'XRPUSD(t)', 
            'DOGE-USD': 'DOGEUSD(t)',
            'ADA-USD': 'ADAUSD(t)',
            # ======= الفوركس الحقيقي (يعمل من الإثنين للجمعة) =======
            'EURUSD=X': 'EUR/USD', 
            'GBPUSD=X': 'GBP/USD', 
            'USDJPY=X': 'USD/JPY', 
            'AUDUSD=X': 'AUD/USD', 
            'USDCAD=X': 'USD/CAD', 
            'EURGBP=X': 'EUR/GBP', 
            'NZDUSD=X': 'NZD/USD', 
            'EURJPY=X': 'EUR/JPY'
        }
        
        self.yf_tickers_list = list(self.SYMBOLS_MAP.keys())
        self.last_signal_time = {}
        self.stats = {'signals_sent': 0, 'scans': 0}
        self.report_time = time.time()
        
        # إعدادات الاستراتيجية
        self.TIMEFRAME = '5m'
        self.COOLDOWN_SEC = 300 # منع إرسال إشارة لنفس الزوج قبل مرور 5 دقائق
        
        msg  = "🎯 *بوت القناص (5 دقائق)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "🕐 التوقيت: ليبيا (GMT+2)\n"
        msg += f"📋 مراقبة {len(self.SYMBOLS_MAP)} زوج (فوركس + كريبتو)\n"
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
    #                            جلب البيانات
    # ================================================================
    
    def _fetch_all_data(self):
        """جلب بيانات جميع العملات دفعة واحدة لتجنب حظر الـ API"""
        try:
            # نجلب بيانات يومين بفريم 5 دقائق لكل الأزواج
            data = yf.download(
                tickers=self.yf_tickers_list, 
                period='2d', 
                interval=self.TIMEFRAME, 
                group_by='ticker',
                progress=False,
                threads=True
            )
            return data
        except Exception as e:
            self.log(f"Data Fetch Error: {e}")
            return None

    # ================================================================
    #                  🎯 استراتيجية القناص (Triple Confirmation)
    # ================================================================
    
    def _analyze_symbol(self, df):
        if df is None or len(df) < 200:
            return None, 0
            
        # تنظيف البيانات وتوحيد أسماء الأعمدة
        df = df.copy()
        df.dropna(inplace=True)
        
        # 1. حساب المتوسط المتحرك (EMA 200) لتحديد الاتجاه العام
        df['ema200'] = ta.trend.ema_indicator(df['Close'], window=200)
        
        # 2. حساب البولينجر باندز (Bollinger Bands 20, 2) لمعرفة مناطق الانعكاس
        bb = ta.volatility.BollingerBands(close=df['Close'], window=20, window_dev=2)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_lower'] = bb.bollinger_lband()
        
        # 3. حساب الستوكاستيك (Stochastic 14, 3, 3) كلحظة دخول
        stoch = ta.momentum.StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'], window=14, smooth_window=3)
        df['stoch_k'] = stoch.stoch()
        df['stoch_d'] = stoch.stoch_signal()
        
        cur = df.iloc[-1]
        prev = df.iloc[-2]
        price = cur['Close']
        
        if pd.isna(cur['ema200']) or pd.isna(cur['bb_upper']) or pd.isna(cur['stoch_k']):
            return None, price

        # ==========================================
        # 🟢 شرط الشراء (CALL)
        # ==========================================
        # 1. الترند صاعد (السعر فوق EMA 200)
        uptrend = price > cur['ema200']
        # 2. السعر ضرب الخط السفلي للبولينجر (تشبع بيعي قوي)
        bb_touch_lower = cur['Low'] <= cur['bb_lower'] or prev['Low'] <= prev['bb_lower']
        # 3. الستوكاستيك تحت 20 وحصل تقاطع للأعلى
        stoch_cross_up = (prev['stoch_k'] <= prev['stoch_d']) and (cur['stoch_k'] > cur['stoch_d']) and (cur['stoch_k'] < 20)
        
        if uptrend and bb_touch_lower and stoch_cross_up:
            return 'CALL', price
            
        # ==========================================
        # 🔴 شرط البيع (PUT)
        # ==========================================
        # 1. الترند هابط (السعر تحت EMA 200)
        downtrend = price < cur['ema200']
        # 2. السعر ضرب الخط العلوي للبولينجر (تشبع شرائي قوي)
        bb_touch_upper = cur['High'] >= cur['bb_upper'] or prev['High'] >= prev['bb_upper']
        # 3. الستوكاستيك فوق 80 وحصل تقاطع للأسفل
        stoch_cross_down = (prev['stoch_k'] >= prev['stoch_d']) and (cur['stoch_k'] < cur['stoch_d']) and (cur['stoch_k'] > 80)
        
        if downtrend and bb_touch_upper and stoch_cross_down:
            return 'PUT', price
            
        return None, price

    # ================================================================
    #                            إرسال الإشارة
    # ================================================================

    def _send_signal(self, yf_sym, qx_sym, direction, price):
        self.stats['signals_sent'] += 1
        self.last_signal_time[yf_sym] = time.time()
        
        icon = "🟢" if direction == 'CALL' else "🔴"
        now_libya = datetime.datetime.now(self.TZ)
        expiry_time = now_libya + datetime.timedelta(minutes=5)
        
        msg  = f"🎯 *إشارة قنص مؤكدة*\n"
        msg += f"━━━━━━━━━━━━━━━━\n"
        msg += f"🪙 الزوج: *{qx_sym}*\n"
        msg += f"📊 الاتجاه: *{direction}* {icon}\n"
        msg += f"⏱️ الانتهاء: *{expiry_time.strftime('%H:%M:%S')}* (5 دقائق)\n"
        msg += f"💵 السعر: `{price:.5f}`\n"
        msg += f"🧠 الاستراتيجية: `EMA200 + BB + Stoch`\n"
        msg += f"━━━━━━━━━━━━━━━━"
        
        self.tg(msg)
        self.log(f"SIGNAL FIRED: {qx_sym} {direction} @ {price:.5f}")

    # ================================================================
    #                            التشغيل الرئيسي
    # ================================================================
    
    def run(self):
        self.log("SNIPER STARTED - Fetching bulk data every 60 seconds...")
        
        while True:
            try:
                self.stats['scans'] += 1
                
                # جلب بيانات كل العملات في طلب واحد سريع
                all_data = self._fetch_all_data()
                
                if all_data is not None and not all_data.empty:
                    for yf_sym in self.yf_tickers_list:
                        
                        # استخراج بيانات الزوج المحدد من الجدول الضخم
                        if len(self.yf_tickers_list) > 1:
                            df_symbol = all_data[yf_sym]
                        else:
                            df_symbol = all_data
                            
                        qx_sym = self.SYMBOLS_MAP[yf_sym]
                        
                        # حماية الـ Cooldown (منع إرسال إشارة لنفس الزوج قبل 5 دقائق)
                        if yf_sym in self.last_signal_time:
                            if time.time() - self.last_signal_time[yf_sym] < self.COOLDOWN_SEC:
                                continue
                                
                        direction, price = self._analyze_symbol(df_symbol)
                        
                        if direction:
                            self._send_signal(yf_sym, qx_sym, direction, price)
                else:
                    self.log("No data received from Yahoo Finance. Retrying...")

                # تقرير صامت كل ساعة
                if time.time() - self.report_time >= 3600:
                    self.tg(f"📊 القناص يعمل | إشارات اليوم: {self.stats['signals_sent']}")
                    self.report_time = time.time()
                    
            except Exception as e: 
                self.log(f"MAIN LOOP ERR: {e}")
                time.sleep(10)
            
            # انتظار دقيقة كاملة قبل سحب شمعة جديدة (لأن الفريم 5 دقائق، لا داعي للضغط)
            self.log("Cycle complete. Waiting 60 seconds...")
            time.sleep(60) 

if __name__ == "__main__":
    bot = QuotexSniperBot()
    if bot.tg_token:
        bot.run()
