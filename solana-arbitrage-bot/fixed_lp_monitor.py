"""
Fixed LP Arbitrage Monitor with proper data handling for Meteora DLMM.
"""
import asyncio
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional
import httpx
import structlog
from dataclasses import dataclass
from enum import Enum


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
    timestamp: datetime = None


# Configure minimal logging
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


# Token mappings
TOKENS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
}

MINT_TO_SYMBOL = {v: k for k, v in TOKENS.items()}


def safe_float(value, default=0.0):
    """Safely convert value to float."""
    try:
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


class FixedLPMonitor:
    """Fixed LP monitor with proper data handling."""
    
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self.meteora_url = "https://dlmm-api.meteora.ag"
        self.jupiter_url = "https://quote-api.jup.ag/v6"
    
    def _get_token_symbol(self, mint_address: str) -> Optional[str]:
        """Get token symbol from mint address."""
        return MINT_TO_SYMBOL.get(mint_address)
    
    def _normalize_pair_name(self, symbol_a: str, symbol_b: str) -> str:
        """Create normalized pair name."""
        tokens = sorted([symbol_a, symbol_b])
        return f"{tokens[0]}/{tokens[1]}"
    
    async def fetch_meteora_pools(self) -> List[LPPool]:
        """Fetch and filter Meteora DLMM pools."""
        pools = []
        
        try:
            print("📡 Fetching Meteora pools...")
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.meteora_url}/pair/all")
                
                if response.status_code != 200:
                    print(f"❌ Meteora API error: {response.status_code}")
                    return pools
                
                data = response.json()
                print(f"✅ Fetched {len(data)} total pools")
                
                # Filter for our target tokens
                target_tokens = set(TOKENS.keys())
                processed = 0
                
                for pool_data in data:
                    try:
                        mint_x = pool_data.get("mint_x", "")
                        mint_y = pool_data.get("mint_y", "")
                        
                        symbol_x = self._get_token_symbol(mint_x)
                        symbol_y = self._get_token_symbol(mint_y)
                        
                        # Skip if we don't recognize both tokens
                        if not (symbol_x and symbol_y):
                            continue
                        
                        # Only process target pairs
                        if not (symbol_x in target_tokens and symbol_y in target_tokens):
                            continue
                        
                        # Check if pool is hidden or blacklisted
                        if pool_data.get("is_blacklisted", False) or pool_data.get("hide", False):
                            continue
                        
                        # Extract and validate pool data
                        liquidity_raw = pool_data.get("liquidity", 0)
                        liquidity_usd = safe_float(liquidity_raw)
                        
                        # Skip pools with very low liquidity
                        if liquidity_usd < 100:  # Lowered threshold to $100
                            continue
                        
                        reserve_x = safe_float(pool_data.get("reserve_x", 0))
                        reserve_y = safe_float(pool_data.get("reserve_y", 0))
                        current_price = safe_float(pool_data.get("current_price", 0))
                        
                        # Skip if no price data
                        if current_price <= 0:
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
                            fee_tier=safe_float(pool_data.get("base_fee_percentage", 0)),
                            volume_24h=safe_float(pool_data.get("trade_volume_24h", 0)),
                            apr=safe_float(pool_data.get("apr", 0)),
                            timestamp=datetime.now()
                        )
                        
                        pools.append(pool)
                        processed += 1
                        
                    except Exception as e:
                        # Silently skip problematic pools
                        continue
                
                print(f"✅ Processed {processed} target pools")
                        
        except Exception as e:
            print(f"❌ Error fetching Meteora pools: {e}")
        
        print(f"🎯 Found {len(pools)} valid pools")
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
                        
        except Exception as e:
            pass
        
        return None
    
    async def display_pool_summary(self, pools: List[LPPool]):
        """Display summary of found pools."""
        if not pools:
            print("   No pools to display")
            return
        
        # Group by pair
        pairs = {}
        for pool in pools:
            pair_name = self._normalize_pair_name(pool.token_a_symbol, pool.token_b_symbol)
            if pair_name not in pairs:
                pairs[pair_name] = []
            pairs[pair_name].append(pool)
        
        print(f"\n💱 Pool Summary by Trading Pair:")
        print("-" * 50)
        
        for pair, pool_list in pairs.items():
            total_tvl = sum(p.tvl_usd for p in pool_list if p.tvl_usd)
            avg_tvl = total_tvl / len(pool_list) if pool_list else 0
            max_tvl = max((p.tvl_usd for p in pool_list if p.tvl_usd), default=0)
            
            print(f"   {pair}: {len(pool_list)} pools")
            print(f"     Total TVL: ${total_tvl:,.0f}")
            print(f"     Avg TVL: ${avg_tvl:,.0f}")
            print(f"     Max TVL: ${max_tvl:,.0f}")
        
        # Show top pools by TVL
        pools_by_tvl = sorted([p for p in pools if p.tvl_usd and p.tvl_usd > 0], 
                              key=lambda x: x.tvl_usd, reverse=True)
        
        print(f"\n🏆 Top 10 Pools by TVL:")
        print("-" * 50)
        
        for i, pool in enumerate(pools_by_tvl[:10], 1):
            pair_name = self._normalize_pair_name(pool.token_a_symbol, pool.token_b_symbol)
            print(f"   {i:2d}. {pair_name}")
            print(f"       TVL: ${pool.tvl_usd:,.0f}")
            print(f"       Price: 1 {pool.token_a_symbol} = {pool.price_a_to_b:.6f} {pool.token_b_symbol}")
            print(f"       Fee: {pool.fee_tier*100:.3f}%" if pool.fee_tier else "       Fee: N/A")
            print(f"       Volume 24h: ${pool.volume_24h:,.0f}" if pool.volume_24h else "       Volume 24h: N/A")
    
    async def compare_with_jupiter(self, pools: List[LPPool]) -> List[Dict[str, Any]]:
        """Compare top pools with Jupiter quotes."""
        opportunities = []
        
        print(f"\n🔍 Comparing prices with Jupiter aggregator...")
        
        # Test amounts
        test_amounts = {
            "SOL": 1000000000,  # 1 SOL in lamports
            "USDC": 100000000,   # 100 USDC
            "USDT": 100000000,   # 100 USDT
        }
        
        # Test top 10 pools by TVL
        top_pools = sorted([p for p in pools if p.tvl_usd and p.tvl_usd > 1000], 
                          key=lambda x: x.tvl_usd, reverse=True)[:10]
        
        for i, pool in enumerate(top_pools, 1):
            print(f"   Testing pool {i}/10: {pool.token_a_symbol}/{pool.token_b_symbol}...")
            
            # Test both directions
            for input_token, output_token in [(pool.token_a_symbol, pool.token_b_symbol), 
                                              (pool.token_b_symbol, pool.token_a_symbol)]:
                
                if input_token not in test_amounts:
                    continue
                
                input_mint = TOKENS[input_token]
                output_mint = TOKENS[output_token]
                test_amount = test_amounts[input_token]
                
                # Get Jupiter quote
                jupiter_quote = await self.get_jupiter_quote(input_mint, output_mint, test_amount)
                
                if not jupiter_quote:
                    continue
                
                # Calculate rates
                jupiter_input = safe_float(jupiter_quote.get("inAmount", 0))
                jupiter_output = safe_float(jupiter_quote.get("outAmount", 0))
                
                if jupiter_input == 0:
                    continue
                
                # Convert to human-readable amounts
                if input_token == "SOL":
                    jupiter_input_readable = jupiter_input / 1e9
                    jupiter_output_readable = jupiter_output / 1e6
                else:
                    jupiter_input_readable = jupiter_input / 1e6
                    jupiter_output_readable = jupiter_output / (1e9 if output_token == "SOL" else 1e6)
                
                jupiter_rate = jupiter_output_readable / jupiter_input_readable if jupiter_input_readable > 0 else 0
                
                # Get LP rate from pool
                if input_token == pool.token_a_symbol:
                    lp_rate = pool.price_a_to_b
                else:
                    lp_rate = pool.price_b_to_a
                
                # Compare rates
                if jupiter_rate > 0 and lp_rate > 0:
                    rate_diff = abs(jupiter_rate - lp_rate)
                    rate_diff_pct = (rate_diff / min(jupiter_rate, lp_rate)) * 100
                    
                    if rate_diff_pct > 0.05:  # Lower threshold: 0.05%
                        
                        better_on = "Jupiter" if jupiter_rate > lp_rate else "Meteora"
                        
                        # Get route info
                        route_plan = jupiter_quote.get("routePlan", [])
                        route_dexes = []
                        for step in route_plan[:3]:
                            dex_label = step.get("swapInfo", {}).get("label", "Unknown")
                            route_dexes.append(dex_label)
                        
                        opportunity = {
                            "pair": f"{input_token}/{output_token}",
                            "test_amount": f"{jupiter_input_readable:.2f} {input_token}",
                            "price_difference_pct": rate_diff_pct,
                            "better_on": better_on,
                            "meteora_rate": lp_rate,
                            "jupiter_rate": jupiter_rate,
                            "meteora_pool": {
                                "address": pool.pool_address,
                                "tvl": pool.tvl_usd,
                                "fee": pool.fee_tier,
                                "volume_24h": pool.volume_24h
                            },
                            "jupiter_route": route_dexes,
                            "price_impact": safe_float(jupiter_quote.get("priceImpactPct", 0)),
                            "timestamp": datetime.now().isoformat()
                        }
                        
                        opportunities.append(opportunity)
        
        return opportunities
    
    async def run_lp_scan(self):
        """Run the LP arbitrage scan."""
        print("🚀 Meteora LP vs Jupiter Arbitrage Scanner")
        print("=" * 60)
        
        # Fetch pools
        pools = await self.fetch_meteora_pools()
        
        if not pools:
            print("❌ No pools found, cannot continue")
            return
        
        # Display summary
        await self.display_pool_summary(pools)
        
        # Compare with Jupiter
        opportunities = await self.compare_with_jupiter(pools)
        
        if opportunities:
            print(f"\n🎯 Found {len(opportunities)} Price Differences!")
            print("=" * 60)
            
            # Sort by difference percentage
            opportunities.sort(key=lambda x: x["price_difference_pct"], reverse=True)
            
            for i, opp in enumerate(opportunities[:10], 1):  # Show top 10
                print(f"\n{i}. {opp['pair']} - {opp['price_difference_pct']:.3f}% difference")
                print(f"   Test Amount: {opp['test_amount']}")
                print(f"   📈 Better rate on: {opp['better_on']}")
                
                print(f"   🌊 Meteora: {opp['meteora_rate']:.6f}")
                print(f"      TVL: ${opp['meteora_pool']['tvl']:,.0f}")
                print(f"      Fee: {opp['meteora_pool']['fee']*100:.3f}%")
                
                print(f"   🪐 Jupiter: {opp['jupiter_rate']:.6f}")
                print(f"      Route: {' → '.join(opp['jupiter_route'])}")
                print(f"      Price Impact: {opp['price_impact']:.3f}%")
        else:
            print(f"\n📊 No significant price differences found")
            print("   (Threshold: 0.05%)")
        
        print(f"\n✅ Scan completed at {datetime.now().strftime('%H:%M:%S')}")


async def main():
    """Main entry point."""
    monitor = FixedLPMonitor()
    await monitor.run_lp_scan()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)