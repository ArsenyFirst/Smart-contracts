"""
Working LP Arbitrage Monitor using Meteora DLMM and Jupiter APIs.
Monitors real liquidity pool data for arbitrage opportunities.
"""
import asyncio
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional
import httpx
import structlog
from dataclasses import dataclass
from enum import Enum
import json


class LPSource(Enum):
    METEORA_DLMM = "meteora_dlmm"
    JUPITER_AGG = "jupiter_aggregator"


@dataclass
class LPPool:
    source: LPSource
    pool_address: str
    token_a: str
    token_b: str
    token_a_symbol: str
    token_b_symbol: str
    token_a_reserve: float
    token_b_reserve: float
    price_a_to_b: float
    price_b_to_a: float
    tvl_usd: Optional[float] = None
    fee_tier: Optional[float] = None
    volume_24h: Optional[float] = None
    apr: Optional[float] = None
    apy: Optional[float] = None
    timestamp: datetime = None


# Configure structured logging
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


# Known token mappings
TOKENS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "WSOL": "So11111111111111111111111111111111111111112",
}

# Reverse mapping for quick lookups
MINT_TO_SYMBOL = {v: k for k, v in TOKENS.items()}


class WorkingLPMonitor:
    """Working LP monitor using successful APIs."""
    
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self.meteora_url = "https://dlmm-api.meteora.ag"
        self.jupiter_url = "https://quote-api.jup.ag/v6"
        
        # Cache for token symbol lookups
        self.token_cache = {}
    
    def _get_token_symbol(self, mint_address: str) -> Optional[str]:
        """Get token symbol from mint address."""
        if mint_address in MINT_TO_SYMBOL:
            return MINT_TO_SYMBOL[mint_address]
        
        # Cache unknown tokens
        if mint_address in self.token_cache:
            return self.token_cache[mint_address]
        
        return None
    
    def _normalize_pair_name(self, symbol_a: str, symbol_b: str) -> str:
        """Create normalized pair name (alphabetical order)."""
        tokens = sorted([symbol_a, symbol_b])
        return f"{tokens[0]}/{tokens[1]}"
    
    async def fetch_meteora_pools(self) -> List[LPPool]:
        """Fetch real LP data from Meteora DLMM."""
        pools = []
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.meteora_url}/pair/all")
                
                if response.status_code != 200:
                    logger.error("Meteora API error", status_code=response.status_code)
                    return pools
                
                data = response.json()
                logger.info(f"Fetched {len(data)} Meteora pools")
                
                # Filter for our target tokens
                target_tokens = set(TOKENS.keys())
                
                for pool_data in data:
                    try:
                        mint_x = pool_data.get("mint_x", "")
                        mint_y = pool_data.get("mint_y", "")
                        
                        symbol_x = self._get_token_symbol(mint_x)
                        symbol_y = self._get_token_symbol(mint_y)
                        
                        # Skip if we don't recognize both tokens
                        if not (symbol_x and symbol_y):
                            continue
                        
                        # Only monitor target pairs
                        if not (symbol_x in target_tokens and symbol_y in target_tokens):
                            continue
                        
                        # Skip blacklisted or hidden pools
                        if pool_data.get("is_blacklisted", False) or pool_data.get("hide", False):
                            continue
                        
                        # Extract pool data
                        reserve_x = float(pool_data.get("reserve_x", 0))
                        reserve_y = float(pool_data.get("reserve_y", 0))
                        current_price = float(pool_data.get("current_price", 0))
                        liquidity_usd = pool_data.get("liquidity")
                        
                        # Skip pools with very low liquidity
                        if liquidity_usd and liquidity_usd < 1000:  # Min $1000 TVL
                            continue
                        
                        # Calculate prices
                        price_x_to_y = current_price
                        price_y_to_x = 1 / current_price if current_price > 0 else 0
                        
                        pool = LPPool(
                            source=LPSource.METEORA_DLMM,
                            pool_address=pool_data.get("address", ""),
                            token_a=mint_x,
                            token_b=mint_y,
                            token_a_symbol=symbol_x,
                            token_b_symbol=symbol_y,
                            token_a_reserve=reserve_x,
                            token_b_reserve=reserve_y,
                            price_a_to_b=price_x_to_y,
                            price_b_to_a=price_y_to_x,
                            tvl_usd=liquidity_usd,
                            fee_tier=pool_data.get("base_fee_percentage", 0),
                            volume_24h=pool_data.get("trade_volume_24h"),
                            apr=pool_data.get("apr"),
                            apy=pool_data.get("apy"),
                            timestamp=datetime.now()
                        )
                        
                        pools.append(pool)
                        
                    except Exception as e:
                        logger.debug("Error parsing pool", error=str(e), pool_address=pool_data.get("address"))
                        continue
                        
        except Exception as e:
            logger.error("Error fetching Meteora pools", error=str(e))
        
        logger.info(f"Filtered to {len(pools)} relevant pools")
        return pools
    
    async def get_jupiter_quote(self, input_mint: str, output_mint: str, amount_lamports: int) -> Optional[Dict]:
        """Get quote from Jupiter aggregator."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                params = {
                    "inputMint": input_mint,
                    "outputMint": output_mint,
                    "amount": str(amount_lamports),
                    "slippageBps": 50,
                }
                
                response = await client.get(f"{self.jupiter_url}/quote", params=params)
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.debug("Jupiter quote error", status_code=response.status_code)
                    
        except Exception as e:
            logger.debug("Jupiter quote exception", error=str(e))
        
        return None
    
    async def compare_with_jupiter(self, pools: List[LPPool]) -> List[Dict[str, Any]]:
        """Compare LP prices with Jupiter aggregated quotes."""
        opportunities = []
        
        # Test amount (1 SOL or 100 USDC equivalent)
        test_amounts = {
            "SOL": 1000000000,  # 1 SOL in lamports
            "USDC": 100000000,   # 100 USDC in smallest units
            "USDT": 100000000,   # 100 USDT in smallest units
        }
        
        for pool in pools:
            symbol_a = pool.token_a_symbol
            symbol_b = pool.token_b_symbol
            
            # Test both directions
            for input_token, output_token in [(symbol_a, symbol_b), (symbol_b, symbol_a)]:
                
                # Skip if we don't have a test amount for this token
                if input_token not in test_amounts:
                    continue
                
                input_mint = TOKENS[input_token]
                output_mint = TOKENS[output_token]
                test_amount = test_amounts[input_token]
                
                # Get Jupiter quote
                jupiter_quote = await self.get_jupiter_quote(input_mint, output_mint, test_amount)
                
                if not jupiter_quote:
                    continue
                
                # Calculate Jupiter rate
                jupiter_input = float(jupiter_quote.get("inAmount", 0))
                jupiter_output = float(jupiter_quote.get("outAmount", 0))
                
                if jupiter_input == 0:
                    continue
                
                # Convert to same units as pool
                if input_token == "SOL":
                    jupiter_input_readable = jupiter_input / 1e9
                    jupiter_output_readable = jupiter_output / 1e6
                else:
                    jupiter_input_readable = jupiter_input / 1e6
                    jupiter_output_readable = jupiter_output / (1e9 if output_token == "SOL" else 1e6)
                
                jupiter_rate = jupiter_output_readable / jupiter_input_readable if jupiter_input_readable > 0 else 0
                
                # Get LP rate
                if input_token == symbol_a:
                    lp_rate = pool.price_a_to_b
                else:
                    lp_rate = pool.price_b_to_a
                
                # Compare rates
                if jupiter_rate > 0 and lp_rate > 0:
                    rate_diff = abs(jupiter_rate - lp_rate)
                    rate_diff_pct = (rate_diff / min(jupiter_rate, lp_rate)) * 100
                    
                    # Determine which is better
                    better_on = "Jupiter" if jupiter_rate > lp_rate else "Meteora"
                    worse_on = "Meteora" if jupiter_rate > lp_rate else "Jupiter"
                    
                    if rate_diff_pct > 0.1:  # 0.1% threshold
                        
                        # Get Jupiter route info
                        route_plan = jupiter_quote.get("routePlan", [])
                        route_dexes = []
                        for step in route_plan[:3]:  # First 3 steps
                            dex_label = step.get("swapInfo", {}).get("label", "Unknown")
                            route_dexes.append(dex_label)
                        
                        opportunity = {
                            "pair": f"{input_token}/{output_token}",
                            "test_amount": f"{jupiter_input_readable:.6f} {input_token}",
                            "price_difference_pct": rate_diff_pct,
                            "better_on": better_on,
                            "worse_on": worse_on,
                            "meteora_pool": {
                                "address": pool.pool_address,
                                "rate": lp_rate,
                                "tvl": pool.tvl_usd,
                                "fee": pool.fee_tier,
                                "volume_24h": pool.volume_24h,
                                "apr": pool.apr
                            },
                            "jupiter_aggregator": {
                                "rate": jupiter_rate,
                                "route_dexes": route_dexes,
                                "price_impact": jupiter_quote.get("priceImpactPct"),
                                "route_plan_length": len(route_plan)
                            },
                            "estimated_profit_per_100": rate_diff_pct * 1.0,  # Rough estimate
                            "timestamp": datetime.now().isoformat()
                        }
                        
                        opportunities.append(opportunity)
        
        return opportunities
    
    async def display_top_pools(self, pools: List[LPPool], limit: int = 10):
        """Display top pools by TVL and volume."""
        if not pools:
            print("   No pools to display")
            return
        
        # Sort by TVL
        pools_by_tvl = sorted([p for p in pools if p.tvl_usd], key=lambda x: x.tvl_usd, reverse=True)
        
        print(f"\n💰 Top {limit} Pools by TVL:")
        print("-" * 60)
        
        for i, pool in enumerate(pools_by_tvl[:limit], 1):
            pair_name = self._normalize_pair_name(pool.token_a_symbol, pool.token_b_symbol)
            print(f"   {i:2d}. {pair_name}")
            print(f"       TVL: ${pool.tvl_usd:,.0f}")
            print(f"       Price: 1 {pool.token_a_symbol} = {pool.price_a_to_b:.6f} {pool.token_b_symbol}")
            print(f"       Fee: {pool.fee_tier*100:.2f}%" if pool.fee_tier else "       Fee: N/A")
            print(f"       Volume 24h: ${pool.volume_24h:,.0f}" if pool.volume_24h else "       Volume 24h: N/A")
            print(f"       APR: {pool.apr:.2f}%" if pool.apr else "       APR: N/A")
            print()
    
    async def run_lp_arbitrage_scan(self):
        """Run complete LP arbitrage scan."""
        print("🚀 Live LP Arbitrage Monitoring")
        print("=" * 70)
        print("📡 Fetching live data from Meteora DLMM and Jupiter...")
        
        # Fetch Meteora pools
        pools = await self.fetch_meteora_pools()
        
        if not pools:
            print("❌ No pools fetched, cannot continue")
            return
        
        print(f"✅ Found {len(pools)} relevant pools")
        
        # Group by pair
        pairs = {}
        for pool in pools:
            pair_name = self._normalize_pair_name(pool.token_a_symbol, pool.token_b_symbol)
            if pair_name not in pairs:
                pairs[pair_name] = []
            pairs[pair_name].append(pool)
        
        print(f"📊 Monitoring {len(pairs)} trading pairs:")
        for pair, pool_list in pairs.items():
            avg_tvl = sum(p.tvl_usd for p in pool_list if p.tvl_usd) / len(pool_list)
            print(f"   {pair}: {len(pool_list)} pools, avg TVL: ${avg_tvl:,.0f}")
        
        # Display top pools
        await self.display_top_pools(pools)
        
        # Compare with Jupiter
        print("🔍 Comparing LP prices with Jupiter aggregator...")
        opportunities = await self.compare_with_jupiter(pools[:20])  # Test top 20 pools
        
        if opportunities:
            print(f"\n🎯 Found {len(opportunities)} Arbitrage Opportunities!")
            print("=" * 70)
            
            # Sort by profit potential
            opportunities.sort(key=lambda x: x["price_difference_pct"], reverse=True)
            
            for i, opp in enumerate(opportunities[:10], 1):  # Show top 10
                print(f"\n{i}. {opp['pair']} - {opp['price_difference_pct']:.3f}% difference")
                print(f"   Test Amount: {opp['test_amount']}")
                print(f"   📈 Better rate on: {opp['better_on']}")
                print(f"   📉 Worse rate on: {opp['worse_on']}")
                
                meteora = opp['meteora_pool']
                jupiter = opp['jupiter_aggregator']
                
                print(f"   🌊 Meteora DLMM:")
                print(f"      Rate: {meteora['rate']:.6f}")
                print(f"      TVL: ${meteora['tvl']:,.0f}" if meteora['tvl'] else "      TVL: N/A")
                print(f"      Fee: {meteora['fee']*100:.2f}%" if meteora['fee'] else "      Fee: N/A")
                
                print(f"   🪐 Jupiter Aggregator:")
                print(f"      Rate: {jupiter['rate']:.6f}")
                print(f"      Route: {' → '.join(jupiter['route_dexes'])}")
                print(f"      Steps: {jupiter['route_plan_length']}")
                print(f"      Price Impact: {jupiter['price_impact']:.3f}%" if jupiter['price_impact'] else "      Price Impact: N/A")
                
                print(f"   💵 Est. profit on $100: ${opp['estimated_profit_per_100']:.2f}")
        else:
            print("\n📊 No significant arbitrage opportunities found")
            print("   (Threshold: 0.1% price difference)")
        
        print(f"\n✅ Scan completed at {datetime.now().strftime('%H:%M:%S')}")


async def main():
    """Main entry point."""
    monitor = WorkingLPMonitor()
    
    if len(sys.argv) > 1 and sys.argv[1] == "loop":
        # Continuous monitoring
        interval = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
        
        print(f"🔄 Starting continuous monitoring (every {interval}s)")
        print("Press Ctrl+C to stop\n")
        
        iteration = 0
        try:
            while True:
                iteration += 1
                print(f"\n🔄 Scan #{iteration} - {datetime.now().strftime('%H:%M:%S')}")
                print("-" * 50)
                
                await monitor.run_lp_arbitrage_scan()
                
                print(f"\n💤 Waiting {interval}s until next scan...")
                await asyncio.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n👋 Monitoring stopped by user")
    else:
        # Single scan
        await monitor.run_lp_arbitrage_scan()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)