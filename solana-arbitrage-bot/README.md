# 🤖 Solana Arbitrage Bot

A Python prototype for detecting and executing arbitrage opportunities on Solana between Jupiter RFQ and AMM DEXes (Orca, Raydium, Meteora).

## 🎯 Features

- **Multi-source Quote Fetching**: Fetches quotes from Jupiter RFQ API and AMM DEXes
- **Real-time Arbitrage Detection**: Compares quotes to find profitable opportunities
- **Atomic Execution**: Bundles buy/sell transactions atomically
- **P&L Tracking**: Tracks performance and profitability
- **CLI Interface**: Easy-to-use command-line interface
- **Configurable**: Flexible configuration for different trading strategies
- **Structured Logging**: Comprehensive logging for monitoring and debugging

## 🏗 Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Jupiter RFQ   │    │   AMM DEXes     │    │   Arbitrage     │
│     Client      │    │   (Orca, etc.)  │    │    Engine       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                     ┌─────────────────┐
                     │  Transaction    │
                     │    Builder      │
                     └─────────────────┘
                                 │
                     ┌─────────────────┐
                     │    Solana       │
                     │   Blockchain    │
                     └─────────────────┘
```

## 🛠 Installation

### Prerequisites

- Python 3.10+
- Solana wallet with private key
- SOL for transaction fees

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd solana-arbitrage-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Configure your Solana wallet:
```bash
export SOLANA_PRIVATE_KEY="your_base58_private_key"
export SOLANA_RPC_URL="https://api.mainnet-beta.solana.com"
```

## 🚀 Usage

### Configuration

The bot can be configured through environment variables or CLI arguments:

- `SOLANA_PRIVATE_KEY`: Your Solana wallet private key (base58 encoded)
- `SOLANA_RPC_URL`: Solana RPC endpoint
- Trade amount, profit thresholds, and other parameters can be set via CLI

### Running the Bot

#### 1. Check for Opportunities (Dry Run)

```bash
python main.py check --pair SOL/USDC --amount 1000
```

This will:
- Fetch quotes from all sources
- Identify arbitrage opportunities
- Display results without executing trades

#### 2. Start Continuous Trading

```bash
python main.py start --pair SOL/USDC --amount 1000 --threshold 10
```

Parameters:
- `--pair`: Token pair to trade (e.g., SOL/USDC)
- `--amount`: Trade amount in quote currency
- `--threshold`: Minimum profit threshold in basis points
- `--interval`: Loop interval in seconds

#### 3. View Configuration

```bash
python main.py config-show
```

#### 4. Export Configuration

```bash
python main.py config-export --output my-config.json
```

#### 5. View Statistics

```bash
python main.py stats
```

### Example Output

```
=== Arbitrage Check Results ===
Token Pair: SOL/USDC
Trade Amount: 1000.0
RFQ Quotes: 2
AMM Quotes: 4
Opportunities Found: 1

=== Best Opportunity ===
Profit: 15 bps (1.5 USDC)
Buy from: raydium
Sell to: jupiter_rfq
Executable: Yes

=== Configuration ===
Min Profit Threshold: 10 bps
Loop Interval: 1.0s
Request Timeout: 2.0s
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SOLANA_PRIVATE_KEY` | Base58 encoded private key | Required |
| `SOLANA_RPC_URL` | Solana RPC endpoint | `https://api.mainnet-beta.solana.com` |

### Bot Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `trade_amount` | Amount to trade | 1000.0 |
| `min_profit_threshold_bps` | Minimum profit in basis points | 10 |
| `loop_interval_seconds` | Time between checks | 1.0 |
| `request_timeout_seconds` | API request timeout | 2.0 |

### Supported DEXes

- **Jupiter RFQ**: Request-for-quote system
- **Raydium**: AMM with concentrated liquidity
- **Meteora**: Dynamic liquidity market maker
- **Orca**: Concentrated liquidity AMM (simplified implementation)

## 📊 Monitoring & Logging

The bot uses structured logging with JSON output:

```json
{
  "event": "Arbitrage opportunity found",
  "profit_bps": 15,
  "profit_amount": 1.5,
  "buy_source": "raydium",
  "sell_source": "jupiter_rfq",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## ⚠️ Important Notes

### Risk Warnings

- **High Risk**: Arbitrage trading involves significant financial risk
- **MEV Competition**: Other bots may front-run your transactions
- **Slippage**: Actual execution may differ from quoted prices
- **Gas Costs**: Transaction fees can eliminate small profits
- **TTL Expiry**: RFQ quotes expire quickly (100-200ms)

### Limitations of This Prototype

This is a **prototype implementation** with several limitations:

1. **Simplified Transaction Building**: Real DEX integrations require full SDK implementations
2. **No MEV Protection**: Transactions are not protected from front-running
3. **Basic Fee Calculation**: Gas and priority fee estimation is simplified
4. **No Flash Loans**: Capital requirements limit position sizes
5. **Limited Orca Support**: Orca implementation requires on-chain data fetching

### Production Considerations

For a production implementation, you would need:

- **Advanced Transaction Bundling**: Use Jito or similar bundling services
- **Dynamic Fee Management**: Real-time priority fee optimization
- **Full DEX SDK Integration**: Complete implementation for each DEX
- **MEV Protection**: Bundle transactions to prevent front-running
- **Advanced Monitoring**: Real-time alerts and performance tracking
- **Risk Management**: Position sizing and loss limits
- **High-Performance Infrastructure**: Low-latency servers near validators

## 🔧 Development

### Project Structure

```
solana-arbitrage-bot/
├── config.py          # Configuration management
├── models.py           # Data models and types
├── rfq_client.py       # Jupiter RFQ API client
├── amm_client.py       # AMM DEX clients
├── engine.py           # Core arbitrage logic
├── tx_builder.py       # Transaction building
├── main.py             # CLI interface
├── requirements.txt    # Dependencies
└── README.md          # Documentation
```

### Adding New DEXes

To add support for a new DEX:

1. Create a new client class in `amm_client.py`
2. Implement the `get_quote()` method
3. Add transaction building logic in `tx_builder.py`
4. Register the client in `AMMClientManager`

### Testing

```bash
# Run a dry-run check
python main.py check --pair SOL/USDC

# Test with different parameters
python main.py check --pair SOL/USDC --amount 500

# View configuration
python main.py config-show
```

## 📈 Performance Optimization

### Speed Optimizations

1. **Parallel Quote Fetching**: All quotes are fetched simultaneously
2. **Connection Pooling**: HTTP clients reuse connections
3. **Minimal Processing**: Fast quote comparison algorithms
4. **Async Operations**: Non-blocking I/O throughout

### Latency Considerations

- **RPC Proximity**: Use RPC endpoints close to validators
- **Quote TTL**: RFQ quotes expire in ~100-200ms
- **Network Latency**: Every millisecond counts in arbitrage
- **Transaction Priority**: Higher priority fees for faster inclusion

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Implement your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is provided as-is for educational and research purposes. Use at your own risk.

## ⚡ Quick Start Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export SOLANA_PRIVATE_KEY="your_private_key"

# Check for opportunities
python main.py check --pair SOL/USDC

# Start the bot (if opportunities exist)
python main.py start --pair SOL/USDC --threshold 15

# Monitor performance
python main.py stats
```

## 🆘 Troubleshooting

### Common Issues

1. **No quotes returned**: Check API endpoints and network connectivity
2. **Transaction failures**: Ensure sufficient SOL balance for fees
3. **Expired quotes**: Reduce loop interval or increase processing speed
4. **RPC errors**: Try different RPC endpoints or increase timeout

### Debug Mode

```bash
python main.py --log-level DEBUG check --pair SOL/USDC
```

This will provide detailed logging for troubleshooting.

---

**Disclaimer**: This is a prototype implementation for educational purposes. Real arbitrage trading requires significant additional development, testing, and risk management. Trade at your own risk.