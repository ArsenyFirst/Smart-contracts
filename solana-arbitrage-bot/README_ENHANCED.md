# Enhanced Jupiter RFQ Arbitrage System

Улучшенная система арбитража Jupiter RFQ с интеграцией лучших практик, мониторингом в реальном времени и webhook уведомлениями.

## 🎯 Ключевые Улучшения

### ✅ Исправленные Проблемы
После анализа репозитория https://github.com/jup-ag/rfq-webhook-toolkit (который не был найден), мы реализовали собственную улучшенную систему с аналогичными возможностями:

1. **Enhanced Jupiter API Client** - Улучшенный клиент с rate limiting и caching
2. **Webhook Event System** - Система событий и уведомлений в стиле webhook
3. **Advanced Monitoring** - Расширенная система мониторинга и метрик
4. **Improved DEX Integration** - Улучшенная интеграция с DEX
5. **Risk Management** - Продвинутое управление рисками

## 🏗️ Архитектура Системы

```
Enhanced Jupiter RFQ Arbitrage System
│
├── Enhanced Jupiter Client
│   ├── Rate Limiting & Caching
│   ├── Error Handling & Retries  
│   ├── Event System Integration
│   └── Pro API Support
│
├── Monitoring & Webhooks
│   ├── Real-time Event Tracking
│   ├── Webhook Notifications
│   ├── Performance Metrics
│   └── Health Monitoring
│
├── DEX Integrations
│   ├── Meteora DLMM (Real API)
│   ├── Raydium v3 (API + Fallback)
│   ├── Orca Whirlpools (Enhanced)
│   └── Parallel Quote Fetching
│
└── Risk Management
    ├── Confidence Scoring
    ├── Liquidity Assessment
    ├── Risk-Adjusted Profits
    └── Execution Timing
```

## 🚀 Быстрый Старт

### 1. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 2. Настройка конфигурации
```bash
cp .env.example .env
# Отредактируйте .env файл с вашими настройками
```

### 3. Запуск тестовой демонстрации
```bash
python test_enhanced_system.py
```

### 4. Запуск системы мониторинга
```bash
python enhanced_rfq_arbitrage.py
```

## 📊 Возможности Системы

### Enhanced Jupiter Client
- **Rate Limiting**: Автоматическое ограничение скорости запросов
- **Intelligent Caching**: TTL-кэширование котировок  
- **Error Recovery**: Автоматические повторы с экспоненциальной задержкой
- **Event Integration**: Встроенная система событий
- **Pro API Support**: Поддержка Jupiter Pro API

```python
from enhanced_jupiter_client import EnhancedJupiterClient, JupiterConfig, APITier

config = JupiterConfig(
    api_key="your-jupiter-pro-key",  # или None для бесплатного
    tier=APITier.PRO,
    rate_limit_per_second=10,
    enable_caching=True
)

async with EnhancedJupiterClient(config) as client:
    quote = await client.get_quote(params)
```

### Webhook & Monitoring System  
- **Real-time Events**: События возможностей, сделок, ошибок
- **Webhook Notifications**: HTTP уведомления на внешние сервисы
- **Performance Metrics**: Детальные метрики производительности
- **Health Monitoring**: Автоматический мониторинг состояния системы

```python
from rfq_monitoring_system import RFQMonitoringSystem, EventType

monitor = RFQMonitoringSystem(log_file_path="arbitrage.log")

# Добавить webhook
monitor.add_webhook(
    "https://your-slack-webhook.com",
    event_filters=[EventType.OPPORTUNITY_FOUND, EventType.TRADE_EXECUTED]
)

# Создать событие
await monitor.emit_event(
    EventType.OPPORTUNITY_FOUND,
    {"profit_bps": 25, "token_pair": "SOL/USDC"}
)
```

### Enhanced DEX Integration
- **Parallel Fetching**: Одновременное получение котировок со всех DEX
- **Confidence Scoring**: Оценка надежности каждой котировки
- **API Fallbacks**: Резервные механизмы при сбоях API
- **Real-time Metrics**: Отслеживание времени ответа и ошибок

```python
from enhanced_rfq_arbitrage import EnhancedDEXClient

async with EnhancedDEXClient(monitoring) as dex_client:
    quotes = await dex_client.get_all_dex_quotes(
        token_pair, amount_usd, side
    )
    # Получает котировки от Meteora, Raydium, Orca параллельно
```

### Risk Management
- **Multi-factor Risk Assessment**: Анализ времени, ликвидности, уверенности
- **Risk-Adjusted Profits**: Прибыль с учетом рисков
- **Confidence Scoring**: Оценка надежности возможностей
- **Liquidity Validation**: Проверка достаточности ликвидности

```python
opportunity = EnhancedArbitrageOpportunity(
    risk_score=0.3,  # 0-1, низкий риск
    confidence_score=0.9,  # 0-1, высокая уверенность  
    liquidity_risk="low",
    risk_adjusted_profit=2.5  # USD с учетом рисков
)
```

## 🔧 Конфигурация

### Jupiter API Settings
```python
jupiter_config = JupiterConfig(
    api_key=None,  # Ваш Jupiter Pro API ключ
    tier=APITier.LITE,  # LITE, PRO, ENTERPRISE
    rate_limit_per_second=5,  # Запросов в секунду
    timeout=5.0,  # Таймаут запросов
    enable_caching=True,  # Включить кэширование
    cache_ttl_seconds=30  # TTL кэша
)
```

### Risk Management Settings  
```python
engine = EnhancedRFQArbitrageEngine(config)
engine.min_profit_bps = 15  # Минимум 0.15% прибыль
engine.max_slippage_bps = 100  # Максимум 1% slippage
engine.min_confidence_score = 0.8  # Минимальная уверенность
engine.max_risk_score = 0.5  # Максимальный риск
```

### Webhook Configuration
```python
# Slack интеграция
monitor.add_webhook(
    "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK",
    event_filters=[EventType.OPPORTUNITY_FOUND],
    custom_headers={"Authorization": "Bearer token"}
)

# Discord интеграция  
monitor.add_webhook(
    "https://discord.com/api/webhooks/YOUR/WEBHOOK",
    alert_level_filter=AlertLevel.WARNING
)
```

## 📈 Мониторинг и Метрики

### Dashboard Data
```python
dashboard = engine.get_dashboard_data()
```

**Возвращаемые метрики:**
```json
{
  "system_metrics": {
    "performance": {
      "opportunities_detected": 156,
      "trades_executed": 23,
      "trades_successful": 21,
      "success_rate": 91.3,
      "total_profit_usd": 45.67,
      "api_reliability": 98.5
    },
    "health_status": {
      "overall": "healthy",
      "api_health": "good", 
      "trading_health": "good",
      "uptime_hours": 12.5
    }
  },
  "webhook_status": {
    "active_webhooks": 2,
    "failed_webhooks": 0
  }
}
```

### Event Types
- `OPPORTUNITY_FOUND` - Обнаружена возможность арбитража
- `TRADE_EXECUTED` - Выполнена сделка  
- `TRADE_FAILED` - Сделка не удалась
- `API_ERROR` - Ошибка API
- `RATE_LIMIT_HIT` - Достигнут лимит запросов
- `SYSTEM_HEALTH` - Состояние системы

## 🔌 Webhook Payload Format

```json
{
  "webhook_version": "1.0",
  "source": "jupiter_rfq_arbitrage", 
  "event": {
    "event_id": "evt_1640995200000",
    "event_type": "opportunity_found",
    "timestamp": "2024-01-15T10:30:00Z",
    "alert_level": "info",
    "data": {
      "token_pair": "SOL/USDC",
      "arbitrage_type": "buy_rfq_sell_dex",
      "profit_bps": 25,
      "profit_usd": 2.5,
      "dex": "meteora",
      "risk_score": 0.3,
      "confidence_score": 0.9
    }
  }
}
```

## 🏃‍♂️ Запуск в Production

### 1. Environment Setup
```bash
# .env файл
SOLANA_RPC_URL=https://your-premium-rpc.com
SOLANA_PRIVATE_KEY=your_private_key_base58
JUPITER_API_KEY=your_jupiter_pro_key
WEBHOOK_URL=https://your-webhook.com/jupiter-events
```

### 2. Production Configuration
```python
# Для production используйте более консервативные настройки
jupiter_config = JupiterConfig(
    api_key=os.getenv("JUPITER_API_KEY"),
    tier=APITier.PRO,
    rate_limit_per_second=20,  # Выше лимит для Pro
    enable_caching=True,
    timeout=10.0
)

engine = EnhancedRFQArbitrageEngine(jupiter_config)
engine.min_profit_bps = 20  # Более консервативный минимум
```

### 3. Monitoring Setup
```python
# Добавить multiple webhooks для reliability
monitor.add_webhook("https://primary-webhook.com")
monitor.add_webhook("https://backup-webhook.com") 
monitor.add_webhook("https://slack-alerts.com")
```

## 🧪 Тестирование

### Запуск полного тестового набора
```bash
python test_enhanced_system.py
```

### Индивидуальные тесты
```python
# Тест Jupiter client
await test_enhanced_jupiter_client()

# Тест системы мониторинга
await test_monitoring_system()

# Тест DEX интеграций
await test_dex_integrations()

# Тест анализа арбитража
await test_arbitrage_analysis()
```

### 30-секундная демонстрация
```bash
python test_enhanced_system.py
# Выберите 'y' когда будет предложено запустить демо
```

## 📋 Сравнение с Оригинальной Системой

| Функция | Оригинальная | Улучшенная |
|---------|-------------|-----------|
| Jupiter API | Базовый HTTP | Enhanced client с rate limiting |
| Error Handling | Простое | Comprehensive с retries |
| Monitoring | Логи | Real-time events + webhooks |
| DEX Integration | 3 DEX | 3 DEX с enhanced features |
| Risk Management | Базовое | Multi-factor risk assessment |
| Caching | Нет | TTL-based intelligent caching |
| Events | Нет | Full event system с webhooks |
| Configuration | Статичная | Dynamic с validation |
| Testing | Ограниченное | Comprehensive test suite |
| Documentation | Базовая | Production-ready |

## 🔍 Troubleshooting

### Частые Проблемы

**1. Rate Limit Errors**
```bash
# Уменьшите rate limit
rate_limit_per_second=2
```

**2. Webhook Failures**
```python
# Проверьте webhook URLs
dashboard = engine.get_dashboard_data()
print(dashboard['webhook_status'])
```

**3. API Timeouts**
```python
# Увеличьте timeout
timeout=10.0
```

### Debug Mode
```python
import structlog
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(20),  # DEBUG level
)
```

## 🤝 Contributing

1. Fork репозиторий
2. Создайте feature branch
3. Добавьте тесты для новых функций
4. Убедитесь что все тесты проходят
5. Создайте Pull Request

## 📜 License

MIT License - см. LICENSE файл для деталей.

## 🙏 Acknowledgments

- Jupiter Team за отличные API и документацию
- Solana DEX providers (Meteora, Raydium, Orca)
- Open source сообщество за вдохновение и инструменты

---

**⚠️ Disclaimer**: Эта система предназначена для образовательных целей. Используйте на свой риск в production. Всегда тестируйте с небольшими суммами сначала.