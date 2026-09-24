FROM python:3.11-slim

WORKDIR /bot
COPY requirements.txt bot.py ./
RUN pip install --no-cache-dir -r requirements.txt

CMD ["sh", "-c", "mkdir -p /appdata && cp -f /bot/bot.py /appdata/ && cd /appdata && exec python bot.py"]
