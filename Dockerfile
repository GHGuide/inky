# Inky on any Linux server: bots keep working while your laptop sleeps.
#   docker build -t inky .
#   docker run -d --name inky -p 8800:8800 -v inky-data:/data inky
#   docker logs inky        # prints the pairing code; type it in Computers → Add a server
FROM python:3.12-slim
RUN pip install --no-cache-dir playwright==1.63.0 httpx==0.28.1 \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY inky ./inky
COPY library ./library
ENV PYTHONUNBUFFERED=1 INKY_HEADLESS=1
EXPOSE 8800
VOLUME /data
CMD ["python", "-m", "inky", "--host", "0.0.0.0", "--port", "8800", "--home", "/data", "--no-open", "--name", "Linux server"]
