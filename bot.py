import time, pandas as pd, ta, requests, datetime, os, sys
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class QuotexSniperBot:
    """
    بوت القناص V18.0 (الرادار الذكي - Smart Radar)
    ==================================================
    - يسحب البيانات بناءً على "نشاط السوق" وليس الوقت.
    - الأزواج النشطة: فحص كل 45 ثانية.
    - الأزواج الهادئة: تجاهل تام لمدة 10 دقائق.
    - يضمن عدم تفويت الفرص داخل الجلسات الطويلة بدون استنزاف الـ API.
    """

    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')
        self.twelve_api_key = os.environ.get('TWELVE_DATA_API_KEY')

        if not self.tg_token or not self.tg_chat:
            print("[FATAL ERROR] Missing TELEGRAM_TOKEN or CHAT_ID!"); return
        if not self.twelve_api_key:
            print("[FATAL ERROR] Missing TWELVE_DATA_API_KEY!"); return

        self.TZ = ZoneInfo("Africa/Tripoli")
        self.SYMBOLS_MAP = {
            'EUR/USD': 'EUR/USD', 'GBP/JPY': 'GBP/JPY', 'USD/CAD': 'USD/CAD',
            'EUR/GBP': 'EUR/GBP', 'USD/CHF': 'USD/CHF', 'AUD/USD': 'AUD/USD', 'GBP/USD': 'GBP/USD'
        }
        self.pair_list = list(self.SYMBOLS_MAP.keys())

        # الجلسات الصباحية (08:00 - 11:00) والمسائية (17:00 - 20:00) بتوقيت ليبيا
        self.morning_session = (480, 660)  # 8*60 إلى 11*60
        self.evening_session = (1020, 1200) # 17*60 إلى 20*60

        self.daily_signal_count = 0
        self.current_day = datetime.datetime.now(self.TZ).day

        # === نظام حماية وتوزيع الـ API ===
        self.daily_api_calls = 0
        self.MAX_DAILY_API_CALLS = 750
        self.limit_notified = False

        # === ذاكرة الاستراتيجية ===
        self.stage_memory = {}
        self.stage_time = {}
        self.last_signal_time = {}
        self.COOLDOWN_SEC = 180 # 3 دقائق冷却 بين الإشارات لنفس الزوج

        # === نظام الرادار الذكي (القلب الجديد للبوت) ===
        self.pair_status = {sym: {'next_check': 0, 'is_hot': False} for sym in self.pair_list}
        self.HOT_SCAN_INTERVAL = 45   # فحص الزوج النشط كل 45 ثانية
        self.COLD_SCAN_INTERVAL = 600 # تجاهل الزوج الهادئ لمدة 10 دقائق
        self.VOLATILITY_THRESHOLD = 0.0004 # حد النشاط (4 نقاط تقريباً)

        if self._test_connection():
            self.log("Connected Successfully - Smart Radar V18.0 Active")
            msg  = "🧠 *بوت القناص V18.0 (الرادار الذكي)*\n"
            msg += "━━━━━━━━━━━━━━━━\n"
            msg += "⚡ الاستراتيجية: استوكاستيك + EMA 10/20\n"
            msg += "📡 النظام: سحب ذكي مرتبط بنشاط السوق\n"
            msg += "🔴 السوق نشط = فحص مكثف (كل 45 ثانية)\n"
            msg += "🔵 السوق هادئ = توفير طاقة (تجاهل 10 دقائق)\n"
            msg += f"⚠️ حد الطلبات: {self.MAX_DAILY_API_CALLS} يومياً\n"
            msg += "━━━━━━━━━━━━━━━━"
            self.tg(msg)
        else:
            self.log("Failed to connect!")

    def _get_time(self):
        return datetime.datetime.now(self.TZ)

    def _get_time_str(self):
        return self._get_time().strftime("%H:%M:%S")

    def tg(self, msg):
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'}, timeout=5
            )
        except: pass

    def log(self, msg):
        print(f"[{self._get_time_str()}] {msg}")

    def _test_connection(self):
        return self._fetch_twelve_data(self.pair_list[0]) is not None

    def _fetch_twelve_data(self, sym):
        if self.daily_api_calls >= self.MAX_DAILY_API_CALLS:
            if not self.limit_notified:
                self.log(f"🛑 تم الوصول للحد الأقصى ({self.MAX_DAILY_API_CALLS}). دخول وضع السبات.")
                self.tg(f"🛑 *تنبيه:* تم الوصول لحد الاستهلاك اليومي ({self.MAX_DAILY_API_CALLS}).\nالبوت يتوقف لحماية الرصيد.")
                self.limit_notified = True
            return None

        url = "https://api.twelvedata.com/time_series"
        params = {'symbol': sym, 'interval': '1min', 'outputsize': 30, 'apikey': self.twelve_api_key}
        try:
            r = requests.get(url, params=params, timeout=5)
            self.daily_api_calls += 1
            d = r.json()
            if 'values' in d and len(d['values']) >= 25:
                raw = d['values']; raw.reverse()
                df = pd.DataFrame(raw, columns=['datetime', 'open', 'high', 'low', 'close'])
                df['time'] = pd.to_datetime(df['datetime'])
                return df.drop(columns=['datetime'])
        except Exception as e:
            self.log(f"API Err {sym}: {str(e)[:30]}")
        return None

    def _get_session_name(self, current_mins):
        if self.morning_session[0] <= current_mins < self.morning_session[1]:
            return "☀️ صباحية"
        elif self.evening_session[0] <= current_mins < self.evening_session[1]:
            return "🌙 مسائية"
        return ""

    def _check_volatility(self, df):
        """يقيس نشاط السوق لآخر 5 شموع لاتخاذ قرار السحب"""
        try:
            recent = df.tail(5)
            highs = recent['high'].astype(float)
            lows = recent['low'].astype(float)
            avg_range = (highs - lows).mean()
            return avg_range > self.VOLATILITY_THRESHOLD
        except:
            return False

    def _analyze_symbol(self, api_sym, df):
        if df is None or len(df) < 25: return None, 0, ""
        try:
            df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}).copy()
            df['ema10'] = ta.trend.ema_indicator(df['Close'], window=10)
            df['ema20'] = ta.trend.ema_indicator(df['Close'], window=20)
            stoch = ta.momentum.StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'], window=14, smooth_window=3)
            df['stoch_k'] = stoch.stoch()

            cur = df.iloc[-1]; prev = df.iloc[-2]
            price = float(cur['Close'])

            if pd.isna(cur['ema10']) or pd.isna(cur['stoch_k']) or pd.isna(prev['ema10']): return None, price, ""

            now = time.time()
            stoch_k_cur = float(cur['stoch_k'])

            # تحديث الذاكرة (المرحلة الأولى: الاستوكاستيك يدخل منطقة تشبع)
            if stoch_k_cur > 75: 
                self.stage_memory[api_sym] = 'PUT_READY'; self.stage_time[api_sym] = now
            elif stoch_k_cur < 25: 
                self.stage_memory[api_sym] = 'CALL_READY'; self.stage_time[api_sym] = now
            else:
                # إعادة ضبط إذا خرج من منطقة التشبع قبل حدوث التقاطع
                if self.stage_memory.get(api_sym) in ['PUT_READY', 'CALL_READY']:
                    self.stage_memory[api_sym] = None

            current_stage = self.stage_memory.get(api_sym)
            
            # المرحلة الثانية: التقاطع يحدث والاستوكاستيك لا يزال في التشبع
            if current_stage == 'PUT_READY':
                if (float(prev['ema10']) >= float(prev['ema20'])) and (float(cur['ema10']) < float(cur['ema20'])):
                    self.stage_memory[api_sym] = None
                    return 'PUT', price, "Stoch+EMA Cross 🔥"
            elif current_stage == 'CALL_READY':
                if (float(prev['ema10']) <= float(prev['ema20'])) and (float(cur['ema10']) > float(cur['ema20'])):
                    self.stage_memory[api_sym] = None
                    return 'CALL', price, "Stoch+EMA Cross 🔥"
        except Exception as e:
            pass
        return None, 0, ""

    def _send_signal(self, api_sym, qx_sym, direction, price, confirmation, session_name):
        self.last_signal_time[api_sym] = time.time()
        self.daily_signal_count += 1
        arrow = "⬆️" if direction == 'CALL' else "⬇️"
        expiry_time = self._get_time() + datetime.timedelta(minutes=2)

        msg  = f"⚡ *إشارة {direction} {arrow}*\n"
        msg += f"━━━━━━━━━━━━━━━━\n"
        msg += f"🪙 الزوج: *{qx_sym}*\n"
        msg += f"📊 الجلسة: *{session_name}*\n"
        msg += f"🎯 إشارة رقم: *{self.daily_signal_count}*\n"
        msg += f"🔑 التأكيد: *{confirmation}*\n"
        msg += f"⏱️ الانتهاء: *{expiry_time.strftime('%H:%M:%S')}*\n"
        msg += f"💵 السعر: `{price:.5f}`\n"
        msg += f"🛡️ API مستخدم اليوم: *{self.daily_api_calls}*\n"
        msg += f"━━━━━━━━━━━━━━━━"
        self.tg(msg)
        self.log(f"Signal: {direction} {qx_sym} | API Used: {self.daily_api_calls}")

    def run(self):
        self.log("SNIPER V18.0 RUNNING - Smart Radar Active")
        scan_index = 0 # للمرور على الأزواج بالتناوب

        while True:
            try:
                now = self._get_time()
                current_mins = now.hour * 60 + now.minute
                now_ts = time.time()

                # 1. إعادة تصفير العدادات في منتصف الليل
                if now.day != self.current_day:
                    self.current_day = now.day
                    self.daily_signal_count = 0
                    self.daily_api_calls = 0
                    self.limit_notified = False
                    self.stage_memory = {}
                    # إعادة ضبط أوقات الفحص لتبدأ فوراً في الجلسة القادمة
                    for sym in self.pair_list:
                        self.pair_status[sym]['next_check'] = 0
                    self.log("🔄 يوم جديد! تم تصفير العدادات.")

                # 2. التحقق من وجودنا داخل إحدى الجلسات
                in_morning = self.morning_session[0] <= current_mins < self.morning_session[1]
                in_evening = self.evening_session[0] <= current_mins < self.evening_session[1]

                if not in_morning and not in_evening:
                    # خارج الجلسات: سكون تام لتوفير الموارد
                    time.sleep(30)
                    continue

                session_name = self._get_session_name(current_mins)

                # 3. جلب الزوج التالي في الدور (نظام الطابور لتوزيع الطلبات وليس سحبها دفعة واحدة)
                current_sym = self.pair_list[scan_index % len(self.pair_list)]
                scan_index += 1

                status = self.pair_status[current_sym]

                # 4. التحقق: هل حان وقت فحص هذا الزوج؟
                if now_ts < status['next_check']:
                    time.sleep(1) # انتظر ثانية ثم تحقق من الزوج التالي
                    continue

                # 5. التحقق من الـ Cooldown بعد إعطاء إشارة
                if now_ts - self.last_signal_time.get(current_sym, 0) < self.COOLDOWN_SEC:
                    status['next_check'] = now_ts + self.COOLDOWN_SEC
                    continue

                # 6. سحب البيانات
                df = self._fetch_twelve_data(current_sym)
                if df is not None:
                    # 7. قياس نشاط السوق لهذا الزوج
                    is_active = self._check_volatility(df)
                    status['is_hot'] = is_active

                    # 8. تحديد متى يتم فحص هذا الزوج مرة أخرى بناءً على نشاطه
                    if is_active:
                        status['next_check'] = now_ts + self.HOT_SCAN_INTERVAL
                        self.log(f"🔥 [{current_sym}] نشط! فحص مرة أخرى بعد 45 ثانية.")
                    else:
                        status['next_check'] = now_ts + self.COLD_SCAN_INTERVAL
                        self.log(f"❄️ [{current_sym}] هادئ. تجاهل لمدة 10 دقائق.")

                    # 9. تحليل البيانات hunted للإشارة
                    direction, price, confirmation = self._analyze_symbol(current_sym, df)
                    if direction:
                        self._send_signal(current_sym, self.SYMBOLS_MAP[current_sym], direction, price, confirmation, session_name)
                        # بعد الإشارة، نعطي هذا الزوج راحة لكي لا يتكرر نفس النمط المزيف
                        status['next_check'] = now_ts + 300 
                
                time.sleep(0.5)

            except Exception as e:
                self.log(f"ERR: {e}")
                time.sleep(5)

if __name__ == "__main__":
    bot = QuotexSniperBot()
    if bot.tg_token and bot.twelve_api_key: bot.run()
