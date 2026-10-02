"""
═══════════════════════════════════════════════════════════════════════
  🔥 القناص الأسطوري V8.0 — Legendary Sniper (Adaptive Self-Healing) 🔥
═══════════════════════════════════════════════════════════════════════
  تحديثات V8.0 (إصلاح شامل + ذكاء تكيفي + شفاء ذاتي):
  ✅ إصلاح فجوة استبدال الستوب: وضع الجديد قبل حذف القديم (لا مركز عارٍ أبداً)
  ✅ الإغلاق حسب حجم المركز الفعلي (positionAmt) وليس الكمية المخزّنة
  ✅ جني TP2 كأمر TAKE_PROFIT_MARKET على المنصة (الربح ينجو من انهيار البوت)
  ✅ فحص الرصيد قبل الدخول + تخزين maxQty + مزامنة وقت الخادم (علاج -1021)
  ✅ منع إسهام تنبيهات الاكتشاف (dedup 30 دقيقة) — لا حظر من Telegram
  ✅ صلاحية SL (موجب/منطقي) + حد أدنى للمخاطرة + استخدام bid للشورت
  ✅ نظام تقييم مرن (Score/10) مع تريجر بديل: إعادة اختبار OB (Retest)
     → نشاط أعلى بكثير مع الحفاظ على فلاتر الترند والمخاطر الأساسية
  ✅ المطوّر التكيفي (AdaptiveTuner): يتعلم من آخر 20 صفقة، يرتخي عند قلة
     النشاط ويشدد عند تدهور الفوز — ضمن حدود آمنة ومحفوظ في القاعدة
  ✅ مصالحة ذاتية عند الإقلاع: تبنّي المراكز اليتيمة + إلغاء الأوامر اليتيمة
     + إغلاق صفقات القاعدة التي انتهت أثناء التوقف
  ✅ إيقاف آمن (SIGINT/SIGTERM) + نبض قلب ساعي + تقرير يومي
  ✅ دعم Testnet عبر TESTNET=true + تحقق صارم من الإعدادات (fail-fast)
  ✅ سجل إشارات (signal_log) لتغذية التعلم مستقبلاً
  ✅ تنظيف دوري للذواكر المؤقتة واستثناءات محددة بدل الصامتة
═══════════════════════════════════════════════════════════════════════
"""

import asyncio, aiohttp, json, math, os, sys, time, logging, requests
import collections
import pandas as pd
import numpy as np
import hmac
import hashlib
import signal
import threading
from decimal import Decimal
from urllib.parse import urlencode
from logging.handlers import RotatingFileHandler
import websockets
import aiosqlite

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

logger = logging.getLogger('SniperV8')
logger.setLevel(logging.INFO)
fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh = RotatingFileHandler('bot_v8.log', maxBytes=2*1024*1024, backupCount=2, encoding='utf-8')
fh.setFormatter(fmt); logger.addHandler(fh)
ch = logging.StreamHandler(); ch.setFormatter(fmt); logger.addHandler(ch)


class TelegramLoggingHandler(logging.Handler):
    """معالج أخطاء تلغرام مع صمام خنق (رسالة كل 5 دقائق لنفس المصدر)"""
    THROTTLE_SECONDS = 300

    def __init__(self):
        super().__init__()
        self._last_sent = {}

    def emit(self, record):
        try:
            if record.levelno >= logging.ERROR:
                tok = os.environ.get('TELEGRAM_TOKEN', '')
                cid = os.environ.get('CHAT_ID', '')
                if tok and cid:
                    key = (record.module, record.lineno)
                    now = time.time()
                    if now - self._last_sent.get(key, 0) < self.THROTTLE_SECONDS:
                        return
                    self._last_sent[key] = now
                    msg_text = f"🚨 *خطأ:*\n```\n{self.format(record)[:400]}\n```"
                    url = f"https://api.telegram.org/bot{tok}/sendMessage"
                    threading.Thread(target=self._send, args=(url, cid, msg_text), daemon=True).start()
        except Exception:
            pass

    def _send(self, url, cid, msg_text):
        try:
            requests.post(url, data={'chat_id': cid, 'text': msg_text, 'parse_mode': 'Markdown'}, timeout=5)
        except Exception:
            pass

tg_handler = TelegramLoggingHandler()
tg_handler.setLevel(logging.ERROR)
logger.addHandler(tg_handler)


# ═══════════════════════ قاعدة البيانات ═════════════════════
class DatabaseManager:
    def __init__(self, db_name='sniper_v8.db'):
        self.db_name = db_name

    async def init_db(self):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS active_trades (
                symbol TEXT PRIMARY KEY, side TEXT, entry_price REAL, quantity REAL,
                sl REAL, tp REAL, tp2 REAL, trailing_active INTEGER, highest_price REAL,
                lowest_price REAL, entry_time REAL, partial_closed INTEGER,
                realized_pnl REAL DEFAULT 0, stop_order_id INTEGER, tp_order_id INTEGER)""")
            for col_def in ('realized_pnl REAL DEFAULT 0', 'stop_order_id INTEGER',
                            'tp2 REAL', 'tp_order_id INTEGER'):
                try:
                    await db.execute(f"ALTER TABLE active_trades ADD COLUMN {col_def}")
                except Exception:
                    pass
            await db.execute("""CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY, realized_pnl REAL, wins INTEGER, losses INTEGER)""")
            await db.execute("""CREATE TABLE IF NOT EXISTS bot_params (
                key TEXT PRIMARY KEY, value TEXT)""")
            await db.execute("""CREATE TABLE IF NOT EXISTS signal_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, direction TEXT,
                entry_ts REAL, score REAL, components TEXT,
                result INTEGER DEFAULT -1, pnl REAL)""")
            await db.commit()

    async def get_param(self, key):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                async with db.execute("SELECT value FROM bot_params WHERE key=?", (key,)) as cur:
                    row = await cur.fetchone()
                    return row[0] if row else None
        except Exception:
            return None

    async def set_param(self, key, value):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("INSERT OR REPLACE INTO bot_params (key, value) VALUES (?,?)", (key, value))
            await db.commit()

    async def log_signal(self, symbol, direction, entry_ts, score, components):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute(
                    "INSERT INTO signal_log (symbol, direction, entry_ts, score, components) VALUES (?,?,?,?,?)",
                    (symbol, direction, entry_ts, score, json.dumps(components, ensure_ascii=False)))
                await db.commit()
        except Exception as e:
            logger.warning(f"تعذر تسجيل الإشارة: {e}")

    async def set_signal_result(self, symbol, entry_ts, win, pnl):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute(
                    "UPDATE signal_log SET result=?, pnl=? WHERE symbol=? AND entry_ts=? AND result=-1",
                    (int(win), pnl, symbol, entry_ts))
                await db.commit()
        except Exception as e:
            logger.warning(f"تعذر تحديث نتيجة الإشارة: {e}")

    async def save_trade(self, t):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""INSERT OR REPLACE INTO active_trades
                (symbol, side, entry_price, quantity, sl, tp, tp2, trailing_active,
                 highest_price, lowest_price, entry_time, partial_closed,
                 realized_pnl, stop_order_id, tp_order_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (t['symbol'], t['side'], t['entry_price'], t['quantity'],
                 t['sl'], t['tp'], t.get('tp2'), int(t.get('trailing_active', False)),
                 t.get('highest_price', 0), t.get('lowest_price', 999999),
                 t['entry_time'], int(t.get('partial_closed', 0)),
                 float(t.get('realized_pnl', 0.0)), t.get('stop_order_id'), t.get('tp_order_id')))
            await db.commit()

    async def load_active_trades(self):
        trades = {}
        try:
            async with aiosqlite.connect(self.db_name) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""SELECT symbol, side, entry_price, quantity, sl, tp, tp2,
                    trailing_active, highest_price, lowest_price, entry_time, partial_closed,
                    realized_pnl, stop_order_id, tp_order_id FROM active_trades""") as cur:
                    async for row in cur:
                        trades[row['symbol']] = {
                            'symbol': row['symbol'], 'side': row['side'],
                            'entry_price': row['entry_price'], 'quantity': row['quantity'],
                            'sl': row['sl'], 'tp': row['tp'], 'tp2': row['tp2'],
                            'trailing_active': bool(row['trailing_active']),
                            'highest_price': row['highest_price'],
                            'lowest_price': row['lowest_price'],
                            'entry_time': row['entry_time'],
                            'partial_closed': bool(row['partial_closed']),
                            'realized_pnl': row['realized_pnl'] if row['realized_pnl'] is not None else 0.0,
                            'stop_order_id': row['stop_order_id'],
                            'tp_order_id': row['tp_order_id'],
                            'stop_synced_price': None, 'tp_skipped': False
                        }
        except Exception as e:
            logger.error(f"❌ فشل تحميل الصفقات من القاعدة: {e}")
        return trades

    async def remove_trade(self, symbol):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("DELETE FROM active_trades WHERE symbol=?", (symbol,))
            await db.commit()

    async def update_daily_pnl(self, pnl, is_win=None):
        today = time.strftime("%Y-%m-%d")
        w = 1 if is_win is True else 0
        l = 1 if is_win is False else 0
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT * FROM daily_stats WHERE date=?", (today,)) as cur:
                row = await cur.fetchone()
            if row:
                await db.execute("UPDATE daily_stats SET realized_pnl=?, wins=?, losses=? WHERE date=?",
                    (row[1]+pnl, row[2]+w, row[3]+l, today))
            else:
                await db.execute("INSERT INTO daily_stats VALUES (?,?,?,?)", (today, pnl, w, l))
            await db.commit()

    async def get_day_stats(self, day):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                async with db.execute(
                        "SELECT realized_pnl, wins, losses FROM daily_stats WHERE date=?", (day,)) as cur:
                    return await cur.fetchone()
        except Exception:
            return None


# ═══════════════════════ المطوّر التكيفي (Self-Tuning) ═════════════════════
class AdaptiveTuner:
    """
    يتعلم من آخر الصفقات ويعدّل صرامة الدخول تلقائياً ضمن حدود آمنة:
    - قلة النشاط (لا صفقات منذ 10 ساعات وأقل من 3 اليوم) → يرتخي تدريجياً
    - تدهور الفوز (<38% في آخر 10) → يشدد تدريجياً
    المحفوظ في قاعدة البيانات ويستمر عبر إعادات التشغيل.
    """
    def __init__(self, db):
        self.db = db
        self.min_score = 4
        self.proximity_pct = 0.02
        self.strict_stoch = True
        self.results = collections.deque(maxlen=20)

    def _clamp(self):
        self.min_score = max(3, min(6, int(self.min_score)))
        self.proximity_pct = max(0.015, min(0.045, float(self.proximity_pct)))

    async def load(self):
        raw = await self.db.get_param('tuner')
        if raw:
            try:
                d = json.loads(raw)
                self.min_score = int(d.get('min_score', 4))
                self.proximity_pct = float(d.get('proximity_pct', 0.02))
                self.strict_stoch = bool(d.get('strict_stoch', True))
                self.results = collections.deque(d.get('results', [])[-20:], maxlen=20)
                self._clamp()
                logger.info(f"🧠 المطوّر التكيفي محمّل: {self.describe()}")
            except Exception as e:
                logger.warning(f"تعذر تحميل المطوّر التكيفي (سيبدأ افتراضياً): {e}")

    async def save(self):
        try:
            await self.db.set_param('tuner', json.dumps({
                'min_score': self.min_score, 'proximity_pct': self.proximity_pct,
                'strict_stoch': self.strict_stoch, 'results': list(self.results)}))
        except Exception as e:
            logger.warning(f"تعذر حفظ المطوّر التكيفي: {e}")

    def record(self, win):
        self.results.append(bool(win))

    def recent_winrate(self, n=10):
        recent = list(self.results)[-n:]
        if len(recent) < 5:
            return None
        return sum(recent) / len(recent)

    def relax_step(self):
        before = (self.min_score, round(self.proximity_pct, 4))
        if self.min_score > 3:
            self.min_score -= 1
        else:
            self.proximity_pct = round(min(0.045, self.proximity_pct + 0.005), 4)
        if self.min_score <= 3:
            self.strict_stoch = False
        return before != (self.min_score, round(self.proximity_pct, 4))

    def tighten_step(self):
        before = (self.min_score, round(self.proximity_pct, 4))
        if self.proximity_pct > 0.02:
            self.proximity_pct = round(max(0.02, self.proximity_pct - 0.005), 4)
        elif self.min_score < 6:
            self.min_score += 1
        if self.min_score >= 4:
            self.strict_stoch = True
        return before != (self.min_score, round(self.proximity_pct, 4))

    def describe(self):
        return (f"min_score={self.min_score} | قرب OB≤{self.proximity_pct*100:.1f}% | "
                f"ستوك صارم={'نعم' if self.strict_stoch else 'لا'}")


# ═══════════════════════ محرك SMC - صياد الحيتان ═════════════════════
class WhaleSMCEngine:
    @staticmethod
    def detect_order_blocks(df, trend):
        obs = []
        threshold = 0.015

        for i in range(2, len(df)-1):
            if df['close'].iloc[i] > df['open'].iloc[i]:
                impulse_pct = (df['close'].iloc[i] - df['low'].iloc[i-1]) / df['low'].iloc[i-1]
                if df['close'].iloc[i-1] < df['open'].iloc[i-1] and impulse_pct > threshold:
                    obs.append({'type': 'demand', 'top': df['open'].iloc[i-1],
                                'bottom': df['low'].iloc[i-1], 'index': i-1})
            elif df['close'].iloc[i] < df['open'].iloc[i]:
                impulse_pct = (df['high'].iloc[i-1] - df['close'].iloc[i]) / df['high'].iloc[i-1]
                if df['close'].iloc[i-1] > df['open'].iloc[i-1] and impulse_pct > threshold:
                    obs.append({'type': 'supply', 'top': df['high'].iloc[i-1],
                                'bottom': df['close'].iloc[i-1], 'index': i-1})
        return obs

    @staticmethod
    def detect_liquidity_sweep(df_15m, ob_zone, direction):
        """تصفية سيولة (الزناد القوي) — الشمعة المغلقة الأخيرة فقط (منع Repainting)"""
        current_low = df_15m['low'].iloc[-2]
        current_high = df_15m['high'].iloc[-2]
        current_close = df_15m['close'].iloc[-2]
        prev_close = df_15m['close'].iloc[-3]

        if direction == 'BUY' and ob_zone['type'] == 'demand':
            if current_low < ob_zone['bottom'] and current_close > ob_zone['top'] and current_close > prev_close:
                return True
        elif direction == 'SELL' and ob_zone['type'] == 'supply':
            if current_high > ob_zone['top'] and current_close < ob_zone['bottom'] and current_close < prev_close:
                return True
        return False

    @staticmethod
    def detect_ob_retest(df_15m, ob_zone, direction):
        """
        الزناد البديل: إعادة اختبار المنطقة — السعر دخل OB خلال آخر 3 شمعات
        وأغلق الشمعة الأخيرة عائداً خارجها في اتجاه الترند (دخول أكثر نشاطاً)
        """
        lows = df_15m['low'].iloc[-4:-1]
        highs = df_15m['high'].iloc[-4:-1]
        closes = df_15m['close'].iloc[-4:-1]
        if len(closes) < 3:
            return False
        if direction == 'BUY' and ob_zone['type'] == 'demand':
            touched = bool((lows <= ob_zone['top']).any())
            return bool(touched and closes.iloc[-1] > ob_zone['top'] and closes.iloc[-1] > closes.iloc[-2])
        if direction == 'SELL' and ob_zone['type'] == 'supply':
            touched = bool((highs >= ob_zone['bottom']).any())
            return bool(touched and closes.iloc[-1] < ob_zone['bottom'] and closes.iloc[-1] < closes.iloc[-2])
        return False

    @staticmethod
    def calculate_stochastic(df, k_period=14, d_period=3):
        low_min = df['low'].rolling(window=k_period).min()
        high_max = df['high'].rolling(window=k_period).max()
        diff = (high_max - low_min).replace(0, np.nan)
        df['stoch_k'] = 100 * ((df['close'] - low_min) / diff)
        df['stoch_d'] = df['stoch_k'].rolling(window=d_period).mean()
        df['stoch_k'] = df['stoch_k'].fillna(50)
        df['stoch_d'] = df['stoch_d'].fillna(50)
        return df


# ══════════════════════════════════════════════════════════════════════
#           🔥 القناص الأسطوري V8.0 (Adaptive Self-Healing) 🔥
# ══════════════════════════════════════════════════════════════════════
class LegendarySniperFuturesV8:
    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN', '')
        self.tg_chat = os.environ.get('CHAT_ID', '')
        self.binance_api_key = os.environ.get('BINANCE_API_KEY', '')
        self.binance_api_secret = os.environ.get('BINANCE_API_SECRET', '')

        self.TRADE_ENABLED = os.environ.get('TRADE_ENABLED', 'false').lower() == 'true'
        self.LEVERAGE = 10
        self.TRADE_SIZE_USDT = float(os.environ.get('TRADE_SIZE_USDT', '25'))
        self.MAX_OPEN_TRADES = int(os.environ.get('MAX_OPEN_TRADES', '1'))
        self.TESTNET = os.environ.get('TESTNET', 'false').lower() == 'true'

        # ✅ تحقق صارم من الإعدادات — فشل سريع وواضح بدل التشغيل المعطوب
        problems = []
        if self.TRADE_SIZE_USDT <= 0:
            problems.append("TRADE_SIZE_USDT يجب أن يكون أكبر من صفر")
        if not (1 <= self.MAX_OPEN_TRADES <= 10):
            problems.append("MAX_OPEN_TRADES يجب أن يكون بين 1 و 10")
        if self.TESTNET:
            logger.info("🧪 وضع Testnet التجريبي مفعّل")
        if problems:
            raise SystemExit("❌ إعدادات خاطئة:\n- " + "\n- ".join(problems))

        if self.TRADE_ENABLED and (not self.binance_api_key or not self.binance_api_secret):
            self.TRADE_ENABLED = False
            logger.error("❌ التداول مفعّل لكن مفاتيح API ناقصة! التحويل للمراقبة فقط")

        # ثوابت حماية تشغيلية
        self.PRICE_MAX_AGE = 30
        self.REENTRY_COOLDOWN = 900
        self.VERIFY_EVERY_N_LOOPS = 5
        self.WS_STALE_ALERT = 120
        self.BALANCE_CACHE_SECONDS = 60

        self.data_url = "https://fapi.binance.com"
        self.trade_url = ("https://testnet.binancefuture.com" if self.TESTNET
                          else "https://fapi.binance.com")
        self.time_offset_ms = 0

        self.db = DatabaseManager()
        self.smc = WhaleSMCEngine()
        self.tuner = AdaptiveTuner(self.db)
        self.session = None
        self.ws_task = None
        self._shutdown_requested = False

        self.all_futures_pairs = []
        self.step_sizes_cache = {}
        self.tick_sizes_cache = {}
        self.min_qty_cache = {}
        self.max_qty_cache = {}
        self.min_notional_cache = {}
        self.live_prices = {}
        self.active_trades = {}
        self.reentry_cooldown = {}
        self.error_counts = {}
        self.last_discovery_alert = {}
        self.entry_history = collections.deque(maxlen=200)   # (ts, date) لحساب صفقات اليوم
        self._last_heartbeat = 0
        self._report_day = time.strftime("%Y-%m-%d")
        self._last_freq_check = 0
        self._last_tighten = 0
        self._balance_cache = (0.0, 0.0)

        self.stats = {'total_scans': 0, 'trades_executed': 0, 'wins': 0, 'losses': 0}

    # ═══ نظام مكافحة الصمت ═══
    def _notify_error(self, source, exc=None, context=""):
        count = self.error_counts.get(source, 0) + 1
        self.error_counts[source] = count
        txt = f"⚠️ {source}" + (f" — {context}" if context else "")
        if exc is not None:
            txt += f" | `{str(exc)[:100]}`"
        logger.warning(f"{txt} (تكرار #{count})")
        if count == 1 or count % 10 == 0:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.tg(f"{txt}\n🔢 مرات التكرار: {count}"))
            except RuntimeError:
                pass

    def _reset_error(self, source):
        self.error_counts.pop(source, None)

    def fmt_price(self, price):
        if price is None or price == 0: return "$0"
        if price < 0.00001: return f"${price:.10f}"
        elif price < 0.001: return f"${price:.6f}"
        elif price < 1: return f"${price:.4f}"
        elif price < 100: return f"${price:.2f}"
        else: return f"${price:,.1f}"

    async def tg(self, msg):
        try:
            if not self.session or not self.tg_token: return
            await self.session.post(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'}, timeout=10)
        except Exception as e:
            logger.warning(f"تعذر إرسال رسالة تلغرام: {e}")

    # ═══ توقيت الخادم (علاج خطأ -1021 الشهير) ═══
    async def sync_server_time(self):
        try:
            res = await self._fapi_request('GET', '/fapi/v1/time')
            if res and 'serverTime' in res:
                self.time_offset_ms = int(res['serverTime']) - int(time.time() * 1000)
                logger.info(f"🕐 مزامنة وقت الخادم: إزاحة {self.time_offset_ms}ms")
        except Exception as e:
            logger.warning(f"تعذر مزامنة وقت الخادم: {e}")

    def _sign(self, params):
        params['timestamp'] = int(time.time() * 1000) + self.time_offset_ms
        params['recvWindow'] = 5000
        query = urlencode(params)
        params['signature'] = hmac.new(
            self.binance_api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        return params

    async def _fapi_request(self, method, endpoint, params=None, signed=False, retries=3):
        for attempt in range(retries):
            try:
                url = f"{self.trade_url}{endpoint}"
                headers = {'X-MBX-APIKEY': self.binance_api_key} if signed else {}
                req_params = self._sign(dict(params) if params else {}) if signed else params

                async with self.session.request(method, url, params=req_params,
                                                headers=headers, timeout=15) as r:
                    if r.status == 200:
                        return await r.json()
                    body = await r.text()
                    if r.status in (429, 418):
                        await asyncio.sleep(10 * (attempt + 1))
                        continue
                    if r.status == 401:
                        self._notify_error("خطأ 401 من Binance", context="مفاتيح API خاطئة أو مقيدة بـIP")
                        return None
                    if '-1021' in body:  # توقيت غير متزامن → مزامنة وإعادة
                        logger.warning("⚠️ خطأ توقيم -1021 — مزامنة الوقت وإعادة المحاولة")
                        await self.sync_server_time()
                        await asyncio.sleep(1)
                        continue
                    if r.status >= 500:
                        logger.warning(f"Futures API {r.status} — إعادة محاولة...")
                        await asyncio.sleep(2 ** attempt)
                        continue
                    logger.warning(f"Futures API Error {r.status}: {body[:120]}")
                    return None
            except asyncio.TimeoutError:
                if attempt == retries - 1:
                    self._notify_error("انتهت مهلة طلب Binance", context=endpoint)
                    return None
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                if attempt == retries - 1:
                    self._notify_error("فشل طلب Binance", exc=e, context=endpoint)
                    return None
                await asyncio.sleep(2 ** attempt)
        return None

    async def setup_futures_account(self):
        msg = f"⚙️ *إعداد حساب العقود الآجلة (الرافعة {self.LEVERAGE}x)*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        setup_count = 0
        for pair in self.all_futures_pairs[:50]:
            symbol = pair['symbol']
            try:
                lev_res = await self._fapi_request('POST', '/fapi/v1/leverage',
                    {'symbol': symbol, 'leverage': self.LEVERAGE}, signed=True)
                await self._fapi_request('POST', '/fapi/v1/marginType',
                    {'symbol': symbol, 'marginType': 'ISOLATED'}, signed=True)
                if lev_res and lev_res.get('leverage') == self.LEVERAGE:
                    setup_count += 1
            except Exception as e:
                logger.debug(f"تخطي إعداد {symbol}: {e}")
            await asyncio.sleep(0.15)
        msg += f"✅ تم ضبط الرافعة والهامش المعزول لـ {setup_count} زوج"
        await self.tg(msg)

    async def load_market_data(self):
        data = await self._fapi_request('GET', '/fapi/v1/exchangeInfo')
        if not data: return
        new_pairs = []
        for s in data.get('symbols', []):
            if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING' and s['contractType'] == 'PERPETUAL':
                new_pairs.append({'symbol': s['symbol'], 'baseAsset': s['baseAsset']})
                for f in s.get('filters', []):
                    if f['filterType'] == 'LOT_SIZE':
                        self.step_sizes_cache[s['symbol']] = float(f['stepSize'])
                        self.min_qty_cache[s['symbol']] = float(f.get('minQty', f['stepSize']))
                        self.max_qty_cache[s['symbol']] = float(f.get('maxQty', 1e12))
                    elif f['filterType'] == 'PRICE_FILTER':
                        self.tick_sizes_cache[s['symbol']] = float(f['tickSize'])
                    elif f['filterType'] == 'MIN_NOTIONAL':
                        self.min_notional_cache[s['symbol']] = float(f.get('notional', f.get('minNotional', 5.0)))
        self.all_futures_pairs = new_pairs
        logger.info(f"📊 تم تحميل {len(self.all_futures_pairs)} زوج عقود آجلة")

    # ═══ أدوات التنسيق الدقيق ═══
    @staticmethod
    def _decimals_of(step):
        try:
            exp = Decimal(str(step)).normalize().as_tuple().exponent
            return max(0, -exp)
        except Exception:
            return 8

    def _step_qty(self, symbol, qty):
        step = self.step_sizes_cache.get(symbol) or 1.0
        if step <= 0: step = 1.0
        dec = self._decimals_of(step)
        return round(math.floor(round(qty / step, 9)) * step, dec)

    def format_quantity(self, symbol, qty):
        return self._step_qty(symbol, qty)

    def qty_to_str(self, symbol, qty):
        step = self.step_sizes_cache.get(symbol) or 1.0
        dec = self._decimals_of(step)
        return f"{self._step_qty(symbol, qty):.{dec}f}"

    def price_to_str(self, symbol, price):
        tick = self.tick_sizes_cache.get(symbol)
        if not tick or tick <= 0:
            if price >= 100: dec = 2
            elif price >= 1: dec = 4
            elif price >= 0.01: dec = 6
            else: dec = 8
            return f"{price:.{dec}f}"
        dec = self._decimals_of(tick)
        stepped = math.floor(round(price / tick, 9)) * tick
        return f"{round(stepped, dec):.{dec}f}"

    def get_price(self, symbol):
        p = self.live_prices.get(symbol)
        if p and (time.time() - p.get('ts', 0)) <= self.PRICE_MAX_AGE:
            return p
        return None

    def set_cooldown(self, symbol):
        self.reentry_cooldown[symbol] = time.time() + self.REENTRY_COOLDOWN

    def is_in_cooldown(self, symbol):
        expiry = self.reentry_cooldown.get(symbol, 0)
        if time.time() < expiry: return True
        self.reentry_cooldown.pop(symbol, None)
        return False

    async def get_available_usdt(self):
        now = time.time()
        cached_val, cached_ts = self._balance_cache
        if now - cached_ts < self.BALANCE_CACHE_SECONDS and cached_ts > 0:
            return cached_val
        res = await self._fapi_request('GET', '/fapi/v2/balance', signed=True)
        avail = 0.0
        if isinstance(res, list):
            for b in res:
                if b.get('asset') == 'USDT':
                    avail = float(b.get('availableBalance', 0))
                    break
        self._balance_cache = (avail, now)
        return avail

    # ═══ WebSocket ═══
    async def ws_manager(self):
        # ✅ إصلاح 1: الستريم يتبع الوضع — Testnet يستقبل أسعار Testnet نفسها
        ws_url = ("wss://stream.binancefuture.com/ws/!bookTicker" if self.TESTNET
                  else "wss://fstream.binance.com/ws/!bookTicker")
        while True:
            try:
                async with websockets.connect(ws_url, ping_interval=20) as ws:
                    logger.info("✅ Futures WebSocket متصل (Global Mode)!")
                    self._reset_error("انقطاع WebSocket")
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            if 's' in data and 'b' in data and 'a' in data:
                                self.live_prices[data['s']] = {
                                    'bid': float(data['b']), 'ask': float(data['a']),
                                    'ts': time.time()}
                        except (ValueError, KeyError, TypeError):
                            continue
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._notify_error("انقطاع WebSocket", exc=e, context="إعادة الاتصال خلال 5 ثوانٍ")
                await asyncio.sleep(5)

    async def get_klines(self, symbol, interval='15m', limit=100):
        data = await self._fapi_request('GET', '/fapi/v1/klines',
            {'symbol': symbol, 'interval': interval, 'limit': limit})
        if data and len(data) > 20:
            df = pd.DataFrame(data, columns=[
                'time','open','high','low','close','volume',
                'close_time','quote_volume','trades','taker_buy_vol',
                'taker_buy_quote_vol','ignore'])
            for col in ['open','high','low','close','volume','quote_volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            return df
        return None

    @staticmethod
    def _compute_atr(df, period=14):
        hl = df['high'] - df['low']
        hc = (df['high'] - df['close'].shift()).abs()
        lc = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])

    # ═══ التحليل بنظام التقييم المرن (Score) — أكثر نشاطاً مع نفس الجودة ═══
    async def analyze_whale_zone(self, symbol):
        tuner = self.tuner
        df_4h = await self.get_klines(symbol, '4h', 100)
        df_1h = await self.get_klines(symbol, '1h', 100)
        df_15m = await self.get_klines(symbol, '15m', 100)
        if (df_4h is None or len(df_4h) < 30 or df_1h is None or len(df_1h) < 30
                or df_15m is None or len(df_15m) < 30):
            return None

        prices = self.get_price(symbol)
        if not prices: return None

        mid = (prices['bid'] + prices['ask']) / 2
        ema50_4h = df_4h['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        trend = 'BUY' if mid > ema50_4h else 'SELL'
        current_price = prices['ask'] if trend == 'BUY' else prices['bid']   # ✅ bid للشورت

        # 1) قرب منطقة الحوت (نقاط حسب القرب)
        obs = self.smc.detect_order_blocks(df_1h, trend)
        if not obs: return None
        nearby_ob = None
        proximity_pts = 0
        for ob in reversed(obs):
            if trend == 'BUY' and ob['type'] == 'demand':
                distance_pct = (current_price - ob['top']) / current_price
                if -0.005 <= distance_pct <= tuner.proximity_pct:
                    nearby_ob = ob
                    proximity_pts = 2 if distance_pct <= 0.01 else 1
                    break
            elif trend == 'SELL' and ob['type'] == 'supply':
                distance_pct = (ob['bottom'] - current_price) / current_price
                if -0.005 <= distance_pct <= tuner.proximity_pct:
                    nearby_ob = ob
                    proximity_pts = 2 if distance_pct <= 0.01 else 1
                    break
        if not nearby_ob: return None

        # 2) الزناد: تصفية سيولة (3 نقاط) أو إعادة اختبار OB (نقطتان)
        sweep = self.smc.detect_liquidity_sweep(df_15m, nearby_ob, trend)
        retest = False if sweep else self.smc.detect_ob_retest(df_15m, nearby_ob, trend)
        if not (sweep or retest): return None
        trigger_pts = 3 if sweep else 2

        # 3) توقيت الاستوكاستك: كروس من منطقة قصوى (نقطتان) أو كروس عادي
        df_15m = self.smc.calculate_stochastic(df_15m)
        current_k = df_15m['stoch_k'].iloc[-2]
        prev_k = df_15m['stoch_k'].iloc[-3]
        current_d = df_15m['stoch_d'].iloc[-2]
        prev_d = df_15m['stoch_d'].iloc[-3]

        if trend == 'BUY':
            if not (current_k > current_d and prev_k <= prev_d):
                return None
            stoch_pts = 2 if current_k < 20 else (0 if tuner.strict_stoch else 1)
        else:
            if not (current_k < current_d and prev_k >= prev_d):
                return None
            stoch_pts = 2 if current_k > 80 else (0 if tuner.strict_stoch else 1)

        # 4) تأكيد حجم التداول (نقطة إضافية)
        vol_pts = 0
        try:
            qv = df_15m['quote_volume']
            base = qv.iloc[-22:-2].mean()
            if base and qv.iloc[-2] > base * 1.3:
                vol_pts = 1
        except Exception:
            pass

        score = proximity_pts + trigger_pts + stoch_pts + vol_pts
        if score < tuner.min_score:
            return None

        # 5) الدخول والأهداف بـ ATR + فلاتر المخاطرة والصلاحية
        atr = self._compute_atr(df_15m)
        if not atr or atr <= 0 or math.isnan(atr):
            return None
        sl_buffer = atr * 2.0
        if trend == 'BUY':
            sl = nearby_ob['bottom'] - sl_buffer
            tp1 = current_price + atr * 1.5
            tp2 = current_price + atr * 4.0
        else:
            sl = nearby_ob['top'] + sl_buffer
            tp1 = current_price - atr * 1.5
            tp2 = current_price - atr * 4.0

        # ✅ صلاحية الوقف: موجب، منطقي، وعلى الجهة الصحيحة
        if sl <= 0 or math.isnan(sl): return None
        if trend == 'BUY' and sl >= current_price: return None
        if trend == 'SELL' and sl <= current_price: return None

        risk_pct = abs(current_price - sl) / current_price * 100
        if risk_pct > 3.0 or risk_pct < 0.05:   # ✅ حد أدنى أيضاً ضد صفقات الغبار
            return None

        return {
            'symbol': symbol, 'direction': trend, 'price': current_price,
            'sl': sl, 'tp1': tp1, 'tp2': tp2, 'score': score,
            'components': {
                'proximity': proximity_pts,
                'trigger': 'sweep' if sweep else 'retest',
                'trigger_pts': trigger_pts,
                'stoch': stoch_pts,
                'volume': vol_pts,
                'score': score,
                'tuner': tuner.describe()
            },
            'signals_smc': [
                f"🐋 {'صيد حوت' if sweep else 'إعادة اختبار'} في منطقة {'طلب' if trend=='BUY' else 'عرض'}",
                f"📊 تقييم الإشارة: {score}/10",
                f"🛡️ وقف ATR ({risk_pct:.1f}%)"]
        }

    # ═══ التنفيذ ═══
    async def execute_trade(self, analysis):
        if not self.TRADE_ENABLED: return
        if len(self.active_trades) >= self.MAX_OPEN_TRADES: return

        symbol = analysis['symbol']
        if symbol in self.active_trades: return
        if self.is_in_cooldown(symbol): return

        # ✅ فحص الرصيد المتاح (بذاكرة مؤقتة 60 ثانية)
        available = await self.get_available_usdt()
        if available < self.TRADE_SIZE_USDT * 1.2:
            self._notify_error("رصيد غير كافٍ للدخول",
                               context=f"المتاح {available:.2f}$ < المطلوب {self.TRADE_SIZE_USDT * 1.2:.2f}$")
            return

        notional = self.TRADE_SIZE_USDT * self.LEVERAGE
        quantity = self.format_quantity(symbol, notional / analysis['price'])
        if quantity <= 0: return
        if quantity < self.min_qty_cache.get(symbol, 0.0): return
        if quantity > self.max_qty_cache.get(symbol, 1e12): return   # ✅ حد أقصى للزوج
        if quantity * analysis['price'] < self.min_notional_cache.get(symbol, 5.0) * 1.02:
            return

        await self._fapi_request('POST', '/fapi/v1/leverage',
            {'symbol': symbol, 'leverage': self.LEVERAGE}, signed=True)
        await self._fapi_request('POST', '/fapi/v1/marginType',
            {'symbol': symbol, 'marginType': 'ISOLATED'}, signed=True)

        side = 'BUY' if analysis['direction'] == 'BUY' else 'SELL'
        result = await self._fapi_request('POST', '/fapi/v1/order', {
            'symbol': symbol, 'side': side, 'type': 'MARKET',
            'quantity': self.qty_to_str(symbol, quantity)
        }, signed=True)

        if not result or result.get('status') not in ['FILLED', 'NEW']:
            await self.tg(f"❌ *فشل تنفيذ {side} (`{symbol}`)*\n⚠️ تأكد من إعدادات العقود الآجلة وصلاحيات المفتاح")
            return

        avg = float(result.get('avgPrice') or 0)
        entry_price = avg if avg > 0 else analysis['price']

        trade_data = {
            'symbol': symbol, 'side': side, 'entry_price': entry_price,
            'quantity': quantity, 'sl': analysis['sl'], 'tp': analysis['tp1'],
            'tp2': analysis['tp2'],
            'trailing_active': False, 'highest_price': entry_price,
            'lowest_price': entry_price, 'entry_time': time.time(),
            'partial_closed': False, 'realized_pnl': 0.0,
            'stop_order_id': None, 'tp_order_id': None,
            'stop_synced_price': None, 'tp_skipped': False
        }
        self.active_trades[symbol] = trade_data
        await self.db.save_trade(trade_data)
        self.stats['trades_executed'] += 1
        self.entry_history.append((time.time(), time.strftime("%Y-%m-%d")))
        await self.db.log_signal(symbol, side, trade_data['entry_time'],
                                 analysis['score'], analysis['components'])

        prices = self.get_price(symbol)
        ref_price = (prices['bid'] if side == 'BUY' else prices['ask']) if prices else entry_price
        await self._sync_stop_order(trade_data, ref_price)
        await self.db.save_trade(trade_data)

        msg = (f"✅ *صفقة منفذة!* (تقييم {analysis['score']}/10)\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"🪙 `{symbol}` | رافعة {self.LEVERAGE}x | هامش {self.TRADE_SIZE_USDT:.0f}$\n"
               f"💵 الدخول: {self.fmt_price(entry_price)}\n"
               f"🛑 SL: {self.fmt_price(analysis['sl'])}\n"
               f"🎯 TP1: {self.fmt_price(analysis['tp1'])} | TP2: {self.fmt_price(analysis['tp2'])}\n"
               f"🛡️ ستوب المنصة: {'✅' if trade_data['stop_order_id'] else '⏳'}\n"
               f"🧠 {self.tuner.describe()}")
        await self.tg(msg)

    # ═══ مزامنة الستوب: وضع الجديد أولاً ثم حذف القديم (لا فجوة حماية أبداً) ═══
    async def _sync_stop_order(self, trade, current_price):
        symbol = trade['symbol']
        is_buy = trade['side'] == 'BUY'
        desired = trade['sl']
        if desired is None: return False

        if current_price and ((is_buy and desired >= current_price) or (not is_buy and desired <= current_price)):
            return False

        desired_str = self.price_to_str(symbol, desired)
        if trade.get('stop_order_id') and trade.get('stop_synced_price') is not None:
            if self.price_to_str(symbol, trade['stop_synced_price']) == desired_str:
                return False

        stop_side = 'SELL' if is_buy else 'BUY'
        res = await self._fapi_request('POST', '/fapi/v1/order', {
            'symbol': symbol, 'side': stop_side, 'type': 'STOP_MARKET',
            'stopPrice': desired_str, 'closePosition': 'true'
        }, signed=True)

        if res and res.get('orderId'):
            old_id = trade.get('stop_order_id')          # ✅ الجديد حي الآن — احذف القديم بأمان
            if old_id:
                await self._fapi_request('DELETE', '/fapi/v1/order',
                    {'symbol': symbol, 'orderId': old_id}, signed=True)
            trade['stop_order_id'] = res['orderId']
            trade['stop_synced_price'] = desired
            self._reset_error(f"ستوب المنصة {symbol}")
            return True

        self._notify_error(f"تعذّر وضع ستوب المنصة لـ {symbol}",
                           context="سيُعاد — الوقف المحلي يعمل")
        return False

    # ═══ جني TP2 على المنصة (للكمية المتبقية بعد الجزئي) ═══
    async def _place_tp_order(self, trade, current_price):
        symbol = trade['symbol']
        is_buy = trade['side'] == 'BUY'
        if trade.get('tp_order_id') or trade.get('tp_skipped'):
            return
        tp2 = trade.get('tp2')
        if not tp2: return
        if (is_buy and tp2 <= current_price) or (not is_buy and tp2 >= current_price):
            trade['tp_skipped'] = True   # السعر تجاوز الهدف — الوقف المتحرك كافٍ
            return
        close_side = 'SELL' if is_buy else 'BUY'
        res = await self._fapi_request('POST', '/fapi/v1/order', {
            'symbol': symbol, 'side': close_side, 'type': 'TAKE_PROFIT_MARKET',
            'stopPrice': self.price_to_str(symbol, tp2),
            'quantity': self.qty_to_str(symbol, trade['quantity']),
            'reduceOnly': 'true'
        }, signed=True)
        if res and res.get('orderId'):
            trade['tp_order_id'] = res['orderId']
            await self.tg(f"🎯 *هدف TP2 مثبّت على المنصة* (`{symbol}`) عند {self.fmt_price(tp2)}")
        else:
            trade['tp_skipped'] = True
            self._notify_error(f"تعذر تثبيت TP2 لـ {symbol}",
                               context="الوقف المتحرك سيُدير الخروج بدلاً منه")

    # ═══ استعلامات المنصة ═══
    async def get_position_amt(self, symbol):
        try:
            res = await self._fapi_request('GET', '/fapi/v2/positionRisk',
                {'symbol': symbol}, signed=True)
            if isinstance(res, list) and res:
                return float(res[0].get('positionAmt', 0))
        except Exception as e:
            logger.warning(f"فشل استعلام المركز لـ {symbol}: {e}")
        return None

    async def get_last_realized_pnl(self, symbol, trade):
        try:
            res = await self._fapi_request('GET', '/fapi/v1/income',
                {'symbol': symbol, 'incomeType': 'REALIZED_PNL', 'limit': 20}, signed=True)
            if isinstance(res, list) and res:
                entry_ms = int(trade.get('entry_time', 0) * 1000)
                last = None
                for e in res:
                    if int(e.get('time', 0)) >= entry_ms - 5000:
                        last = e
                        break
                if last is not None:
                    return float(last.get('income', 0))
        except Exception as e:
            logger.warning(f"فشل جلب الأرباح المحققة لـ {symbol}: {e}")
        return None

    async def verify_positions(self):
        if not self.TRADE_ENABLED or not self.binance_api_key:
            return
        if not self.active_trades: return
        for symbol, trade in list(self.active_trades.items()):
            try:
                amt = await self.get_position_amt(symbol)
                if amt is None: continue
                step = self.step_sizes_cache.get(symbol) or 1.0
                if abs(amt) < step:
                    pnl = await self.get_last_realized_pnl(symbol, trade)
                    prices = self.get_price(symbol)
                    px = (prices['bid'] if trade['side'] == 'BUY' else prices['ask']) if prices else trade['entry_price']
                    await self._finalize_trade(trade, px, "🛑 أُغلق على المنصة (Stop-Loss)", pnl)
            except Exception as e:
                self._notify_error(f"فشل التحقق من مركز {symbol}", exc=e)

    # ═══ إغلاق آمن بالكمية الفعلية على المنصة ═══
    async def _close_position(self, trade, current_price):
        symbol = trade['symbol']
        is_buy = trade['side'] == 'BUY'
        close_side = 'SELL' if is_buy else 'BUY'

        amt = await self.get_position_amt(symbol)
        if amt is None:
            self._notify_error(f"تعذر قراءة مركز {symbol}", context="إعادة المحاولة لاحقاً")
            return False, None, None
        step = self.step_sizes_cache.get(symbol) or 1.0
        if abs(amt) < step:   # المركز مأفول أصلاً (الستوب سبقنا)
            pnl = await self.get_last_realized_pnl(symbol, trade)
            return True, current_price, pnl

        qty = self.format_quantity(symbol, min(trade['quantity'], abs(amt)))
        if qty <= 0:
            return True, current_price, await self.get_last_realized_pnl(symbol, trade)

        res = await self._fapi_request('POST', '/fapi/v1/order', {
            'symbol': symbol, 'side': close_side, 'type': 'MARKET',
            'quantity': self.qty_to_str(symbol, qty), 'reduceOnly': 'true'
        }, signed=True)

        if res and res.get('status') in ['FILLED', 'NEW']:
            fill = float(res.get('avgPrice') or 0)
            fill_price = fill if fill > 0 else current_price
            self._reset_error(f"إغلاق {symbol}")
            return True, fill_price, None

        amt2 = await self.get_position_amt(symbol)
        if amt2 is not None and abs(amt2) < step:
            return True, current_price, await self.get_last_realized_pnl(symbol, trade)

        self._notify_error(f"فشل إغلاق {symbol}",
                           context="ستُعاد المحاولة — ستوب المنصة يحمي المركز")
        return False, None, None

    # ═══ إنهاء الصفقة (محاسبة كاملة + تغذية المطوّر التكيفي) ═══
    async def _finalize_trade(self, trade, fill_price, reason, pnl_override=None):
        symbol = trade['symbol']
        is_buy = trade['side'] == 'BUY'

        for oid_key in ('stop_order_id', 'tp_order_id'):
            oid = trade.get(oid_key)
            if oid:
                await self._fapi_request('DELETE', '/fapi/v1/order',
                    {'symbol': symbol, 'orderId': oid}, signed=True)

        if pnl_override is not None:
            final_pnl = pnl_override
        else:
            if is_buy: final_pnl = (fill_price - trade['entry_price']) * trade['quantity']
            else: final_pnl = (trade['entry_price'] - fill_price) * trade['quantity']

        total_pnl = trade.get('realized_pnl', 0.0) + final_pnl
        margin_used = self.TRADE_SIZE_USDT
        margin_pnl_pct = (total_pnl / margin_used * 100) if margin_used > 0 else 0

        is_win = total_pnl > 0
        if is_win: self.stats['wins'] += 1
        else: self.stats['losses'] += 1

        # ✅ تغذية التعلم: نتيجة للمطوّر التكيفي + سجل الإشارات
        self.tuner.record(is_win)
        try:
            await self.db.set_signal_result(symbol, trade['entry_time'], is_win, total_pnl)
        except Exception:
            pass

        await self.db.update_daily_pnl(total_pnl, is_win)
        await self.db.remove_trade(symbol)
        self.active_trades.pop(symbol, None)
        self.set_cooldown(symbol)

        icon = "✅" if is_win else "❌"
        partial_note = (f"\n🧾 جني جزئي سابق: `{trade.get('realized_pnl', 0.0):.4f} USDT`"
                        if abs(trade.get('realized_pnl', 0.0)) > 1e-9 else "")
        score_note = f"\n📊 تقييم الإشارة: `{trade.get('score', '—')}/10`" if trade.get('score') else ""
        msg = (f"🏁 {icon} *إغلاق `{symbol}`*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"{reason}\n"
               f"💵 النتيجة: `{total_pnl:.4f} USDT` ({margin_pnl_pct:.1f}% من الهامش)\n"
               f"🏆 الإجمالي: {self.stats['wins']}W / {self.stats['losses']}L{partial_note}{score_note}\n"
               f"🧠 {self.tuner.describe()}")
        await self.tg(msg)

    # ═══ مراقبة الصفقات (Hit & Run + TP2 على المنصة) ═══
    async def monitor_trades(self):
        if not self.active_trades: return
        stale_symbols = []

        for symbol, trade in list(self.active_trades.items()):
            prices = self.get_price(symbol)
            if not prices:
                stale_symbols.append(symbol)
                continue

            is_buy = trade['side'] == 'BUY'
            current_price = prices['bid'] if is_buy else prices['ask']
            changed = False

            if is_buy and current_price > trade.get('highest_price', 0):
                trade['highest_price'] = current_price; changed = True
            elif not is_buy and current_price < trade.get('lowest_price', 999999):
                trade['lowest_price'] = current_price; changed = True

            # 1) وقف الخسارة
            if (is_buy and current_price <= trade['sl']) or (not is_buy and current_price >= trade['sl']):
                closed, fill_price, pnl_override = await self._close_position(trade, current_price)
                if closed:
                    await self._finalize_trade(trade, fill_price, "🛑 ضرب SL", pnl_override)
                continue

            # 2) جني 90% عند TP1
            if not trade.get('partial_closed', False) and trade.get('tp'):
                if (is_buy and current_price >= trade['tp']) or (not is_buy and current_price <= trade['tp']):
                    partial_qty = self.format_quantity(symbol, trade['quantity'] * 0.9)
                    remaining_qty = self.format_quantity(symbol, trade['quantity'] - partial_qty)
                    min_notional = self.min_notional_cache.get(symbol, 5.0)

                    if (partial_qty <= 0 or remaining_qty <= 0
                            or partial_qty * current_price < min_notional
                            or remaining_qty * current_price < min_notional):
                        closed, fill_price, pnl_override = await self._close_position(trade, current_price)
                        if closed:
                            await self._finalize_trade(trade, fill_price,
                                "🎯 TP1 (إغلاق كامل — حدود الزوج)", pnl_override)
                        continue

                    close_side = 'SELL' if is_buy else 'BUY'
                    res = await self._fapi_request('POST', '/fapi/v1/order', {
                        'symbol': symbol, 'side': close_side, 'type': 'MARKET',
                        'quantity': self.qty_to_str(symbol, partial_qty),
                        'reduceOnly': 'true'
                    }, signed=True)

                    if res and res.get('status') in ['FILLED', 'NEW']:
                        fill = float(res.get('avgPrice') or 0)
                        fill_price = fill if fill > 0 else current_price
                        if is_buy: partial_pnl = (fill_price - trade['entry_price']) * partial_qty
                        else: partial_pnl = (trade['entry_price'] - fill_price) * partial_qty

                        trade['realized_pnl'] = trade.get('realized_pnl', 0.0) + partial_pnl
                        await self.db.update_daily_pnl(partial_pnl, None)
                        trade['quantity'] = remaining_qty
                        trade['partial_closed'] = True
                        trade['sl'] = trade['entry_price'] * 1.003 if is_buy else trade['entry_price'] * 0.997
                        changed = True
                        await self.tg(f"🎯 *جني أرباح أول (`{symbol}`)*\n"
                                      f"💸 أُغلق 90% بربح: `{partial_pnl:.4f} USDT`\n"
                                      f"🛡️ الوقف على التعادل (+0.3%)")
                        # ✅ ثبّت TP2 للكمية المتبقية على المنصة (ينجو من انهيار البوت)
                        await self._place_tp_order(trade, current_price)
                        changed = True
                    else:
                        amt = await self.get_position_amt(symbol)
                        if amt is not None and abs(amt) < (self.step_sizes_cache.get(symbol) or 1.0):
                            pnl = await self.get_last_realized_pnl(symbol, trade)
                            await self._finalize_trade(trade, current_price, "🛑 أُغلق على المنصة (Stop)", pnl)
                            continue
                        self._notify_error(f"فشل الجني الجزئي لـ {symbol}",
                                           context="إعادة المحاولة في الدورة القادمة")

            # 3) الوقف المتحرك (بعد الجزئي)
            if trade.get('partial_closed'):
                if is_buy:
                    new_sl = trade['highest_price'] * 0.99
                    if new_sl > trade['sl']:
                        trade['sl'] = new_sl; changed = True
                else:
                    new_sl = trade['lowest_price'] * 1.01
                    if new_sl < trade['sl']:
                        trade['sl'] = new_sl; changed = True

            # 4) مزامنة ستوب المنصة
            if await self._sync_stop_order(trade, current_price):
                changed = True

            if changed:
                await self.db.save_trade(trade)

        if stale_symbols:
            self._notify_error("أسعار مجمّدة لمراكز مفتوحة",
                               context=f"{', '.join(stale_symbols)} — ستوب المنصة يحميها")

    # ═══ المسح الديناميكي (مع منع تكرار التنبيهات) ═══
    async def scan_volatile_coins(self):
        tickers = await self._fapi_request('GET', '/fapi/v1/ticker/24hr')
        if not tickers:
            self._notify_error("فشل جلب بيانات تقلب السوق", context="مشكلة اتصال مؤقتة")
            return
        self._reset_error("فشل جلب بيانات تقلب السوق")

        targets = []
        for t in tickers:
            symbol = t.get('symbol', '')
            try:
                change = abs(float(t.get('priceChangePercent', 0)))
            except (TypeError, ValueError):
                continue
            if change > 5 and symbol in self.step_sizes_cache:
                targets.append({'symbol': symbol, 'change': change})
        targets.sort(key=lambda x: x['change'], reverse=True)

        results = []
        for target in targets[:20]:
            symbol = target['symbol']
            if symbol in self.active_trades: continue
            if self.is_in_cooldown(symbol): continue
            analysis = await self.analyze_whale_zone(symbol)
            if analysis:
                results.append(analysis)
            await asyncio.sleep(0.5)

        # ✅ تنبيه فريد لكل زوج/اتجاه كل 30 دقيقة كحد أقصى
        fresh_lines = []
        now = time.time()
        for a in results:
            key = (a['symbol'], a['direction'])
            if now - self.last_discovery_alert.get(key, 0) < 1800:
                continue
            self.last_discovery_alert[key] = now
            fresh_lines.append(f"🐋 `{a['symbol']}` *{a['direction']}* @ {self.fmt_price(a['price'])}"
                               f" (تقييم {a['score']}/10)")

        if fresh_lines:
            await self.tg("🚀 *إشارات جديدة!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n" + "\n".join(fresh_lines))

        for a in results:
            await self.execute_trade(a)
            await asyncio.sleep(1)

    # ═══ المطوّر التكيفي: حارس التردد + حارس الفوز ═══
    def _trades_today(self):
        today = time.strftime("%Y-%m-%d")
        return sum(1 for _, d in self.entry_history if d == today)

    def _frequency_guard(self):
        now = time.time()
        if now - self._last_freq_check < 3600:
            return
        self._last_freq_check = now

        # ارتخاء تدريجي عند الجمود (هدف النشاط 3-5 صفقات/يوم)
        last_ts = self.entry_history[-1][0] if self.entry_history else 0
        hours_since = (now - last_ts) / 3600 if last_ts else 999
        if hours_since >= 10 and self._trades_today() < 3:
            if self.tuner.relax_step():
                logger.info("🧠 ارتخاء تكيفي بسبب قلة النشاط")
                asyncio.get_running_loop().create_task(self.tuner.save())
                asyncio.get_running_loop().create_task(self.tg(
                    f"🧠 *المطوّر التكيفي:* رفع النشاط تلقائياً\n{self.tuner.describe()}"))

        # تشديد عند تدهور الفوز
        wr = self.tuner.recent_winrate(10)
        if wr is not None and wr < 0.38 and now - self._last_tighten > 6 * 3600:
            self._last_tighten = now
            if self.tuner.tighten_step():
                logger.info("🧠 تشديد تكيفي بسبب تدهور نسبة الفوز")
                asyncio.get_running_loop().create_task(self.tuner.save())
                asyncio.get_running_loop().create_task(self.tg(
                    f"🧠 *المطوّر التكيفي:* تشديد الجودة (فوز آخر 10 = {wr*100:.0f}%)\n{self.tuner.describe()}"))

    # ═══ الصيانة الذاتية ═══
    def _cleanup_memory(self):
        now = time.time()
        self.reentry_cooldown = {k: v for k, v in self.reentry_cooldown.items() if v > now}
        self.last_discovery_alert = {k: v for k, v in self.last_discovery_alert.items()
                                     if v > now - 7200}
        if len(self.error_counts) > 500:
            self.error_counts.clear()

    async def _send_daily_report(self, day):
        row = await self.db.get_day_stats(day)
        if not row: return
        pnl, w, l = row
        wr = (w / (w + l) * 100) if (w + l) > 0 else 0
        await self.tg(f"📊 *تقرير {day}*\n💰 PnL: `{pnl:.4f} USDT`\n"
                      f"🏆 {w}W / {l}L (فوز {wr:.0f}%)\n🧠 {self.tuner.describe()}")

    async def _heartbeat_and_report(self, loop_count):
        now = time.time()
        today = time.strftime("%Y-%m-%d")
        if today != self._report_day:
            await self._send_daily_report(self._report_day)
            self._report_day = today
        if now - self._last_heartbeat >= 3600:
            self._last_heartbeat = now
            wr = self.tuner.recent_winrate(10)
            wr_txt = f"{wr*100:.0f}%" if wr is not None else "غير كافٍ بعد"
            await self.tg(f"💓 *النبض:* حي ✓ | مسح #{loop_count} | "
                          f"صفقات اليوم: {self._trades_today()} | فوز آخر 10: {wr_txt}\n"
                          f"🧠 {self.tuner.describe()}")

    # ═══ المصالحة الذاتية عند الإقلاع (شفاء ذاتي) ═══
    async def reconcile(self):
        if not self.binance_api_key or not self.TRADE_ENABLED:
            return
        try:
            positions = await self._fapi_request('GET', '/fapi/v2/positionRisk', signed=True)
            open_pos = {}
            if isinstance(positions, list):
                for p in positions:
                    try:
                        amt = float(p.get('positionAmt', 0))
                    except (TypeError, ValueError):
                        continue
                    if abs(amt) > 0:
                        open_pos[p['symbol']] = {'amt': amt, 'entry': float(p.get('entryPrice', 0))}

            # 1) صفقة في القاعدة بلا مركز على المنصة → أُغلقت أثناء التوقف
            for symbol, trade in list(self.active_trades.items()):
                pos = open_pos.get(symbol)
                step = self.step_sizes_cache.get(symbol) or 1.0
                if not pos or abs(pos['amt']) < step:
                    pnl = await self.get_last_realized_pnl(symbol, trade)
                    await self._finalize_trade(trade, trade['entry_price'],
                                               "🔄 أُغلق أثناء توقف البوت", pnl)

            # 2) مركز على المنصة بلا صفقة في القاعدة → تبنّيه بوقف ATR
            for symbol, pos in open_pos.items():
                if symbol in self.active_trades:
                    continue
                df = await self.get_klines(symbol, '15m', 50)
                atr = self._compute_atr(df) if df is not None else None
                if not atr or atr <= 0 or math.isnan(atr):
                    atr = pos['entry'] * 0.01
                side = 'BUY' if pos['amt'] > 0 else 'SELL'
                entry = pos['entry'] or (self.live_prices.get(symbol, {}).get('bid', 0))
                if side == 'BUY':
                    sl, tp1, tp2 = entry - 2*atr, entry + 1.5*atr, entry + 4*atr
                else:
                    sl, tp1, tp2 = entry + 2*atr, entry - 1.5*atr, entry - 4*atr
                trade = {
                    'symbol': symbol, 'side': side, 'entry_price': entry,
                    'quantity': abs(pos['amt']), 'sl': sl, 'tp': tp1, 'tp2': tp2,
                    'trailing_active': False, 'highest_price': entry, 'lowest_price': entry,
                    'entry_time': time.time(), 'partial_closed': False,
                    'realized_pnl': 0.0, 'stop_order_id': None, 'tp_order_id': None,
                    'stop_synced_price': None, 'tp_skipped': False
                }
                self.active_trades[symbol] = trade
                await self.db.save_trade(trade)
                await self._sync_stop_order(trade, entry)
                await self.db.save_trade(trade)
                await self.tg(f"🔄 *تم تبنّي مركز يتيم* (`{symbol}`)\n"
                              f"وقف ATR تلقائي عند {self.fmt_price(sl)}")

            # 3) إلغاء أوامر يتيمة (ستوب/TP لا تطابق أي صفقة حية)
            orders = await self._fapi_request('GET', '/fapi/v1/openOrders', signed=True)
            known_ids = set()
            for t in self.active_trades.values():
                if t.get('stop_order_id'): known_ids.add(t['stop_order_id'])
                if t.get('tp_order_id'): known_ids.add(t['tp_order_id'])
            cancelled = 0
            for o in orders or []:
                if o.get('orderId') not in known_ids and o.get('type') in ('STOP_MARKET', 'TAKE_PROFIT_MARKET'):
                    await self._fapi_request('DELETE', '/fapi/v1/order',
                        {'symbol': o['symbol'], 'orderId': o['orderId']}, signed=True)
                    cancelled += 1
            if cancelled:
                await self.tg(f"🧹 *تنظيف ذاتي:* أُلغي {cancelled} أمر يتيم على المنصة")
            logger.info(f"🧾 المصالحة الذاتية: {len(open_pos)} مركز حي، {cancelled} أمر يتيم ملغى")
        except Exception as e:
            self._notify_error("فشل المصالحة الذاتية", exc=e, context="غير قاتل — تُعاد كل دورات")

    # ═══ إيقاف آمن ═══
    async def request_shutdown(self):
        if self._shutdown_requested: return
        self._shutdown_requested = True
        logger.info("🛑 طلب إيقاف آمن...")
        try:
            await self.tg("🛑 *إيقاف آمن:* ستوب/أوامر TP على المنصة تبقى فعالة وتحمي المراكز.")
        except Exception:
            pass

    # ═══ اللوب الرئيسي ═══
    async def main_loop(self):
        self.session = aiohttp.ClientSession()
        try:
            loop = asyncio.get_running_loop()
            for sig_name in ('SIGINT', 'SIGTERM'):
                try:
                    loop.add_signal_handler(getattr(signal, sig_name),
                        lambda: asyncio.ensure_future(self.request_shutdown()))
                except (NotImplementedError, ValueError, AttributeError, RuntimeError):
                    pass

            await self.db.init_db()
            await self.tuner.load()

            market_tries = 0
            while not self.all_futures_pairs:
                market_tries += 1
                await self.load_market_data()
                if self.all_futures_pairs: break
                if market_tries == 1 or market_tries % 5 == 0:
                    await self.tg(f"❌ *فشل تحميل بيانات السوق* (محاولة {market_tries})\n"
                                  f"⏳ إعادة خلال 30 ثانية...")
                logger.error(f"فشل تحميل بيانات السوق (محاولة {market_tries})")
                await asyncio.sleep(30)

            self.active_trades = await self.db.load_active_trades()
            await self.sync_server_time()

            try:
                dual = await self._fapi_request('GET', '/fapi/v1/positionSide/dual', signed=True)
                if dual and dual.get('dualSidePosition'):
                    if self.TRADE_ENABLED:
                        self.TRADE_ENABLED = False
                        logger.error("❌ الحساب في وضع Hedge Mode — التحويل للمراقبة فقط")
                        await self.tg("⚠️ *تنبيه:* Hedge Mode مفعّل — البوت لوضع One-way فقط. تم التحويل للمراقبة.")
            except Exception as e:
                logger.warning(f"تعذر فحص Hedge Mode: {e}")

            if self.TRADE_ENABLED and self.binance_api_key:
                await self.setup_futures_account()

            self.ws_task = asyncio.create_task(self.ws_manager())
            await asyncio.sleep(10)

            if self.TRADE_ENABLED and self.binance_api_key:
                await self.reconcile()
                await self.verify_positions()

            mode_trade = "⚔️ تداول تلقائي" + (" (TESTNET 🧪)" if self.TESTNET else "") \
                         if self.TRADE_ENABLED else "👁️ مراقبة فقط"
            msg = ("🔥 *القناص الأسطوري V8.0 — الذكي التكيفي!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                   f"📡 الوضع: {mode_trade} | رافعة {self.LEVERAGE}x | هامش {self.TRADE_SIZE_USDT:.0f}$\n"
                   f"🧠 المطوّر التكيفي: {self.tuner.describe()}\n"
                   "🎯 دخول: تقييم مرن (Sweep=3 / Retest=2 / ستوك / حجم / قرب OB)\n"
                   "🛡️ ستوب مزدوج + TP2 مثبّت على المنصة + مصالحة ذاتية + تقرير يومي\n"
                   "━━━━━━━━━━━━━━━━━━━━━━━━\n⏰ بدء المسح...")
            await self.tg(msg)

            loop_count = 0
            while not self._shutdown_requested:
                try:
                    newest_ts = max((p.get('ts', 0) for p in self.live_prices.values()), default=0)
                    if newest_ts and (time.time() - newest_ts) > self.WS_STALE_ALERT:
                        self._notify_error("توقف تدفق الأسعار (WebSocket)",
                            context=f"لا تحديثات منذ {int(time.time() - newest_ts)} ثانية — ستوب المنصة يحمي المراكز")

                    await self.monitor_trades()
                    await self.scan_volatile_coins()

                    loop_count += 1
                    self.stats['total_scans'] = loop_count
                    if loop_count % self.VERIFY_EVERY_N_LOOPS == 0:
                        await self.verify_positions()

                    self._frequency_guard()
                    self._cleanup_memory()
                    await self._heartbeat_and_report(loop_count)
                    await asyncio.sleep(60)
                except asyncio.CancelledError:
                    raise
                except Exception as loop_err:
                    logger.error(f"خطأ في الحلقة: {loop_err}")
                    self._notify_error("خطأ في الحلقة الرئيسية", exc=loop_err)
                    await asyncio.sleep(15)
        finally:
            if self.ws_task:
                self.ws_task.cancel()
            if self.session and not self.session.closed:
                await self.session.close()

    def start(self):
        asyncio.run(self.main_loop())

if __name__ == "__main__":
    bot = LegendarySniperFuturesV8()
    bot.start()
