"""
═══════════════════════════════════════════════════════════════════════
  🔥 القناص الأسطوري V6.2 — Legendary Sniper (Strict Capital Protection) 🔥
═══════════════════════════════════════════════════════════════════════
  تحديثات V6.2:
  ✅ فلتر HTF صارم: رفض قاطع لأي صفقة تعاكس فريم الساعة (حماية رأس المال)
  ✅ Pre-filter صارم: سيولة عالية فقط (500K$ حجم، 200+ صفقة، أفضل 80 عملة)
  ✅ تثبيت MIN_SCORE_TO_TRADE = 7 كحد أدنى إجباري
  ✅保留了 V6.1 Fixes: تنسيق الأسعار، DexScreener، معالجة Testnet
═══════════════════════════════════════════════════════════════════════
"""

import asyncio, aiohttp, json, math, os, sys, time, logging, requests, sqlite3
import pandas as pd
import numpy as np
import ta
import hmac
import hashlib
from urllib.parse import urlencode
from logging.handlers import RotatingFileHandler
from datetime import datetime
from zoneinfo import ZoneInfo
import websockets
import aiosqlite

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

logger = logging.getLogger('SniperBotV6')
logger.setLevel(logging.INFO)
fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh = RotatingFileHandler('bot_v6.log', maxBytes=2*1024*1024, backupCount=1, encoding='utf-8')
fh.setFormatter(fmt); logger.addHandler(fh)
ch = logging.StreamHandler(); ch.setFormatter(fmt); logger.addHandler(ch)

class TelegramLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            if record.levelno >= logging.ERROR:
                tok = os.environ.get('TELEGRAM_TOKEN', '')
                cid = os.environ.get('CHAT_ID', '')
                if tok and cid:
                    msg_text = f"🚨 *خطأ:*\n```\n{self.format(record)[:400]}\n```"
                    url = f"https://api.telegram.org/bot{tok}/sendMessage"
                    requests.post(url, data={'chat_id': cid, 'text': msg_text,
                                  'parse_mode': 'Markdown'}, timeout=5)
        except Exception:
            pass

tg_handler = TelegramLoggingHandler()
tg_handler.setLevel(logging.ERROR)
logger.addHandler(tg_handler)


# ═══════════════════════ متتبع وزن API ═══════════════════════
class WeightTracker:
    def __init__(self, max_per_minute=2400):
        self.max_weight = max_per_minute
        self.window = []

    def _cleanup(self):
        cutoff = time.time() - 60
        self.window = [(t, w) for t, w in self.window if t > cutoff]

    @property
    def current(self):
        self._cleanup()
        return sum(w for _, w in self.window)

    @property
    def remaining(self):
        return self.max_weight - self.current

    def can_request(self, weight):
        return self.current + weight <= self.max_weight

    async def wait_for_capacity(self, weight):
        waited = 0
        while not self.can_request(weight):
            await asyncio.sleep(1)
            waited += 1
            if waited > 65:
                self._cleanup()
                break
        self.window.append((time.time(), weight))

    def update_from_headers(self, headers):
        try:
            used = headers.get('X-MBX-USED-WEIGHT-1M')
            if used:
                actual = int(used)
                if actual > self.current:
                    diff = actual - self.current
                    self.window.append((time.time(), diff))
        except Exception:
            pass


# ═══════════════════════ قاعدة البيانات ═══════════════════════
class DatabaseManager:
    def __init__(self, db_name='sniper_v6.db'):
        self.db_name = db_name

    async def init_db(self):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS active_trades (
                symbol TEXT PRIMARY KEY, side TEXT, entry_price REAL, quantity REAL,
                sl REAL, tp REAL, trailing_active INTEGER, highest_price REAL,
                lowest_price REAL, entry_time REAL, score INTEGER)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY, realized_pnl REAL, wins INTEGER, losses INTEGER)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS seen_announcements (
                article_id TEXT PRIMARY KEY, title TEXT, seen_time REAL)''')
            await db.commit()

    async def save_trade(self, t):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''INSERT OR REPLACE INTO active_trades VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (t['symbol'], t['side'], t['entry_price'], t['quantity'],
                 t['sl'], t['tp'], int(t['trailing_active']),
                 t.get('highest_price', 0), t.get('lowest_price', 999999),
                 t['entry_time'], t['score']))
            await db.commit()

    async def load_active_trades(self):
        trades = {}
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT * FROM active_trades") as cur:
                async for row in cur:
                    trades[row[0]] = {
                        'symbol': row[0], 'side': row[1], 'entry_price': row[2],
                        'quantity': row[3], 'sl': row[4], 'tp': row[5],
                        'trailing_active': bool(row[6]), 'highest_price': row[7],
                        'lowest_price': row[8], 'entry_time': row[9], 'score': row[10]
                    }
        return trades

    async def remove_trade(self, symbol):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("DELETE FROM active_trades WHERE symbol=?", (symbol,))
            await db.commit()

    async def update_daily_pnl(self, pnl, is_win):
        today = time.strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT * FROM daily_stats WHERE date=?", (today,)) as cur:
                row = await cur.fetchone()
            if row:
                await db.execute("UPDATE daily_stats SET realized_pnl=?, wins=?, losses=? WHERE date=?",
                    (row[1]+pnl, row[2]+(1 if is_win else 0), row[3]+(0 if is_win else 1), today))
            else:
                await db.execute("INSERT INTO daily_stats VALUES (?,?,?,?)",
                    (today, pnl, 1 if is_win else 0, 0 if is_win else 1))
            await db.commit()

    async def get_daily_pnl(self):
        today = time.strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT realized_pnl FROM daily_stats WHERE date=?", (today,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else 0.0

    async def get_seen_announcements(self):
        ids = set()
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT article_id FROM seen_announcements") as cur:
                async for row in cur:
                    ids.add(row[0])
        return ids

    async def add_seen_announcement(self, article_id, title):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("INSERT OR IGNORE INTO seen_announcements VALUES (?,?,?)",
                (article_id, title, time.time()))
            await db.commit()

    async def cleanup_old_announcements(self, max_age_hours=48):
        cutoff = time.time() - (max_age_hours * 3600)
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("DELETE FROM seen_announcements WHERE seen_time < ?", (cutoff,))
            await db.commit()


# ═══════════════════════ محرك SMC ═══════════════════════
class SMCEngine:
    @staticmethod
    def detect_swings(df, window=3):
        df = df.copy()
        df.loc[:, 'sw_high'] = np.nan
        df.loc[:, 'sw_low'] = np.nan
        highs, lows = df['high'].values, df['low'].values
        for i in range(window, len(df) - window):
            if all(highs[i] >= highs[i-window:i]) and all(highs[i] >= highs[i+1:i+window+1]):
                df.loc[df.index[i], 'sw_high'] = highs[i]
            if all(lows[i] <= lows[i-window:i]) and all(lows[i] <= lows[i+1:i+window+1]):
                df.loc[df.index[i], 'sw_low'] = lows[i]
        return df

    @staticmethod
    def detect_bos_choch(df):
        signals, trend = [], None
        last_sw_high, last_sw_low = np.nan, np.nan
        closes = df['close'].values
        sw_highs, sw_lows = df['sw_high'].values, df['sw_low'].values
        for i in range(len(df)):
            if not pd.isna(sw_highs[i]): last_sw_high = sw_highs[i]
            if not pd.isna(sw_lows[i]): last_sw_low = sw_lows[i]
            if not pd.isna(last_sw_high) and not pd.isna(last_sw_low):
                if closes[i] > last_sw_high:
                    sig_type = 'CHoCH_Bull' if trend == 'bear' else 'BOS_Bull'
                    signals.append({'index': i, 'type': sig_type})
                    trend = 'bull'
                elif closes[i] < last_sw_low:
                    sig_type = 'CHoCH_Bear' if trend == 'bull' else 'BOS_Bear'
                    signals.append({'index': i, 'type': sig_type})
                    trend = 'bear'
        return signals, trend

    @staticmethod
    def detect_fvg(df):
        fvgs = []
        lows, highs = df['low'].values, df['high'].values
        for i in range(2, len(df)):
            if lows[i] > highs[i-2]:
                fvgs.append({'type': 'bull_fvg', 'top': lows[i], 'bottom': highs[i-2]})
            elif highs[i] < lows[i-2]:
                fvgs.append({'type': 'bear_fvg', 'top': lows[i-2], 'bottom': highs[i]})
        return fvgs

    @staticmethod
    def detect_order_blocks(df, signals, trend):
        obs = []
        opens, closes = df['open'].values, df['close'].values
        highs, lows = df['high'].values, df['low'].values
        for sig in signals:
            is_bull = sig['type'] in ['BOS_Bull', 'CHoCH_Bull']
            if (is_bull and trend == 'bull') or (not is_bull and trend == 'bear'):
                for j in range(sig['index'], max(sig['index']-10, 0), -1):
                    if is_bull and closes[j] < opens[j]:
                        obs.append({'type': 'bull_ob', 'top': opens[j], 'bottom': lows[j]}); break
                    elif not is_bull and closes[j] > opens[j]:
                        obs.append({'type': 'bear_ob', 'top': highs[j], 'bottom': opens[j]}); break
        return obs


# ═══════════════════════ إدارة المخاطر ═══════════════════════
class RiskManager:
    def __init__(self, bot):
        self.bot = bot
        self.MAX_DRAWDOWN_PCT = 5.0

    async def check_daily_drawdown(self):
        daily_pnl = await self.bot.db.get_daily_pnl()
        balance = await self.bot.get_usdt_balance()
        if balance > 0 and daily_pnl < 0:
            if abs(daily_pnl) / balance * 100 >= self.MAX_DRAWDOWN_PCT:
                return False
        return True

    def check_spread(self, symbol, ask, bid):
        if not ask or not bid or bid == 0: return False
        return ((ask - bid) / bid) * 100 <= 0.1


# ══════════════════════════════════════════════════════════════════════
#                  🔥 القناص الأسطوري V6.2 🔥
# ══════════════════════════════════════════════════════════════════════
class LegendarySniperBotV6:
    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN', '')
        self.tg_chat = os.environ.get('CHAT_ID', '')
        self.binance_api_key = os.environ.get('BINANCE_API_KEY', '')
        self.binance_api_secret = os.environ.get('BINANCE_API_SECRET', '')

        self.TRADE_ENABLED = os.environ.get('TRADE_ENABLED', 'false').lower() == 'true'
        self.RISK_PER_TRADE_PCT = float(os.environ.get('RISK_PCT', '1.5'))
        self.STOP_LOSS_PCT = float(os.environ.get('SL_PCT', '3'))
        self.TAKE_PROFIT_PCT = float(os.environ.get('TP_PCT', '6'))
        
        # ═══ تعديل 3: تثبيت النقاط كحد أدنى لحماية رأس المال ═══
        self.MIN_SCORE_TO_TRADE = 7  # مقفل على 7 كحد أدنى إجباري لحماية رأس المال
        
        self.MAX_OPEN_TRADES = int(os.environ.get('MAX_TRADES', '3'))
        self.MIN_TRADE_USDT = float(os.environ.get('MIN_TRADE_USDT', '10'))

        self.db = DatabaseManager()
        self.risk = RiskManager(self)
        self.smc = SMCEngine()
        self.weight_tracker = WeightTracker(max_per_minute=2400)
        self.session = None

        self.mode = os.environ.get('BINANCE_MODE', 'real').lower()
        self.data_url = "https://api.binance.com"
        self.trade_url = "https://api.binance.com"
        self._testnet_failed = False

        if self.mode == 'test':
            self.data_url = "https://testnet.binance.vision"
            self.trade_url = "https://testnet.binance.vision"
        else:
            self.data_url = "https://api.binance.com"
            self.trade_url = "https://api.binance.com"

        self.all_usdt_pairs = []
        self.known_symbols = set()
        self.step_sizes_cache = {}
        self.live_prices = {}
        self.live_klines = {}

        self.priority_coins = [
            'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA', 'AVAX',
            'DOT', 'LINK', 'UNI', 'ATOM', 'LTC', 'NEAR', 'APT',
            'ARB', 'OP', 'SUI', 'SEI', 'TIA', 'INJ', 'FET',
            'WLD', 'PEPE', 'SHIB', 'TRX', 'TON', 'FIL', 'AAVE', 'MATIC'
        ]

        self.hot_coins = set()
        self.volume_spikes = []

        self.analysis_cache = {}
        self.CACHE_TTL = 300

        self.timers = {
            'announcement': 0, 'coingecko': 0, 'dexscreener': 0,
            'fear_greed': 0, 'full_scan': 0, 'volume_spike': 0,
            'quick_scan': 0, 'hot_scan': 0, 'reload_market': 0,
            'sync': 0,
        }

        self.stats = {
            'total_scans': 0, 'signals_found': 0,
            'trades_executed': 0, 'wins': 0, 'losses': 0
        }

        self.TZ = ZoneInfo("Africa/Tripoli")

    # ═════════════════════ تنسيق ذكي ═════════════════════
    def fmt_price(self, price):
        if price is None or price == 0: return "$0"
        if price < 0.00001: return f"${price:.10f}"
        elif price < 0.0001: return f"${price:.8f}"
        elif price < 0.001: return f"${price:.6f}"
        elif price < 0.01: return f"${price:.5f}"
        elif price < 1: return f"${price:.4f}"
        elif price < 100: return f"${price:.2f}"
        elif price < 10000: return f"${price:.1f}"
        else: return f"${price:,.0f}"

    def fmt_pct(self, pct):
        if pct is None: return "0.0%"
        if pct > 0: return f"+{pct:.1f}%"
        elif pct < 0: return f"{pct:.1f}%"
        else: return "0.0%"

    # ═════════════════════ تيليجرام ═════════════════════
    async def tg(self, msg):
        try:
            if not self.session or not self.tg_token: return
            if len(msg) > 4000:
                for i in range(0, len(msg), 4000):
                    await self.session.post(
                        f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                        data={'chat_id': self.tg_chat, 'text': msg[i:i+4000],
                              'parse_mode': 'Markdown'}, timeout=10)
                    await asyncio.sleep(0.5)
            else:
                await self.session.post(
                    f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                    data={'chat_id': self.tg_chat, 'text': msg,
                          'parse_mode': 'Markdown'}, timeout=10)
        except Exception:
            pass

    # ═════════════════════ بينانس API (محصّن) ═════════════════════
    async def _switch_to_real(self):
        if not self._testnet_failed:
            self._testnet_failed = True
            self.data_url = "https://api.binance.com"
            self.trade_url = "https://api.binance.com"
            logger.warning("⚠️ Testnet غير متاح! تم التحول للسيرفر الحقيقي — التداول يعمل بمفاتيح API الحقيقية")
            await self.tg("⚠️ *Testnet غير متاح!*\nتم التحول للسيرفر الحقيقي\n📝 التداول فعّال — تأكد أن مفاتيح API حقيقية!")

    async def _binance_request(self, method, endpoint, params=None,
                               signed=False, is_trade_endpoint=False,
                               weight=2, retries=3):
        await self.weight_tracker.wait_for_capacity(weight)

        for attempt in range(retries):
            try:
                base = self.trade_url if is_trade_endpoint else self.data_url
                url = f"{base}{endpoint}"
                headers = {}
                req_params = params.copy() if params else {}

                if signed:
                    if not self.binance_api_key: return None
                    await asyncio.sleep(0.05)
                    req_params = self._sign(req_params)
                    headers = {'X-MBX-APIKEY': self.binance_api_key}

                async with self.session.request(method, url, params=req_params,
                                                 headers=headers, timeout=15) as r:
                    self.weight_tracker.update_from_headers(r.headers)

                    if r.status == 200:
                        return await r.json()
                    elif r.status == 429:
                        wait = 10 * (attempt + 1)
                        logger.warning(f"⏳ Rate limited! انتظار {wait}s")
                        await asyncio.sleep(wait)
                    elif r.status in [500, 502, 503]:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        return None

            except (aiohttp.ClientConnectorError, aiohttp.ClientSSLError) as e:
                err_str = str(e)
                if 'testnet' in err_str.lower() or 'name or service not known' in err_str.lower():
                    if self.mode == 'test' and not self._testnet_failed:
                        await self._switch_to_real()
                        continue

                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.warning(f"خطأ اتصال بينانس: {err_str[:100]}")
                    return None

            except asyncio.TimeoutError:
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.warning("انتهت مهلة طلب بينانس")
                    return None

            except Exception as e:
                err_str = str(e)
                if 'testnet' in err_str.lower():
                    if self.mode == 'test' and not self._testnet_failed:
                        await self._switch_to_real()
                        continue
                logger.warning(f"طلب بينانس خطأ: {err_str[:100]}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return None
        return None

    def _sign(self, params):
        params['timestamp'] = int(time.time() * 1000)
        query = urlencode(params)
        params['signature'] = hmac.new(
            self.binance_api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        return params

    async def get_usdt_balance(self):
        data = await self._binance_request('GET', '/api/v3/account',
                                            signed=True, is_trade_endpoint=True, weight=10)
        if data:
            for b in data.get('balances', []):
                if b['asset'] == 'USDT': return float(b['free'])
        return 0.0

    # ═════════════════════ تحميل بيانات السوق ═════════════════════
    async def load_market_data(self):
        data = await self._binance_request('GET', '/api/v3/exchangeInfo', weight=10)
        if not data: return

        new_pairs = []
        new_symbols = set()

        for s in data.get('symbols', []):
            if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING':
                new_pairs.append({
                    'symbol': s['symbol'],
                    'baseAsset': s['baseAsset'],
                    'status': s['status']
                })
                new_symbols.add(s['symbol'])
                for f in s.get('filters', []):
                    if f['filterType'] == 'LOT_SIZE':
                        self.step_sizes_cache[s['symbol']] = float(f['stepSize'])

        if self.known_symbols:
            newly_listed = new_symbols - self.known_symbols
            if newly_listed:
                msg = "🆕 *عملات مدرجة حديثاً على بينانس!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                for sym in list(newly_listed)[:10]:
                    msg += f"⚡ `{sym}` — تم الإدراج للتو!\n"
                    base = sym.replace('USDT', '')
                    self.hot_coins.add(base)
                msg += "\n🔥 عادة ترتفع العملات الجديدة بنسبة كبيرة!"
                await self.tg(msg)

        self.all_usdt_pairs = new_pairs
        self.known_symbols = new_symbols
        logger.info(f"📊 تم تحميل {len(self.all_usdt_pairs)} زوج USDT و {len(self.step_sizes_cache)} حجم خطوة")

    def format_quantity(self, symbol, qty):
        step = self.step_sizes_cache.get(symbol, 1.0)
        precision = int(round(-math.log10(step))) if step < 1 else 0
        return math.floor(qty * (10 ** precision)) / (10 ** precision)

    # ═════════════════════ WebSocket + REST ═════════════════════
    async def ws_manager(self):
        streams = []
        for coin in self.priority_coins:
            sym = f"{coin.lower()}usdt"
            streams.append(f"{sym}@bookTicker")
            streams.append(f"{sym}@kline_15m")

        if self.mode == 'test' and not self._testnet_failed:
    ws_url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"
else:
    ws_url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"
        else:
            ws_url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"

        while True:
            try:
                async with websockets.connect(ws_url, ping_interval=20) as ws:
                    logger.info("✅ WebSocket متصل!")
                    async for message in ws:
                        data = json.loads(message).get('data', {})
                        if not data: continue
                        event = data.get('e')

                        if event == 'bookTicker':
                            self.live_prices[data['s']] = {
                                'bid': float(data['b']), 'ask': float(data['a'])
                            }
                        elif event == 'kline':
                            symbol = data['s']
                            k = data['k']
                            if symbol not in self.live_klines:
                                self.live_klines[symbol] = []
                            if k['x']:
                                self.live_klines[symbol].append({
                                    'time': k['t'], 'open': float(k['o']),
                                    'high': float(k['h']), 'low': float(k['l']),
                                    'close': float(k['c']), 'volume': float(k['v']),
                                    'taker_buy_vol': float(k['V'])
                                })
                                self.live_klines[symbol] = self.live_klines[symbol][-100:]
            except Exception as e:
                err_str = str(e)
                logger.error(f"❌ خطأ WebSocket: {err_str[:100]}")
                if "404" in err_str or "403" in err_str or "rejected" in err_str:
                    await self.rest_poller()
                    break
                await asyncio.sleep(5)

    async def rest_poller(self):
        logger.info("🔄 سحب الأسعار عبر REST كل 30 ثانية...")
        while True:
            try:
                for coin in self.priority_coins:
                    symbol = f"{coin}USDT"
                    ticker = await self._binance_request('GET', '/api/v3/ticker/bookTicker',
                                                         {'symbol': symbol}, weight=2)
                    if ticker:
                        self.live_prices[symbol] = {
                            'bid': float(ticker['bidPrice']),
                            'ask': float(ticker['askPrice'])
                        }
                    klines_data = await self._binance_request('GET', '/api/v3/klines',
                        {'symbol': symbol, 'interval': '15m', 'limit': 100}, weight=2)
                    if klines_data and len(klines_data) > 20:
                        self.live_klines[symbol] = [{
                            'time': k[0], 'open': float(k[1]), 'high': float(k[2]),
                            'low': float(k[3]), 'close': float(k[4]),
                            'volume': float(k[5]), 'taker_buy_vol': float(k[9])
                        } for k in klines_data]
                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"خطأ REST Poller: {e}")
                await asyncio.sleep(60)

    async def get_klines(self, symbol, interval='15m', limit=100):
        data = await self._binance_request('GET', '/api/v3/klines',
            {'symbol': symbol, 'interval': interval, 'limit': limit}, weight=2)
        if data and len(data) > 20:
            df = pd.DataFrame(data, columns=[
                'time','open','high','low','close','volume',
                'close_time','quote_volume','trades','taker_buy_vol',
                'taker_buy_quote_vol','ignore'])
            for col in ['open','high','low','close','volume','taker_buy_vol']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            return df
        return None

    def get_live_df(self, symbol):
        if symbol not in self.live_klines or len(self.live_klines[symbol]) < 50:
            return None
        df = pd.DataFrame(self.live_klines[symbol])
        for col in ['open','high','low','close','volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    # ═════════════════════ كاش التحليل ═════════════════════
    def get_cached_analysis(self, symbol):
        if symbol in self.analysis_cache:
            cached = self.analysis_cache[symbol]
            if time.time() - cached['time'] < self.CACHE_TTL:
                return cached['result']
        return None

    def set_cached_analysis(self, symbol, result):
        self.analysis_cache[symbol] = {'result': result, 'time': time.time()}
        if len(self.analysis_cache) > 500:
            cutoff = time.time() - self.CACHE_TTL
            self.analysis_cache = {
                k: v for k, v in self.analysis_cache.items() if v['time'] > cutoff
            }

    # ═════════════════════ التحليل التقليدي (7 مؤشرات) ═════════════════════
    def _analyze_indicators(self, df, direction):
        score = 0
        signals = []

        try:
            price = df.iloc[-1]['close']

            # ═══ 1. RSI ═══
            rsi = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
            rsi_val = rsi.iloc[-1]

            if direction == 'BUY':
                if rsi_val < 25:
                    score += 4; signals.append(f"📈 RSI تشبع بيعي شديد ({rsi_val:.0f})")
                elif rsi_val < 30:
                    score += 3; signals.append(f"📈 RSI تشبع بيعي ({rsi_val:.0f})")
                elif rsi_val < 40:
                    score += 1; signals.append(f"📈 RSI منخفض ({rsi_val:.0f})")
                elif rsi_val > 70:
                    score -= 2; signals.append(f"⚠️ RSI مرتفع ({rsi_val:.0f})")
            else:
                if rsi_val > 75:
                    score += 4; signals.append(f"📉 RSI تشبع شرائي شديد ({rsi_val:.0f})")
                elif rsi_val > 70:
                    score += 3; signals.append(f"📉 RSI تشبع شرائي ({rsi_val:.0f})")
                elif rsi_val > 60:
                    score += 1; signals.append(f"📉 RSI مرتفع ({rsi_val:.0f})")
                elif rsi_val < 30:
                    score -= 2; signals.append(f"⚠️ RSI منخفض جداً ({rsi_val:.0f})")

            # ═══ 2. MACD ═══
            macd_ind = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
            macd_line = macd_ind.macd()
            signal_line = macd_ind.macd_signal()
            hist = macd_ind.macd_diff()

            if direction == 'BUY':
                if macd_line.iloc[-1] > signal_line.iloc[-1] and macd_line.iloc[-2] <= signal_line.iloc[-2]:
                    score += 3; signals.append("📈 MACD تقاطع صعودي ⚡")
                if hist.iloc[-1] > 0 and hist.iloc[-1] > hist.iloc[-2]:
                    score += 1; signals.append("📈 زخم MACD متزايد")
                elif hist.iloc[-1] < 0 and hist.iloc[-1] < hist.iloc[-2]:
                    score -= 1
            else:
                if macd_line.iloc[-1] < signal_line.iloc[-1] and macd_line.iloc[-2] >= signal_line.iloc[-2]:
                    score += 3; signals.append("📉 MACD تقاطع هبوطي ⚡")
                if hist.iloc[-1] < 0 and hist.iloc[-1] < hist.iloc[-2]:
                    score += 1; signals.append("📉 زخم MACD هبوطي متزايد")
                elif hist.iloc[-1] > 0 and hist.iloc[-1] > hist.iloc[-2]:
                    score -= 1

            # ═══ 3. EMA ═══
            ema9 = ta.trend.EMAIndicator(df['close'], window=9).ema_indicator()
            ema21 = ta.trend.EMAIndicator(df['close'], window=21).ema_indicator()
            ema50 = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()

            if direction == 'BUY':
                if ema9.iloc[-1] > ema21.iloc[-1] and ema9.iloc[-2] <= ema21.iloc[-2]:
                    score += 2; signals.append("📈 EMA9 فوق EMA21")
                if price > ema50.iloc[-1]:
                    score += 1
                else:
                    score -= 1
            else:
                if ema9.iloc[-1] < ema21.iloc[-1] and ema9.iloc[-2] >= ema21.iloc[-2]:
                    score += 2; signals.append("📉 EMA9 تحت EMA21")
                if price < ema50.iloc[-1]:
                    score += 1
                else:
                    score -= 1

            # ═══ 4. Bollinger Bands ═══
            bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
            bb_lower = bb.bollinger_lband().iloc[-1]
            bb_upper = bb.bollinger_hband().iloc[-1]

            if direction == 'BUY':
                if price <= bb_lower:
                    score += 3; signals.append("📈 لامس البولنجر السفلي!")
                elif price <= bb_lower * 1.02:
                    score += 1; signals.append("📈 قريب من البولنجر السفلي")
            else:
                if price >= bb_upper:
                    score += 3; signals.append("📉 لامس البولنجر العلوي!")
                elif price >= bb_upper * 0.98:
                    score += 1; signals.append("📉 قريب من البولنجر العلوي")

            # ═══ 5. Volume ═══
            vol_avg = df['volume'].rolling(20).mean().iloc[-1]
            vol_current = df.iloc[-1]['volume']
            vol_ratio = vol_current / vol_avg if vol_avg > 0 else 1

            if vol_ratio > 3:
                score += 3; signals.append(f"🔥 حجم ضخم! ({vol_ratio:.1f}x)")
            elif vol_ratio > 2:
                score += 2; signals.append(f"📊 حجم عالي ({vol_ratio:.1f}x)")
            elif vol_ratio > 1.5:
                score += 1; signals.append(f"📈 حجم فوق المتوسط ({vol_ratio:.1f}x)")

            # ═══ 6. Stochastic ═══
            stoch = ta.momentum.StochasticOscillator(
                high=df['high'], low=df['low'], close=df['close'],
                window=14, smooth_window=3)
            k = stoch.stoch().iloc[-1]
            d = stoch.stoch_signal().iloc[-1]
            k_prev = stoch.stoch().iloc[-2]
            d_prev = stoch.stoch_signal().iloc[-2]

            if direction == 'BUY':
                if k < 20 and d < 20 and k_prev < d_prev and k > d:
                    score += 3; signals.append("📈 Stochastic تقاطع صعودي في القاع")
            else:
                if k > 80 and d > 80 and k_prev > d_prev and k < d:
                    score += 3; signals.append("📉 Stochastic تقاطع هبوطي في القمة")

            # ═══ 7. تغير السعر ═══
            if len(df) >= 25:
                change_24h = ((df.iloc[-1]['close'] - df.iloc[-25]['close'])
                              / df.iloc[-25]['close']) * 100
                if direction == 'BUY' and -15 < change_24h < -5:
                    score += 2; signals.append(f"📉 هبوط {change_24h:.1f}% (فرصة!)")
                elif direction == 'BUY' and 5 < change_24h < 15:
                    score += 1; signals.append(f"📈 صعود معتدل {change_24h:.1f}%")
                elif direction == 'SELL' and change_24h > 20:
                    score += 2; signals.append(f"⚠️ صعود حاد {change_24h:.1f}% (فقاعة!)")
                elif direction == 'SELL' and -15 < change_24h < -5:
                    score += 1; signals.append(f"📉 هبوط مستمر {change_24h:.1f}%")

        except Exception as e:
            logger.debug(f"خطأ تحليل المؤشرات: {e}")

        return score, signals

    # ═════════════════════ التحليل المزدوج الشامل ═════════════════════
    async def analyze_coin_full(self, symbol):
        cached = self.get_cached_analysis(symbol)
        if cached is not None: return cached

        try:
            # ═══ 1. تحليل الفريم الأكبر (1h) ═══
            df_1h = await self.get_klines(symbol, '1h', 100)
            if df_1h is None or len(df_1h) < 50: return None

            df_1h = self.smc.detect_swings(df_1h, window=3)
            _, htf_trend = self.smc.detect_bos_choch(df_1h)

            # ═══ 2. تحليل الفريم الأساسي (15m) ═══
            df_15m = self.get_live_df(symbol)
            if df_15m is None or len(df_15m) < 50:
                df_15m = await self.get_klines(symbol, '15m', 100)
            if df_15m is None or len(df_15m) < 50: return None

            df_15m = self.smc.detect_swings(df_15m, window=3)
            signals_smc, micro_trend = self.smc.detect_bos_choch(df_15m)
            if not micro_trend: return None

            fvgs = self.smc.detect_fvg(df_15m)
            obs = self.smc.detect_order_blocks(df_15m, signals_smc, micro_trend)

            prices = self.live_prices.get(symbol)
            if not prices: return None

            price = prices['bid'] if micro_trend == 'bull' else prices['ask']

            result = {
                'symbol': symbol, 'price': price,
                'score': 0, 'direction': None,
                'sl': 0, 'tp': 0,
                'signals_smc': [], 'signals_indicators': [],
                'rsi': None, 'volume_ratio': None
            }

            # ═══ 3. تقييم SMC ═══
            if micro_trend == 'bull':
                result['score'] += 3; result['direction'] = 'BUY'
            elif micro_trend == 'bear':
                result['score'] -= 3; result['direction'] = 'SELL'
            else:
                return None

            # ─── إضافة إشارات BOS/CHoCH للعرض ───
            for sig in signals_smc[-5:]:
                sig_type = sig['type']
                if sig_type == 'BOS_Bull':
                    result['signals_smc'].append("📈 BOS صعودي (كسر هيكل)")
                elif sig_type == 'CHoCH_Bull':
                    result['signals_smc'].append("📈 CHoCH صعودي (تغيير اتجاه) ⚡")
                elif sig_type == 'BOS_Bear':
                    result['signals_smc'].append("📉 BOS هبوطي (كسر هيكل)")
                elif sig_type == 'CHoCH_Bear':
                    result['signals_smc'].append("📉 CHoCH هبوطي (تغيير اتجاه) ⚡")

            # ═══ تعديل 1: فلتر HTF صارم — رفض قاطع لحماية رأس المال ═══
            if result['direction'] == 'BUY' and htf_trend != 'bull': return None
            if result['direction'] == 'SELL' and htf_trend != 'bear': return None

            # FVG
            for fvg in fvgs[-5:]:
                if (fvg['type'] == 'bull_fvg' and fvg['bottom'] <= price <= fvg['top']
                    and result['direction'] == 'BUY'):
                    result['score'] += 2
                    result['signals_smc'].append("📈 FVG صعودي في منطقة السعر")
                    break
                elif (fvg['type'] == 'bear_fvg' and fvg['bottom'] <= price <= fvg['top']
                      and result['direction'] == 'SELL'):
                    result['score'] -= 2
                    result['signals_smc'].append("📉 FVG هبوطي في منطقة السعر")
                    break

            # Order Blocks
            for ob in obs[-3:]:
                if (ob['type'] == 'bull_ob' and ob['bottom'] <= price <= ob['top']
                    and result['direction'] == 'BUY'):
                    result['score'] += 4
                    result['signals_smc'].append("📦 Order Block صعودي ⚡")
                    break
                elif (ob['type'] == 'bear_ob' and ob['bottom'] <= price <= ob['top']
                      and result['direction'] == 'SELL'):
                    result['score'] -= 4
                    result['signals_smc'].append("📦 Order Block هبوطي ⚡")
                    break

            # ═══ 4. تحليل المؤشرات التقليدية ═══
            ind_score, ind_signals = self._analyze_indicators(df_15m, result['direction'])
            if result['direction'] == 'SELL':
                ind_score = -ind_score
            result['score'] += ind_score
            result['signals_indicators'] = ind_signals

            # RSI و Volume للعرض
            try:
                rsi_val = ta.momentum.RSIIndicator(df_15m['close'], window=14).rsi().iloc[-1]
                result['rsi'] = round(rsi_val, 1)
                vol_avg = df_15m['volume'].rolling(20).mean().iloc[-1]
                vol_current = df_15m.iloc[-1]['volume']
                result['volume_ratio'] = round(vol_current / vol_avg, 1) if vol_avg > 0 else 1
            except Exception:
                pass

            # ═══ 5. حساب SL/TP ═══
            try:
                atr = ta.volatility.AverageTrueRange(
                    high=df_15m['high'], low=df_15m['low'],
                    close=df_15m['close'], window=14
                ).average_true_range().iloc[-1]

                if result['direction'] == 'BUY':
                    result['sl'] = price - (atr * 1.5)
                    result['tp'] = price + (atr * 3.0)
                else:
                    result['sl'] = price + (atr * 1.5)
                    result['tp'] = price - (atr * 3.0)
            except Exception:
                if result['direction'] == 'BUY':
                    result['sl'] = price * (1 - self.STOP_LOSS_PCT / 100)
                    result['tp'] = price * (1 + self.TAKE_PROFIT_PCT / 100)
                else:
                    result['sl'] = price * (1 + self.STOP_LOSS_PCT / 100)
                    result['tp'] = price * (1 - self.TAKE_PROFIT_PCT / 100)

            # ═══ 6. فلتر النقاط الأدنى ═══
            if abs(result['score']) < self.MIN_SCORE_TO_TRADE:
                self.set_cached_analysis(symbol, None)
                return None

            self.set_cached_analysis(symbol, result)
            return result

        except Exception as e:
            logger.debug(f"خطأ تحليل {symbol}: {e}")
            return None

    # ═════════════════════ إعلانات بينانس ═════════════════════
    async def check_binance_announcements(self):
        try:
            url = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
            params = {'type': 1, 'catalogId': 48, 'pageNo': 1, 'pageSize': 15}

            async with self.session.get(url, params=params, timeout=10) as r:
                if r.status != 200: return
                data = await r.json()

            articles = data.get('data', {}).get('articles', [])
            if not articles: return

            listing_keywords = [
                'LIST', 'LISTS', 'LISTING', 'WILL LIST',
                'LAUNCH', 'NEW TOKEN', 'ADDED', 'TRADES OPEN',
                'الإدراج', 'إدراج', 'DELIST', 'REMOVAL', 'REMOVE'
            ]

            seen_ids = await self.db.get_seen_announcements()
            current_ids = set()
            new_listings = []
            deleted_signals = []

            for article in articles:
                aid = str(article.get('id', ''))
                title = article.get('title', '')
                title_upper = title.upper()
                release_date = article.get('releaseDate', 0)
                current_ids.add(aid)

                if aid not in seen_ids:
                    if any(kw in title_upper for kw in listing_keywords):
                        if release_date > (time.time() * 1000 - 3600000):
                            new_listings.append({'title': title, 'id': aid})
                            words = title_upper.split()
                            for word in words:
                                if word in self.known_symbols:
                                    base = word.replace('USDT', '')
                                    self.hot_coins.add(base)
                    await self.db.add_seen_announcement(aid, title)

            deleted = seen_ids - current_ids
            if deleted:
                for did in list(deleted)[:5]:
                    deleted_signals.append(did)
                if deleted_signals:
                    msg = "🗑️ *إعلانات محذوفة من بينانس!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    msg += "⚠️ قد تشير لإدراج قادم!\n\n"
                    for did in deleted_signals[:3]:
                        msg += f"📌 ID: `{did}`\n"
                    msg += "\n🎯 استعد للقنص عند الإدراج الرسمي!"
                    await self.tg(msg)

            if new_listings:
                msg = "🚨 *إعلان إدراج جديد على بينانس!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                for listing in new_listings:
                    msg += f"📢 {listing['title']}\n\n"
                msg += "⚡ العملات المدرجة حديثاً ترتفع عادة 20-200%!"
                await self.tg(msg)

            await self.db.cleanup_old_announcements()

        except Exception as e:
            logger.debug(f"خطأ فحص الإعلانات: {e}")

    # ═════════════════════ CoinGecko ═════════════════════
    async def scan_coingecko_trending(self):
        trending_on_binance = []
        try:
            url = "https://api.coingecko.com/api/v3/search/trending"
            async with self.session.get(url, timeout=10) as r:
                if r.status != 200: return []
                data = await r.json()

            coins = data.get('coins', [])
            msg = "🔥 *عملات رائجة على CoinGecko*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"

            for i, coin_data in enumerate(coins[:7]):
                coin = coin_data.get('item', {})
                name = coin.get('name', 'N/A')
                symbol = coin.get('symbol', '').upper()
                rank = coin.get('market_cap_rank', 'N/A')
                on_binance = f"{symbol}USDT" in self.known_symbols
                icon = "✅" if on_binance else "❌"

                msg += f"{i+1}. 🪙 *{name}* (`{symbol}`) {icon}\n"
                msg += f"   📊 ترتيب: #{rank}\n\n"

                if on_binance:
                    trending_on_binance.append(symbol)
                    self.hot_coins.add(symbol)

            msg += "✅ = متاحة على بينانس | ❌ = غير متاحة بعد"
            await self.tg(msg)

        except Exception as e:
            logger.debug(f"خطأ CoinGecko Trending: {e}")

        return trending_on_binance

    async def scan_coingecko_gainers(self):
        gainers = []
        try:
            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                'vs_currency': 'usd',
                'order': 'price_change_percentage_24h_desc',
                'per_page': 50, 'page': 1,
                'price_change_percentage': '24h'
            }
            async with self.session.get(url, params=params, timeout=10) as r:
                if r.status != 200: return []
                data = await r.json()

            binance_gainers = []
            for coin in data:
                symbol = coin.get('symbol', '').upper()
                name = coin.get('name', '')
                change = coin.get('price_change_percentage_24h', 0) or 0
                price = coin.get('current_price', 0) or 0
                mcap = coin.get('market_cap', 0) or 0
                binance_sym = f"{symbol}USDT"

                if binance_sym in self.known_symbols and mcap > 1000000:
                    binance_gainers.append({
                        'symbol': binance_sym, 'name': name,
                        'change': change, 'price': price, 'mcap': mcap
                    })
                    self.hot_coins.add(symbol)

            if binance_gainers:
                msg = "🚀 *أكثر العملات ارتفاعاً (على بينانس)*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                for i, g in enumerate(binance_gainers[:7]):
                    msg += (f"{i+1}. 🪙 *{g['name']}* (`{g['symbol']}`)\n"
                           f"   💰 {self.fmt_price(g['price'])} | 📈 {self.fmt_pct(g['change'])}\n\n")
                await self.tg(msg)
                gainers = [g['symbol'] for g in binance_gainers]

        except Exception as e:
            logger.debug(f"خطأ CoinGecko Gainers: {e}")

        return gainers

    # ═════════════════════ DexScreener (محسّن) ═════════════════════
    async def scan_dexscreener_hot(self):
        try:
            url = "https://api.dexscreener.com/token-boosts/top/v1"
            async with self.session.get(url, timeout=10) as r:
                if r.status != 200:
                    url2 = "https://api.dexscreener.com/token-profiles/latest/v1"
                    async with self.session.get(url2, timeout=10) as r2:
                        if r2.status != 200: return []
                        data = await r2.json()
                else:
                    data = await r.json()

            if not data or not isinstance(data, list): return []

            binance_tokens = []
            other_tokens = []

            for token in data[:30]:
                symbol = token.get('symbol', '').upper()
                name = token.get('name', '')
                chain = token.get('chainId', '')
                price_usd = token.get('priceUsd', '0')
                change = 0

                on_binance = f"{symbol}USDT" in self.known_symbols

                if on_binance:
                    binance_tokens.append({
                        'symbol': symbol, 'name': name,
                        'price': price_usd, 'change': change,
                        'chain': chain, 'on_binance': True
                    })
                    self.hot_coins.add(symbol)
                elif len(other_tokens) < 3:
                    other_tokens.append({
                        'symbol': symbol, 'name': name,
                        'price': price_usd, 'change': change,
                        'chain': chain, 'on_binance': False
                    })

            all_tokens = binance_tokens[:5] + other_tokens[:3]
            if not all_tokens: return []

            msg = "🦎 *عملات ساخنة على DEX*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"

            for i, t in enumerate(all_tokens):
                icon = "✅" if t['on_binance'] else "🔄"
                try:
                    p = float(t['price']) if t['price'] else 0
                    price_str = self.fmt_price(p) if p > 0 else "N/A"
                except:
                    price_str = "N/A"

                msg += (f"{i+1}. 🪙 *{t['name']}* (`{t['symbol']}`) {icon}\n"
                       f"   💰 {price_str} | شبكة: {t['chain']}\n\n")

            msg += "✅ = على بينانس | 🔄 = قد تُدرج قريباً"
            await self.tg(msg)

        except Exception as e:
            logger.debug(f"خطأ DexScreener: {e}")
        return []

    # ═════════════════════ مؤشر الخوف والطمع ═════════════════════
    async def check_fear_greed(self):
        try:
            url = "https://api.alternative.me/fng/?limit=1"
            async with self.session.get(url, timeout=10) as r:
                if r.status != 200: return 50
                data = await r.json()

            fng = data.get('data', [{}])[0]
            value = int(fng.get('value', 50))
            label = fng.get('value_classification', 'Neutral')

            emoji_map = {
                'Extreme Fear': '😱', 'Fear': '😨',
                'Neutral': '😐', 'Greed': '😊',
                'Extreme Greed': '🤑'
            }
            emoji = emoji_map.get(label, '😐')

            msg = f"{emoji} *مؤشر الخوف والطمع*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"📊 القيمة: *{value}/100*\n📌 التصنيف: *{label}*\n\n"

            if value < 25:
                msg += "💡 السوق في خوف شديد — فرص شراء ممتازة!"
            elif value < 40:
                msg += "💡 السوق خائف — قد تكون فرصة جيدة"
            elif value > 75:
                msg += "⚠️ السوق جشع جداً — حذر من التصحيح!"
            elif value > 60:
                msg += "💡 السوق متفائل — تأكد من وقف الخسارة"

            await self.tg(msg)
            return value
        except Exception as e:
            logger.debug(f"خطأ Fear & Greed: {e}")
        return 50

    # ═════════════════════ كشف ارتفاعات الحجم ═════════════════════
    async def detect_volume_spikes(self):
        spikes = []
        try:
            data = await self._binance_request('GET', '/api/v3/ticker/24hr', weight=40)
            if not data: return spikes

            for ticker in data:
                symbol = ticker.get('symbol', '')
                if not symbol.endswith('USDT'): continue

                quote_vol = float(ticker.get('quoteVolume', 0))
                price_change = float(ticker.get('priceChangePercent', 0))
                trades = int(ticker.get('count', 0))

                if quote_vol > 5000000 and 2 < price_change < 20 and trades > 1000:
                    spikes.append({
                        'symbol': symbol,
                        'volume_usdt': quote_vol,
                        'change_pct': price_change,
                        'trades': trades
                    })
                    base = symbol.replace('USDT', '')
                    self.hot_coins.add(base)

            spikes.sort(key=lambda x: x['volume_usdt'], reverse=True)
            self.volume_spikes = spikes

            if spikes[:7]:
                msg = "📊 *ارتفاعات حجم مشبوهة (ذكاء أموال)*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                for i, s in enumerate(spikes[:7]):
                    vol_m = s['volume_usdt'] / 1_000_000
                    msg += (f"{i+1}. 🪙 `{s['symbol']}`\n"
                           f"   💧 حجم: ${vol_m:.1f}M | 📈 {self.fmt_pct(s['change_pct'])}"
                           f" | 🔄 {s['trades']:,} صفقة\n\n")
                await self.tg(msg)

        except Exception as e:
            logger.debug(f"خطأ كشف الحجم: {e}")

        return spikes

    # ═════════════════════ المسح الذكي بالتصفية الخارجية ═════════════════════
    async def smart_scan_with_external_filter(self):
        binance_targets = set()

        try:
            url = "https://api.coingecko.com/api/v3/search/trending"
            async with self.session.get(url, timeout=10) as r:
                if r.status == 200:
                    data = await r.json()
                    for coin_data in data.get('coins', []):
                        symbol = coin_data.get('item', {}).get('symbol', '').upper()
                        if f"{symbol}USDT" in self.known_symbols:
                            binance_targets.add(f"{symbol}USDT")
                            self.hot_coins.add(symbol)
        except Exception:
            pass

        await asyncio.sleep(1)

        try:
            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {'vs_currency': 'usd', 'order': 'price_change_percentage_24h_desc',
                      'per_page': 50, 'page': 1}
            async with self.session.get(url, params=params, timeout=10) as r:
                if r.status == 200:
                    data = await r.json()
                    for coin in data:
                        symbol = coin.get('symbol', '').upper()
                        mcap = coin.get('market_cap', 0) or 0
                        if f"{symbol}USDT" in self.known_symbols and mcap > 1000000:
                            binance_targets.add(f"{symbol}USDT")
                            self.hot_coins.add(symbol)
        except Exception:
            pass

        await asyncio.sleep(1)

        try:
            url = "https://api.dexscreener.com/token-boosts/top/v1"
            async with self.session.get(url, timeout=10) as r:
                if r.status == 200:
                    data = await r.json()
                    if isinstance(data, list):
                        for token in data[:30]:
                            symbol = token.get('symbol', '').upper()
                            if f"{symbol}USDT" in self.known_symbols:
                                binance_targets.add(f"{symbol}USDT")
                                self.hot_coins.add(symbol)
        except Exception:
            pass

        for spike in self.volume_spikes[:10]:
            binance_targets.add(spike['symbol'])

        for coin in self.hot_coins:
            sym = f"{coin}USDT"
            if sym in self.known_symbols:
                binance_targets.add(sym)

        for coin in self.priority_coins:
            sym = f"{coin}USDT"
            if sym in self.known_symbols:
                binance_targets.add(sym)

        logger.info(f"🎯 مسح ذكي: {len(binance_targets)} هدف مُصفّى")

        results = []
        for i, symbol in enumerate(list(binance_targets)):
            if symbol in self.active_trades: continue
            if symbol not in self.known_symbols: continue
            if symbol not in self.step_sizes_cache: continue

            analysis = await self.analyze_coin_full(symbol)
            if analysis and abs(analysis['score']) >= self.MIN_SCORE_TO_TRADE:
                results.append(analysis)
                self.stats['signals_found'] += 1

            await asyncio.sleep(0.5)
            if (i + 1) % 15 == 0:
                await asyncio.sleep(3)

        results.sort(key=lambda x: abs(x['score']), reverse=True)

        buys = [a for a in results if a['direction'] == 'BUY'][:5]
        sells = [a for a in results if a['direction'] == 'SELL'][:3]

        if buys:
            msg = "🟢 *أفضل فرص الشراء (مسح ذكي)!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for i, a in enumerate(buys):
                msg += (f"{i+1}. 🪙 `{a['symbol']}` | 💵 {self.fmt_price(a['price'])}\n"
                       f"   📊 نقاط: *{a['score']}* | RSI: {a.get('rsi','N/A')}"
                       f" | Vol: {a.get('volume_ratio','N/A')}x\n")
                for sig in (a.get('signals_smc', []) + a.get('signals_indicators', []))[:3]:
                    msg += f"   {sig}\n"
                msg += "\n"
            await self.tg(msg)

            for a in buys:
                await self.execute_trade(a)
                await asyncio.sleep(1)

        if sells:
            msg = "🔴 *إشارات بيع قوية (مسح ذكي)*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for i, a in enumerate(sells):
                msg += f"{i+1}. 🪙 `{a['symbol']}` | نقاط: *{a['score']}* | {self.fmt_price(a['price'])}\n"
            await self.tg(msg)

        self.stats['total_scans'] += len(binance_targets)
        return results

    # ═════════════════════ المسح الشامل المحصّن ═════════════════════
    async def full_market_scan(self):
        now_str = datetime.now(self.TZ).strftime('%Y-%m-%d %H:%M')
        msg = (f"🔍 *بدء المسح الشامل المحصّن*\n📅 {now_str}\n"
               f"📊 عدد الأزواج: {len(self.all_usdt_pairs)}\n━━━━━━━━━━━━━━━━━━━━━━━━")
        await self.tg(msg)

        all_tickers = await self._binance_request('GET', '/api/v3/ticker/24hr', weight=40)
        if not all_tickers:
            await self.tg("❌ فشل تحميل بيانات السوق")
            return

        candidates = []
        for ticker in all_tickers:
            symbol = ticker.get('symbol', '')
            if not symbol.endswith('USDT'): continue
            if symbol in self.active_trades: continue

            quote_vol = float(ticker.get('quoteVolume', 0))
            price_change = float(ticker.get('priceChangePercent', 0))
            trades = int(ticker.get('count', 0))

            # ═══ تعديل 2: تشديد الفلتر المسبق لسيولة عالية فقط ═══
            if quote_vol > 500000 and -30 < price_change < 30 and trades > 200:
                interest_score = 0
                base = symbol.replace('USDT', '')

                if base in self.hot_coins:
                    interest_score += 100
                if quote_vol > 10000000:
                    interest_score += 50
                elif quote_vol > 5000000:
                    interest_score += 30
                elif quote_vol > 1000000:
                    interest_score += 15
                if abs(price_change) > 5:
                    interest_score += 20
                if base in self.priority_coins:
                    interest_score += 15

                candidates.append({
                    'symbol': symbol,
                    'volume': quote_vol,
                    'change': price_change,
                    'interest': interest_score
                })

        candidates.sort(key=lambda x: x['interest'], reverse=True)

        # ═══ تعديل 2: تضييق النطاق لأفضل 80 عملة فقط ═══
        top_candidates = candidates[:80]

        logger.info(f"📊 Pre-filter: {len(candidates)} مرشح ← تحليل أفضل {len(top_candidates)}")

        CHUNK_SIZE = 10
        results = []
        scanned = 0

        for chunk_start in range(0, len(top_candidates), CHUNK_SIZE):
            chunk = top_candidates[chunk_start:chunk_start + CHUNK_SIZE]

            for candidate in chunk:
                symbol = candidate['symbol']

                if symbol not in self.step_sizes_cache:
                    scanned += 1
                    continue

                cached = self.get_cached_analysis(symbol)
                if cached is not None:
                    if cached and abs(cached['score']) >= self.MIN_SCORE_TO_TRADE:
                        results.append(cached)
                    scanned += 1
                    continue

                analysis = await self.analyze_coin_full(symbol)
                if analysis and abs(analysis['score']) >= self.MIN_SCORE_TO_TRADE:
                    results.append(analysis)
                    self.stats['signals_found'] += 1
                scanned += 1

                await asyncio.sleep(0.5)

            await asyncio.sleep(3)

            if (chunk_start + CHUNK_SIZE) % 30 == 0:
                logger.info(f"📊 تم فحص {scanned}/{len(top_candidates)} — وزن: {self.weight_tracker.current}")

        self.stats['total_scans'] += scanned

        results.sort(key=lambda x: abs(x['score']), reverse=True)

        buys = [a for a in results if a['direction'] == 'BUY'][:5]
        sells = [a for a in results if a['direction'] == 'SELL'][:3]

        if buys:
            msg = "🟢 *أفضل فرص الشراء (مسح شامل)!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for i, a in enumerate(buys):
                msg += (f"{i+1}. 🪙 `{a['symbol']}` | 💵 {self.fmt_price(a['price'])}\n"
                       f"   📊 نقاط: *{a['score']}* | RSI: {a.get('rsi','N/A')}"
                       f" | Vol: {a.get('volume_ratio','N/A')}x\n")
                for sig in (a.get('signals_smc', []) + a.get('signals_indicators', []))[:3]:
                    msg += f"   {sig}\n"
                msg += "\n"
            await self.tg(msg)

            for a in buys:
                await self.execute_trade(a)
                await asyncio.sleep(1)

        if sells:
            msg = "🔴 *إشارات بيع قوية (مسح شامل)*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for i, a in enumerate(sells):
                msg += f"{i+1}. 🪙 `{a['symbol']}` | نقاط: *{a['score']}* | {self.fmt_price(a['price'])}\n"
            await self.tg(msg)

        total = self.stats['wins'] + self.stats['losses']
        win_rate = (self.stats['wins'] / total * 100) if total > 0 else 0
        weight_used = self.weight_tracker.current

        msg = (f"📋 *تقرير المسح الشامل*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"✅ تم فحص: {scanned} عملة (من {len(candidates)} مرشح)\n"
               f"🎯 فرص وُجدت: {len(results)}\n"
               f"🟢 شراء قوي: {len(buys)}\n"
               f"🔴 بيع قوي: {len(sells)}\n"
               f"🔥 عملات ساخنة: {len(self.hot_coins)}\n"
               f"⚖️ وزن API: {weight_used}/2400\n"
               f"🏆 نسبة الفوز: {win_rate:.1f}%\n"
               f"📈 الإجمالي: {self.stats['wins']}W / {self.stats['losses']}L")
        await self.tg(msg)

    # ═════════════════════ الفحص السريع ═════════════════════
    async def quick_scan(self):
        targets = set()

        for coin in self.priority_coins:
            sym = f"{coin}USDT"
            if sym in self.known_symbols and sym in self.step_sizes_cache:
                targets.add(sym)

        for coin in self.hot_coins:
            sym = f"{coin}USDT"
            if sym in self.known_symbols and sym in self.step_sizes_cache:
                targets.add(sym)

        found = []
        for symbol in list(targets)[:40]:
            if symbol in self.active_trades: continue

            analysis = await self.analyze_coin_full(symbol)
            if analysis and abs(analysis['score']) >= self.MIN_SCORE_TO_TRADE:
                found.append(analysis)

            await asyncio.sleep(0.3)

        if found:
            found.sort(key=lambda x: abs(x['score']), reverse=True)
            msg = "⚡ *فحص سريع — فرص!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for i, a in enumerate(found[:5]):
                icon = "🟢" if a['direction'] == 'BUY' else "🔴"
                smc_count = len(a.get('signals_smc', []))
                ind_count = len(a.get('signals_indicators', []))
                msg += (f"{icon} `{a['symbol']}` | نقاط: *{a['score']}*"
                       f" | {self.fmt_price(a['price'])}\n"
                       f"   SMC: {smc_count} إشارات | مؤشرات: {ind_count} إشارات\n")
            await self.tg(msg)

            best_buys = [a for a in found if a['direction'] == 'BUY']
            if best_buys:
                await self.execute_trade(best_buys[0])

    # ═════════════════════ التداول التلقائي ═════════════════════
    async def execute_trade(self, analysis):
        if not self.TRADE_ENABLED: return
        if len(self.active_trades) >= self.MAX_OPEN_TRADES: return

        symbol = analysis['symbol']
        direction = analysis['direction']
        if symbol in self.active_trades: return

        prices = self.live_prices.get(symbol)
        if not prices: return
        if not self.risk.check_spread(symbol, prices.get('ask'), prices.get('bid')): return
        if not await self.risk.check_daily_drawdown(): return

        balance = await self.get_usdt_balance()
        risk_amount = balance * (self.RISK_PER_TRADE_PCT / 100)
        sl_distance = abs(analysis['price'] - analysis['sl'])
        if sl_distance == 0: return

        raw_qty = risk_amount / sl_distance
        qty = self.format_quantity(symbol, raw_qty)
        side = 'BUY' if direction == 'BUY' else 'SELL'

        cost_estimate = qty * analysis['price']
        if cost_estimate < self.MIN_TRADE_USDT: return

        result = await self._binance_request('POST', '/api/v3/order', {
            'symbol': symbol, 'side': side, 'type': 'MARKET', 'quantity': qty
        }, signed=True, is_trade_endpoint=True, weight=1)

        if not result:
            await self.tg(f"❌ *فشل تنفيذ {side} (`{symbol}`)*\n⚠️ لا استجابة من بينانس")
            return

        status = result.get('status')
        if status in ['FILLED', 'PARTIALLY_FILLED']:
            fills = result.get('fills', [])
            total_cost = sum(float(f['price']) * float(f['qty']) for f in fills)
            total_qty = sum(float(f['qty']) for f in fills)
            fill_price = total_cost / total_qty if total_qty > 0 else analysis['price']

            self.stats['trades_executed'] += 1
            trade_data = {
                'symbol': symbol, 'side': side, 'entry_price': fill_price,
                'quantity': total_qty, 'sl': analysis['sl'], 'tp': analysis['tp'],
                'trailing_active': False, 'highest_price': fill_price,
                'lowest_price': fill_price, 'entry_time': time.time(),
                'score': analysis['score']
            }
            self.active_trades[symbol] = trade_data
            await self.db.save_trade(trade_data)

            smc_signals = analysis.get('signals_smc', [])
            ind_signals = analysis.get('signals_indicators', [])

            msg = (f"✅ *صفقة {side} منفذة!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                   f"🪙 الزوج: `{symbol}`\n"
                   f"💵 سعر الدخول: {self.fmt_price(fill_price)}\n"
                   f"📊 الكمية: `{total_qty}`\n"
                   f"💰 المبلغ: ${total_cost:.2f}\n"
                   f"🛑 وقف الخسارة: {self.fmt_price(analysis['sl'])}\n"
                   f"🎯 هدف الربح: {self.fmt_price(analysis['tp'])}\n"
                   f"📈 نقاط التحليل: *{analysis['score']}*\n"
                   f"🏛️ SMC: {' | '.join(smc_signals[:2])}\n"
                   f"📊 مؤشرات: {' | '.join(ind_signals[:2])}")
            await self.tg(msg)

        elif status in ['EXPIRED', 'CANCELED', 'REJECTED']:
            reason = result.get('msg', 'Unknown')
            await self.tg(f"🚫 *رفض أمر {side} (`{symbol}`)*\nReason: `{reason}`")

    # ═════════════════════ مراقبة الصفقات ═════════════════════
    async def monitor_trades(self):
        if not self.active_trades: return

        symbols_to_close = []
        for symbol, trade in list(self.active_trades.items()):
            prices = self.live_prices.get(symbol)
            if not prices: continue

            is_buy = trade['side'] == 'BUY'
            current_price = prices['bid'] if is_buy else prices['ask']

            if is_buy:
                if current_price > trade.get('highest_price', current_price):
                    trade['highest_price'] = current_price
                    await self.db.save_trade(trade)
            else:
                if current_price < trade.get('lowest_price', current_price):
                    trade['lowest_price'] = current_price
                    await self.db.save_trade(trade)

            current_pnl_pct = ((current_price - trade['entry_price']) / trade['entry_price']) * 100
            if not is_buy: current_pnl_pct = -current_pnl_pct

            should_close, reason = False, ""

            if is_buy:
                if current_price <= trade['sl']: should_close, reason = True, "🛑 ضرب SL"
                elif current_price >= trade['tp']: should_close, reason = True, "🎯 وصل TP"
            else:
                if current_price >= trade['sl']: should_close, reason = True, "🛑 ضرب SL"
                elif current_price <= trade['tp']: should_close, reason = True, "🎯 وصل TP"

            if not trade['trailing_active'] and current_pnl_pct > 1.5:
                trade['trailing_active'] = True
                if is_buy: trade['sl'] = trade['entry_price'] * 1.002
                else: trade['sl'] = trade['entry_price'] * 0.998
                await self.db.save_trade(trade)

            if trade['trailing_active']:
                if is_buy:
                    new_sl = trade['highest_price'] * 0.985
                    if new_sl > trade['sl']: trade['sl'] = new_sl
                    if current_price <= trade['sl']:
                        should_close, reason = True, "🔄 وقف متحرك صعودي"
                else:
                    new_sl = trade['lowest_price'] * 1.015
                    if new_sl < trade['sl']: trade['sl'] = new_sl
                    if current_price >= trade['sl']:
                        should_close, reason = True, "🔄 وقف متحرك هبوطي"

            if time.time() - trade['entry_time'] > 43200 and abs(current_pnl_pct) < 0.5:
                should_close, reason = True, "⏰ خروج زمني"

            df = self.get_live_df(symbol)
            if df is not None and len(df) > 5:
                try:
                    rsi = ta.momentum.RSIIndicator(df['close'], window=14).rsi().iloc[-1]
                    if is_buy and rsi > 75:
                        should_close, reason = True, "⚠️ تشبع شرائي"
                    elif not is_buy and rsi < 25:
                        should_close, reason = True, "⚠️ تشبع بيعي"
                except Exception:
                    pass

            if should_close:
                symbols_to_close.append((symbol, reason, current_price))

        for symbol, reason, close_price in symbols_to_close:
            trade = self.active_trades.get(symbol)
            if not trade: continue

            close_side = 'SELL' if trade['side'] == 'BUY' else 'BUY'
            qty = self.format_quantity(symbol, trade['quantity'])

            result = await self._binance_request('POST', '/api/v3/order', {
                'symbol': symbol, 'side': close_side, 'type': 'MARKET', 'quantity': qty
            }, signed=True, is_trade_endpoint=True, weight=1)

            if result and result.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
                fills = result.get('fills', [])
                total_cost = sum(float(f['price']) * float(f['qty']) for f in fills)
                total_qty = sum(float(f['qty']) for f in fills)
                fill_price = total_cost / total_qty if total_qty > 0 else close_price
            else:
                fill_price = close_price

            if trade['side'] == 'BUY':
                pnl = (fill_price - trade['entry_price']) * trade['quantity']
            else:
                pnl = (trade['entry_price'] - fill_price) * trade['quantity']

            is_win = pnl > 0
            if is_win:
                self.stats['wins'] += 1
            else:
                self.stats['losses'] += 1

            await self.db.update_daily_pnl(pnl, is_win)
            await self.db.remove_trade(symbol)
            if symbol in self.active_trades:
                del self.active_trades[symbol]

            icon = "✅" if is_win else "❌"
            msg = (f"🏁 *إغلاق `{symbol}`*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                   f"{reason}\n"
                   f"💵 الدخول: {self.fmt_price(trade['entry_price'])}\n"
                   f"💵 الإغلاق: {self.fmt_price(fill_price)}\n"
                   f"{icon} النتيجة: `{pnl:.2f} USDT`\n"
                   f"🏆 الإجمالي: {self.stats['wins']}W / {self.stats['losses']}L")
            await self.tg(msg)

    # ═════════════════════ مزامنة ═════════════════════
    async def sync_with_binance(self):
        open_orders = await self._binance_request('GET', '/api/v3/openOrders',
                                                    signed=True, is_trade_endpoint=True, weight=3)
        if open_orders is None: return

        for sym in list(self.active_trades.keys()):
            if sym not in self.active_trades: continue
            trade = self.active_trades[sym]
            if time.time() - trade.get('entry_time', 0) > 86400:
                logger.warning(f"⚠️ {sym} صفقة قديمة، يتم الحذف...")
                await self.db.remove_trade(sym)
                del self.active_trades[sym]

    # ═════════════════════ اللوب الرئيسي ═════════════════════
    async def main_loop(self):
        self.session = aiohttp.ClientSession()
        await self.db.init_db()
        await self.load_market_data()
        self.active_trades = await self.db.load_active_trades()
        await self.sync_with_binance()
        asyncio.create_task(self.ws_manager())
        await asyncio.sleep(10)

        if self.mode == 'test' and not self._testnet_failed:
            mode_str = "🧪 تجريبي (Testnet)"
        elif self.mode == 'test' and self._testnet_failed:
            mode_str = "💰 حقيقي (Real) — Testnet كان معطّلاً"
        else:
            mode_str = "💰 حقيقي (Real)"

        mode_trade = "⚔️ تداول تلقائي" if self.TRADE_ENABLED else "👁️ مراقبة فقط"

        msg = ("🔥 *القناص الأسطوري V6.2 — بدأ العمل!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"📡 الوضع: {mode_trade}\n"
               f"🌐 السيرفر: {mode_str}\n"
               f"💰 المخاطرة/صفقة: {self.RISK_PER_TRADE_PCT}%\n"
               f"📊 حد النقاط: {self.MIN_SCORE_TO_TRADE} (مقفل لحماية رأس المال)\n"
               f"📂 أقصى صفقات: {self.MAX_OPEN_TRADES}\n"
               f"🪙 أزواج محملة: {len(self.all_usdt_pairs)}\n"
               f"📏 أحجام خطوة: {len(self.step_sizes_cache)}\n"
               "━━━━━━━━━━━━━━━━━━━━━━━━\n"
               "🛡️ فلاتر صارمة: HTF صارم + سيولة عالية + 7 نقاط حد أدنى\n"
               "━━━━━━━━━━━━━━━━━━━━━━━━\n"
               "⏰ المسح الشامل: كل ساعتين\n"
               "🎯 المسح الذكي: كل 30 دقيقة\n"
               "⚡ فحص سريع: كل 15 دقيقة\n"
               "📡 إعلانات بينانس: كل دقيقتين\n"
               "🔥 CoinGecko + DEX: كل 30 دقيقة\n"
               "😱 مؤشر الخوف: كل ساعة\n"
               "📊 ارتفاعات الحجم: كل 30 دقيقة\n"
               "👀 مراقبة الصفقات: كل 30 ثانية\n"
               "━━━━━━━━━━━━━━━━━━━━━━━━\n"
               "🛡️ نظام Weight Tracker يحمي من الحظر!")
        await self.tg(msg)

        try:
            while True:
                try:
                    now = time.time()

                    await self.monitor_trades()

                    if now - self.timers['announcement'] > 120:
                        await self.check_binance_announcements()
                        self.timers['announcement'] = now

                    if now - self.timers['quick_scan'] > 900:
                        await self.quick_scan()
                        self.timers['quick_scan'] = now

                    if now - self.timers['coingecko'] > 1800:
                        await self.scan_coingecko_trending()
                        await asyncio.sleep(2)
                        await self.scan_coingecko_gainers()
                        await asyncio.sleep(2)
                        await self.scan_dexscreener_hot()
                        self.timers['coingecko'] = now

                        await self.detect_volume_spikes()
                        self.timers['volume_spike'] = now

                        await self.smart_scan_with_external_filter()
                        self.timers['hot_scan'] = now

                    if now - self.timers['fear_greed'] > 3600:
                        await self.check_fear_greed()
                        self.timers['fear_greed'] = now

                    if now - self.timers['full_scan'] > 7200:
                        await self.load_market_data()
                        self.timers['reload_market'] = now
                        await self.full_market_scan()
                        self.timers['full_scan'] = now

                    if now - self.timers.get('sync', 0) > 14400:
                        await self.sync_with_binance()
                        self.timers['sync'] = now

                    await asyncio.sleep(30)

                except Exception as loop_err:
                    logger.error(f"خطأ في الحلقة: {loop_err}")
                    await asyncio.sleep(30)

        finally:
            await self.session.close()

    def start(self):
        asyncio.run(self.main_loop())


if __name__ == "__main__":
    bot = LegendarySniperBotV6()
    bot.start()
