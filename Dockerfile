FROM python:3.11-slim

WORKDIR /bot
COPY requirements.txt bot.py web_panel.py ./
RUN pip install --no-cache-dir -r requirements.txt

# ✅ التشغيل من داخل الـVolume — القاعدة تُكتب في /appdata
CMD ["sh", "-c", "cp -f /bot/bot.py /bot/web_panel.py /appdata/ && cd /appdata && exec python bot.py"]
