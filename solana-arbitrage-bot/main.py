"""
Main entry point for the Solana arbitrage bot.
"""
import asyncio
import signal
import sys
from typing import Optional
import click
import structlog
import json
from datetime import datetime

from models import TokenPair
from engine import ArbitrageEngine
from config import config


# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class ArbitrageBotApp:
    """Main application class for the arbitrage bot."""
    
    def __init__(self):
        self.engine = ArbitrageEngine()
        self.running = False
    
    async def start(self, token_pair: TokenPair):
        """Start the arbitrage bot."""
        self.running = True
        
        # Setup signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info("Received shutdown signal", signal=signum)
            self.running = False
            self.engine.stop()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        logger.info(
            "Starting Solana Arbitrage Bot",
            token_pair=str(token_pair),
            trade_amount=config.trade_amount,
            min_profit_threshold_bps=config.min_profit_threshold_bps
        )
        
        try:
            await self.engine.start(token_pair)
        except Exception as e:
            logger.error("Bot crashed", error=str(e))
            raise
        finally:
            logger.info("Arbitrage bot stopped")
    
    async def run_single_check(self, token_pair: TokenPair):
        """Run a single arbitrage check."""
        logger.info("Running single arbitrage check", token_pair=str(token_pair))
        
        result = await self.engine.run_single_check(token_pair)
        
        logger.info("Single check completed", result=result)
        return result
    
    async def get_stats(self):
        """Get bot statistics."""
        return self.engine.get_stats()


@click.group()
@click.option('--config-file', help='Path to configuration file')
@click.option('--log-level', default='INFO', help='Logging level')
def cli(config_file, log_level):
    """Solana Arbitrage Bot - Find and execute arbitrage opportunities."""
    
    # Set log level
    import logging
    logging.getLogger().setLevel(getattr(logging, log_level.upper()))
    
    if config_file:
        # Load configuration from file
        logger.info("Loading configuration", file=config_file)
        # In a real implementation, you'd load config from file


@cli.command()
@click.option('--pair', default='SOL/USDC', help='Token pair to trade (e.g., SOL/USDC)')
@click.option('--amount', default=None, type=float, help='Trade amount in quote currency')
@click.option('--threshold', default=None, type=int, help='Minimum profit threshold in basis points')
@click.option('--interval', default=None, type=float, help='Loop interval in seconds')
def start(pair, amount, threshold, interval):
    """Start the arbitrage bot."""
    
    # Override config with CLI arguments
    if amount:
        config.trade_amount = amount
    if threshold:
        config.min_profit_threshold_bps = threshold
    if interval:
        config.loop_interval_seconds = interval
    
    # Validate configuration
    if not config.private_key:
        logger.error("SOLANA_PRIVATE_KEY environment variable is required")
        sys.exit(1)
    
    # Parse token pair
    try:
        token_pair = TokenPair.from_string(pair)
    except Exception as e:
        logger.error("Invalid token pair", pair=pair, error=str(e))
        sys.exit(1)
    
    # Start the bot
    app = ArbitrageBotApp()
    
    try:
        asyncio.run(app.start(token_pair))
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as e:
        logger.error("Fatal error", error=str(e))
        sys.exit(1)


@cli.command()
@click.option('--pair', default='SOL/USDC', help='Token pair to check (e.g., SOL/USDC)')
@click.option('--amount', default=None, type=float, help='Trade amount in quote currency')
def check(pair, amount):
    """Run a single arbitrage check."""
    
    if amount:
        config.trade_amount = amount
    
    # Parse token pair
    try:
        token_pair = TokenPair.from_string(pair)
    except Exception as e:
        logger.error("Invalid token pair", pair=pair, error=str(e))
        sys.exit(1)
    
    # Run single check
    app = ArbitrageBotApp()
    
    async def run_check():
        result = await app.run_single_check(token_pair)
        
        # Pretty print results
        print(f"\n=== Arbitrage Check Results ===")
        print(f"Token Pair: {pair}")
        print(f"Trade Amount: {config.trade_amount}")
        print(f"RFQ Quotes: {result['rfq_quotes_count']}")
        print(f"AMM Quotes: {result['amm_quotes_count']}")
        print(f"Opportunities Found: {result['opportunities_found']}")
        
        if result['best_opportunity']:
            opp = result['best_opportunity']
            print(f"\n=== Best Opportunity ===")
            print(f"Profit: {opp['profit_bps']} bps ({opp['profit_amount']:.6f})")
            print(f"Buy from: {opp['buy_source']}")
            print(f"Sell to: {opp['sell_source']}")
            print(f"Executable: {'Yes' if result['executable'] else 'No'}")
            
            if not result['executable']:
                print(f"Reason: Below threshold ({config.min_profit_threshold_bps} bps)")
        else:
            print("No profitable opportunities found")
        
        print(f"\n=== Configuration ===")
        print(f"Min Profit Threshold: {config.min_profit_threshold_bps} bps")
        print(f"Loop Interval: {config.loop_interval_seconds}s")
        print(f"Request Timeout: {config.request_timeout_seconds}s")
    
    try:
        asyncio.run(run_check())
    except Exception as e:
        logger.error("Check failed", error=str(e))
        sys.exit(1)


@cli.command()
def stats():
    """Show bot statistics."""
    
    app = ArbitrageBotApp()
    
    async def show_stats():
        stats = await app.get_stats()
        
        print(f"\n=== Bot Statistics ===")
        print(f"Total Trades: {stats['total_trades']}")
        print(f"Successful Trades: {stats['successful_trades']}")
        print(f"Failed Trades: {stats['failed_trades']}")
        print(f"Success Rate: {stats['success_rate']:.1f}%")
        print(f"Total Profit: {stats['total_profit']:.6f}")
        print(f"Average Profit per Trade: {stats['average_profit_per_trade']:.6f}")
        print(f"Total Fees: {stats['total_fees']:.6f}")
        print(f"Uptime: {stats['uptime_hours']:.2f} hours")
    
    try:
        asyncio.run(show_stats())
    except Exception as e:
        logger.error("Failed to get stats", error=str(e))
        sys.exit(1)


@cli.command()
def config_show():
    """Show current configuration."""
    
    print(f"\n=== Configuration ===")
    print(f"Asset Pair: {config.asset_pair}")
    print(f"Trade Amount: {config.trade_amount}")
    print(f"Min Profit Threshold: {config.min_profit_threshold_bps} bps")
    print(f"Loop Interval: {config.loop_interval_seconds}s")
    print(f"Request Timeout: {config.request_timeout_seconds}s")
    print(f"Max Retries: {config.max_retries}")
    print(f"Solana RPC: {config.solana_rpc_url}")
    print(f"Log Level: {config.log_level}")
    print(f"Log to File: {config.log_to_file}")
    
    print(f"\n=== API Endpoints ===")
    print(f"Jupiter RFQ: {config.jupiter_rfq_url}")
    print(f"Raydium: {config.raydium_api_url}")
    print(f"Meteora: {config.meteora_api_url}")
    print(f"Orca: {config.orca_api_url}")
    
    print(f"\n=== Supported Tokens ===")
    for symbol, mint in config.tokens.items():
        print(f"{symbol}: {mint}")


@cli.command()
@click.option('--output', default='config.json', help='Output file path')
def config_export(output):
    """Export configuration to JSON file."""
    
    config_dict = {
        'asset_pair': config.asset_pair,
        'trade_amount': config.trade_amount,
        'min_profit_threshold_bps': config.min_profit_threshold_bps,
        'loop_interval_seconds': config.loop_interval_seconds,
        'request_timeout_seconds': config.request_timeout_seconds,
        'max_retries': config.max_retries,
        'solana_rpc_url': config.solana_rpc_url,
        'log_level': config.log_level,
        'log_to_file': config.log_to_file,
        'jupiter_rfq_url': config.jupiter_rfq_url,
        'raydium_api_url': config.raydium_api_url,
        'meteora_api_url': config.meteora_api_url,
        'orca_api_url': config.orca_api_url,
        'tokens': config.tokens
    }
    
    with open(output, 'w') as f:
        json.dump(config_dict, f, indent=2)
    
    logger.info("Configuration exported", file=output)


if __name__ == '__main__':
    cli()