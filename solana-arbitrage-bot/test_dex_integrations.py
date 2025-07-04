#!/usr/bin/env python3
"""
Comprehensive DEX Integration Test

This script tests all integrated DEX APIs:
- Jupiter RFQ (primary quote source)
- Meteora DLMM (real API integration)
- Raydium v3 API (with fallback estimation)
- Orca Whirlpools (estimated quotes)

Demonstrates complete arbitrage opportunity detection across all platforms.
"""

import asyncio
import sys
from datetime import datetime
from typing import List, Dict, Any
import structlog
import json

# Import all our DEX integration modules
from jupiter_rfq_arbitrage import (
    JupiterRFQArbitrageClient,
    DirectDEXClient,
    RFQArbitrageEngine,
    SUPPORTED_PAIRS,
    JUPITER_RFQ_FEE_BPS
)
from models import TokenPair, Side

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class DEXIntegrationTester:
    """Comprehensive DEX integration testing suite."""
    
    def __init__(self):
        self.rfq_client = JupiterRFQArbitrageClient()
        self.dex_client = DirectDEXClient()
        self.engine = RFQArbitrageEngine()
        
    async def test_all_dex_integrations(self):
        """Test all DEX integrations individually."""
        print("🔧 Testing All DEX Integrations")
        print("=" * 70)
        
        test_pair = SUPPORTED_PAIRS[0]  # SOL/USDC
        test_amount = 1000.0  # $1000 USD
        
        # Test each integration
        await self._test_jupiter_rfq(test_pair, test_amount)
        await self._test_meteora_integration(test_pair, test_amount)
        await self._test_raydium_integration(test_pair, test_amount)
        await self._test_orca_integration(test_pair, test_amount)
    
    async def _test_jupiter_rfq(self, token_pair: TokenPair, amount: float):
        """Test Jupiter RFQ integration."""
        print(f"\n📡 Testing Jupiter RFQ Integration")
        print("-" * 50)
        
        async with self.rfq_client:
            for side in [Side.BUY, Side.SELL]:
                try:
                    quote = await self.rfq_client.get_rfq_quote(token_pair, amount, side)
                    
                    if quote:
                        print(f"   ✅ {side.value.upper()} quote received")
                        print(f"      Gross Price: {quote.gross_price:.6f}")
                        print(f"      Effective Price: {quote.effective_price:.6f}")
                        print(f"      RFQ Fee: ${quote.rfq_fee_amount:.3f} ({JUPITER_RFQ_FEE_BPS/100:.1f}%)")
                        print(f"      Expires in: {quote.time_to_expiry_seconds:.1f}s")
                        print(f"      Quote ID: {quote.quote_id}")
                    else:
                        print(f"   ❌ {side.value.upper()} quote failed")
                        
                except Exception as e:
                    print(f"   ❌ {side.value.upper()} quote error: {e}")
    
    async def _test_meteora_integration(self, token_pair: TokenPair, amount: float):
        """Test Meteora DLMM integration."""
        print(f"\n🌊 Testing Meteora DLMM Integration")
        print("-" * 50)
        
        async with self.dex_client:
            for side in [Side.BUY, Side.SELL]:
                try:
                    quote = await self.dex_client.get_meteora_quote(token_pair, amount, side)
                    
                    if quote:
                        print(f"   ✅ {side.value.upper()} quote received")
                        print(f"      Price: {quote.price:.6f}")
                        print(f"      Fee: {quote.fee_bps/100:.2f}%")
                        print(f"      Pool Address: {quote.pool_address}")
                        print(f"      Liquidity: ${quote.liquidity:,.0f}")
                        print(f"      Input Amount: {quote.input_amount:.6f}")
                        print(f"      Output Amount: {quote.output_amount:.6f}")
                    else:
                        print(f"   ❌ {side.value.upper()} quote failed")
                        
                except Exception as e:
                    print(f"   ❌ {side.value.upper()} quote error: {e}")
    
    async def _test_raydium_integration(self, token_pair: TokenPair, amount: float):
        """Test Raydium v3 API integration."""
        print(f"\n⚡ Testing Raydium V3 Integration")
        print("-" * 50)
        
        async with self.dex_client:
            for side in [Side.BUY, Side.SELL]:
                try:
                    quote = await self.dex_client.get_raydium_quote(token_pair, amount, side)
                    
                    if quote:
                        print(f"   ✅ {side.value.upper()} quote received")
                        print(f"      Price: {quote.price:.6f}")
                        print(f"      Fee: {quote.fee_bps/100:.2f}%")
                        print(f"      Pool: {quote.pool_address}")
                        print(f"      Liquidity: ${quote.liquidity:,.0f}")
                        print(f"      Input Amount: {quote.input_amount:.6f}")
                        print(f"      Output Amount: {quote.output_amount:.6f}")
                        
                        # Indicate if this is estimated vs real API data
                        if quote.pool_address == "estimated":
                            print(f"      ⚠️  Note: Fallback estimation (API unavailable)")
                        else:
                            print(f"      ✅ Real API data")
                    else:
                        print(f"   ❌ {side.value.upper()} quote failed")
                        
                except Exception as e:
                    print(f"   ❌ {side.value.upper()} quote error: {e}")
    
    async def _test_orca_integration(self, token_pair: TokenPair, amount: float):
        """Test Orca Whirlpools integration."""
        print(f"\n🐋 Testing Orca Whirlpools Integration")
        print("-" * 50)
        
        async with self.dex_client:
            for side in [Side.BUY, Side.SELL]:
                try:
                    quote = await self.dex_client.get_orca_quote(token_pair, amount, side)
                    
                    if quote:
                        print(f"   ✅ {side.value.upper()} quote received")
                        print(f"      Price: {quote.price:.6f}")
                        print(f"      Fee: {quote.fee_bps/100:.2f}% (dynamic)")
                        print(f"      Pool Type: Whirlpool CLMM")
                        print(f"      Liquidity: ${quote.liquidity:,.0f}")
                        print(f"      Input Amount: {quote.input_amount:.6f}")
                        print(f"      Output Amount: {quote.output_amount:.6f}")
                        print(f"      ⚠️  Note: Estimated quote (on-chain data required for exact pricing)")
                    else:
                        print(f"   ❌ {side.value.upper()} quote failed")
                        
                except Exception as e:
                    print(f"   ❌ {side.value.upper()} quote error: {e}")
    
    async def test_cross_dex_arbitrage(self):
        """Test arbitrage detection across all DEX integrations."""
        print(f"\n🔍 Cross-DEX Arbitrage Analysis")
        print("=" * 70)
        
        for pair in SUPPORTED_PAIRS:
            print(f"\n📊 Analyzing {pair}")
            print("-" * 30)
            
            for amount_usd in [500, 1000, 2500]:
                print(f"\n   💰 ${amount_usd} trade size:")
                
                try:
                    # Get RFQ quotes
                    async with self.rfq_client:
                        rfq_buy = await self.rfq_client.get_rfq_quote(pair, amount_usd, Side.BUY)
                        rfq_sell = await self.rfq_client.get_rfq_quote(pair, amount_usd, Side.SELL)
                    
                    # Get all DEX quotes
                    async with self.dex_client:
                        meteora_buy = await self.dex_client.get_meteora_quote(pair, amount_usd, Side.BUY)
                        meteora_sell = await self.dex_client.get_meteora_quote(pair, amount_usd, Side.SELL)
                        
                        raydium_buy = await self.dex_client.get_raydium_quote(pair, amount_usd, Side.BUY)
                        raydium_sell = await self.dex_client.get_raydium_quote(pair, amount_usd, Side.SELL)
                        
                        orca_buy = await self.dex_client.get_orca_quote(pair, amount_usd, Side.BUY)
                        orca_sell = await self.dex_client.get_orca_quote(pair, amount_usd, Side.SELL)
                    
                    # Analyze price differences
                    quotes = {
                        "Jupiter RFQ": {"buy": rfq_buy, "sell": rfq_sell},
                        "Meteora": {"buy": meteora_buy, "sell": meteora_sell},
                        "Raydium": {"buy": raydium_buy, "sell": raydium_sell},
                        "Orca": {"buy": orca_buy, "sell": orca_sell}
                    }
                    
                    await self._analyze_price_spreads(quotes, amount_usd)
                    
                except Exception as e:
                    print(f"      ❌ Error analyzing {pair} at ${amount_usd}: {e}")
    
    async def _analyze_price_spreads(self, quotes: Dict[str, Dict[str, Any]], amount_usd: float):
        """Analyze price spreads between different DEXs."""
        print(f"      📈 Price Analysis:")
        
        # Extract valid quotes
        valid_quotes = {}
        for dex_name, quote_pair in quotes.items():
            buy_quote = quote_pair["buy"]
            sell_quote = quote_pair["sell"]
            
            if buy_quote and sell_quote:
                # Use effective price for RFQ, regular price for others
                if dex_name == "Jupiter RFQ":
                    buy_price = buy_quote.effective_price
                    sell_price = sell_quote.effective_price
                else:
                    buy_price = buy_quote.price
                    sell_price = sell_quote.price
                
                valid_quotes[dex_name] = {
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "spread": abs(buy_price - sell_price) / min(buy_price, sell_price) * 100
                }
        
        if len(valid_quotes) < 2:
            print(f"         ⚠️  Insufficient quotes for comparison")
            return
        
        # Display prices
        for dex_name, prices in valid_quotes.items():
            fee_note = " (incl. 0.1% RFQ fee)" if dex_name == "Jupiter RFQ" else ""
            print(f"         {dex_name}: Buy {prices['buy_price']:.6f}, Sell {prices['sell_price']:.6f}{fee_note}")
        
        # Find arbitrage opportunities
        opportunities = []
        dex_names = list(valid_quotes.keys())
        
        for i, dex1 in enumerate(dex_names):
            for dex2 in dex_names[i+1:]:
                # Strategy 1: Buy from dex1, sell to dex2
                profit1 = valid_quotes[dex2]["sell_price"] - valid_quotes[dex1]["buy_price"]
                profit1_pct = (profit1 / valid_quotes[dex1]["buy_price"]) * 100
                
                # Strategy 2: Buy from dex2, sell to dex1
                profit2 = valid_quotes[dex1]["sell_price"] - valid_quotes[dex2]["buy_price"]
                profit2_pct = (profit2 / valid_quotes[dex2]["buy_price"]) * 100
                
                if profit1_pct > 0.1:  # More than 0.1% profit
                    opportunities.append({
                        "strategy": f"Buy {dex1}, Sell {dex2}",
                        "profit_pct": profit1_pct,
                        "profit_usd": profit1 * amount_usd / valid_quotes[dex1]["buy_price"]
                    })
                
                if profit2_pct > 0.1:  # More than 0.1% profit
                    opportunities.append({
                        "strategy": f"Buy {dex2}, Sell {dex1}",
                        "profit_pct": profit2_pct,
                        "profit_usd": profit2 * amount_usd / valid_quotes[dex2]["buy_price"]
                    })
        
        # Display opportunities
        if opportunities:
            opportunities.sort(key=lambda x: x["profit_pct"], reverse=True)
            print(f"         🎯 Arbitrage Opportunities Found:")
            for opp in opportunities[:3]:  # Top 3
                print(f"            {opp['strategy']}: {opp['profit_pct']:.3f}% (${opp['profit_usd']:.2f})")
        else:
            print(f"         📊 No significant arbitrage opportunities (>0.1%)")
    
    async def run_comprehensive_test(self):
        """Run all tests in sequence."""
        print("🤖 Comprehensive DEX Integration Test Suite")
        print("=" * 70)
        print("Testing Jupiter RFQ arbitrage with Meteora, Raydium, and Orca")
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # Test individual integrations
            await self.test_all_dex_integrations()
            
            # Test cross-platform arbitrage
            await self.test_cross_dex_arbitrage()
            
            # Test the full engine
            await self._test_arbitrage_engine()
            
        except Exception as e:
            print(f"\n❌ Test suite error: {e}")
            logger.error("Test suite error", error=str(e))
        
        print(f"\n✅ Test suite completed at {datetime.now().strftime('%H:%M:%S')}")
    
    async def _test_arbitrage_engine(self):
        """Test the complete arbitrage engine."""
        print(f"\n🎯 Testing Complete Arbitrage Engine")
        print("=" * 70)
        
        print("   🔍 Scanning for arbitrage opportunities...")
        opportunities = await self.engine.scan_arbitrage_opportunities()
        
        if opportunities:
            print(f"   ✅ Found {len(opportunities)} profitable opportunities!")
            
            for i, opp in enumerate(opportunities[:3], 1):
                print(f"\n   🏆 Opportunity #{i}")
                print(f"      Pair: {opp.rfq_quote.token_pair}")
                print(f"      Strategy: {opp.arbitrage_type}")
                print(f"      Net Profit: {opp.net_profit_bps} bps (${opp.profit_amount_usd:.2f})")
                print(f"      Capital Required: ${opp.min_capital_required:.2f}")
                print(f"      ROI: {opp.roi_percentage:.3f}%")
                
                # Source details
                rfq_side = opp.rfq_quote.side.value
                dex_side = opp.dex_quote.side.value
                dex_name = opp.dex_quote.source.value.title()
                
                print(f"      RFQ: {rfq_side} at {opp.rfq_quote.effective_price:.6f}")
                print(f"      {dex_name}: {dex_side} at {opp.dex_quote.price:.6f}")
                print(f"      Time to execute: {opp.rfq_quote.time_to_expiry_seconds:.1f}s")
        else:
            print("   📊 No profitable arbitrage opportunities found")
            print("   This is normal - profitable opportunities are rare and fleeting")
    
    async def benchmark_api_performance(self):
        """Benchmark the performance of all DEX APIs."""
        print(f"\n⏱️  API Performance Benchmark")
        print("=" * 70)
        
        test_pair = SUPPORTED_PAIRS[0]
        test_amount = 1000.0
        iterations = 5
        
        print(f"   Testing {iterations} iterations for each DEX...")
        
        # Test each DEX performance
        apis = [
            ("Jupiter RFQ", self._benchmark_rfq),
            ("Meteora DLMM", self._benchmark_meteora),
            ("Raydium V3", self._benchmark_raydium),
            ("Orca Whirlpools", self._benchmark_orca)
        ]
        
        for api_name, benchmark_func in apis:
            print(f"\n   📊 {api_name}:")
            avg_time = await benchmark_func(test_pair, test_amount, iterations)
            print(f"      Average response time: {avg_time:.3f}s")
    
    async def _benchmark_rfq(self, pair: TokenPair, amount: float, iterations: int) -> float:
        """Benchmark Jupiter RFQ performance."""
        total_time = 0
        successful = 0
        
        async with self.rfq_client:
            for _ in range(iterations):
                start = datetime.now()
                try:
                    quote = await self.rfq_client.get_rfq_quote(pair, amount, Side.BUY)
                    if quote:
                        successful += 1
                except:
                    pass
                total_time += (datetime.now() - start).total_seconds()
        
        avg_time = total_time / iterations
        print(f"         Success rate: {successful}/{iterations}")
        return avg_time
    
    async def _benchmark_meteora(self, pair: TokenPair, amount: float, iterations: int) -> float:
        """Benchmark Meteora performance."""
        total_time = 0
        successful = 0
        
        async with self.dex_client:
            for _ in range(iterations):
                start = datetime.now()
                try:
                    quote = await self.dex_client.get_meteora_quote(pair, amount, Side.BUY)
                    if quote:
                        successful += 1
                except:
                    pass
                total_time += (datetime.now() - start).total_seconds()
        
        avg_time = total_time / iterations
        print(f"         Success rate: {successful}/{iterations}")
        return avg_time
    
    async def _benchmark_raydium(self, pair: TokenPair, amount: float, iterations: int) -> float:
        """Benchmark Raydium performance."""
        total_time = 0
        successful = 0
        
        async with self.dex_client:
            for _ in range(iterations):
                start = datetime.now()
                try:
                    quote = await self.dex_client.get_raydium_quote(pair, amount, Side.BUY)
                    if quote:
                        successful += 1
                except:
                    pass
                total_time += (datetime.now() - start).total_seconds()
        
        avg_time = total_time / iterations
        print(f"         Success rate: {successful}/{iterations}")
        return avg_time
    
    async def _benchmark_orca(self, pair: TokenPair, amount: float, iterations: int) -> float:
        """Benchmark Orca performance."""
        total_time = 0
        successful = 0
        
        async with self.dex_client:
            for _ in range(iterations):
                start = datetime.now()
                try:
                    quote = await self.dex_client.get_orca_quote(pair, amount, Side.BUY)
                    if quote:
                        successful += 1
                except:
                    pass
                total_time += (datetime.now() - start).total_seconds()
        
        avg_time = total_time / iterations
        print(f"         Success rate: {successful}/{iterations}")
        return avg_time


async def main():
    """Main test function."""
    tester = DEXIntegrationTester()
    
    try:
        choice = input("Select test mode:\n1. Full comprehensive test\n2. Quick integration test\n3. Performance benchmark\nChoice (1-3): ").strip()
        
        if choice == "1":
            await tester.run_comprehensive_test()
        elif choice == "2":
            await tester.test_all_dex_integrations()
        elif choice == "3":
            await tester.benchmark_api_performance()
        else:
            print("Running default comprehensive test...")
            await tester.run_comprehensive_test()
            
    except KeyboardInterrupt:
        print("\n👋 Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Test error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())