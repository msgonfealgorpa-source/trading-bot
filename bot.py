"""
═══════════════════════════════════════════════════════════════
  🔥 القناص الأسطوري V3.0 — النسخة الاحترافية العالمية 🔥
═══════════════════════════════════════════════════════════════
"""

import asyncio, aiohttp, json, math, os, sys, time, logging, requests
import pandas as pd
import ta
import hmac
import hashlib
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
import websockets

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ═══ إعداد نظام التسجيل الاحترافي (Logging) ═══
logger = logging.getLogger('SniperBot')
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

file_handler = logging.FileHandler('bot.log', encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

class TelegramLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            if record.levelno >= logging.ERROR:
                tg_token = os.environ.get('TELEGRAM_TOKEN', '')
                tg_chat = os.environ.get('CHAT_ID', '')
                if tg_token and tg_chat:
                    msg = f"🚨 *خطأ حرج:*\n```\n{self.format(record)[:400]}\n```"
                    url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
                    requests.post(url, data={'chat_id': tg_chat, 'text': msg, 'parse_mode': 'Markdown'}, timeout=5)
        except Exception:
            pass

tg_handler = TelegramLoggingHandler()
tg_handler.setLevel(logging.ERROR)
logger.addHandler(tg_handler)

class LegendarySniperBotV3:
    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN', '')
        self.tg_chat = os.environ.get('CHAT_ID', '')
        self.binance_api_key = os.environ.get('BINANCE_API_KEY', '')
        self.binance_api_secret = os.environ.get('BINANCE_API_SECRET', '')
        
        self.TRADE_ENABLED = os.environ.get('TRADE_ENABLED', 'false').lower() == 'true'
        self.BACKTEST_MODE = os.environ.get('BACKTEST_MODE', 'false').lower() == 'true'
        self.RISK_PER_TRADE_PCT = float(os.environ.get('RISK_PCT', '2'))
        self.MIN_SCORE_TO_TRADE = int(os.environ.get('MIN_SCORE', '6'))
        self.MAX_OPEN_TRADES = int(os.environ.get('MAX_TRADES', '3'))
        self.MIN_TRADE_USDT = float(os.environ.get('MIN_TRADE_USDT', '10'))

        self.usdt_pairs = []
        self.known_symbols = set()
        self.active_trades = {}
        self.stats = {'total_scans': 0, 'signals_found': 0, 'trades_executed': 0, 'wins': 0, 'losses': 0}
        self.step_sizes_cache = {}
        
        self.ws_url = "wss://testnet.binance.vision/ws"
        self.live_prices = {}
        self.session = None

        mode = "Backtest" if self.BACKTEST_MODE else ("Auto Trade" if self.TRADE_ENABLED else "Monitor Only")
        logger.info(f"🔥 القناص الأسطوري V3.0 بدأ التشغيل — الوضع: {mode}")

    async def tg(self, msg):
        try:
            if not self.session: return
            if not self.tg_token or not self.tg_chat: return
            if len(msg) > 4000:
                for i in range(0, len(msg), 4000):
                    await self.session.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                                            data={'chat_id': self.tg_chat, 'text': msg[i:i+4000], 'parse_mode': 'Markdown'})
                    await asyncio.sleep(0.5)
            else:
                await self.session.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                                        data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'})
        except Exception as e:
            logger.error(f"فشل إرسال تيليجرام: {e}")

    def _sign(self, params):
        params['timestamp'] = int(time.time() * 1000)
        query = urlencode(params)
        signature = hmac.new(self.binance_api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        params['signature'] = signature
        return params

    async def _binance_request(self, method, endpoint, params=None, signed=False):
        try:
            base = "https://testnet.binance.vision"
            url = f"{base}{endpoint}"
            headers = {}
            if signed:
                if not self.binance_api_key: return None
                params = self._sign(params or {})
                headers = {'X-MBX-APIKEY': self.binance_api_key}

            async with self.session.request(method, url, params=params, headers=headers) as r:
                if r.status == 200: return await r.json()
                elif r.status == 429: 
                    await asyncio.sleep(10); return None
                else: 
                    return None
        except Exception as e:
            logger.error(f"استثناء بينانس: {e}")
            return None

    async def load_market_data(self):
        data = await self._binance_request('GET', '/api/v3/exchangeInfo')
        if not data: return
        new_pairs, new_symbols_set = [], set()
        for s in data.get('symbols', []):
            if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING':
                new_pairs.append({'symbol': s['symbol'], 'baseAsset': s['baseAsset']})
                new_symbols_set.add(s['symbol'])
                for f in s.get('filters', []):
                    if f['filterType'] == 'LOT_SIZE':
                        self.step_sizes_cache[s['symbol']] = float(f['stepSize'])
        
        self.usdt_pairs = new_pairs
        self.known_symbols = new_symbols_set
        logger.info(f"تم تحميل {len(self.usdt_pairs)} زوج.")

    async def get_klines(self, symbol, interval='15m', limit=100):
        data = await self._binance_request('GET', '/api/v3/klines', {'symbol': symbol, 'interval': interval, 'limit': limit})
        if data and len(data) > 20:
            df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_volume', 'trades', 'taker_buy_vol', 'taker_buy_quote_vol', 'ignore'])
            for col in ['open', 'high', 'low', 'close', 'volume']: df[col] = pd.to_numeric(df[col], errors='coerce')
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            return df
        return None

    def detect_order_blocks(self, df, is_bullish_trend):
        if df is None or len(df) < 10: return None
        if is_bullish_trend:
            for i in range(len(df)-1, 3, -1):
                prev_candle = df.iloc[i-1]
                curr_candle = df.iloc[i]
                if prev_candle['close'] < prev_candle['open'] and curr_candle['close'] > prev_candle['high']:
                    return {'type': 'bullish', 'high': prev_candle['high'], 'low': prev_candle['low']}
        elif not is_bullish_trend:
            for i in range(len(df)-1, 3, -1):
                prev_candle = df.iloc[i-1]
                curr_candle = df.iloc[i]
                if prev_candle['close'] > prev_candle['open'] and curr_candle['close'] < prev_candle['low']:
                    return {'type': 'bearish', 'high': prev_candle['high'], 'low': prev_candle['low']}
        return None

    async def analyze_coin(self, symbol):
        try:
            df_4h = await self.get_klines(symbol, '4h', 50)
            if df_4h is None or len(df_4h) < 50: return None
            
            ema50_calc = ta.trend.EMAIndicator(df_4h['close'], window=50).ema_indicator()
            if ema50_calc.isna().iloc[-1]: return None
            ema50_4h = ema50_calc.iloc[-1]
            is_bullish_trend = df_4h.iloc[-1]['close'] > ema50_4h

            df_15m = await self.get_klines(symbol, '15m', 100)
            if df_15m is None or len(df_15m) < 50: return None

            price = df_15m.iloc[-1]['close']
            result = {'symbol': symbol, 'price': price, 'score': 0, 'signals': [], 'direction': None}

            rsi_val = ta.momentum.RSIIndicator(df_15m['close'], window=14).rsi().iloc[-1]
            if is_bullish_trend and rsi_val < 35: 
                result['score'] += 2; result['signals'].append("RSI Oversold")

            macd_ind = ta.trend.MACD(df_15m['close'])
            if macd_ind.macd().iloc[-1] > macd_ind.macd_signal().iloc[-1] and macd_ind.macd().iloc[-2] <= macd_ind.macd_signal().iloc[-2]:
                result['score'] += 2; result['signals'].append("MACD Cross")

            vol_avg = df_15m['volume'].rolling(20).mean().iloc[-1]
            if df_15m.iloc[-1]['volume'] > vol_avg * 2: 
                result['score'] += 2; result['signals'].append("High Volume")

            ob = self.detect_order_blocks(df_15m, is_bullish_trend)
            if ob and is_bullish_trend and ob['type'] == 'bullish':
                if ob['low'] <= price <= ob['high'] * 1.01:
                    result['score'] += 4
                    result['signals'].append("Order Block!")
            
            if is_bullish_trend and result['score'] >= self.MIN_SCORE_TO_TRADE: 
                result['direction'] = 'BUY'
            elif not is_bullish_trend and result['score'] <= -self.MIN_SCORE_TO_TRADE: 
                result['direction'] = 'SELL'

            return result
        except Exception as e:
            logger.error(f"خطأ تحليل {symbol}: {e}")
            return None

    async def websocket_listener(self):
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    subscribe_msg = {"method": "SUBSCRIBE", "params": ["!miniTicker@arr"], "id": 1}
                    await ws.send(json.dumps(subscribe_msg))
                    logger.info("✅ WebSockets Connected")
                    while True:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        if isinstance(data, list):
                            for t in data:
                                self.live_prices[t['s']] = float(t['c'])
            except Exception as e:
                logger.error(f"WS Error: {e}")
                await asyncio.sleep(5)

    async def monitor_trades(self):
        if not self.active_trades: return
        for symbol in list(self.active_trades.keys()):
            trade = self.active_trades[symbol]
            current_price = self.live_prices.get(symbol)
            if not current_price: continue
            
            entry_price = trade['entry_price']
            if current_price > trade['highest_price']: trade['highest_price'] = current_price
            closed, close_reason = False, ""

            if current_price <= trade['stop_loss'] and not trade['trailing_active']:
                closed, close_reason = True, "Stop Loss Hit"
            elif current_price >= trade['take_profit'] and not trade['trailing_active']:
                trade['trailing_active'] = True
                trade['stop_loss'] = entry_price * 1.005
                await self.tg(f"⚡ Trailing Active! `{symbol}`")
                self._save_active_trades()
            elif trade['trailing_active']:
                new_sl = trade['highest_price'] * (1 - trade['trailing_distance_pct'] / 100)
                if new_sl > trade['stop_loss']: trade['stop_loss'] = new_sl
                if current_price <= trade['stop_loss']:
                    closed, close_reason = True, "Trailing Hit!"

            if closed:
                if self.TRADE_ENABLED:
                    step_size = self.step_sizes_cache.get(symbol, 1)
                    qty = self.adjust_quantity(trade['quantity'], step_size)
                    await self._binance_request('POST', '/api/v3/order', {'symbol': symbol, 'side': 'SELL', 'type': 'MARKET', 'quantity': qty}, signed=True)
                
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                await self.tg(f"🏁 Closed `{symbol}`\nReason: {close_reason}\nResult: `{pnl_pct:+.2f}%`")
                del self.active_trades[symbol]
                self._save_active_trades()

    def adjust_quantity(self, quantity, step_size):
        if step_size >= 1: return math.floor(quantity)
        precision = len(str(step_size).rstrip('0').split('.')[-1])
        return math.floor(quantity * (10 ** precision)) / (10 ** precision)

    async def scan_market(self):
        logger.info("🔍 Scanning Market...")
        tasks = []
        pairs_to_scan = [p['symbol'] for p in self.usdt_pairs[:30] if p['symbol'] not in self.active_trades]
        for sym in pairs_to_scan:
            tasks.append(self.analyze_coin(sym))
        results = await asyncio.gather(*tasks)
        signals = [r for r in results if r and abs(r['score']) >= self.MIN_SCORE_TO_TRADE]
        
        if signals:
            signals.sort(key=lambda x: x['score'], reverse=True)
            msg = "⚡ *Strong Signals!*\n"
            for a in signals[:3]: 
                msg += f"🟢 `{a['symbol']}` | Score: *{a['score']}* | {a['signals'][0]}\n"
            await self.tg(msg)
            if self.TRADE_ENABLED and signals[0]['direction'] == 'BUY':
                await self.execute_trade(signals[0])

    async def execute_trade(self, analysis):
        symbol, price = analysis['symbol'], analysis['price']
        balance_data = await self._binance_request('GET', '/api/v3/account', signed=True)
        usdt_balance = 0
        if balance_data:
            for b in balance_data.get('balances', []):
                if b['asset'] == 'USDT': usdt_balance = float(b['free'])
        
        trade_amount = usdt_balance * (self.RISK_PER_TRADE_PCT / 100)
        if trade_amount < self.MIN_TRADE_USDT: return

        df = await self.get_klines(symbol, '15m', 30)
        atr = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range().iloc[-1]
        atr_pct = (atr / price) * 100
        
        sl_price = price * (1 - (atr_pct * 1.5) / 100)
        tp_price = price * (1 + (atr_pct * 3.0) / 100)
        trailing_dist = atr_pct * 1.5

        result = await self._binance_request('POST', '/api/v3/order', {
            'symbol': symbol, 'side': 'BUY', 'type': 'MARKET', 'quoteOrderQty': round(trade_amount, 2)
        }, signed=True)

        if result and result.get('status') == 'FILLED':
            fill_price, fill_qty = float(result['fills'][0]['price']), float(result['fills'][0]['qty'])
            self.active_trades[symbol] = {
                'entry_price': fill_price, 'quantity': fill_qty,
                'stop_loss': sl_price, 'take_profit': tp_price,
                'trailing_distance_pct': trailing_dist,
                'highest_price': fill_price, 'trailing_active': False, 'entry_time': time.time()
            }
            self._save_active_trades()
            await self.tg(f"✅ BUY `{symbol}`\nEntry: `{fill_price:.4f}`")

    def _save_active_trades(self):
        try:
            with open('active_trades.json', 'w') as f: json.dump(self.active_trades, f)
        except Exception: pass

    def _load_active_trades(self):
        try:
            if os.path.exists('active_trades.json'):
                with open('active_trades.json', 'r') as f: self.active_trades = json.load(f)
        except Exception: self.active_trades = {}

    async def main_loop(self):
        self.session = aiohttp.ClientSession()
        await self.load_market_data()
        self._load_active_trades()
        await self.tg("🔥 *Sniper Bot V3.0 is LIVE!*")
        
        asyncio.create_task(self.websocket_listener())
        scan_counter = 0
        try:
            while True:
                scan_counter += 1
                await self.monitor_trades()
                if scan_counter % 900 == 0:
                    await self.scan_market()
                await asyncio.sleep(1)
        except Exception as e:
            logger.critical(f"System Crash: {e}")
        finally:
            await self.session.close()

    def start(self):
        asyncio.run(self.main_loop())

if __name__ == "__main__":
    bot = LegendarySniperBotV3()
    bot.start()
