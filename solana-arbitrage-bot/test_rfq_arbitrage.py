#!/usr/bin/env python3
"""
Test Script for Jupiter RFQ Arbitrage System

This script demonstrates the complete RFQ arbitrage workflow:
1. Fetches real Jupiter RFQ quotes
2. Compares with actual Meteora pool prices
3. Identifies arbitrage opportunities
4. Builds and simulates bundle transactions
5. Shows detailed profit calculations with 0.1% RFQ fee
"""

import asyncio
import sys
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any
import structlog

# Import our RFQ arbitrage modules
from jupiter_rfq_arbitrage import (
    RFQArbitrageEngine, 
    JupiterRFQArbitrageClient,
    DirectDEXClient,
    SUPPORTED_PAIRS,
    JUPITER_RFQ_FEE_BPS
)
from rfq_bundle_builder import execute_rfq_arbitrage_with_bundles
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


class RFQArbitrageDemo:
    """Demo class for testing Jupiter RFQ arbitrage system."""
    
    def __init__(self):
        self.engine = RFQArbitrageEngine()
        
    async def test_individual_components(self):
        """Test individual components of the RFQ arbitrage system."""
        print("🧪 Testing Individual Components")
        print("=" * 60)
        
        # Test 1: Jupiter RFQ quotes
        await self._test_jupiter_rfq_quotes()
        
        # Test 2: Meteora direct quotes
        await self._test_meteora_quotes()
        
        # Test 3: Arbitrage detection
        await self._test_arbitrage_detection()
    
    async def _test_jupiter_rfq_quotes(self):
        """Test Jupiter RFQ quote fetching."""
        print("\n📡 Testing Jupiter RFQ Quotes...")
        
        async with JupiterRFQArbitrageClient() as client:
            for pair in SUPPORTED_PAIRS[:1]:  # Test first pair only
                print(f"   Testing {pair}...")
                
                for side in [Side.BUY, Side.SELL]:
                    quote = await client.get_rfq_quote(pair, 1000.0, side)
                    
                    if quote:
                        print(f"   ✅ {side.value} quote: {quote.effective_price:.6f}")
                        print(f"      RFQ Fee: ${quote.rfq_fee_amount:.2f} ({JUPITER_RFQ_FEE_BPS/100:.1f}%)")
                        print(f"      Expires: {quote.time_to_expiry_seconds:.1f}s")
                    else:
                        print(f"   ❌ Failed to get {side.value} quote")
    
    async def _test_meteora_quotes(self):
        """Test Meteora direct quote fetching."""
        print("\n🌊 Testing Meteora Direct Quotes...")
        
        async with DirectDEXClient() as client:
            for pair in SUPPORTED_PAIRS[:1]:  # Test first pair only
                print(f"   Testing {pair}...")
                
                for side in [Side.BUY, Side.SELL]:
                    quote = await client.get_meteora_quote(pair, 1000.0, side)
                    
                    if quote:
                        print(f"   ✅ {side.value} quote: {quote.price:.6f}")
                        print(f"      Pool: ${quote.liquidity:,.0f} TVL")
                        print(f"      Fee: {quote.fee_bps/100:.2f}%")
                    else:
                        print(f"   ❌ Failed to get {side.value} quote")
    
    async def _test_arbitrage_detection(self):
        """Test arbitrage opportunity detection."""
        print("\n🔍 Testing Arbitrage Detection...")
        
        opportunities = await self.engine.scan_arbitrage_opportunities()
        
        if opportunities:
            print(f"   ✅ Found {len(opportunities)} opportunities")
            best = opportunities[0]
            print(f"   Best: {best.net_profit_bps} bps profit")
            print(f"   Type: {best.arbitrage_type}")
        else:
            print("   ❌ No opportunities found")
    
    async def run_full_arbitrage_scan(self):
        """Run a complete arbitrage scan with detailed output."""
        print("\n🚀 Jupiter RFQ vs DEX Arbitrage Scanner")
        print("=" * 60)
        print(f"📊 Scanning {len(SUPPORTED_PAIRS)} pairs: {', '.join(str(p) for p in SUPPORTED_PAIRS)}")
        print(f"💰 Test amounts: {self.engine.trade_amounts}")
        print(f"🎯 Min profit threshold: {self.engine.min_profit_bps} bps")
        print(f"💸 Jupiter RFQ fee: {JUPITER_RFQ_FEE_BPS/100:.1f}%")
        
        # Scan for opportunities
        start_time = datetime.now()
        opportunities = await self.engine.scan_arbitrage_opportunities()
        scan_time = (datetime.now() - start_time).total_seconds()
        
        print(f"\n⏱️  Scan completed in {scan_time:.2f} seconds")
        
        if not opportunities:
            print("❌ No profitable arbitrage opportunities found")
            return
        
        print(f"🎯 Found {len(opportunities)} profitable opportunities!")
        print("\n" + "=" * 60)
        
        # Display opportunities
        for i, opp in enumerate(opportunities[:5], 1):  # Show top 5
            await self._display_opportunity_details(i, opp)
        
        # Test bundle execution on best opportunity
        if opportunities:
            await self._test_bundle_execution(opportunities[0])
    
    async def _display_opportunity_details(self, index: int, opp):
        """Display detailed information about an arbitrage opportunity."""
        print(f"\n🏆 Opportunity #{index}")
        print("-" * 40)
        print(f"   Pair: {opp.rfq_quote.token_pair}")
        print(f"   Strategy: {opp.arbitrage_type}")
        print(f"   💰 Net Profit: {opp.net_profit_bps} bps (${opp.profit_amount_usd:.2f})")
        print(f"   📈 ROI: {opp.roi_percentage:.3f}%")
        print(f"   💵 Capital Required: ${opp.min_capital_required:.2f}")
        
        print(f"\n   📡 Jupiter RFQ Quote:")
        print(f"      Side: {opp.rfq_quote.side.value}")
        print(f"      Gross Price: {opp.rfq_quote.gross_price:.6f}")
        print(f"      Effective Price: {opp.rfq_quote.effective_price:.6f}")
        print(f"      RFQ Fee: ${opp.rfq_quote.rfq_fee_amount:.3f}")
        print(f"      Expires: {opp.rfq_quote.time_to_expiry_seconds:.1f}s")
        
        print(f"\n   🌊 {opp.dex_quote.source.value.title()} Quote:")
        print(f"      Side: {opp.dex_quote.side.value}")
        print(f"      Price: {opp.dex_quote.price:.6f}")
        print(f"      Fee: {opp.dex_quote.fee_bps/100:.2f}%")
        print(f"      Liquidity: ${opp.dex_quote.liquidity:,.0f}")
        
        print(f"\n   📊 Profit Breakdown:")
        print(f"      Gross Profit: {opp.gross_profit_bps} bps")
        print(f"      DEX Fees: -{opp.dex_quote.fee_bps} bps")
        print(f"      Gas Cost: -${opp.estimated_gas_cost:.3f}")
        print(f"      Net Profit: {opp.net_profit_bps} bps")
        
        # Calculate execution urgency
        if opp.rfq_quote.time_to_expiry_seconds < 15:
            urgency = "🔴 URGENT"
        elif opp.rfq_quote.time_to_expiry_seconds < 30:
            urgency = "🟡 MODERATE"
        else:
            urgency = "🟢 NORMAL"
        
        print(f"   ⏰ Execution Urgency: {urgency}")
    
    async def _test_bundle_execution(self, opportunity):
        """Test bundle transaction building and execution."""
        print(f"\n🛠️  Testing Bundle Transaction Execution")
        print("-" * 40)
        
        # Use test wallet address
        test_wallet = "2AQdpHJ2JpcEgPiATUXjQxA8QmafFegfQwSLWSprPicm"
        
        try:
            # Execute bundle (simulation)
            result = await execute_rfq_arbitrage_with_bundles(
                opportunity,
                wallet_address=test_wallet,
                priority_fee_lamports=2000
            )
            
            if result["success"]:
                print("   ✅ Bundle execution successful!")
                print(f"   Bundle ID: {result['bundle_id']}")
                print(f"   Execution time: {result['execution_result']['execution_time_ms']}ms")
                print(f"   Tx signatures: {len(result['execution_result']['transaction_signatures'])}")
            else:
                print(f"   ❌ Bundle execution failed: {result['error']}")
                
        except Exception as e:
            print(f"   ❌ Bundle execution error: {e}")
    
    async def run_continuous_monitoring(self, duration_minutes: int = 5):
        """Run continuous monitoring for a specified duration."""
        print(f"\n🔄 Starting Continuous Monitoring ({duration_minutes} minutes)")
        print("=" * 60)
        
        end_time = datetime.now() + timedelta(minutes=duration_minutes)
        cycle_count = 0
        total_opportunities = 0
        best_profit_seen = 0
        
        try:
            while datetime.now() < end_time:
                cycle_count += 1
                cycle_start = datetime.now()
                
                print(f"\n🔍 Cycle #{cycle_count} - {cycle_start.strftime('%H:%M:%S')}")
                
                # Scan for opportunities
                opportunities = await self.engine.scan_arbitrage_opportunities()
                total_opportunities += len(opportunities)
                
                if opportunities:
                    best_opp = opportunities[0]
                    best_profit_seen = max(best_profit_seen, best_opp.net_profit_bps)
                    
                    print(f"   🎯 Found {len(opportunities)} opportunities")
                    print(f"   🏆 Best: {best_opp.net_profit_bps} bps profit")
                    print(f"   📈 Type: {best_opp.arbitrage_type}")
                    print(f"   ⏰ RFQ expires: {best_opp.rfq_quote.time_to_expiry_seconds:.1f}s")
                    
                    # Would execute in production
                    if best_opp.net_profit_bps >= 50:  # High profit threshold for demo
                        print(f"   🚀 HIGH PROFIT - Would execute in production!")
                else:
                    print("   📊 No opportunities found this cycle")
                
                # Wait for next cycle
                cycle_time = (datetime.now() - cycle_start).total_seconds()
                await asyncio.sleep(max(0, 2.0 - cycle_time))  # 2-second cycles
                
        except KeyboardInterrupt:
            print("\n👋 Monitoring stopped by user")
        
        # Summary
        print(f"\n📈 Monitoring Summary")
        print("-" * 40)
        print(f"   Cycles completed: {cycle_count}")
        print(f"   Total opportunities: {total_opportunities}")
        print(f"   Best profit seen: {best_profit_seen} bps")
        print(f"   Avg opportunities/cycle: {total_opportunities/cycle_count:.1f}")
    
    async def run_price_comparison_analysis(self):
        """Run detailed price comparison analysis between Jupiter RFQ and DEXs."""
        print(f"\n📊 Price Comparison Analysis")
        print("=" * 60)
        
        async with JupiterRFQArbitrageClient() as rfq_client, DirectDEXClient() as dex_client:
            for pair in SUPPORTED_PAIRS:
                print(f"\n🔍 Analyzing {pair}")
                print("-" * 30)
                
                for amount_usd in [100, 500, 1000, 2500]:
                    print(f"\n   💰 ${amount_usd} trade size:")
                    
                    # Get RFQ quotes
                    rfq_buy = await rfq_client.get_rfq_quote(pair, amount_usd, Side.BUY)
                    rfq_sell = await rfq_client.get_rfq_quote(pair, amount_usd, Side.SELL)
                    
                    # Get DEX quotes
                    dex_buy = await dex_client.get_meteora_quote(pair, amount_usd, Side.BUY)
                    dex_sell = await dex_client.get_meteora_quote(pair, amount_usd, Side.SELL)
                    
                    # Compare prices
                    if rfq_buy and dex_sell:
                        spread = abs(rfq_buy.effective_price - dex_sell.price)
                        spread_pct = (spread / min(rfq_buy.effective_price, dex_sell.price)) * 100
                        print(f"      RFQ Buy vs DEX Sell: {spread_pct:.3f}% spread")
                    
                    if rfq_sell and dex_buy:
                        spread = abs(rfq_sell.effective_price - dex_buy.price)
                        spread_pct = (spread / min(rfq_sell.effective_price, dex_buy.price)) * 100
                        print(f"      RFQ Sell vs DEX Buy: {spread_pct:.3f}% spread")


async def main():
    """Main test function."""
    demo = RFQArbitrageDemo()
    
    print("🤖 Jupiter RFQ Arbitrage System Test Suite")
    print("=" * 60)
    print("This demo showcases Jupiter RFQ arbitrage opportunities")
    print("comparing RFQ quotes with direct DEX pricing.")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Test menu
        print("\n📋 Available Tests:")
        print("1. Component Testing")
        print("2. Full Arbitrage Scan")  
        print("3. Continuous Monitoring (5 min)")
        print("4. Price Comparison Analysis")
        print("5. All Tests")
        
        choice = input("\nSelect test (1-5): ").strip()
        
        if choice == "1":
            await demo.test_individual_components()
        elif choice == "2":
            await demo.run_full_arbitrage_scan()
        elif choice == "3":
            await demo.run_continuous_monitoring(5)
        elif choice == "4":
            await demo.run_price_comparison_analysis()
        elif choice == "5":
            await demo.test_individual_components()
            await demo.run_full_arbitrage_scan()
            await demo.run_price_comparison_analysis()
        else:
            print("Running default full scan...")
            await demo.run_full_arbitrage_scan()
            
    except KeyboardInterrupt:
        print("\n👋 Test suite interrupted by user")
    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
        logger.error("Test suite error", error=str(e))
    
    print(f"\n✅ Test suite completed at {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    # Run the test suite
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        sys.exit(1)