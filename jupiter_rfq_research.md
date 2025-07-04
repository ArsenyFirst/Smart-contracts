# Jupiter RFQ Research Report

## 📋 Обзор

**RFQ (Request for Quote)** - это система запроса котировок, используемая в Jupiter для интеграции маркетмейкеров и обеспечения более эффективного ценообразования в экосистеме Solana DeFi.

## 🔍 Ключевые находки

### 1. Архитектура Jupiter

Jupiter построен исключительно на **Solana MAINNET** и использует:
- **Программы (Programs)** - исполняемый код, развернутый в блокчейне
- **Инструкции (Instructions)** - определяются программой (аналог API endpoints)
- **Аккаунты (Accounts)** - хранят данные и могут обновляться программами
- **Транзакции (Transactions)** - отправляются для взаимодействия с сетью

### 2. Методы интеграции с Jupiter

| Метод | Описание |
|-------|----------|
| **Swap API** | Получение котировок через Quote API и выполнение свопов через Swap API |
| **Flash Fill** | Альтернативный метод для on-chain программ с использованием Versioned Transactions |
| **CPI (Cross Program Invocation)** | **Рекомендуемый метод** с января 2025 года |

### 3. Система RFQ в контексте Jupiter

#### Роль RFQ в экосистеме:
- **Интеграция маркетмейкеров** - позволяет профессиональным участникам рынка предоставлять ликвидность
- **Конкуренция с AMM** - RFQ котировки конкурируют с автоматическими маркетмейкерами
- **Улучшение ценообразования** - более точные цены за счет профессиональных участников

#### Принципы работы RFQ:
1. **Taker** (получатель) создает RFQ запрос
2. **Maker** (поставщик) предоставляет котировки
3. **Конкуренция** - лучшие котировки побеждают
4. **Исполнение** - транзакция выполняется по лучшей цене

### 4. Технические особенности

#### Новые API endpoints (2025):
- **Бесплатные**: `lite-api.jup.ag` (без API ключа)
- **Платные**: `api.jup.ag` (с API ключом)

#### Важные контракты:
- **Jupiter Swap**: `JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4`
- **Jupiter Limit Order**: `jupoNjAxXgZ4rjzxzPMP4oxduvQsQtZzyknqvzYNrNu`
- **Jupiter DCA**: `DCA265Vj8a9CEuX1eb1LWRnDT7uK6q1xMipnNyatn23M`

### 5. Комиссии и монетизация

#### Платформенные комиссии:
- Интеграторы могут устанавливать комиссию в **basis points** (bps)
- Jupiter берет **2.5% от платформенной комиссии**
- Для ExactIn - комиссия с input или output токена
- Для ExactOut - комиссия только с input токена
- **Не поддерживает Token2022**

#### Пример использования:
```javascript
// В /quote запросе
platformFeeBps: 20  // 0.2% комиссия

// В /swap запросе  
feeAccount: "YourFeeAccountPublicKey"
```

### 6. Оптимизация транзакций

#### Priority Fee система:
- **Priority Fee = Compute Budget × Compute Unit Price**
- Базовая комиссия: 5,000 lamports (0.000005 SOL)
- Чем выше Priority Fee, тем быстрее исполнение

#### Compute Units:
- Максимум: 1.4 млн CU на транзакцию
- По умолчанию: 200k CU на инструкцию
- Можно настроить через `SetComputeUnitLimit`

#### Методы отправки:
1. **Typical RPCs**
2. **RPCs with SWQoS**
3. **Jito RPC**

### 7. Интеграция AMM

Jupiter предоставляет **Jupiter AMM Interface** для:
- Десериализации состояния AMM
- Получения котировок через SDK
- Тестирования интеграций

#### Рекомендации:
- Ограничить AMM имплементацию до десериализации и вызова SDK
- Перенести логику в `update`, а не в `quote`
- Использовать снапшоты для тестирования

## 💡 Применение для арбитражного бота

### Стратегия использования RFQ:

1. **Мониторинг RFQ котировок** - получение цен от профессиональных маркетмейкеров
2. **Сравнение с AMM** - поиск арбитражных возможностей между RFQ и AMM
3. **Быстрое исполнение** - использование Priority Fee для гарантированного исполнения
4. **Комиссионная модель** - учет 0.1% комиссии Jupiter RFQ

### Преимущества RFQ:
- ✅ **Более точные цены** от профессиональных участников
- ✅ **Меньший проскальзывание** на больших объемах
- ✅ **Конкуренция** между маркетмейкерами
- ✅ **Интеграция с Jupiter** экосистемой

### Недостатки:
- ❌ **Комиссия 0.1%** снижает профитабельность
- ❌ **Зависимость от маркетмейкеров** (доступность котировок)
- ❌ **Сложность интеграции** по сравнению с простыми AMM

## 🎯 Рекомендации для бота

1. **Использовать RFQ как один из источников** ликвидности наряду с AMM
2. **Учитывать комиссию 0.1%** при расчете профитабельности
3. **Мониторить доступность** RFQ котировок
4. **Оптимизировать Priority Fee** для быстрого исполнения
5. **Тестировать в testnet** перед продакшеном

## � Технические детали и SDK

### Официальные SDK и клиенты:

#### Rust
- **jupiter-swap-api-client**: Официальный Rust клиент
- **jupiter-amm-implementation**: Интеграция с AMM протоколами
- Пример использования:
```rust
use jupiter_swap_api_client::{JupiterSwapApiClient, QuoteRequest};

let client = JupiterSwapApiClient::new("https://quote-api.jup.ag/v6");
let quote = client.quote(&QuoteRequest {
    amount: 1_000_000,
    input_mint: USDC_MINT,
    output_mint: NATIVE_MINT,
    slippage_bps: 50,
    ..Default::default()
}).await?;
```

#### JavaScript/TypeScript
- **@jup-ag/api**: NPM пакет для интеграции
- **Jupiter Terminal**: Готовый UI компонент
- Пример интеграции через CDN в HTML

#### Go
- **jupiter-go**: Неофициальный Go клиент
- Поддержка Jito tips и priority fees
- Мониторинг транзакций через WebSocket

### Endpoints и API версии:

#### Актуальные endpoints (2025):
```
# Бесплатное использование
GET https://lite-api.jup.ag/swap/v1/quote
POST https://lite-api.jup.ag/swap/v1/swap

# Платные планы
GET https://api.jup.ag/swap/v1/quote  
POST https://api.jup.ag/swap/v1/swap
```

#### Пример запроса котировки:
```bash
curl -G "https://lite-api.jup.ag/swap/v1/quote" \
  --data-urlencode "inputMint=So11111111111111111111111111111111111111112" \
  --data-urlencode "outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" \
  --data-urlencode "amount=100000000" \
  --data-urlencode "slippageBps=50" \
  --data-urlencode "platformFeeBps=20"
```

### Интеграция с AMM:

#### Jupiter AMM Interface
- Стандартизированный интерфейс для AMM протоколов
- Поддержка различных DEX (Orca, Raydium, Meteora и др.)
- Снапшоты состояния для тестирования

#### Пример интеграции AMM:
```rust
// Ограничить реализацию до десериализации состояния
impl Amm for YourAmm {
    fn quote(&self, params: &QuoteParams) -> Result<Quote, AmmError> {
        // Вызвать ваш SDK для получения котировки
        your_sdk::get_quote(params)
    }
    
    fn update(&mut self, account_map: &AccountMap) -> Result<(), AmmError> {
        // Обновить состояние при изменении аккаунтов
        self.deserialize_accounts(account_map)
    }
}
```

## 📈 Практические рекомендации для арбитражного бота

### Архитектура бота:

1. **Модульная структура**:
   - Отдельные модули для каждого DEX
   - Унифицированный интерфейс для всех источников ликвидности
   - Система приоритизации и фильтрации возможностей

2. **Стратегия мониторинга**:
   - Параллельный мониторинг Jupiter RFQ и AMM
   - Кэширование котировок с TTL
   - Алерты на значимые изменения цен

3. **Исполнение арбитража**:
   - Bundled transactions для атомарного исполнения
   - Динамическое управление Priority Fee
   - Резервные RPC endpoints

### Оптимизация производительности:

```python
# Пример структуры для Python бота
class JupiterRFQClient:
    def __init__(self, api_key=None):
        self.base_url = "https://api.jup.ag" if api_key else "https://lite-api.jup.ag"
        self.session = httpx.AsyncClient()
    
    async def get_quote(self, input_mint, output_mint, amount, platform_fee_bps=10):
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount,
            "platformFeeBps": platform_fee_bps
        }
        response = await self.session.get(f"{self.base_url}/swap/v1/quote", params=params)
        return response.json()
```

### Управление рисками:

- **Slippage protection**: Динамическое управление slippage в зависимости от волатильности
- **MEV protection**: Использование private mempools (Jito)
- **Capital efficiency**: Оптимальное разделение капитала между возможностями

## �📚 Дополнительные ресурсы

### Официальные ресурсы:
- **Discord**: [https://discord.gg/jup](https://discord.gg/jup)
- **GitHub**: [https://github.com/jup-ag](https://github.com/jup-ag)
- **Документация**: [https://dev.jup.ag/docs](https://dev.jup.ag/docs)
- **API Portal**: [https://portal.jup.ag](https://portal.jup.ag)

### Примеры кода:
- **Rust примеры**: [jupiter-swap-api-client](https://github.com/jup-ag/jupiter-swap-api-client)
- **JavaScript примеры**: [jupiter-swap](https://github.com/AlmostEfficient/jupiter-swap)
- **Go примеры**: [jupiter-go](https://github.com/ilkamo/jupiter-go)
- **AMM интеграция**: [jupiter-amm-implementation](https://github.com/jup-ag/jupiter-amm-implementation)

### Сообщество:
- **Telegram**: Jupiter community updates
- **Reddit**: r/jupiterexchange
- **Twitter**: @JupiterExchange

---

*Отчет составлен на основе официальной документации Jupiter Developer Docs и анализа открытых репозиториев*