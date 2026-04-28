import time, pandas as pd, ta, requests, datetime, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class QuotexSniperBot:
    """
    بوت القناص V14.2 Final (تم إصلاح خلل المرحلة المتزامنة)
    ==========================================================
    - إذا دخلت المرحلة 1 والمرحلة 2 في نفس الشمعة يتم إطلاق الإشارة فوراً.
    """

    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')

        if not self.tg_token or not self.tg_chat:
            print("[FATAL ERROR] Missing TELEGRAM_TOKEN or CHAT_ID!")
            return

        self.TZ = ZoneInfo("Africa/Tripoli")

        self.SYMBOLS_MAP = {
            'BTC/USDT': 'BTCUSD(t)', 'ETH/USDT': 'ETHUSD(t)',
            'BNB/USDT': 'BNBUSD(t)', 'SOL/USDT': 'SOLUSD(t)',
            'XRP/USDT': 'XRPUSD(t)', 'DOGE/USDT': 'DOGEUSD(t)',
            'ADA/USDT': 'ADAUSD(t)', 'EUR/USD': 'EUR/USD OTC',
            'GBP/USD': 'GBP/USD OTC', 'USD/JPY': 'USD/JPY OTC',
            'AUD/USD': 'AUD/USD OTC', 'USD/CAD': 'USD/CAD OTC',
            'EUR/GBP': 'EUR/GBP OTC', 'NZD/USD': 'NZD/USD OTC',
            'EUR/JPY': 'EUR/JPY OTC', 'GBP/CAD': 'GBP/CAD OTC',
        }

        self.stage_memory = {}
        self.stage_time = {}
        self.last_signal_time = {}
        self.stats = {'signals_sent': 0, 'stage1_hits': 0, 'engulfing_hits': 0}
        self.report_time = time.time()
        self.COOLDOWN_SEC = 180
        self.STAGE_TIMEOUT = 900

        msg  = "⚡ *بوت القناص V14.2 (مُصلح)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "🔧 تم إصلاح خلل الإشارات المتزامنة\n"
        msg += "🚀 جاهز للانقضاض..."
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
        except:
            pass

    def log(self, msg):
        ts = self._get_time()
        print(f"[{ts}] {msg}")

    def _fetch_single(self, sym):
        base, quote = sym.split('/')
        url = "https://min-api.cryptocompare.com/data/v2/histominute"
        params = {'fsym': base, 'tsym': quote, 'limit': 30}
        try:
            r = requests.get(url, params=params, timeout=5)
            d = r.json()
            if d.get('Response') == 'Success':
                raw = d.get('Data', {}).get('Data', [])
                if raw:
                    df = pd.DataFrame(raw, columns=['time', 'open', 'high', 'low', 'close', 'volumeto'])
                    df['time'] = pd.to_datetime(df['time'], unit='ms')
                    return sym, df
        except:
            pass
        return sym, None

    def _get_all_data_parallel(self):
        data_dict = {}
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = {executor.submit(self._fetch_single, sym): sym for sym in self.SYMBOLS_MAP.keys()}
            for future in as_completed(futures):
                sym, df = future.result()
                if df is not None:
                    data_dict[sym] = df
        return data_dict

    # ================================================================
    #   استراتيجية V14.2 (النسخة المُصلحة)
    # ================================================================

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
            if api_sym in self.stage_memory and self.stage_memory[api_sym] is not None:
                if now - self.stage_time.get(api_sym, 0) > self.STAGE_TIMEOUT:
                    self.stage_memory[api_sym] = None

            stoch_k_cur = cur['stoch_k']

            # ==========================================
            # المرحلة 1: الستوكاستيك (تم إزالة return)
            # ==========================================
            if (stoch_k_cur > 70 and self.stage_memory.get(api_sym) != 'PUT_READY'):
                self.stage_memory[api_sym] = 'PUT_READY'
                self.stage_time[api_sym] = now
                self.stats['stage1_hits'] += 1
                # تم حذف return None عشان يكمل للمرحلة 2 لو التقاطع صار بنفس الشمعة

            if (stoch_k_cur < 30 and self.stage_memory.get(api_sym) != 'CALL_READY'):
                self.stage_memory[api_sym] = 'CALL_READY'
                self.stage_time[api_sym] = now
                self.stats['stage1_hits'] += 1
                # تم حذف return None عشان يكمل للمرحلة 2 لو التقاطع صار بنفس الشمعة

            # ==========================================
            # المرحلة 2: التقاطع + برايس أكشن
            # ==========================================
            current_stage = self.stage_memory.get(api_sym)
            
            is_bearish_engulfing = (cur['Close'] < cur['Open']) and (prev['Close'] > prev['Open']) and (cur['Open'] >= prev['Close']) and (cur['Close'] <= prev['Open'])
            is_bullish_engulfing = (cur['Close'] > cur['Open']) and (prev['Close'] < prev['Open']) and (cur['Open'] <= prev['Close']) and (cur['Close'] >= prev['Open'])

            confirmation = "تقاطع EMA"

            if current_stage == 'PUT_READY':
                cross_down = (prev['ema10'] >= prev['ema20']) and (cur['ema10'] < cur['ema20'])
                if cross_down:
                    self.stage_memory[api_sym] = None
                    if is_bearish_engulfing:
                        confirmation = "تقاطع + ابتلاعية 🔥"
                        self.stats['engulfing_hits'] += 1
                    return 'PUT', price, confirmation
                    
            elif current_stage == 'CALL_READY':
                cross_up = (prev['ema10'] <= prev['ema20']) and (cur['ema10'] > cur['ema20'])
                if cross_up:
                    self.stage_memory[api_sym] = None
                    if is_bullish_engulfing:
                        confirmation = "تقاطع + ابتلاعية 🔥"
                        self.stats['engulfing_hits'] += 1
                    return 'CALL', price, confirmation

        except Exception as e:
            return None, 0, ""

        return None, 0, ""

    def _send_signal(self, api_sym, qx_sym, direction, price, confirmation):
        self.stats['signals_sent'] += 1
        self.last_signal_time[api_sym] = time.time()

        icon = "🟢" if direction == 'CALL' else "🔴"
        arrow = "⬆️" if direction == 'CALL' else "⬇️"
        now_libya = datetime.datetime.now(self.TZ)
        expiry_time = now_libya + datetime.timedelta(minutes=2)
        decimals = 5 if 'USD' in api_sym and 'USDT' not in api_sym else 2

        msg  = f"⚡ *إشارة {direction} {arrow}*\n"
        msg += f"━━━━━━━━━━━━━━━━\n"
        msg += f"🪙 الزوج: *{qx_sym}*\n"
        msg += f"⏱️ الانتهاء: *{expiry_time.strftime('%H:%M:%S')}*\n"
        msg += f"💵 السعر: `{price:.{decimals}f}`\n"
        msg += f"🔑 التأكيد: *{confirmation}*\n"
        msg += f"━━━━━━━━━━━━━━━━"
        
        self.tg(msg)
        self.log(f">>>> SIGNAL: {qx_sym} {direction} | {confirmation}")

    def run(self):
        self.log("SNIPER V14.2 FINAL STARTED - Bug Fixed")
        self.log("========================================")

        while True:
            try:
                now_libya = datetime.datetime.now(self.TZ)
                current_second = now_libya.second
                
                sec_left = 60 - current_second - (now_libya.microsecond / 1_000_000)

                if sec_left > 2:
                    self.log(f"⏳ انتظار ذكي... باقي {int(sec_left)-2} ثانية.")
                    time.sleep(sec_left - 2)
                    continue

                self.log("🔥 [الثانية 58] جلب البيانات بالتوازي وتحليل الأزواج...")
                
                data_dict = self._get_all_data_parallel()
                
                for api_sym, df in data_dict.items():
                    if api_sym in self.last_signal_time:
                        if time.time() - self.last_signal_time[api_sym] < self.COOLDOWN_SEC:
                            continue

                    direction, price, confirmation = self._analyze_symbol(api_sym, df)
                    
                    if direction and price > 0:
                        qx_sym = self.SYMBOLS_MAP[api_sym]
                        self._send_signal(api_sym, qx_sym, direction, price, confirmation)

                self.log("✅ تم فحص الشمعة.")

                if time.time() - self.report_time >= 3600:
                    self.tg(
                        f"📊 *تقرير V14.2 (ساعة)*\n━━━━━━━━━━━━━━━━\n"
                        f"📍 مراحل أولى: {self.stats['stage1_hits']}\n"
                        f"🔥 شموع ابتلاعية: {self.stats['engulfing_hits']}\n"
                        f"🎯 إشارات نهائية: {self.stats['signals_sent']}\n━━━━━━━━━━━━━━━━"
                    )
                    self.report_time = time.time()

                time.sleep(3)

            except Exception as e:
                self.log(f"ERR: {e}")
                time.sleep(10)


if __name__ == "__main__":
    bot = QuotexSniperBot()
    if bot.tg_token:
        bot.run()
