"""
Test Enhanced Jupiter RFQ Arbitrage System

This script demonstrates the enhanced system capabilities:
- Enhanced Jupiter API client with rate limiting
- Webhook notifications and monitoring
- Improved DEX integrations
- Risk assessment and profitability analysis
"""

import asyncio
import json
from enhanced_rfq_arbitrage import EnhancedRFQArbitrageEngine
from enhanced_jupiter_client import JupiterConfig, APITier
from rfq_monitoring_system import EventType, AlertLevel


async def test_enhanced_jupiter_client():
    """Test the enhanced Jupiter client."""
    print("=== Testing Enhanced Jupiter Client ===")
    
    from enhanced_jupiter_client import EnhancedJupiterClient, QuoteParams
    from config import config
    
    jupiter_config = JupiterConfig(
        api_key=None,  # Free tier
        tier=APITier.LITE,
        rate_limit_per_second=5,
        enable_caching=True
    )
    
    async with EnhancedJupiterClient(jupiter_config) as client:
        # Setup test event handler
        @client.event_system.on("quote_received")
        async def on_quote_received(data):
            print(f"✅ Quote received: {data.get('quote_id')}")
        
        # Test quote request
        params = QuoteParams(
            input_mint=config.tokens["SOL"],
            output_mint=config.tokens["USDC"],
            amount=100_000_000,  # 0.1 SOL
            slippage_bps=50
        )
        
        quote = await client.get_quote(params)
        
        if quote:
            print(f"Quote ID: {quote.quote_id}")
            print(f"Effective Price: ${quote.effective_price:.2f}")
            print(f"RFQ Fee: ${quote.rfq_fee_amount:.4f}")
            print(f"Expires in: {quote.time_to_expiry_seconds:.1f}s")
        else:
            print("❌ Failed to get quote")
        
        # Show metrics
        metrics = client.get_metrics()
        print(f"Client Metrics: {json.dumps(metrics, indent=2)}")


async def test_monitoring_system():
    """Test the monitoring and webhook system."""
    print("\n=== Testing Monitoring System ===")
    
    from rfq_monitoring_system import RFQMonitoringSystem
    
    monitor = RFQMonitoringSystem(log_file_path="test_events.log")
    
    # Add custom event handler
    @monitor.on_event(EventType.OPPORTUNITY_FOUND)
    async def on_opportunity(data):
        print(f"🎯 Opportunity: {data.get('profit_bps')} bps profit from {data.get('dex')}")
    
    # Simulate events
    await monitor.emit_event(
        EventType.OPPORTUNITY_FOUND,
        {
            "token_pair": "SOL/USDC",
            "profit_bps": 25,
            "profit_usd": 2.5,
            "dex": "meteora",
            "arbitrage_type": "buy_rfq_sell_dex"
        },
        AlertLevel.INFO
    )
    
    await monitor.emit_event(
        EventType.TRADE_EXECUTED,
        {
            "success": True,
            "profit_usd": 2.5,
            "volume_usd": 1000,
            "execution_time_ms": 1200
        },
        AlertLevel.INFO
    )
    
    # Get dashboard data
    dashboard = monitor.get_dashboard_data()
    print(f"Dashboard: {json.dumps(dashboard, indent=2, default=str)}")


async def test_dex_integrations():
    """Test enhanced DEX integrations."""
    print("\n=== Testing DEX Integrations ===")
    
    from enhanced_rfq_arbitrage import EnhancedDEXClient
    from rfq_monitoring_system import RFQMonitoringSystem
    from models import TokenPair, Side
    
    monitoring = RFQMonitoringSystem()
    
    async with EnhancedDEXClient(monitoring) as dex_client:
        token_pair = TokenPair("SOL", "USDC")
        amount_usd = 1000.0
        
        # Test all DEX quotes
        quotes = await dex_client.get_all_dex_quotes(
            token_pair, amount_usd, Side.BUY
        )
        
        print(f"Received {len(quotes)} DEX quotes:")
        for quote in quotes:
            print(f"  {quote.source}: ${quote.price:.2f} (confidence: {quote.confidence_score:.2f})")


async def test_arbitrage_analysis():
    """Test arbitrage opportunity analysis."""
    print("\n=== Testing Arbitrage Analysis ===")
    
    from enhanced_rfq_arbitrage import EnhancedRFQArbitrageEngine
    
    jupiter_config = JupiterConfig(
        api_key=None,
        tier=APITier.LITE,
        rate_limit_per_second=3,  # Conservative for testing
        enable_caching=True
    )
    
    engine = EnhancedRFQArbitrageEngine(jupiter_config)
    
    # Test short scan
    print("Starting short arbitrage scan...")
    
    # Override the main loop for testing
    async with engine.monitoring as monitor:
        # Add test webhook (optional)
        # monitor.add_webhook("https://httpbin.org/post")
        
        # Simulate running for a few cycles
        scan_count = 0
        max_scans = 3
        
        from enhanced_jupiter_client import EnhancedJupiterClient
        from enhanced_rfq_arbitrage import EnhancedDEXClient
        
        async with EnhancedJupiterClient(engine.jupiter_config) as jupiter_client:
            async with EnhancedDEXClient(engine.monitoring) as dex_client:
                
                while scan_count < max_scans:
                    try:
                        opportunities = await engine._scan_opportunities(
                            jupiter_client, dex_client
                        )
                        
                        print(f"Scan {scan_count + 1}: Found {len(opportunities)} opportunities")
                        
                        if opportunities:
                            best = max(opportunities, key=lambda op: op.risk_adjusted_profit)
                            print(f"  Best: {best.profit_amount_usd:.2f} USD profit, "
                                  f"risk: {best.risk_score:.2f}, "
                                  f"confidence: {best.confidence_score:.2f}")
                        
                        scan_count += 1
                        await asyncio.sleep(1)
                        
                    except Exception as e:
                        print(f"❌ Scan error: {e}")
                        break
        
        # Show final dashboard
        dashboard = engine.get_dashboard_data()
        print(f"\nFinal Dashboard:")
        print(f"  Opportunities detected: {dashboard['system_metrics']['performance']['opportunities_detected']}")
        print(f"  API calls made: {dashboard['system_metrics']['performance']['api_calls_made']}")
        print(f"  Health status: {dashboard['system_metrics']['health_status']['overall']}")


async def run_mini_demo():
    """Run a mini demo of the system for 30 seconds."""
    print("\n=== Running Mini Demo (30 seconds) ===")
    
    jupiter_config = JupiterConfig(
        api_key=None,
        tier=APITier.LITE,
        rate_limit_per_second=2,  # Very conservative
        enable_caching=True
    )
    
    engine = EnhancedRFQArbitrageEngine(jupiter_config)
    
    # Add demo event handler
    @engine.monitoring.on_event(EventType.OPPORTUNITY_FOUND)
    async def demo_opportunity_handler(data):
        print(f"🎯 DEMO: {data.get('arbitrage_type')} opportunity - "
              f"{data.get('profit_bps')} bps profit on {data.get('token_pair')}")
    
    @engine.monitoring.on_event(EventType.TRADE_EXECUTED)  
    async def demo_trade_handler(data):
        status = "✅ SUCCESS" if data.get("success") else "❌ FAILED"
        print(f"💰 DEMO: Trade {status} - ${data.get('profit_usd', 0):.2f} profit")
    
    # Run demo
    print("Starting demo monitoring... Press Ctrl+C to stop early")
    
    try:
        # Start monitoring in background
        monitor_task = asyncio.create_task(
            engine.start_monitoring(scan_interval_seconds=5.0)
        )
        
        # Let it run for 30 seconds
        await asyncio.sleep(30)
        
        # Stop monitoring
        engine.stop_monitoring()
        monitor_task.cancel()
        
        print("\n📊 Demo Complete! Final Stats:")
        dashboard = engine.get_dashboard_data()
        metrics = dashboard['system_metrics']['performance']
        print(f"  Opportunities found: {metrics['opportunities_detected']}")
        print(f"  Trades executed: {metrics['trades_executed']}")
        print(f"  Success rate: {metrics.get('success_rate', lambda: 0)():.1f}%")
        print(f"  Total profit: ${metrics['total_profit_usd']:.2f}")
        
    except KeyboardInterrupt:
        print("\n🛑 Demo stopped by user")
        engine.stop_monitoring()


async def main():
    """Run all tests."""
    print("🚀 Enhanced Jupiter RFQ Arbitrage System - Test Suite")
    print("=" * 60)
    
    try:
        # Individual component tests
        await test_enhanced_jupiter_client()
        await test_monitoring_system()
        await test_dex_integrations()
        await test_arbitrage_analysis()
        
        # Interactive demo
        print("\n" + "=" * 60)
        response = input("Run 30-second live demo? (y/n): ")
        if response.lower() in ['y', 'yes']:
            await run_mini_demo()
        
        print("\n✅ All tests completed!")
        
    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())