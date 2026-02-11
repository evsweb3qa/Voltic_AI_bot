FROM python:3.10.11-slim


RUN sed -i 's|http://deb.debian.org|http://mirror.yandex.ru|g' /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]