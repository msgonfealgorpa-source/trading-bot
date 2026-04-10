import ccxt
import time
import pandas as pd
import ta 
import requests
import datetime 

class PerformanceTracker:
    def __init__(self, telegram_token, chat_id, exchange_client):
        self.trades_log = []
        self.TELEGRAM_TOKEN = telegram_token
        self.CHAT_ID = chat_id
        self.exchange = exchange_client 
        self.send_telegram = lambda msg: self._send_telegram(msg) 

    def _send_telegram(self, message):
        try:
            url = f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, data={'chat_id': self.CHAT_ID, 'text': message, 'parse_mode': 'Markdown'})
        except Exception as e:
            print(f"❌ خطأ في إرسال التلجرام (Tracker): {e}")

    def log_trade(self, symbol, entry_price, exit_price, quantity, is_profit, profit_pct, reason):
        formatted_quantity = self.exchange.amount_to_precision(symbol, quantity)
        self.trades_log.append({
            'timestamp': datetime.datetime.now(),
            'symbol': symbol,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'quantity': float(formatted_quantity), 
            'is_profit': is_profit,
            'profit_pct': profit_pct,
            'reason': reason
        })
        print(f"Trade Logged: {symbol} | Profit: {profit_pct:.2f}% | Reason: {reason}")

    def get_stats(self):
        if not self.trades_log:
            return {"total_trades": 0, "win_rate": 0, "total_profit_sum_pct": 0, "avg_profit_pct_wins": 0, "avg_loss_pct_losses": 0, "best_trade_pct": 0, "worst_trade_pct": 0}
        total_trades = len(self.trades_log)
        winning_trades = [t for t in self.trades_log if t['is_profit']]
        losing_trades = [t for t in self.trades_log if not t['is_profit']]
        win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
        all_profit_pct = [t['profit_pct'] for t in self.trades_log]
        total_profit_sum_pct = sum(all_profit_pct)
        avg_profit_pct_wins = sum([t['profit_pct'] for t in winning_trades]) / len(winning_trades) if winning_trades else 0
        avg_loss_pct_losses = sum([t['profit_pct'] for t in losing_trades]) / len(losing_trades) if losing_trades else 0
        best_trade_pct = max(all_profit_pct) if all_profit_pct else 0
        worst_trade_pct = min(all_profit_pct) if all_profit_pct else 0
        return {"total_trades": total_trades, "win_rate": win_rate, "total_profit_sum_pct": total_profit_sum_pct, "avg_profit_pct_wins": avg_profit_pct_wins, "avg_loss_pct_losses": avg_loss_pct_losses, "best_trade_pct": best_trade_pct, "worst_trade_pct": worst_trade_pct}

    def _generate_daily_report(self):
        stats = self.get_stats()
        report = f"📊 *تقرير أداء البوت اليومي*\n\n"
        report += f"📅 التاريخ: {datetime.date.today().strftime('%Y-%m-%d')}\n"
        report += f"🚀 إجمالي الصفقات: {stats['total_trades']}\n"
        report += f"🏆 نسبة الفوز (Win Rate): {stats['win_rate']:.2f}%\n"
        report += f"📈 إجمالي الربح (Sum %): {stats['total_profit_sum_pct']:.2f}%\n"
        report += f"💰 متوسط ربح الصفقة الرابحة: {stats['avg_profit_pct_wins']:.2f}%\n"
        report += f"💸 متوسط خسارة الصفقة الخاسرة: {stats['avg_loss_pct_losses']:.2f}%\n"
        report += f"🌟 أفضل صفقة: {stats['best_trade_pct']:.2f}%\n"
        report += f"❌ أسوأ صفقة: {stats['worst_trade_pct']:.2f}%\n\n"
        if self.trades_log:
            best_strat_trade = max(self.trades_log, key=lambda t: t['profit_pct'])
            worst_strat_trade = min(self.trades_log, key=lambda t: t['profit_pct'])
            report += f"✨ **أفضل صفقة:** {best_strat_trade['symbol']} ({best_strat_trade['profit_pct']:.2f}%) - السبب: {best_strat_trade['reason']}\n"
            report += f"⚠️ **أسوأ صفقة:** {worst_strat_trade['symbol']} ({worst_strat_trade['profit_pct']:.2f}%) - السبب: {worst_strat_trade['reason']}\n"
        return report
        
    def send_daily_report(self):
        report = self._generate_daily_report()
        self.send_telegram(report)
        self.trades_log = [t for t in self.trades_log if t['timestamp'].date() == datetime.date.today()]

class LegendaryBot:
    def __init__(self):
        self.API_KEY = 'egAeFM8kVEn7YRKPIHRpJGpDW4GFuHRDHFnRmRqdEWcZxPRAb0qHbvd6T6X3MC94Ffqfgc4BSv9mxbBPXSQ'
        self.API_SECRET = 'OC7UgGik9WOSjUI6r4AvbqfZIq9O9BrjzC2LRrott95Ewcu2jQHRnjCNQj8sn9ZdKIsAf9ioAkp89xs1e7g'
        self.TELEGRAM_TOKEN = '8744586010:AAET91PN6ApW3FiX4WU1nSH_F5xoHuzIQKk'
        self.CHAT_ID = '7520475220'
        self.RISK_PER_TRADE_PCT = 1.5
        self.STOP_LOSS_ATR_MULTIPLIER = 2.5
        self.MAX_CONSECUTIVE_LOSSES = 3
        self.LOSS_SIZE_REDUCTION_FACTOR = 0.5
        self.DAILY_LOSS_LIMIT_PCT = 3.0
        self.ENTRY_CONFIRMATION_TimEframe = '15m'
        self.DIRECTION_CONFIRMATION_TimEframe = '1h'
        self.INITIAL_TRADE_AMOUNT_USD = 100
        self.STOP_LOSS_PCT = -2.5
        self.TAKE_PROFIT_PCT = 5.0
        self.TRAILING_ACTIVATE_PCT = 2.5
        self.TRAILING_DROP_PCT = 0.5
        self.MAX_RETRIES = 7
        self.RETRY_DELAY = 7
        self.MIN_VOLUME_24H = 5000000
        self.MIN_PRICE_CHANGE_PCT_DAY = 1.5
        self.exchange = ccxt.bingx({'apiKey': self.API_KEY, 'secret': self.API_SECRET, 'enableRateLimit': True, 'options': {'defaultType': 'spot'}, 'rateLimit': 2000})
        self.active_trade = None
        self.consecutive_losses = 0
        self.daily_loss = 0.0
        self.last_trade_date = None
        self.last_report_time = datetime.datetime.now()
        self.performance_tracker = PerformanceTracker(self.TELEGRAM_TOKEN, self.CHAT_ID, self.exchange)
        self.send_telegram("✨ *نظام Sniper Pro Pro Legend بدأ العمل بالتحسينات الاحترافية!*")
        self._load_markets()

    def send_telegram(self, message):
        self.performance_tracker._send_telegram(message)

    def _load_markets(self):
        try:
            self.exchange.load_markets()
            print("✅ تم تحميل معلومات الأسواق بنجاح.")
        except Exception as e:
            error_msg = f"🚨 *خطأ فادح:* فشل تحميل أسواق المنصة: {e}. سيتم إعادة المحاولة..."
            self.send_telegram(error_msg)
            print(error_msg)
            time.sleep(10)
            self._load_markets()

    def _fetch_with_retry(self, method, *args, **kwargs):
        for i in range(self.MAX_RETRIES):
            try:
                result = getattr(self.exchange, method)(*args, **kwargs)
                if result is None and method not in ['fetch_trades', 'fetch_orders']:
                    if i == self.MAX_RETRIES - 1:
                        self.send_telegram(f"🚨 *فشل متكرر في استدعاء {method} (No Data Received): {args}")
                    if i > 0:
                        print(f"⚠️ {method} ({args}): No data received. Retrying ({i+1}/{self.MAX_RETRIES})...")
                    time.sleep(self.RETRY_DELAY * (i + 1))
                    continue
                return result
            except (ccxt.NetworkError, ccxt.ExchangeError, ccxt.RequestTimeout, ccxt.BadSymbol) as e:
                print(f"⚠️ فشل استدعاء {method} ({args}): {e}. المحاولة {i+1}/{self.MAX_RETRIES}...")
                if i == self.MAX_RETRIES - 1:
                    self.send_telegram(f"🚨 *فشل متكرر في استدعاء {method}.*")
                time.sleep(self.RETRY_DELAY * (i + 1))
            except Exception as e:
                print(f"❌ خطأ غير متوقع في {method} ({args}): {e}. المحاولة {i+1}/{self.MAX_RETRIES}...")
                if i == self.MAX_RETRIES - 1:
                    self.send_telegram(f"🚨 *خطأ فادح غير متوقع في {method}.*")
                time.sleep(self.RETRY_DELAY * (i + 1))
        return None

    def _fetch_ohlcv(self, symbol, timeframe, limit):
        return self._fetch_with_retry('fetch_ohlcv', symbol, timeframe, limit=limit)

    def _fetch_ticker(self, symbol):
        return self._fetch_with_retry('fetch_ticker', symbol)

    def _create_order(self, order_type, symbol, qty, price=None, params={}):
        method = f'create_market_{order_type}_order' if price is None else f'create_limit_{order_type}_order'
        args = [symbol, qty]
        if price is not None:
            args.append(price)
        order = self._fetch_with_retry(method, *args, params=params)
        if order and order.get('id'):
            print(f"✅ تم تنفيذ الأمر {order_type} لـ {symbol}: ID {order.get('id')}")
            return order
        else:
            self.send_telegram(f"⚠️ *فشل تنفيذ الأمر {order_type} لـ {symbol} بعد عدة محاولات.*")
            return None
            
    def _fetch_balance(self):
        return self._fetch_with_retry('fetch_balance')
        
    def _fetch_tickers(self):
        return self._fetch_with_retry('fetch_tickers')

    def _get_market_regime(self, symbol, timeframe='1h'):
        bars = self._fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
        if not bars: return "neutral"
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        df['ema100'] = ta.trend.ema_indicator(df['c'], window=100)
        df['ema200'] = ta.trend.ema_indicator(df['c'], window=200)
        bb = ta.volatility.BollingerBands(df['c'], window=20, window_dev=2)
        df['bb_width'] = (bb.bollinger_hband() - bb.bollinger_lband()) / df['c'] * 100
        last = df.iloc[-1]
        prev = df.iloc[-2]
        is_uptrend = last['c'] > last['ema100'] and last['ema100'] > last['ema200'] and last['ema100'] > prev['ema100']
        is_sideways = (last['bb_width'] < 5) and (abs(last['c'] - last['ema100']) < (last['c'] * 0.01))
        is_high_risk = last['bb_width'] > 10
        if is_uptrend: return "uptrend"
        elif is_sideways: return "sideways"
        elif is_high_risk: return "high_risk"
        else: return "neutral"

    def _analyze_market(self, symbol, timeframe):
        bars = self._fetch_ohlcv(symbol, timeframe=timeframe, limit=200)
        if not bars: return False, 0, 0
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        df['ema200'] = ta.trend.ema_indicator(df['c'], window=200)
        df['rsi'] = ta.momentum.rsi(df['c'], window=14)
        df['macd'] = ta.trend.macd_diff(df['c'])
        bb = ta.volatility.BollingerBands(df['c'], window=20, window_dev=2)
        df['bb_lower'] = bb.bollinger_lband()
        df['vol_ma'] = df['v'].rolling(20).mean()
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], window=14).average_true_range()
        last = df.iloc[-1]
        prev = df.iloc[-2]
        entry_signal = False
        if timeframe == self.ENTRY_CONFIRMATION_TimEframe:
            if last['atr'] is not None and (last['h'] - last['l']) < (last['atr'] * 0.5):
                 return False, 0, 0
            volume_spike = last['v'] > (last['vol_ma'] * 1.5)
            price_action_confirmation = True
            if last['atr'] is not None and (last['h'] - last['l']) < (last['atr'] * 0.5): 
                price_action_confirmation = False
            trend_up_short = last['c'] > last['ema200']
            oversold_bounce = (prev['c'] < prev['bb_lower']) and (last['c'] > last['bb_lower'])
            rsi_good = 35 < last['rsi'] < 55
            macd_cross = last['macd'] > prev['macd']
            if (trend_up_short and oversold_bounce and rsi_good and macd_cross and volume_spike and price_action_confirmation):
                entry_signal = True
        return entry_signal, last['c'], last['rsi']

    def _calculate_atr(self, symbol, timeframe='15m', period=14):
        bars = self._fetch_ohlcv(symbol, timeframe=timeframe, limit=period + 5)
        if not bars or len(bars) < period: return None
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        atr_indicator = ta.volatility.AverageTrueRange(high=df['h'], low=df['l'], close=df['c'], window=period)
        atr_value = atr_indicator.average_true_range().iloc[-1]
        if pd.isna(atr_value) or atr_value <= 0: return None
        return atr_value

    def _get_free_balance(self, currency='USDT'):
        balance = self._fetch_balance()
        if balance and currency in balance:
            return float(balance[currency].get('free', 0))
        return 0.0

    def _calculate_order_qty(self, symbol, entry_price):
        total_balance = self._get_free_balance()
        if total_balance == 0:
            self.send_telegram("⚠️ *رصيد USDT غير كافٍ.*")
            return 0
        atr_value = self._calculate_atr(symbol, timeframe=self.ENTRY_CONFIRMATION_TimEframe)
        if atr_value is None:
            self.send_telegram(f"⚠️ *تعذر حساب ATR لـ {symbol}.*")
            return 0
        current_risk_per_trade = self.RISK_PER_TRADE_PCT
        if self.consecutive_losses >= self.MAX_CONSECUTIVE_LOSSES:
            current_risk_per_trade *= self.LOSS_SIZE_REDUCTION_FACTOR
            self.send_telegram(f"📉 *تقليل حجم الصفقة لـ {symbol} بسبب خسائر متتالية.*")
        risk_amount_usd = total_balance * (current_risk_per_trade / 100)
        stop_loss_distance_usd = self.STOP_LOSS_ATR_MULTIPLIER * atr_value
        stop_loss_price = entry_price - stop_loss_distance_usd
        if stop_loss_price <= 0 or stop_loss_distance_usd <= 0: return 0
        qty_to_buy = risk_amount_usd / stop_loss_distance_usd
        try:
            market_info = self.exchange.market(symbol)
            formatted_qty = self.exchange.amount_to_precision(symbol, qty_to_buy)
            min_qty = market_info.get('limits', {}).get('amount', {}).get('min')
            if min_qty and float(formatted_qty) < min_qty:
                formatted_qty = self.exchange.amount_to_precision(symbol, min_qty)
        except Exception as e:
            formatted_qty = self.exchange.amount_to_precision(symbol, qty_to_buy)
        if float(formatted_qty) <= 0: return 0
        return float(formatted_qty)

    def _close_trade(self, reason, profit_pct, is_loss=False):
        if not self.active_trade: return False
        symbol = self.active_trade['symbol']
        coin = symbol.split('/')[0]
        balance = self._fetch_balance()
        if not balance or coin not in balance or balance[coin].get('free', 0) <= 0:
            self.send_telegram(f"⚠️ *لا يمكن العثور على رصيد حر لـ {coin}.*")
            self.active_trade = None 
            return False
        qty_to_sell = balance[coin]['free']
        formatted_qty = float(self.exchange.amount_to_precision(symbol, qty_to_sell))
        if formatted_qty <= 0:
            self.active_trade = None
            return False
        ticker = self._fetch_ticker(symbol)
        exit_price = self.active_trade['entry'] if not ticker else ticker['last']
        sell_order = self._create_order('sell', symbol, formatted_qty)
        if not sell_order:
            self.send_telegram(f"🚨 *فشل تنفيذ أمر البيع لـ {symbol}.*")
            return False
        self.performance_tracker.log_trade(symbol=symbol, entry_price=self.active_trade['entry'], exit_price=exit_price, quantity=formatted_qty, is_profit=(profit_pct > 0), profit_pct=profit_pct, reason=reason)
        if is_loss:
            self.consecutive_losses += 1
            total_balance = self._get_free_balance()
            if total_balance > 0: self.daily_loss += (abs(profit_pct) / 100) * (self._get_free_balance() / total_balance * 100)
            else: self.daily_loss += abs(profit_pct)
            self.send_telegram(f"📉 الخسائر المتتالية: {self.consecutive_losses}/{self.MAX_CONSECUTIVE_LOSSES}.")
        else:
            self.consecutive_losses = 0
        msg = f"✅ *تم إغلاق الصفقة*\n🪙 {symbol}\n🎯 {reason}\n💰 {profit_pct:.2f}%"
        self.send_telegram(msg)
        self.active_trade = None
        return True

    def run(self):
        self.send_telegram("🚀 *نظام Sniper Pro Pro Legend بدأ العمل!*")
        while True:
            current_date_today = datetime.date.today()
            if self.last_trade_date != current_date_today:
                self.daily_loss = 0.0
                self.last_trade_date = current_date_today
                self.send_telegram(f"🗓️ *بدأ يوم تداول جديد.*")
            try:
                if self.daily_loss >= self.DAILY_LOSS_LIMIT_PCT:
                    self.send_telegram(f"🛑 **تم الوصول إلى حد الخسارة اليومي.**")
                    time.sleep(3600)
                    continue
                if not self.active_trade:
                    tickers_data = self._fetch_tickers()
                    if not tickers_data:
                        time.sleep(30)
                        continue
                    filtered_symbols = []
                    for symbol, ticker_info in tickers_data.items():
                        if (symbol.endswith('/USDT') and ':' not in symbol and ticker_info and ticker_info.get('quoteVolume') and ticker_info.get('last')):
                            volume_24h = ticker_info.get('quoteVolume', 0) * ticker_info.get('last', 0)
                            price_change_pct_day = ticker_info.get('change', 0)
                            if (volume_24h > self.MIN_VOLUME_24H and abs(price_change_pct_day) > self.MIN_PRICE_CHANGE_PCT_DAY):
                                filtered_symbols.append(symbol)
                    symbols_to_analyze = filtered_symbols[:30]
                    if not symbols_to_analyze:
                        time.sleep(60)
                        continue
                    for symbol in symbols_to_analyze:
                        market_regime = self._get_market_regime(symbol, timeframe=self.DIRECTION_CONFIRMATION_TimEframe)
                        if market_regime != "uptrend": continue
                        is_uptrend_long, _, _ = self._analyze_market(symbol, timeframe=self.DIRECTION_CONFIRMATION_TimEframe)
                        if not is_uptrend_long: continue
                        is_good_entry, price, rsi_value = self._analyze_market(symbol, timeframe=self.ENTRY_CONFIRMATION_TimEframe)
                        if is_good_entry:
                            quantity_to_buy = self._calculate_order_qty(symbol, price)
                            if quantity_to_buy <= 0: continue
                            buy_order = self._create_order('buy', symbol, quantity_to_buy)
                            if buy_order:
                                atr_initial = self._calculate_atr(symbol, self.ENTRY_CONFIRMATION_TimEframe)
                                initial_sl_price = price * (1 - self.STOP_LOSS_ATR_MULTIPLIER * atr_initial / price) if atr_initial else price * (1 - self.STOP_LOSS_PCT/100)
                                self.active_trade = {'symbol': symbol, 'entry': price, 'stop_loss_price': initial_sl_price, 'initial_stop_loss_price': initial_sl_price, 'highest_profit_price': price}
                                self.send_telegram(f"🎯 *تم قنص فرصة!*\n🪙 {symbol}\n💵 {price:.4f}\n⚖️ {quantity_to_buy:.6f}")
                                self.consecutive_losses = 0
                                break
                else:
                    symbol = self.active_trade['symbol']
                    ticker = self._fetch_ticker(symbol)
                    if not ticker:
                        time.sleep(15)
                        continue
                    current_price = ticker['last']
                    entry_price = self.active_trade['entry']
                    current_profit_pct = ((current_price - entry_price) / entry_price) * 100
                    if current_price > self.active_trade['highest_profit_price']:
                        self.active_trade['highest_profit_price'] = current_price
                    highest_profit_pct = ((self.active_trade['highest_profit_price'] - entry_price) / entry_price) * 100
                    print(f"⏱️ مراقبة {symbol} | الربح: {current_profit_pct:.2f}% | SL: {self.active_trade['stop_loss_price']:.4f}", end='\r')
                    safe_stop_loss = max(self.active_trade['stop_loss_price'], self.active_trade['initial_stop_loss_price'])
                    if current_price <= safe_stop_loss:
                        self._close_trade("🛑 ضرب وقف الخسارة", current_profit_pct, is_loss=True)
                        continue
                    if current_profit_pct >= self.TAKE_PROFIT_PCT:
                        self._close_trade("🏆 تحقيق الهدف", current_profit_pct, is_loss=False)
                        continue
                    if highest_profit_pct >= self.TRAILING_ACTIVATE_PCT:
                        atr_value = self._calculate_atr(symbol, self.ENTRY_CONFIRMATION_TimEframe)
                        if atr_value:
                            new_trailing_stop_price_candidate = self.active_trade['highest_profit_price'] * (1 - (self.TRAILING_DROP_PCT / 100))
                            new_trailing_stop_price = max(new_trailing_stop_price_candidate, self.active_trade['initial_stop_loss_price'])
                            if new_trailing_stop_price > self.active_trade['stop_loss_price']:
                                self.active_trade['stop_loss_price'] = new_trailing_stop_price
                                self.send_telegram(f"⬆️ **تم تحديث Trailing SL لـ {symbol} إلى:** {self.active_trade['stop_loss_price']:.4f}")
            except ccxt.RateLimitExceeded as e:
                time.sleep(e.retryAfter / 1000 if e.retryAfter else 60)
            except ccxt.NetworkError as e:
                time.sleep(30)
            except ccxt.ExchangeError as e:
                time.sleep(15)
            except Exception as e:
                print(f"\n⚠️ خطأ غير متوقع: {e}")
                time.sleep(15)
            time.sleep(15)
            now = datetime.datetime.now()
            if (now - self.last_report_time).total_seconds() >= 24 * 60 * 60:
                self.performance_tracker.send_daily_report()
                self.last_report_time = now

if __name__ == "__main__":
    bot = LegendaryBot()
    bot.run()
