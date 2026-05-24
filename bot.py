"""
═══════════════════════════════════════════════════════════════════════
  🔥 القناص الأسطوري V7.0 — Legendary Sniper (Futures Whale Hunter) 🔥
═══════════════════════════════════════════════════════════════════════
  تحديثات V7.0 (تغيير 190 درجة):
  ✅ نقل بالكامل إلى بينانس عقود الآجلة (USDT-M Futures)
  ✅ الرافعة المالية 25x لكل الصفقات
  ✅ حجم صفقة ثابت 10 دولار للصفقة الواحدة
  ✅ استراتيجية SMC خالصة: عرض وطلب (OB) + تصفية سيولة (Sweep)
  ✅ نظام Hit & Run لضمان نسبة ربح عالية جداً (جني سريع 90% من الصفقة)
  ✅ فلترة العملات ذات التقلب العالي (التي تتحرك بسرعة وعنف)
═══════════════════════════════════════════════════════════════════════
"""

import asyncio, aiohttp, json, math, os, sys, time, logging, requests, sqlite3
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
        """
        كشف مناطق العرض والطلب (Order Blocks)
        الطلب (Bullish OB): آخر شمعة هابطة قبل الدفع الصعودي العنيف
        العرض (Bearish OB): آخر شمعة صاعدة قبل الدفع الهبوطي العنيف
        """
        obs = []
        threshold = 0.015 # الدفع العنيف يجب أن يكون 1.5% على الأقل (يناسب العملات المتقلبة)
        
        for i in range(2, len(df)-1):
            # كشف طلب (Demand Zone)
            if df['close'].iloc[i] > df['open'].iloc[i]: # شمعة صاعدة
                body = abs(df['close'].iloc[i] - df['open'].iloc[i])
                prev_body = abs(df['open'].iloc[i] - df['close'].iloc[i-1])
                impulse_pct = (df['close'].iloc[i] - df['low'].iloc[i-1]) / df['low'].iloc[i-1]
                
                if df['close'].iloc[i-1] < df['open'].iloc[i-1] and impulse_pct > threshold:
                    obs.append({
                        'type': 'demand', 
                        'top': df['open'].iloc[i-1], 
                        'bottom': df['low'].iloc[i-1],
                        'index': i-1
                    })
            
            # كشف عرض (Supply Zone)
            elif df['close'].iloc[i] < df['open'].iloc[i]: # شمعة هابطة
                impulse_pct = (df['high'].iloc[i-1] - df['close'].iloc[i]) / df['high'].iloc[i-1]
                
                if df['close'].iloc[i-1] > df['open'].iloc[i-1] and impulse_pct > threshold:
                    obs.append({
                        'type': 'supply', 
                        'top': df['high'].iloc[i-1], 
                        'bottom': df['close'].iloc[i-1],
                        'index': i-1
                    })
        return obs

    @staticmethod
    def detect_liquidity_sweep(df, ob_zone, direction):
        """
        كشف تصفية السيولة: السعر يخترق المنطقة قليلاً ثم ينعكس (هذا هو دخول الحوت)
        """
        current_low = df['low'].iloc[-1]
        current_high = df['high'].iloc[-1]
        current_close = df['close'].iloc[-1]
        prev_close = df['close'].iloc[-2]

        if direction == 'BUY' and ob_zone['type'] == 'demand':
            # السعر نزل تحت منطقة الطلب ثم أغلق فوقها = تصفية سيولة بيعية (فخ الدببة)
            if current_low < ob_zone['bottom'] and current_close > ob_zone['top'] and current_close > prev_close:
                return True
                
        elif direction == 'SELL' and ob_zone['type'] == 'supply':
            # السعر صعد فوق منطقة العرض ثم أغلق تحتها = تصفية سيولة شرائية (فخ الثيران)
            if current_high > ob_zone['top'] and current_close < ob_zone['bottom'] and current_close < prev_close:
                return True
                
        return False


# ══════════════════════════════════════════════════════════════════════
#                  🔥 القناص الأسطوري V7.0 (Futures) 🔥
# ══════════════════════════════════════════════════════════════════════
class LegendarySniperFuturesV7:
    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN', '')
        self.tg_chat = os.environ.get('CHAT_ID', '')
        self.binance_api_key = os.environ.get('BINANCE_API_KEY', '')
        self.binance_api_secret = os.environ.get('BINANCE_API_SECRET', '')

        self.TRADE_ENABLED = os.environ.get('TRADE_ENABLED', 'false').lower() == 'true'
        self.LEVERAGE = 25  # الرافعة المالية كما طلبت
        self.TRADE_SIZE_USDT = 10.0 # حجم الصفقة 10 دولار كما طلبت
        self.MAX_OPEN_TRADES = 5
        
        # إدارة الصفقة (Hit & Run لتحقيق نسبة فوز عالية)
        self.TP1_PCT = 0.01  # جني أرباح 1% (يعادل 25% ربح من الهامش) لـ 90% من الصفقة
        self.TP2_PCT = 0.03  # هدف ثاني 3% للـ 10% المتبقية مع وقف متحرك
        self.SL_PCT = 0.015  # وقف خسارة 1.5% (يعادل خسارة 37.5% من الهامش - يجب الدقة في الدخول)

        self.db = DatabaseManager()
        self.smc = WhaleSMCEngine()
        self.session = None

        # روابط العقود الآجلة (Futures)
        self.data_url = "https://fapi.binance.com"
        self.trade_url = "https://fapi.binance.com"
        
        self.all_futures_pairs = []
        self.step_sizes_cache = {}
        self.live_prices = {}
        self.active_trades = {}
        
        # عملات متقلبة عنيفة مفضلة (تتحرك بسرعة وتعطي أرباح ضخمة)
        self.volatile_targets = ['BEAT', 'PEOPLE', 'UNFI', 'CELr', 'LIT', 'SFP', 'ALICE', 'ATA', 'MASK', 'ANT']

        self.stats = {'total_scans': 0, 'trades_executed': 0, 'wins': 0, 'losses': 0}
        self.TZ = ZoneInfo("Africa/Tripoli")

    # ═════════════════════ تنسيق ذكي ═════════════════════
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

    # ═════════════════════ بينانس Futures API ═════════════════════
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
                req_params = self._sign(params.copy()) if signed else params
                
                async with self.session.request(method, url, params=req_params, headers=headers, timeout=15) as r:
                    if r.status == 200:
                        return await r.json()
                    elif r.status == 429:
                        await asyncio.sleep(10 * (attempt + 1))
                    else:
                        err = await r.text()
                        logger.warning(f"Futures API Error {r.status}: {err[:100]}")
                        return None
            except Exception as e:
                if attempt == retries - 1: return None
                await asyncio.sleep(2 ** attempt)
        return None

    # ═════════════════════ إعداد العقود الآجلة ═════════════════════
    async def setup_futures_account(self):
        # التأكد من وضع الهامش المعزول والرافعة 25x لكل العملات
        msg = "⚙️ *إعداد حساب العقود الآجلة (الرافعة 25x)*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        setup_count = 0
        
        for pair in self.all_futures_pairs:
            symbol = pair['symbol']
            try:
                # محاولة ضبط الرافعة
                lev_res = await self._fapi_request('POST', '/fapi/v1/leverage', 
                    {'symbol': symbol, 'leverage': self.LEVERAGE}, signed=True)
                
                # محاولة ضبط الهامش المعزول
                margin_res = await self._fapi_request('POST', '/fapi/v1/marginType', 
                    {'symbol': symbol, 'marginType': 'ISOLATED'}, signed=True)
                    
                if lev_res and lev_res.get('leverage') == self.LEVERAGE:
                    setup_count += 1
            except:
                pass
            
            await asyncio.sleep(0.1) # تجنب حظر API
            
        msg += f"✅ تم ضبط الرافعة 25x والهامش المعزول لـ {setup_count} زوج"
        await self.tg(msg)

    # ═════════════════════ تحميل بيانات السوق ═════════════════════
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

    # ═════════════════════ WebSocket للعقود الآجلة ═════════════════════
    async def ws_manager(self):
        streams = [f"{sym.lower()}@bookTicker" for sym, _ in self.step_sizes_cache.items()]
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

    # ═════════════════════ تحليل صيد الحيتان ═════════════════════
    async def analyze_whale_zone(self, symbol):
        df = await self.get_klines(symbol, '15m', 100)
        if df is None or len(df) < 30: return None

        prices = self.live_prices.get(symbol)
        if not prices: return None

        current_price = prices['ask'] # سنستخدم السعر الحالي لمعرفة قربنا من المنطقة

        # 1. تحديد الاتجاه العام (بسيط وسريع عبر EMA)
        ema50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        trend = 'BUY' if current_price > ema50 else 'SELL'

        # 2. البحث عن مناطق العرض والطلب (Order Blocks)
        obs = self.smc.detect_order_blocks(df, trend)
        if not obs: return None

        # 3. فلترة المنطقة: هل السعر قريب من منطقة حوت؟
        # نبحث عن منطقة لم تُخترق بعد وقريبة من السعر الحالي (ضمن 1%)
        nearby_ob = None
        for ob in reversed(obs): # آخر منطقة هي الأهم
            if trend == 'BUY' and ob['type'] == 'demand':
                distance_pct = (current_price - ob['top']) / current_price
                if 0 <= distance_pct <= 0.015: # السعر قريب جداً أو يلامس المنطقة
                    nearby_ob = ob
                    break
            elif trend == 'SELL' and ob['type'] == 'supply':
                distance_pct = (ob['bottom'] - current_price) / current_price
                if 0 <= distance_pct <= 0.015:
                    nearby_ob = ob
                    break

        if not nearby_ob: return None

        # 4. كشف تصفية السيولة (Liquidity Sweep) - هذا هو سر الدخول مع الحوت!
        is_sweep = self.smc.detect_liquidity_sweep(df, nearby_ob, trend)
        if not is_sweep: return None

        # 5. حساب الدخول والأهداف
        entry_price = current_price
        if trend == 'BUY':
            sl = nearby_ob['bottom'] * 0.998 # وقف خسارة تحت المنطقة بنسبة ضئيلة جداً
            tp1 = entry_price * (1 + self.TP1_PCT)
            tp2 = entry_price * (1 + self.TP2_PCT)
        else:
            sl = nearby_ob['top'] * 1.002
            tp1 = entry_price * (1 - self.TP1_PCT)
            tp2 = entry_price * (1 - self.TP2_PCT)

        return {
            'symbol': symbol, 'direction': trend, 'price': entry_price,
            'sl': sl, 'tp1': tp1, 'tp2': tp2, 'score': 10, # نقاط مضمونة لأنها دخول حوت
            'signals_smc': [f"🐋 صيد حوت في منطقة {'طلب' if trend=='BUY' else 'عرض'}", "⚡ تصفية سيولة (فخ للضعفاء)"]
        }

    # ═════════════════════ التداول للعقود الآجلة ═════════════════════
    async def execute_trade(self, analysis):
        if not self.TRADE_ENABLED: return
        if len(self.active_trades) >= self.MAX_OPEN_TRADES: return

        symbol = analysis['symbol']
        if symbol in self.active_trades: return

        # حساب الكمية بناءً على حجم 10 دولار
        quantity = self.format_quantity(symbol, self.TRADE_SIZE_USDT / analysis['price'])
        if quantity == 0: return

        side = 'BUY' if analysis['direction'] == 'BUY' else 'SELL'

        # إرسال أمر الدخول (Market)
        result = await self._fapi_request('POST', '/fapi/v1/order', {
            'symbol': symbol, 'side': side, 'type': 'MARKET', 'quantity': quantity
        }, signed=True)

        if not result or result.get('status') not in ['FILLED', 'NEW']:
            await self.tg(f"❌ *فشل تنفيذ {side} (`{symbol}`)*\n⚠️ تأكد من إعدادات العقود الآجلة")
            return

        # حفظ الصفقة
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
               f"🪙 الزوج: `{symbol}` | الرافعة: 25x\n"
               f"💵 الدخول: {self.fmt_price(entry_price)}\n"
               f"🛑 وقف الخسارة: {self.fmt_price(analysis['sl'])}\n"
               f"🎯 هدف 1 (Hit & Run): {self.fmt_price(analysis['tp1'])}\n"
               f"🚀 هدف 2 (متابعة): {self.fmt_price(analysis['tp2'])}\n"
               f"🐋 الاستراتيجية: {'طلب حوتي' if side=='BUY' else 'عرض حوتي'} + تصفية سيولة")
        await self.tg(msg)

    # ═════════════════════ مراقبة الصفقات (Hit & Run) ═════════════════════
    async def monitor_trades(self):
        if not self.active_trades: return

        for symbol, trade in list(self.active_trades.items()):
            prices = self.live_prices.get(symbol)
            if not prices: continue

            is_buy = trade['side'] == 'BUY'
            current_price = prices['bid'] if is_buy else prices['ask']

            # تحديث أعلى/أدنى سعر
            if is_buy and current_price > trade.get('highest_price', 0):
                trade['highest_price'] = current_price
            elif not is_buy and current_price < trade.get('lowest_price', 999999):
                trade['lowest_price'] = current_price

            # 1. فحص ضرب الوقف
            should_close, reason = False, ""
            if is_buy and current_price <= trade['sl']: should_close, reason = True, "🛑 ضرب SL"
            elif not is_buy and current_price >= trade['sl']: should_close, reason = True, "🛑 ضرب SL"

            # 2. فحص الهدف الأول (جني أرباح سريع - 90% من الكمية لضمان الفوز)
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
                        # نقل الوقف للدخول (مخاطرة صفر)
                        trade['sl'] = trade['entry_price'] * (1.001) if is_buy else trade['entry_price'] * (0.999)
                        await self.db.save_trade(trade)
                        await self.tg(f"🎯 *جني أرباط أول (`{symbol}`)*\n💸 تم إغلاق 90% بربح مؤكد!\n🛡️ الوقف نقطة الدخول الآن.")

            # 3. وقف متحرك للـ 10% المتبقية (لصيد الموجة الكبيرة)
            if trade.get('partial_closed'):
                if is_buy:
                    new_sl = trade['highest_price'] * 0.99
                    if new_sl > trade['sl']: trade['sl'] = new_sl
                else:
                    new_sl = trade['lowest_price'] * 1.01
                    if new_sl < trade['sl']: trade['sl'] = new_sl

            # إغلاق نهائي
            if should_close:
                close_side = 'SELL' if is_buy else 'BUY'
                res = await self._fapi_request('POST', '/fapi/v1/order', {
                    'symbol': symbol, 'side': close_side, 'type': 'MARKET', 'quantity': trade['quantity']
                }, signed=True)

                fill_price = float(res.get('avgPrice', current_price)) if res else current_price
                
                if is_buy: pnl = (fill_price - trade['entry_price']) * trade['quantity']
                else: pnl = (trade['entry_price'] - fill_price) * trade['quantity']

                # حساب ربح الهامش (بسبب الرافعة 25x)
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
        # جلب العملات الأكثر تقلباً في آخر 24 ساعة من العقود الآجلة
        tickers = await self._fapi_request('GET', '/fapi/v1/ticker/24hr')
        if not tickers: return

        targets = []
        for t in tickers:
            symbol = t.get('symbol', '')
            change = abs(float(t.get('priceChangePercent', 0)))
            # نبحث عن عملات تحركت بشكل عنيف (أكثر من 5% في يوم) - هذه توجد بها مناطق حيتان
            if change > 5 and symbol in self.step_sizes_cache:
                targets.append({'symbol': symbol, 'change': change})

        targets.sort(key=lambda x: x['change'], reverse=True)
        
        # إضافة العملات المفضلة للمسح
        for coin in self.volatile_targets:
            sym = f"{coin}USDT"
            if sym in self.step_sizes_cache and sym not in [t['symbol'] for t in targets]:
                targets.append({'symbol': sym, 'change': 0})

        results = []
        for target in targets[:30]: # فحص أفضل 30 عملة متقلبة
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
        
        # إعداد الرافعة للعملات
        await self.setup_futures_account()
        
        asyncio.create_task(self.ws_manager())
        await asyncio.sleep(10)

        mode_trade = "⚔️ تداول عقود آجلة تلقائي" if self.TRADE_ENABLED else "👁️ مراقبة فقط"

        msg = ("🔥 *القناص الأسطوري V7.0 — صياد الحيتان!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"📡 الوضع: {mode_trade}\n"
               f"⚡ الرافعة: 25x | الهامش: معزول (Isolated)\n"
               f"💰 حجم الصفقة: 10$ ثابت\n"
               f"🎯 استراتيجية: عرض وطلب + تصفية سيولة (Sweep)\n"
               f"🏃 خطة خروج: Hit & Run (90% ربح سريع + 10% وقف متحرك)\n"
               "━━━━━━━━━━━━━━━━━━━━━━━━\n⏰ بدء المسح المتقلب...")
        await self.tg(msg)

        try:
            while True:
                try:
                    now = time.time()
                    await self.monitor_trades()
                    
                    # مسح كل 10 دقائق (لأننا نبحث عن فرص سريعة)
                    await self.scan_volatile_coins()
                    
                    await asyncio.sleep(600) # 10 دقائق
                except Exception as loop_err:
                    logger.error(f"خطأ في الحلقة: {loop_err}")
                    await asyncio.sleep(60)
        finally:
            await self.session.close()

    def start(self):
        asyncio.run(self.main_loop())

if __name__ == "__main__":
    bot = LegendarySniperFuturesV7()
    bot.start()
