# Jupiter RFQ Webhook Setup - Ответы на ваши вопросы

## 🎯 Вопрос 1: Как получить публичный URL для webhook?

Для получения публичного URL webhook есть несколько вариантов:

### Быстрое тестирование (ngrok)
```bash
# 1. Запустите локальный webhook сервер
python jupiter_webhook_server.py

# 2. В новом терминале запустите ngrok
ngrok http 8080

# 3. Скопируйте публичный URL
# Пример: https://abc123.ngrok.io
```

**Ваш webhook URL для Jupiter:** `https://abc123.ngrok.io/webhook/jupiter/rfq`

### Production развертывание (VPS/Cloud)
```bash
# Автоматическое развертывание на VPS
./quick_deploy.sh --vps yourdomain.com admin@yourdomain.com

# Или ручная настройка согласно DEPLOYMENT_GUIDE.md
```

**Ваш webhook URL для Jupiter:** `https://yourdomain.com/webhook/jupiter/rfq`

---

## 🏗️ Вопрос 2: Как развернуть всю систему с публичным URL?

### Вариант A: Быстрое развертывание (рекомендуется)

#### Локальное тестирование:
```bash
# Клонируйте репозиторий
git clone <your-repo>
cd solana-arbitrage-bot

# Автоматическое развертывание для тестирования
./quick_deploy.sh --local

# В отдельном терминале для публичного доступа
ngrok http 8080
```

#### Production на VPS:
```bash
# Автоматическое развертывание на VPS
./quick_deploy.sh --vps yourdomain.com admin@yourdomain.com
```

### Вариант B: Ручная настройка

#### 1. Подготовка сервера
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

#### 2. Настройка приложения
```bash
# Клонирование кода
git clone <your-repo>
cd solana-arbitrage-bot

# Настройка окружения
cp .env.webhook.example .env
nano .env  # Настройте переменные

# Создание директорий
mkdir -p logs data nginx/ssl
```

#### 3. Настройка SSL (для домена)
```bash
# Установка Certbot
sudo apt install certbot

# Получение SSL сертификата
sudo certbot certonly --standalone -d yourdomain.com

# Копирование сертификатов
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/ssl/
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem nginx/ssl/
sudo chown $USER:$USER nginx/ssl/*.pem
```

#### 4. Запуск системы
```bash
# Запуск с Docker Compose
docker-compose up -d

# Проверка статуса
docker-compose ps

# Просмотр логов
docker-compose logs -f
```

---

## 📝 Основные шаги для регистрации у Jupiter

### 1. Подготовка endpoint
- ✅ Webhook сервер развернут и доступен
- ✅ Health check работает: `GET https://yourdomain.com/`
- ✅ Webhook endpoint работает: `POST https://yourdomain.com/webhook/jupiter/rfq`
- ✅ SSL сертификат настроен (для production)

### 2. Проверка работоспособности
```bash
# Health check
curl https://yourdomain.com/

# Webhook configuration
curl https://yourdomain.com/webhook/config

# Test webhook
curl -X POST https://yourdomain.com/webhook/test
```

### 3. Контакт с Jupiter
**Каналы связи:**
- **Discord:** https://discord.gg/jup (каналы #dev-support, #rfq-market-makers)
- **Email:** support@jup.ag
- **Telegram:** @JupiterSupport

**Предоставьте информацию:**
```json
{
  "webhook_url": "https://yourdomain.com/webhook/jupiter/rfq",
  "organization": "Your Organization",
  "contact_email": "your-email@domain.com",
  "supported_events": ["rfq_quote_received", "rfq_quote_updated", "rfq_quote_expired"],
  "signature_verification": true,
  "timeout_seconds": 30
}
```

---

## 🚀 Быстрый старт - Полная процедура

### Для тестирования (5 минут):
```bash
# 1. Установка зависимостей
pip install -r requirements.txt

# 2. Настройка окружения
cp .env.webhook.example .env

# 3. Запуск сервера
python jupiter_webhook_server.py &

# 4. Создание публичного URL
ngrok http 8080

# 5. Ваш URL: https://abc123.ngrok.io/webhook/jupiter/rfq
```

### Для production (15 минут):
```bash
# 1. Автоматическое развертывание
./quick_deploy.sh --vps yourdomain.com admin@yourdomain.com

# 2. Ваш URL: https://yourdomain.com/webhook/jupiter/rfq
```

---

## 🔧 Настройка и конфигурация

### Основные переменные окружения (.env):
```bash
# Webhook конфигурация
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8080
JUPITER_WEBHOOK_SECRET=your_secret_key

# Домен и URL
DOMAIN_NAME=yourdomain.com
PUBLIC_WEBHOOK_URL=https://yourdomain.com/webhook/jupiter/rfq

# Jupiter API
JUPITER_API_KEY=your_jupiter_api_key

# Solana
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_PRIVATE_KEY=your_private_key
```

### Docker Compose команды:
```bash
# Запуск
docker-compose up -d

# Остановка
docker-compose down

# Перезапуск
docker-compose restart

# Логи
docker-compose logs -f jupiter-webhook

# Статус
docker-compose ps
```

---

## 📊 Мониторинг и проверка

### Endpoints для проверки:
- **Health:** `GET https://yourdomain.com/`
- **Stats:** `GET https://yourdomain.com/stats` 
- **Config:** `GET https://yourdomain.com/webhook/config`
- **Test:** `POST https://yourdomain.com/webhook/test`

### Логи и диагностика:
```bash
# Docker логи
docker-compose logs -f

# Системные логи (если используете systemd)
sudo journalctl -u jupiter-webhook -f

# Файловые логи
tail -f logs/jupiter_webhook.log
```

---

## ✅ Чеклист готовности

- [ ] Webhook сервер запущен и отвечает
- [ ] Публичный URL доступен извне
- [ ] SSL сертификат настроен (для production)
- [ ] Health check проходит: `curl https://yourdomain.com/`
- [ ] Webhook endpoint работает: `curl -X POST https://yourdomain.com/webhook/test`
- [ ] Переменные окружения настроены
- [ ] Мониторинг и логирование работает
- [ ] Контакт с Jupiter командой установлен

**🎯 Итоговый URL для регистрации у Jupiter:**
`https://yourdomain.com/webhook/jupiter/rfq`

---

## 🆘 Поддержка и помощь

Если возникли проблемы:
1. Проверьте логи: `docker-compose logs -f`
2. Проверьте статус: `docker-compose ps`
3. Посмотрите детальное руководство: `DEPLOYMENT_GUIDE.md`
4. Обратитесь к документации: `README_ENHANCED.md`