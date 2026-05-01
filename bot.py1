import time, pandas as pd, ta, requests, datetime, os, sys
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class QuotexSniperBot:
    """
    بوت القناص V17.5 (التوازن المثالي: 750 طلب يومياً)
    =============================================================
    - الاستراتيجية: استوكاستيك + تقاطع الموفينجات فقط (بدون ابتلاعية).
    - نظام السحب متدرج داخل أوقات الجلسات فقط لتوفير الرصيد.
    - يحتوي على صمام أمان يوقف البوت عند 750 طلب لحماية الحساب من الإيقاف.
    """

    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')
        self.twelve_api_key = os.environ.get('TWELVE_DATA_API_KEY')

        if not self.tg_token or not self.tg_chat:
            print("[FATAL ERROR] Missing TELEGRAM_TOKEN or CHAT_ID!")
            return
        if not self.twelve_api_key:
            print("[FATAL ERROR] Missing TWELVE_DATA_API_KEY!")
            return

        self.TZ = ZoneInfo("Africa/Tripoli")

        self.SYMBOLS_MAP = {
            'EUR/USD': 'EUR/USD',
            'GBP/JPY': 'GBP/JPY',
            'USD/CAD': 'USD/CAD',
            'EUR/GBP': 'EUR/GBP',
            'USD/CHF': 'USD/CHF',
            'AUD/USD': 'AUD/USD',
            'GBP/USD': 'GBP/USD'
        }

        self.pair_list = list(self.SYMBOLS_MAP.keys())

        # جلسات التداول
        self.morning_slots = [480, 510, 540, 570, 600]
        self.evening_slots = [1020, 1050, 1080, 1110, 1140]
        self.all_slots = self.morning_slots + self.evening_slots

        self.completed_windows = set()
        self.daily_signal_count = 0
        self.current_day = datetime.datetime.now(self.TZ).day

        # === نظام الحماية من استهلاك الرصيد ===
        self.daily_api_calls = 0
        self.MAX_DAILY_API_CALLS = 750  # هامش أمان ممتاز يمنع تجاوز الـ 800 طلب
        self.limit_notified = False

        self.stage_memory = {}
        self.stage_time = {}
        self.last_signal_time = {}
        self.COOLDOWN_SEC = 180
        self.STAGE_TIMEOUT = 900
        
        self.last_checked_minute = -1
        self.latest_data = {}
        self.fetched_this_minute = {}

        if self._test_connection():
            self.log("Connected Successfully - API Cap Enforced (750 Max)")
            msg  = "🧠 *بوت القناص V17.5 (نظام الـ 750 طلب)*\n"
            msg += "━━━━━━━━━━━━━━━━\n"
            msg += f"⚠️ الحد الأقصى للطلبات: {self.MAX_DAILY_API_CALLS} يومياً\n"
            msg += "⚡ فلتر الابتلاعية: مُلغى ❌\n"
            msg += "📈 7 أزواج فوركس حقيقية\n"
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
                data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'},
                timeout=5
            )
        except: pass

    def log(self, msg):
        print(f"[{self._get_time_str()}] {msg}")

    def _test_connection(self):
        sym = self.pair_list[0]
        df = self._fetch_twelve_data(sym)
        return df is not None

    def _fetch_twelve_data(self, sym):
        if self.daily_api_calls >= self.MAX_DAILY_API_CALLS:
            if not self.limit_notified:
                self.log(f"🛑 تم الوصول للحد الأقصى للطلبات ({self.MAX_DAILY_API_CALLS}). البوت في وضع السبات للغد.")
                self.tg(f"🛑 *تنبيه حد الاستهلاك*\nتم الوصول للحد الأقصى المسموح به اليوم ({self.MAX_DAILY_API_CALLS} طلب).\nتوقف البوت عن سحب البيانات لحماية حسابك حتى منتصف الليل.")
                self.limit_notified = True
            return None

        url = "https://api.twelvedata.com/time_series"
        params = {
            'symbol': sym,
            'interval': '1min',
            'outputsize': 30,
            'apikey': self.twelve_api_key
        }
        try:
            r = requests.get(url, params=params, timeout=5)
            self.daily_api_calls += 1  # زيادة العداد مع كل طلب
            
            d = r.json()
            if 'values' in d and len(d['values']) >= 25:
                raw = d['values']
                raw.reverse() 
                df = pd.DataFrame(raw, columns=['datetime', 'open', 'high', 'low', 'close'])
                df['time'] = pd.to_datetime(df['datetime'])
                df = df.drop(columns=['datetime'])
                return df
        except Exception as e:
            self.log(f"API Err {sym}: {str(e)[:30]}")
        return None

    def _get_session_name(self, slot_mins):
        if slot_mins in self.morning_slots:
            idx = self.morning_slots.index(slot_mins) + 1
            return f"☀️ صباحية {idx}/5"
        else:
            idx = self.evening_slots.index(slot_mins) + 1
            return f"🌙 مسائية {idx}/5"

    def _analyze_symbol(self, api_sym, df):
        if df is None or len(df) < 25: return None, 0, ""
        try:
            df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}).copy()
            df['ema10'] = ta.trend.ema_indicator(df['Close'], window=10)
            df['ema20'] = ta.trend.ema_indicator(df['Close'], window=20)
            stoch = ta.momentum.StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'], window=14, smooth_window=3)
            df['stoch_k'] = stoch.stoch()

            cur = df.iloc[-1]
            prev = df.iloc[-2]
            price = cur['Close']

            if pd.isna(cur['ema10']) or pd.isna(cur['stoch_k']): return None, price, ""

            now = time.time()
            stoch_k_cur = cur['stoch_k']

            if (stoch_k_cur > 70): self.stage_memory[api_sym] = 'PUT_READY'; self.stage_time[api_sym] = now
            if (stoch_k_cur < 30): self.stage_memory[api_sym] = 'CALL_READY'; self.stage_time[api_sym] = now

            current_stage = self.stage_memory.get(api_sym)
            if current_stage == 'PUT_READY':
                if (prev['ema10'] >= prev['ema20']) and (cur['ema10'] < cur['ema20']):
                    self.stage_memory[api_sym] = None
                    return 'PUT', price, "تقاطع EMA 10/20 🔥"
            elif current_stage == 'CALL_READY':
                if (prev['ema10'] <= prev['ema20']) and (cur['ema10'] > cur['ema20']):
                    self.stage_memory[api_sym] = None
                    return 'CALL', price, "تقاطع EMA 10/20 🔥"
        except: pass
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
        msg += f"🎯 رقم: *{self.daily_signal_count}/10*\n"
        msg += f"🔑 التأكيد: *{confirmation}*\n"
        msg += f"⏱️ الانتهاء: *{expiry_time.strftime('%H:%M:%S')}*\n"
        msg += f"💵 السعر: `{price:.5f}`\n"
        msg += f"━━━━━━━━━━━━━━━━"
        self.tg(msg)

    def run(self):
        self.log("SNIPER V17.5 RUNNING - 750 API Calls Limit Active")
        while True:
            try:
                now = self._get_time()
                current_mins = now.hour * 60 + now.minute
                current_sec = now.second

                # إعادة التعيين اليومي (يتم تصفير عداد الطلبات أيضاً)
                if now.day != self.current_day:
                    self.current_day = now.day
                    self.daily_signal_count = 0
                    self.daily_api_calls = 0
                    self.limit_notified = False
                    self.completed_windows = set()
                    self.log("🔄 يوم جديد! تم إعادة تصفير الإشارات وعداد الطلبات.")

                if self.daily_signal_count >= 10:
                    time.sleep(30); continue

                current_slot = None
                for slot in self.all_slots:
                    if slot <= current_mins < slot + 30:
                        current_slot = slot
                        break

                if current_slot is None:
                    if current_sec == 0: self.log(f"Sleeping... Outside session. API used today: {self.daily_api_calls}/{self.MAX_DAILY_API_CALLS}")
                    time.sleep(1); continue
                
                if current_slot in self.completed_windows:
                    time.sleep(10); continue

                # نظام السحب إذا لم نتجاوز الحد الأقصى
                if 45 <= current_sec <= 56 and self.daily_api_calls < self.MAX_DAILY_API_CALLS:
                    for api_sym in self.pair_list:
                        if self.fetched_this_minute.get(api_sym) != current_mins:
                            df = self._fetch_twelve_data(api_sym)
                            if df is not None: self.latest_data[api_sym] = df
                            self.fetched_this_minute[api_sym] = current_mins
                            time.sleep(0.5); break 

                if current_sec == 58:
                    if current_mins != self.last_checked_minute:
                        self.last_checked_minute = current_mins
                        session_name = self._get_session_name(current_slot)
                        for api_sym in self.pair_list:
                            if api_sym not in self.latest_data: continue
                            if time.time() - self.last_signal_time.get(api_sym, 0) < self.COOLDOWN_SEC: continue
                            
                            df = self.latest_data[api_sym]
                            direction, price, confirmation = self._analyze_symbol(api_sym, df)
                            if direction:
                                self._send_signal(api_sym, self.SYMBOLS_MAP[api_sym], direction, price, confirmation, session_name)
                                self.completed_windows.add(current_slot); break
                time.sleep(0.5)
            except Exception as e:
                self.log(f"ERR: {e}"); time.sleep(5)

if __name__ == "__main__":
    bot = QuotexSniperBot()
    if bot.tg_token and bot.twelve_api_key: bot.run()
