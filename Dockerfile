FROM python:3.11-slim

WORKDIR /bot
COPY requirements.txt bot.py web_panel.py ./
RUN pip install --no-cache-dir -r requirements.txt

# ✅ ينشئ المجلد إن لم يكن موجوداً (علاج خطأ النسخ) + تشغيل من الـVolume
CMD ["sh", "-c", "mkdir -p /appdata && cp -f /bot/bot.py /bot/web_panel.py /appdata/ && cd /appdata && exec python bot.py"]
