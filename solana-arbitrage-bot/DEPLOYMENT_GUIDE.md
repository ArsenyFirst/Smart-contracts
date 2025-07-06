# Jupiter RFQ Webhook System - Deployment Guide

Полное руководство по развертыванию системы Jupiter RFQ арбитража с webhook endpoint для регистрации у Jupiter.

## 📋 Содержание

1. [Быстрый старт](#быстрый-старт)
2. [Варианты развертывания](#варианты-развертывания)
3. [Регистрация у Jupiter](#регистрация-у-jupiter)
4. [Production развертывание](#production-развертывание)
5. [Мониторинг и обслуживание](#мониторинг-и-обслуживание)
6. [Troubleshooting](#troubleshooting)

## 🚀 Быстрый старт

### 1. Локальное тестирование

```bash
# Клонирование и настройка
git clone <repository>
cd solana-arbitrage-bot

# Установка зависимостей
pip install -r requirements.txt

# Настройка окружения
cp .env.webhook.example .env
# Отредактируйте .env с вашими настройками

# Запуск webhook сервера
python jupiter_webhook_server.py
```

**Ваш локальный webhook будет доступен по адресу:** `http://localhost:8080/webhook/jupiter/rfq`

### 2. Тестирование с ngrok (для регистрации у Jupiter)

```bash
# Установка ngrok
# Для macOS: brew install ngrok
# Для Linux: скачайте с https://ngrok.com/download

# Запуск ngrok tunnel
ngrok http 8080

# Вы получите публичный URL типа:
# https://abc123.ngrok.io
```

**Ваш публичный webhook URL:** `https://abc123.ngrok.io/webhook/jupiter/rfq`

## 🌐 Варианты развертывания

### Вариант 1: VPS с Docker (Рекомендуется)

#### Шаг 1: Настройка VPS

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

#### Шаг 2: Развертывание приложения

```bash
# Клонирование кода
git clone <repository>
cd solana-arbitrage-bot

# Настройка окружения
cp .env.webhook.example .env
nano .env  # Отредактируйте настройки

# Создание директорий
mkdir -p logs data nginx/ssl nginx/logs

# Запуск с Docker Compose
docker-compose up -d
```

### Вариант 2: Cloud Providers

#### AWS ECS/Fargate

```bash
# Создание ECR репозитория
aws ecr create-repository --repository-name jupiter-rfq-webhook

# Build и push Docker image
docker build -t jupiter-rfq-webhook .
docker tag jupiter-rfq-webhook:latest <account-id>.dkr.ecr.<region>.amazonaws.com/jupiter-rfq-webhook:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/jupiter-rfq-webhook:latest

# Развертывание через ECS или Fargate
# Используйте AWS CLI или консоль
```

#### Google Cloud Run

```bash
# Build и deploy
gcloud builds submit --tag gcr.io/<project-id>/jupiter-rfq-webhook
gcloud run deploy jupiter-rfq-webhook \
  --image gcr.io/<project-id>/jupiter-rfq-webhook \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080
```

#### DigitalOcean App Platform

```yaml
# app.yaml
name: jupiter-rfq-webhook
services:
- name: webhook-server
  source_dir: /
  github:
    repo: your-username/jupiter-rfq-arbitrage
    branch: main
  run_command: python jupiter_webhook_server.py
  environment_slug: python
  instance_count: 1
  instance_size_slug: basic-xxs
  http_port: 8080
  routes:
  - path: /
  envs:
  - key: WEBHOOK_PORT
    value: "8080"
  - key: JUPITER_WEBHOOK_SECRET
    value: your_secret_here
    type: SECRET
```

### Вариант 3: Kubernetes

```yaml
# kubernetes/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: jupiter-rfq-webhook
spec:
  replicas: 2
  selector:
    matchLabels:
      app: jupiter-rfq-webhook
  template:
    metadata:
      labels:
        app: jupiter-rfq-webhook
    spec:
      containers:
      - name: webhook-server
        image: jupiter-rfq-webhook:latest
        ports:
        - containerPort: 8080
        env:
        - name: WEBHOOK_PORT
          value: "8080"
        - name: JUPITER_WEBHOOK_SECRET
          valueFrom:
            secretKeyRef:
              name: jupiter-secrets
              key: webhook-secret
---
apiVersion: v1
kind: Service
metadata:
  name: jupiter-rfq-webhook-service
spec:
  selector:
    app: jupiter-rfq-webhook
  ports:
  - port: 80
    targetPort: 8080
  type: LoadBalancer
```

## 📝 Регистрация у Jupiter

### Шаг 1: Подготовка endpoint

1. **Убедитесь что webhook работает:**
   ```bash
   curl -X GET https://your-domain.com/
   # Должен вернуть: {"status": "healthy", ...}
   ```

2. **Проверьте webhook endpoint:**
   ```bash
   curl -X POST https://your-domain.com/webhook/test
   # Должен вернуть: {"status": "test_completed", ...}
   ```

3. **Получите конфигурацию webhook:**
   ```bash
   curl -X GET https://your-domain.com/webhook/config
   ```

### Шаг 2: Контакт с Jupiter

**Свяжитесь с командой Jupiter через:**

1. **Discord:** https://discord.gg/jup
   - Канал: #dev-support или #rfq-market-makers

2. **Email:** support@jup.ag

3. **Telegram:** @JupiterSupport

**Предоставьте следующую информацию:**

```json
{
  "webhook_url": "https://your-domain.com/webhook/jupiter/rfq",
  "organization": "Your Organization Name",
  "contact_email": "your-email@domain.com",
  "supported_events": [
    "rfq_quote_received",
    "rfq_quote_updated",
    "rfq_quote_expired",
    "rfq_quote_filled"
  ],
  "signature_verification": true,
  "timeout_seconds": 30,
  "description": "Jupiter RFQ Arbitrage System"
}
```

### Шаг 3: Верификация webhook

Jupiter команда проведет тестирование вашего endpoint:

1. **Health check:** `GET https://your-domain.com/`
2. **Webhook test:** `POST https://your-domain.com/webhook/jupiter/rfq`
3. **Signature verification test**
4. **Load testing**

## 🏭 Production развертывание

### Безопасность

1. **SSL/TLS сертификат:**
   ```bash
   # Получение Let's Encrypt сертификата
   sudo apt install certbot
   sudo certbot --nginx -d your-domain.com
   ```

2. **Nginx конфигурация:**
   ```nginx
   # /etc/nginx/sites-available/jupiter-webhook
   server {
       listen 443 ssl;
       server_name your-domain.com;
       
       ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
       
       location / {
           proxy_pass http://localhost:8080;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
       
       location /webhook/ {
           proxy_pass http://localhost:8080;
           proxy_buffering off;
           proxy_cache off;
           
           # Rate limiting
           limit_req zone=webhook burst=10 nodelay;
       }
   }
   
   # Rate limiting zone
   http {
       limit_req_zone $binary_remote_addr zone=webhook:10m rate=30r/m;
   }
   ```

3. **Firewall настройка:**
   ```bash
   sudo ufw allow ssh
   sudo ufw allow 80
   sudo ufw allow 443
   sudo ufw enable
   ```

### Автозапуск

1. **Systemd service:**
   ```bash
   # Создание service файла
   sudo tee /etc/systemd/system/jupiter-webhook.service << 'EOF'
   [Unit]
   Description=Jupiter RFQ Webhook Server
   After=network.target
   
   [Service]
   Type=simple
   User=jupiter
   WorkingDirectory=/opt/jupiter-rfq
   Environment=PATH=/opt/jupiter-rfq/venv/bin
   ExecStart=/opt/jupiter-rfq/venv/bin/python jupiter_webhook_server.py
   Restart=always
   RestartSec=5
   
   [Install]
   WantedBy=multi-user.target
   EOF
   
   # Активация service
   sudo systemctl daemon-reload
   sudo systemctl enable jupiter-webhook
   sudo systemctl start jupiter-webhook
   ```

2. **Логирование:**
   ```bash
   # Просмотр логов
   sudo journalctl -u jupiter-webhook -f
   
   # Ротация логов
   sudo tee /etc/logrotate.d/jupiter-webhook << 'EOF'
   /opt/jupiter-rfq/logs/*.log {
       daily
       missingok
       rotate 30
       compress
       delaycompress
       notifempty
       copytruncate
   }
   EOF
   ```

### Резервное копирование

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/jupiter-rfq"

# Создание директории
mkdir -p $BACKUP_DIR

# Бэкап конфигурации
tar -czf $BACKUP_DIR/config_$DATE.tar.gz /opt/jupiter-rfq/.env /opt/jupiter-rfq/config/

# Бэкап логов
tar -czf $BACKUP_DIR/logs_$DATE.tar.gz /opt/jupiter-rfq/logs/

# Бэкап данных
tar -czf $BACKUP_DIR/data_$DATE.tar.gz /opt/jupiter-rfq/data/

# Удаление старых бэкапов (старше 30 дней)
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
```

## 📊 Мониторинг и обслуживание

### Мониторинг endpoints

1. **Health check:**
   ```bash
   # Простая проверка
   curl -f https://your-domain.com/ || echo "Service down"
   
   # Cron job для мониторинга
   */5 * * * * curl -f https://your-domain.com/ > /dev/null 2>&1 || echo "Jupiter webhook down" | mail -s "Alert" admin@domain.com
   ```

2. **Метрики:**
   ```bash
   # Статистика webhook
   curl https://your-domain.com/stats
   ```

3. **Grafana dashboards:**
   - Импортируйте dashboard из `monitoring/grafana/dashboards/`
   - Настройте алерты для критических метрик

### Обновление системы

```bash
#!/bin/bash
# update.sh

# Остановка сервисов
docker-compose down

# Получение обновлений
git pull origin main

# Обновление зависимостей
docker-compose build --no-cache

# Запуск
docker-compose up -d

# Проверка health
sleep 10
curl -f https://your-domain.com/ || echo "Update failed"
```

## 🔧 Troubleshooting

### Частые проблемы

1. **Webhook не отвечает:**
   ```bash
   # Проверка статуса контейнера
   docker-compose ps
   
   # Просмотр логов
   docker-compose logs jupiter-webhook
   
   # Перезапуск
   docker-compose restart jupiter-webhook
   ```

2. **SSL ошибки:**
   ```bash
   # Проверка сертификата
   openssl s_client -connect your-domain.com:443 -servername your-domain.com
   
   # Обновление сертификата
   sudo certbot renew
   ```

3. **High memory usage:**
   ```bash
   # Мониторинг ресурсов
   docker stats
   
   # Настройка лимитов в docker-compose.yml
   deploy:
     resources:
       limits:
         memory: 512M
         cpus: '0.5'
   ```

### Логи и диагностика

```bash
# Просмотр всех логов
docker-compose logs -f

# Конкретный сервис
docker-compose logs -f jupiter-webhook

# Системные логи
sudo journalctl -u jupiter-webhook -f

# Nginx логи
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Performance tuning

```yaml
# docker-compose.yml оптимизации
services:
  jupiter-webhook:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
        reservations:
          memory: 512M
          cpus: '0.5'
    environment:
      - UVICORN_WORKERS=4
      - UVICORN_MAX_REQUESTS=1000
```

## 📞 Поддержка

- **Documentation:** README_ENHANCED.md
- **Issues:** GitHub Issues
- **Discord:** Jupiter Discord Server
- **Email:** Ваш контактный email

---

**🎯 Итоговый checklist для регистрации у Jupiter:**

- [ ] Webhook сервер развернут и доступен публично
- [ ] Health check endpoint работает: `GET https://your-domain.com/`
- [ ] Webhook endpoint работает: `POST https://your-domain.com/webhook/jupiter/rfq`
- [ ] SSL сертификат настроен и валиден
- [ ] Signature verification включена
- [ ] Мониторинг и логирование настроены
- [ ] Автозапуск и резервное копирование настроены
- [ ] Контакт с Jupiter командой установлен

**Ваш webhook URL для регистрации:** `https://your-domain.com/webhook/jupiter/rfq`