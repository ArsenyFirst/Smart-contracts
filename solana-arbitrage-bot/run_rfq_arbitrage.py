#!/usr/bin/env python3
"""
Jupiter RFQ Arbitrage Bot Launcher

This script provides a simple interface to run the Jupiter RFQ arbitrage system
in different modes: testing, scanning, or continuous trading.

Usage:
    python run_rfq_arbitrage.py [mode]
    
Modes:
    test    - Run test suite
    scan    - Single arbitrage scan
    trade   - Continuous trading (requires wallet)
    demo    - Interactive demo mode
"""

import asyncio
import sys
import os
from datetime import datetime
import argparse

# Import the RFQ arbitrage system
from jupiter_rfq_arbitrage import RFQArbitrageEngine, SUPPORTED_PAIRS
from test_rfq_arbitrage import RFQArbitrageDemo


def print_banner():
    """Print application banner."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    Jupiter RFQ Arbitrage Bot                ║
║                                                              ║
║  🤖 Automated arbitrage between Jupiter RFQ and DEXs        ║
║  💰 SOL/USDC and SOL/USDT pairs only                       ║
║  ⚡ Bundle transactions for atomic execution                 ║
║  📊 0.1% Jupiter RFQ fee factored into calculations         ║
╚══════════════════════════════════════════════════════════════╝
    """)
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 Supported pairs: {', '.join(str(p) for p in SUPPORTED_PAIRS)}")


async def run_test_mode():
    """Run the test suite."""
    print("\n🧪 TEST MODE")
    print("=" * 60)
    demo = RFQArbitrageDemo()
    await demo.test_individual_components()
    await demo.run_full_arbitrage_scan()


async def run_scan_mode():
    """Run a single arbitrage scan."""
    print("\n🔍 SCAN MODE")
    print("=" * 60)
    
    engine = RFQArbitrageEngine()
    opportunities = await engine.scan_arbitrage_opportunities()
    
    if opportunities:
        print(f"🎯 Found {len(opportunities)} profitable opportunities:")
        
        for i, opp in enumerate(opportunities[:3], 1):
            print(f"\n{i}. {opp.arbitrage_type}")
            print(f"   Pair: {opp.rfq_quote.token_pair}")
            print(f"   Net Profit: {opp.net_profit_bps} bps (${opp.profit_amount_usd:.2f})")
            print(f"   ROI: {opp.roi_percentage:.3f}%")
            print(f"   Capital: ${opp.min_capital_required:.2f}")
            print(f"   RFQ expires in: {opp.rfq_quote.time_to_expiry_seconds:.1f}s")
    else:
        print("❌ No profitable arbitrage opportunities found")


async def run_trade_mode():
    """Run continuous trading mode."""
    print("\n💰 TRADE MODE")
    print("=" * 60)
    print("⚠️  WARNING: This mode requires a funded wallet!")
    print("⚠️  Only use with funds you can afford to lose!")
    
    # Check for wallet configuration
    wallet_private_key = os.getenv("SOLANA_PRIVATE_KEY")
    if not wallet_private_key:
        print("\n❌ No wallet configured!")
        print("Please set SOLANA_PRIVATE_KEY environment variable")
        return
    
    confirm = input("\nContinue with live trading? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Trading cancelled")
        return
    
    print("\n🚀 Starting continuous arbitrage trading...")
    engine = RFQArbitrageEngine()
    
    try:
        await engine.run_continuous_monitoring(interval_seconds=2.0)
    except KeyboardInterrupt:
        print("\n🛑 Trading stopped by user")


async def run_demo_mode():
    """Run interactive demo mode."""
    print("\n🎮 DEMO MODE")
    print("=" * 60)
    
    demo = RFQArbitrageDemo()
    
    while True:
        print("\n📋 Demo Options:")
        print("1. Quick scan")
        print("2. Detailed analysis")
        print("3. Price comparison")
        print("4. Continuous monitoring (1 min)")
        print("5. Exit")
        
        choice = input("\nSelect option (1-5): ").strip()
        
        try:
            if choice == "1":
                await demo.run_full_arbitrage_scan()
            elif choice == "2":
                await demo.test_individual_components()
            elif choice == "3":
                await demo.run_price_comparison_analysis()
            elif choice == "4":
                await demo.run_continuous_monitoring(1)
            elif choice == "5":
                break
            else:
                print("Invalid choice")
        except KeyboardInterrupt:
            print("\n⏸️  Operation cancelled")
        except Exception as e:
            print(f"\n❌ Error: {e}")
    
    print("👋 Demo mode ended")


async def main():
    """Main launcher function."""
    parser = argparse.ArgumentParser(
        description="Jupiter RFQ Arbitrage Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_rfq_arbitrage.py test     # Run test suite
    python run_rfq_arbitrage.py scan     # Single scan
    python run_rfq_arbitrage.py trade    # Live trading
    python run_rfq_arbitrage.py demo     # Interactive demo
        """
    )
    
    parser.add_argument(
        "mode",
        nargs="?",
        choices=["test", "scan", "trade", "demo"],
        default="demo",
        help="Operating mode (default: demo)"
    )
    
    parser.add_argument(
        "--min-profit",
        type=int,
        default=25,
        help="Minimum profit in basis points (default: 25)"
    )
    
    parser.add_argument(
        "--trade-amounts",
        nargs="+",
        type=float,
        default=[100, 500, 1000, 2500],
        help="Trade amounts in USD (default: 100 500 1000 2500)"
    )
    
    args = parser.parse_args()
    
    print_banner()
    
    # Configure the engine with user parameters
    if hasattr(args, 'min_profit'):
        # This would configure the engine settings
        pass
    
    try:
        if args.mode == "test":
            await run_test_mode()
        elif args.mode == "scan":
            await run_scan_mode()
        elif args.mode == "trade":
            await run_trade_mode()
        elif args.mode == "demo":
            await run_demo_mode()
        else:
            print(f"❌ Unknown mode: {args.mode}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        sys.exit(1)
    
    print(f"\n✅ Session completed at {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())