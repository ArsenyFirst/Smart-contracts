FROM python:3.11-slim

# Метаданные
LABEL maintainer="Jupiter RFQ Arbitrage System"
LABEL description="Jupiter RFQ Webhook Server for arbitrage operations"

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Создание пользователя
RUN useradd --create-home --shell /bin/bash jupiter

# Рабочая директория
WORKDIR /app

# Копирование requirements и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY . .

# Смена владельца файлов
RUN chown -R jupiter:jupiter /app

# Переключение на пользователя
USER jupiter

# Создание директорий для логов и данных
RUN mkdir -p /app/logs /app/data

# Переменные окружения
ENV PYTHONPATH=/app
ENV WEBHOOK_HOST=0.0.0.0
ENV WEBHOOK_PORT=8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Экспозиция порта
EXPOSE 8080

# Команда запуска
CMD ["python", "jupiter_webhook_server.py"]