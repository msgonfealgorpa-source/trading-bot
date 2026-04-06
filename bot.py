import ccxt
import time
import os
from dotenv import load_dotenv

# تحميل مفاتيح الأمان من بيئة Render بشكل آمن
load_dotenv()
API_KEY = os.getenv('GATEIO_API_KEY')
API_SECRET = os.getenv('GATEIO_API_SECRET')

# إعدادات البوت (يمكنك تعديلها)
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'] # العملات
TRADE_AMOUNT_USDT = 10 # مبلغ الصفقة بالدولار
TAKE_PROFIT_PERCENT = 1.5  # نسبة جني الربح
STOP_LOSS_PERCENT = -1.0   # نسبة وقف الخسارة

def check_entry_condition(symbol):
    # ⚠️ تنبيه: هذه الدالة حالياً تعطي إشارات عشوائية للتوضيح فقط!
    # يجب عليك لاحقاً وضع استراتيجية فنية حقيقية هنا بدلاً من العشوائية.
    import random
    return random.choice([True, False])

def start_bot():
    if not API_KEY or not API_SECRET:
        print("❌ خطأ: مفاتيح API غير موجودة في Render!")
        return

    exchange = ccxt.gateio({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'enableRateLimit': True,
    })

    print("✅ تم تشغيل البوت بنجاح... يبحث عن صفقات")
    
    while True:
        for symbol in SYMBOLS:
            try:
                if check_entry_condition(symbol):
                    print(f"🟢 فرصة في {symbol}! جاري الشراء...")
                    buy_order = exchange.create_market_buy_order(symbol, TRADE_AMOUNT_USDT)
                    buy_price = buy_order['average']
                    
                    in_position = True
                    while in_position:
                        ticker = exchange.fetch_ticker(symbol)
                        current_price = ticker['last']
                        profit_percent = ((current_price - buy_price) / buy_price) * 100
                        
                        print(f"⏳ مراقبة {symbol} | السعر: {current_price} | الربح: {profit_percent:.2f}%")
                        
                        if profit_percent >= TAKE_PROFIT_PERCENT:
                            print(f"🎉 هدف الربح تحقق! جاري البيع...")
                            exchange.create_market_sell_order(symbol, TRADE_AMOUNT_USDT)
                            in_position = False
                        elif profit_percent <= STOP_LOSS_PERCENT:
                            print(f"🛑 وقف الخسارة! جاري البيع...")
                            exchange.create_market_sell_order(symbol, TRADE_AMOUNT_USDT)
                            in_position = False
                        
                        time.sleep(10) # فحص السعر كل 10 ثواني
                    time.sleep(60) # استراحة دقيقة بعد انتهاء الصفقة
            except Exception as e:
                print(f"حدث خطأ في {symbol}: {e}")
                time.sleep(30)

if __name__ == "__main__":
    start_bot()
