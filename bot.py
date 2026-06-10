"""
═══════════════════════════════════════════════════════════════════════
  🔥 القناص الأسطوري V7.2 — Legendary Sniper (Multi-TF & ATR Shield) 🔥
═══════════════════════════════════════════════════════════════════════
  تحديثات V7.2 (التعديلات المطلوبة):
  ✅ تعديل الرافعة المالية: تثبيت الرافعة على 10x فقط
  ✅ دمج الفريمات: 4 ساعات (اتجاه ماكرو) + 1 ساعة (مناطق حيتان) + 15 دقيقة (زناد الدخول)
  ✅ إعادة دمج مؤشر الاستوكاستيك: كروس الزناد على فريم 15 دقيقة في مناطق التشبع
  ✅ إصلاح خطأ التوقيت المنطقي: حذف sleep(600) والاعتماد على فحص كل 60 ثانية
  ✅ إصلاح خطأ الكراش: تصحيح المتغير ution['tp2'] إلى analysis['tp2']
═══════════════════════════════════════════════════════════════════════
"""

import asyncio, aiohttp, json, math, os, sys, time, logging, requests
import pandas as pd
import numpy as np
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

logger = logging.getLogger('SniperV7')
logger.setLevel(logging.INFO)
fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh = RotatingFileHandler('bot_v7.log', maxBytes=2*1024*1024, backupCount=1, encoding='utf-8')
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
                    requests.post(url, data={'chat_id': cid, 'text': msg_text, 'parse_mode': 'Markdown'}, timeout=5)
        except: pass

tg_handler = TelegramLoggingHandler()
tg_handler.setLevel(logging.ERROR)
logger.addHandler(tg_handler)


# ═══════════════════════ قاعدة البيانات ═════════════════════
class DatabaseManager:
    def __init__(self, db_name='sniper_v7.db'):
        self.db_name = db_name

    async def init_db(self):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS active_trades (
                symbol TEXT PRIMARY KEY, side TEXT, entry_price REAL, quantity REAL,
                sl REAL, tp REAL, trailing_active INTEGER, highest_price REAL,
                lowest_price REAL, entry_time REAL, partial_closed INTEGER)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY, realized_pnl REAL, wins INTEGER, losses INTEGER)''')
            await db.commit()

    async def save_trade(self, t):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''INSERT OR REPLACE INTO active_trades VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (t['symbol'], t['side'], t['entry_price'], t['quantity'],
                 t['sl'], t['tp'], int(t['trailing_active']),
                 t.get('highest_price', 0), t.get('lowest_price', 999999),
                 t['entry_time'], int(t.get('partial_closed', 0))))
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
                        'lowest_price': row[8], 'entry_time': row[9], 'partial_closed': bool(row[10])
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


# ═══════════════════════ محرك SMC - صياد الحيتان ═════════════════════
class WhaleSMCEngine:
    @staticmethod
    def detect_order_blocks(df, trend):
        obs = []
        threshold = 0.015 # الدفع العنيف 1.5%
        
        for i in range(2, len(df)-1):
            if df['close'].iloc[i] > df['open'].iloc[i]: 
                impulse_pct = (df['close'].iloc[i] - df['low'].iloc[i-1]) / df['low'].iloc[i-1]
                if df['close'].iloc[i-1] < df['open'].iloc[i-1] and impulse_pct > threshold:
                    obs.append({'type': 'demand', 'top': df['open'].iloc[i-1], 'bottom': df['low'].iloc[i-1], 'index': i-1})
            
            elif df['close'].iloc[i] < df['open'].iloc[i]: 
                impulse_pct = (df['high'].iloc[i-1] - df['close'].iloc[i]) / df['high'].iloc[i-1]
                if df['close'].iloc[i-1] > df['open'].iloc[i-1] and impulse_pct > threshold:
                    obs.append({'type': 'supply', 'top': df['high'].iloc[i-1], 'bottom': df['close'].iloc[i-1], 'index': i-1})
        return obs

    @staticmethod
    def detect_liquidity_sweep(df_15m, ob_zone, direction):
        """
        كشف تصفية السيولة من فريم 15 دقيقة (الزناد السريع)
        """
        current_low = df_15m['low'].iloc[-1]
        current_high = df_15m['high'].iloc[-1]
        current_close = df_15m['close'].iloc[-1]
        prev_close = df_15m['close'].iloc[-2]

        if direction == 'BUY' and ob_zone['type'] == 'demand':
            if current_low < ob_zone['bottom'] and current_close > ob_zone['top'] and current_close > prev_close:
                return True
                
        elif direction == 'SELL' and ob_zone['type'] == 'supply':
            if current_high > ob_zone['top'] and current_close < ob_zone['bottom'] and current_close < prev_close:
                return True
                
        return False

    @staticmethod
    def calculate_stochastic(df, k_period=14, d_period=3):
        """
        حساب مؤشر الاستوكاستيك (Stochastic Oscillator)
        """
        low_min = df['low'].rolling(window=k_period).min()
        high_max = df['high'].rolling(window=k_period).max()
        
        # تجنب القسمة على صفر
        diff = high_max - low_min
        diff = diff.replace(0, np.nan)
        
        df['stoch_k'] = 100 * ((df['close'] - low_min) / diff)
        df['stoch_d'] = df['stoch_k'].rolling(window=d_period).mean()
        
        # تعبئة القيم المفقودة
        df['stoch_k'] = df['stoch_k'].fillna(50)
        df['stoch_d'] = df['stoch_d'].fillna(50)
        return df


# ══════════════════════════════════════════════════════════════════════
#           🔥 القناص الأسطوري V7.2 (Futures Multi-TF) 🔥
# ══════════════════════════════════════════════════════════════════════
class LegendarySniperFuturesV7:
    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN', '')
        self.tg_chat = os.environ.get('CHAT_ID', '')
        self.binance_api_key = os.environ.get('BINANCE_API_KEY', '')
        self.binance_api_secret = os.environ.get('BINANCE_API_SECRET', '')

        self.TRADE_ENABLED = os.environ.get('TRADE_ENABLED', 'false').lower() == 'true'
        self.LEVERAGE = 10  # تعديل الرافعة المالية إلى 10x
        self.TRADE_SIZE_USDT = 10.0
        self.MAX_OPEN_TRADES = 5

        self.db = DatabaseManager()
        self.smc = WhaleSMCEngine()
        self.session = None

        self.data_url = "https://fapi.binance.com"
        self.trade_url = "https://fapi.binance.com"
        
        self.all_futures_pairs = []
        self.step_sizes_cache = {}
        self.live_prices = {}
        self.active_trades = {}
        
        self.volatile_targets = ['BEAT', 'PEOPLE', 'UNFI', 'CELR', 'LIT', 'SFP', 'ALICE', 'ATA', 'MASK', 'ANT']

        self.stats = {'total_scans': 0, 'trades_executed': 0, 'wins': 0, 'losses': 0}

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
        except: pass

    def _sign(self, params):
        params['timestamp'] = int(time.time() * 1000)
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
                req_params = self._sign(params.copy()) if signed and params else params
                
                async with self.session.request(method, url, params=req_params, headers=headers, timeout=15) as r:
                    if r.status == 200:
                        return await r.json()
                    elif r.status == 429:
                        await asyncio.sleep(10 * (attempt + 1))
                    elif r.status == 401:
                        logger.error("❌ خطأ في مفاتيح API!")
                        return None
                    else:
                        err = await r.text()
                        logger.warning(f"Futures API Error {r.status}: {err[:100]}")
                        return None
            except Exception as e:
                if attempt == retries - 1: return None
                await asyncio.sleep(2 ** attempt)
        return None

    async def setup_futures_account(self):
        msg = f"⚙️ *إعداد حساب العقود الآجلة (الرافعة 10x)*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        setup_count = 0
        
        for pair in self.all_futures_pairs[:50]: # نضبط أهم 50 زوج لتسريع البوت
            symbol = pair['symbol']
            try:
                lev_res = await self._fapi_request('POST', '/fapi/v1/leverage', 
                    {'symbol': symbol, 'leverage': self.LEVERAGE}, signed=True)
                
                margin_res = await self._fapi_request('POST', '/fapi/v1/marginType', 
                    {'symbol': symbol, 'marginType': 'ISOLATED'}, signed=True)
                    
                if lev_res and lev_res.get('leverage') == self.LEVERAGE:
                    setup_count += 1
            except:
                pass
            await asyncio.sleep(0.15)
            
        msg += f"✅ تم ضبط الرافعة 10x والهامش المعزول لـ {setup_count} زوج"
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

        self.all_futures_pairs = new_pairs
        logger.info(f"📊 تم تحميل {len(self.all_futures_pairs)} زوج عقود آجلة")

    def format_quantity(self, symbol, qty):
        step = self.step_sizes_cache.get(symbol, 1.0)
        precision = int(round(-math.log10(step))) if step < 1 else 0
        return math.floor(qty * (10 ** precision)) / (10 ** precision)

    async def ws_manager(self):
        streams = [f"{sym.lower()}@bookTicker" for sym in self.step_sizes_cache.keys()]
        ws_url = f"wss://fstream.binance.com/stream?streams={'/'.join(streams[:200])}"

        while True:
            try:
                async with websockets.connect(ws_url, ping_interval=20) as ws:
                    logger.info("✅ Futures WebSocket متصل!")
                    async for message in ws:
                        data = json.loads(message).get('data', {})
                        if data.get('e') == 'bookTicker':
                            self.live_prices[data['s']] = {
                                'bid': float(data['b']), 'ask': float(data['a'])
                            }
            except Exception as e:
                logger.error(f"❌ خطأ WebSocket: {str(e)[:50]}")
                await asyncio.sleep(5)

    async def get_klines(self, symbol, interval='15m', limit=100):
        data = await self._fapi_request('GET', '/fapi/v1/klines', 
            {'symbol': symbol, 'interval': interval, 'limit': limit})
        if data and len(data) > 20:
            df = pd.DataFrame(data, columns=[
                'time','open','high','low','close','volume',
                'close_time','quote_volume','trades','taker_buy_vol',
                'taker_buy_quote_vol','ignore'])
            for col in ['open','high','low','close','volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            return df
        return None

    # ═════════════════════ تحليل صيد الحيتان (Multi-TF + ATR + Stochastic) ═════════════════════
    async def analyze_whale_zone(self, symbol):
        # ═══ سر القناص: دمج 3 فريمات (4H للاتجاه، 1H للمناطق، 15M للزناد) ═══
        df_4h = await self.get_klines(symbol, '4h', 100)   # فريم 4 ساعات لتحديد الاتجاه العام (الماكرو)
        df_1h = await self.get_klines(symbol, '1h', 100)   # فريم الساعة لرسم خريطة الحيتان (Order Blocks)
        df_15m = await self.get_klines(symbol, '15m', 100) # فريم 15 دقيقة لاستخراج زناد الدخول الفعلي
        
        if df_4h is None or len(df_4h) < 30 or df_1h is None or len(df_1h) < 30 or df_15m is None or len(df_15m) < 30: 
            return None

        prices = self.live_prices.get(symbol)
        if not prices: return None

        current_price = prices['ask']

        # 1. نحدد الاتجاه من فريم الـ 4 ساعات (الاتجاه الماكرو الحقيقي)
        ema50_4h = df_4h['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        trend = 'BUY' if current_price > ema50_4h else 'SELL'

        # 2. نرسم مناطق العرض والطلب من فريم الساعة (مناطق الحيتان الكبرى)
        obs = self.smc.detect_order_blocks(df_1h, trend)
        if not obs: return None

        # 3. هل السعر قريب من منطقة الحوت؟
        nearby_ob = None
        for ob in reversed(obs):
            if trend == 'BUY' and ob['type'] == 'demand':
                distance_pct = (current_price - ob['top']) / current_price
                if 0 <= distance_pct <= 0.02: # مسافة 2% لفريم الساعة
                    nearby_ob = ob
                    break
            elif trend == 'SELL' and ob['type'] == 'supply':
                distance_pct = (ob['bottom'] - current_price) / current_price
                if 0 <= distance_pct <= 0.02:
                    nearby_ob = ob
                    break

        if not nearby_ob: return None

        # 4. نبحث عن تصفية السيولة (Sweep) من فريم 15 دقيقة (الزناد السريع)
        is_sweep = self.smc.detect_liquidity_sweep(df_15m, nearby_ob, trend)
        if not is_sweep: return None

        # 5. التأكيد النهائي بكروس الاستوكاستيك على فريم 15 دقيقة
        df_15m = self.smc.calculate_stochastic(df_15m)
        
        current_k = df_15m['stoch_k'].iloc[-1]
        prev_k = df_15m['stoch_k'].iloc[-2]
        current_d = df_15m['stoch_d'].iloc[-1]
        prev_d = df_15m['stoch_d'].iloc[-2]
        
        stoch_confirmed = False
        if trend == 'BUY':
            # كروس صعودي في منطقة التشبع البيعي (أقل من 20)
            if current_k > current_d and prev_k <= prev_d and current_k < 20:
                stoch_confirmed = True
        elif trend == 'SELL':
            # كروس هبوطي في منطقة التشبع الشرائي (أعلى من 80)
            if current_k < current_d and prev_k >= prev_d and current_k > 80:
                stoch_confirmed = True
                
        if not stoch_confirmed: return None

        # ═══ 6. حساب الدخول والأهداف (باستخدام ATR لمواجهة التقلب العنيف) ═══
        entry_price = current_price
        
        # حساب ATR لمعرفة متوسط تقلب العملة من فريم 15 دقيقة
        df_15m['high_low'] = df_15m['high'] - df_15m['low']
        df_15m['high_close'] = abs(df_15m['high'] - df_15m['close'].shift())
        df_15m['low_close'] = abs(df_15m['low'] - df_15m['close'].shift())
        df_15m['tr'] = df_15m[['high_low', 'high_close', 'low_close']].max(axis=1)
        atr = df_15m['tr'].rolling(14).mean().iloc[-1]
        
        # الوقف يجب أن يكون 2 ضعف الـ ATR ليتجاوز ذيول الحيتان (Wicks)
        sl_buffer = atr * 2.0 
        
        if trend == 'BUY':
            sl = nearby_ob['bottom'] - sl_buffer # وقف الخسارة تحت المنطقة بمسافة آمنة
            tp1 = entry_price + (atr * 1.5)      # الهدف الأول 1.5 ضعف التقلب (Hit & Run)
            tp2 = entry_price + (atr * 4.0)      # الهدف الثاني للمتابعة
        else:
            sl = nearby_ob['top'] + sl_buffer
            tp1 = entry_price - (atr * 1.5)
            tp2 = entry_price - (atr * 4.0)

        # تحقق ألا تكون نسبة المخاطرة أكبر من المتوقع
        risk_pct = abs(entry_price - sl) / entry_price * 100
        if risk_pct > 3.0: # إذا كان الوقف يطلب خسارة أكثر من 3% (30% من الهامش مع رافعة 10x)، ارفض الصفقة
            return None

        return {
            'symbol': symbol, 'direction': trend, 'price': entry_price,
            'sl': sl, 'tp1': tp1, 'tp2': tp2, 'score': 10,
            'signals_smc': [f"🐋 صيد حوت في منطقة {'طلب' if trend=='BUY' else 'عرض'}", 
                           "⚡ تصفية سيولة (فخ للضعفاء)",
                           f"📈 كروس استوكاستك مؤكد على 15M",
                           f"🛡️ وقف واسع ({risk_pct:.1f}%) لتجنب الذيل"]
        }

    # ═════════════════════ التداول للعقود الآجلة ═════════════════════
    async def execute_trade(self, analysis):
        if not self.TRADE_ENABLED: return
        if len(self.active_trades) >= self.MAX_OPEN_TRADES: return

        symbol = analysis['symbol']
        if symbol in self.active_trades: return

        quantity = self.format_quantity(symbol, self.TRADE_SIZE_USDT / analysis['price'])
        if quantity == 0: return

        side = 'BUY' if analysis['direction'] == 'BUY' else 'SELL'

        result = await self._fapi_request('POST', '/fapi/v1/order', {
            'symbol': symbol, 'side': side, 'type': 'MARKET', 'quantity': quantity
        }, signed=True)

        if not result or result.get('status') not in ['FILLED', 'NEW']:
            await self.tg(f"❌ *فشل تنفيذ {side} (`{symbol}`)*\n⚠️ تأكد من إعدادات العقود الآجلة")
            return

        entry_price = float(result.get('avgPrice', analysis['price']))
        
        trade_data = {
            'symbol': symbol, 'side': side, 'entry_price': entry_price,
            'quantity': quantity, 'sl': analysis['sl'], 'tp': analysis['tp1'],
            'trailing_active': False, 'highest_price': entry_price,
            'lowest_price': entry_price, 'entry_time': time.time(),
            'partial_closed': False
        }
        self.active_trades[symbol] = trade_data
        await self.db.save_trade(trade_data)
        self.stats['trades_executed'] += 1

        msg = (f"✅ *صفقة عقود آجلة منفذة!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"🪙 الزوج: `{symbol}` | الرافعة: 10x\n"
               f"💵 الدخول: {self.fmt_price(entry_price)}\n"
               f"🛑 وقف الخسارة: {self.fmt_price(analysis['sl'])}\n"
               f"🎯 هدف 1 (Hit & Run): {self.fmt_price(analysis['tp1'])}\n"
               f"🚀 هدف 2 (متابعة): {self.fmt_price(analysis['tp2'])}\n"
               f"🐋 الاستراتيجية: {'طلب حوتي' if side=='BUY' else 'عرض حوتي'} + تصفية سيولة + كروس استوكاستك")
        await self.tg(msg)

    # ═════════════════════ مراقبة الصفقات (Hit & Run) ═════════════════════
    async def monitor_trades(self):
        if not self.active_trades: return

        for symbol, trade in list(self.active_trades.items()):
            prices = self.live_prices.get(symbol)
            if not prices: continue

            is_buy = trade['side'] == 'BUY'
            current_price = prices['bid'] if is_buy else prices['ask']

            if is_buy and current_price > trade.get('highest_price', 0):
                trade['highest_price'] = current_price
            elif not is_buy and current_price < trade.get('lowest_price', 999999):
                trade['lowest_price'] = current_price

            should_close, reason = False, ""
            if is_buy and current_price <= trade['sl']: should_close, reason = True, "🛑 ضرب SL"
            elif not is_buy and current_price >= trade['sl']: should_close, reason = True, "🛑 ضرب SL"

            if not trade.get('partial_closed', False):
                if (is_buy and current_price >= trade['tp1']) or (not is_buy and current_price <= trade['tp1']):
                    partial_qty = self.format_quantity(symbol, trade['quantity'] * 0.9)
                    close_side = 'SELL' if is_buy else 'BUY'
                    
                    res = await self._fapi_request('POST', '/fapi/v1/order', {
                        'symbol': symbol, 'side': close_side, 'type': 'MARKET', 'quantity': partial_qty
                    }, signed=True)

                    if res and res.get('status') in ['FILLED', 'NEW']:
                        trade['quantity'] -= partial_qty
                        trade['partial_closed'] = True
                        trade['sl'] = trade['entry_price'] * (1.001) if is_buy else trade['entry_price'] * (0.999)
                        await self.db.save_trade(trade)
                        await self.tg(f"🎯 *جني أرباح أول (`{symbol}`)*\n💸 تم إغلاق 90% بربح مؤكد!\n🛡️ الوقف نقطة الدخول الآن.")

            if trade.get('partial_closed'):
                if is_buy:
                    new_sl = trade['highest_price'] * 0.99
                    if new_sl > trade['sl']: trade['sl'] = new_sl
                else:
                    new_sl = trade['lowest_price'] * 1.01
                    if new_sl < trade['sl']: trade['sl'] = new_sl

            if should_close:
                close_side = 'SELL' if is_buy else 'BUY'
                res = await self._fapi_request('POST', '/fapi/v1/order', {
                    'symbol': symbol, 'side': close_side, 'type': 'MARKET', 'quantity': trade['quantity']
                }, signed=True)

                fill_price = float(res.get('avgPrice', current_price)) if res else current_price
                
                if is_buy: pnl = (fill_price - trade['entry_price']) * trade['quantity']
                else: pnl = (trade['entry_price'] - fill_price) * trade['quantity']

                margin_pnl_pct = (pnl / self.TRADE_SIZE_USDT) * 100 
                is_win = pnl > 0
                if is_win: self.stats['wins'] += 1
                else: self.stats['losses'] += 1

                await self.db.remove_trade(symbol)
                del self.active_trades[symbol]

                icon = "✅" if is_win else "❌"
                msg = (f"🏁 *إغلاق `{symbol}`*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                       f"{reason}\n"
                       f"💵 النتيجة: `{pnl:.4f} USDT` ({margin_pnl_pct:.1f}% من الهامش)\n"
                       f"🏆 الإجمالي: {self.stats['wins']}W / {self.stats['losses']}L")
                await self.tg(msg)

    # ═════════════════════ المسح السريع للمتقلبات ═════════════════════
    async def scan_volatile_coins(self):
        tickers = await self._fapi_request('GET', '/fapi/v1/ticker/24hr')
        if not tickers: return

        targets = []
        for t in tickers:
            symbol = t.get('symbol', '')
            change = abs(float(t.get('priceChangePercent', 0)))
            if change > 5 and symbol in self.step_sizes_cache:
                targets.append({'symbol': symbol, 'change': change})

        targets.sort(key=lambda x: x['change'], reverse=True)
        
        for coin in self.volatile_targets:
            sym = f"{coin}USDT"
            if sym in self.step_sizes_cache and sym not in [t['symbol'] for t in targets]:
                targets.append({'symbol': sym, 'change': 0})

        results = []
        for target in targets[:20]: # تقليل العدد لتخفيف الضغط على API
            symbol = target['symbol']
            if symbol in self.active_trades: continue

            analysis = await self.analyze_whale_zone(symbol)
            if analysis:
                results.append(analysis)
            await asyncio.sleep(0.5)

        if results:
            msg = "🚀 *مناطق حيتان مكتشفة!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for a in results:
                msg += (f"🐋 `{a['symbol']}` | اتجاه: *{a['direction']}*\n"
                       f"💵 {self.fmt_price(a['price'])} | SL: {self.fmt_price(a['sl'])}\n")
            await self.tg(msg)

            for a in results:
                await self.execute_trade(a)
                await asyncio.sleep(1)

    # ═════════════════════ اللوب الرئيسي ═════════════════════
    async def main_loop(self):
        self.session = aiohttp.ClientSession()
        await self.db.init_db()
        await self.load_market_data()
        self.active_trades = await self.db.load_active_trades()
        
        await self.setup_futures_account()
        
        asyncio.create_task(self.ws_manager())
        await asyncio.sleep(10)

        mode_trade = "⚔️ تداول عقود آجلة تلقائي" if self.TRADE_ENABLED else "👁️ مراقبة فقط"

        msg = ("🔥 *القناص الأسطوري V7.2 — صياد الحيتان!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"📡 الوضع: {mode_trade}\n"
               f"⚡ الرافعة: 10x | الهامش: معزول (Isolated)\n"
               f"💰 حجم الصفقة: 10$ ثابت\n"
               f"🎯 استراتيجية: اتجاه ماكرو (4H) + عرض وطلب (1H) + تصفية سيولة وكروس استوكاستيك (15M)\n"
               f"🛡️ حماية: وقف خسارة ATR ذكي (مضاد للذيل العشوائي)\n"
               f"🏃 خطة خروج: Hit & Run (90% ربح سريع + 10% وقف متحرك)\n"
               "━━━━━━━━━━━━━━━━━━━━━━━━\n⏰ بدء المسح المتقلب...")
        await self.tg(msg)

        try:
            while True:
                try:
                    await self.monitor_trades()
                    await self.scan_volatile_coins()
                    await asyncio.sleep(60) # فحص السوق كل 60 ثانية كحد أقصى لتوافق مع إغلاق شموع 15M
                except Exception as loop_err:
                    logger.error(f"خطأ في الحلقة: {loop_err}")
                    await asyncio.sleep(15)
        finally:
            await self.session.close()

    def start(self):
        asyncio.run(self.main_loop())

if __name__ == "__main__":
    bot = LegendarySniperFuturesV7()
    bot.start()
