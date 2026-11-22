FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY suunto_uploader.py bot_server.py ./

ENV PORT=8080
EXPOSE 8080

# Webhook mode on Render (PUBLIC_URL / RENDER_EXTERNAL_URL set by platform)
CMD ["python3", "bot_server.py"]
