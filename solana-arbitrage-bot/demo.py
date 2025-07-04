"""
Demo script for testing the Solana arbitrage bot functionality.
This script demonstrates the quote fetching and arbitrage detection
without requiring a real private key or executing actual transactions.
"""
import asyncio
import sys
from datetime import datetime
from models import TokenPair, Quote, QuoteSource, Side
from rfq_client import JupiterRFQClient
from amm_client import AMMClientManager
from engine import ArbitrageEngine


async def demo_quote_fetching():
    """Demo quote fetching from various sources."""
    print("🚀 Solana Arbitrage Bot Demo")
    print("=" * 50)
    
    # Initialize clients
    rfq_client = JupiterRFQClient()
    amm_manager = AMMClientManager()
    
    # Test token pair
    token_pair = TokenPair.from_string("SOL/USDC")
    trade_amount = 1000.0
    
    print(f"📊 Fetching quotes for {token_pair} (Amount: {trade_amount})")
    print("-" * 30)
    
    try:
        # Fetch RFQ quotes
        print("🔍 Fetching Jupiter RFQ quotes...")
        rfq_quotes = await rfq_client.get_quotes_for_pair(
            token_pair, 
            trade_amount
        )
        
        print(f"   Found {len(rfq_quotes)} RFQ quotes")
        for quote in rfq_quotes:
            print(f"   - {quote.side.value}: {quote.price:.6f} (source: {quote.source.value})")
        
        # Fetch AMM quotes
        print("\n🔍 Fetching AMM quotes...")
        amm_quotes = await amm_manager.get_all_quotes(
            token_pair,
            trade_amount
        )
        
        print(f"   Found {len(amm_quotes)} AMM quotes")
        for quote in amm_quotes:
            print(f"   - {quote.side.value}: {quote.price:.6f} (source: {quote.source.value})")
        
        # Demonstrate arbitrage detection
        print("\n💰 Checking for arbitrage opportunities...")
        engine = ArbitrageEngine()
        opportunities = engine._find_arbitrage_opportunities(rfq_quotes, amm_quotes)
        
        if opportunities:
            print(f"   Found {len(opportunities)} opportunities!")
            best = max(opportunities, key=lambda o: o.profit_bps)
            print(f"   Best opportunity: {best.profit_bps} bps profit")
            print(f"   Buy from: {best.buy_quote.source.value}")
            print(f"   Sell to: {best.sell_quote.source.value}")
        else:
            print("   No profitable opportunities found")
        
    except Exception as e:
        print(f"❌ Error during demo: {e}")
        
    print("\n✅ Demo completed!")


async def demo_mock_quotes():
    """Demo with mock quotes to show arbitrage detection."""
    print("\n🧪 Mock Quote Arbitrage Demo")
    print("=" * 50)
    
    # Create mock quotes with price differences
    mock_rfq_quotes = [
        Quote(
            source=QuoteSource.JUPITER_RFQ,
            side=Side.BUY,
            input_token="USDC",
            output_token="SOL",
            input_amount=1000.0,
            output_amount=4.95,  # Slightly higher output
            price=0.00495,
            timestamp=datetime.now(),
            ttl_ms=120000
        ),
        Quote(
            source=QuoteSource.JUPITER_RFQ,
            side=Side.SELL,
            input_token="SOL",
            output_token="USDC",
            input_amount=5.0,
            output_amount=1010.0,  # Higher sell price
            price=202.0,
            timestamp=datetime.now(),
            ttl_ms=120000
        )
    ]
    
    mock_amm_quotes = [
        Quote(
            source=QuoteSource.RAYDIUM,
            side=Side.BUY,
            input_token="USDC",
            output_token="SOL",
            input_amount=1000.0,
            output_amount=4.90,  # Lower output (worse buy price)
            price=0.0049,
            timestamp=datetime.now(),
            ttl_ms=30000
        ),
        Quote(
            source=QuoteSource.RAYDIUM,
            side=Side.SELL,
            input_token="SOL",
            output_token="USDC",
            input_amount=5.0,
            output_amount=995.0,  # Lower sell price
            price=199.0,
            timestamp=datetime.now(),
            ttl_ms=30000
        )
    ]
    
    print("📊 Mock Quotes:")
    print("RFQ Quotes:")
    for quote in mock_rfq_quotes:
        print(f"   - {quote.side.value}: {quote.price:.6f}")
    
    print("AMM Quotes:")
    for quote in mock_amm_quotes:
        print(f"   - {quote.side.value}: {quote.price:.6f}")
    
    # Find arbitrage opportunities
    engine = ArbitrageEngine()
    opportunities = engine._find_arbitrage_opportunities(mock_rfq_quotes, mock_amm_quotes)
    
    print(f"\n💰 Found {len(opportunities)} arbitrage opportunities:")
    
    for i, opp in enumerate(opportunities, 1):
        print(f"\n   Opportunity #{i}:")
        print(f"   - Profit: {opp.profit_bps} basis points")
        print(f"   - Profit Amount: ${opp.profit_amount:.2f}")
        print(f"   - Strategy: Buy from {opp.buy_quote.source.value}, Sell to {opp.sell_quote.source.value}")
        print(f"   - Buy Price: {opp.buy_quote.price:.6f}")
        print(f"   - Sell Price: {opp.sell_quote.price:.6f}")


async def main():
    """Run the demo."""
    print("🎯 Welcome to the Solana Arbitrage Bot Demo!")
    print("This demo shows quote fetching and arbitrage detection.")
    print("No real transactions will be executed.\n")
    
    # Run real quote fetching demo
    await demo_quote_fetching()
    
    # Run mock quote demo
    await demo_mock_quotes()
    
    print("\n" + "=" * 50)
    print("📚 Next Steps:")
    print("1. Set up your SOLANA_PRIVATE_KEY environment variable")
    print("2. Run: python main.py check --pair SOL/USDC")
    print("3. If opportunities exist, run: python main.py start")
    print("\n⚠️  Remember: This is a prototype. Test carefully with small amounts!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Demo stopped by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        sys.exit(1)