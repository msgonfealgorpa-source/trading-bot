FROM python:3.11-slim

WORKDIR /bot
COPY requirements.txt bot.py web_panel.py ./
RUN pip install --no-cache-dir -r requirements.txt

# ✅ دعم كامل: ينشئ المجلد لو ناقص + صلاحيات كاملة + تشغيل من داخله
CMD ["sh", "-c", "mkdir -p /appdata 2>/dev/null; chmod 777 /appdata 2>/dev/null; cp -f /bot/bot.py /bot/web_panel.py /appdata/ 2>/dev/null; cd /appdata 2>/dev/null || cd /bot; exec python bot.py"]
