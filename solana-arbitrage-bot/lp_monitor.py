"""
Comprehensive LP (Liquidity Pool) monitoring system for Solana DEXes.
Monitors Raydium, Orca, and Meteora liquidity pools for arbitrage opportunities.
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
    """Enum for LP sources."""
    RAYDIUM_CPMM = "raydium_cpmm"
    RAYDIUM_CLMM = "raydium_clmm"
    ORCA_WHIRLPOOL = "orca_whirlpool"
    METEORA_DLMM = "meteora_dlmm"
    METEORA_DYNAMIC = "meteora_dynamic"


@dataclass
class LPPool:
    """Liquidity Pool data structure."""
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
    timestamp: datetime = None
    raw_data: Dict[str, Any] = None


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


# Token mint addresses
TOKENS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "WSOL": "So11111111111111111111111111111111111111112",
}


class LPMonitor:
    """Comprehensive LP monitoring system."""
    
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self.raydium_url = "https://api-v3.raydium.io"
        self.meteora_dlmm_url = "https://dlmm-api.meteora.ag"
        self.jupiter_price_url = "https://price.jup.ag/v6"
        
        # Orca Whirlpool program ID
        self.orca_program_id = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
    
    def _convert_decimals(self, amount: str, decimals: int) -> float:
        """Convert token amount from units to human readable."""
        try:
            return float(amount) / (10 ** decimals)
        except (ValueError, TypeError):
            return 0.0
    
    def _get_token_decimals(self, token_symbol: str) -> int:
        """Get decimals for common tokens."""
        if token_symbol.upper() in ["SOL", "WSOL"]:
            return 9
        elif token_symbol.upper() in ["USDC", "USDT"]:
            return 6
        else:
            return 6  # Default assumption
    
    async def fetch_raydium_pools(self) -> List[LPPool]:
        """Fetch pools from Raydium V3 API."""
        pools = []
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Get pool list
                response = await client.get(f"{self.raydium_url}/pools/info/list")
                
                if response.status_code != 200:
                    logger.warning("Raydium API error", status_code=response.status_code)
                    return pools
                
                data = response.json()
                
                # Filter for stablecoin/SOL pairs
                target_pairs = [
                    ("SOL", "USDC"), ("USDC", "SOL"),
                    ("SOL", "USDT"), ("USDT", "SOL"),
                    ("WSOL", "USDC"), ("USDC", "WSOL"),
                    ("WSOL", "USDT"), ("USDT", "WSOL"),
                ]
                
                for pool_info in data.get("data", []):
                    try:
                        mint_a = pool_info.get("mintA", {})
                        mint_b = pool_info.get("mintB", {})
                        
                        symbol_a = mint_a.get("symbol", "")
                        symbol_b = mint_b.get("symbol", "")
                        
                        # Check if this is a target pair
                        pair_match = any(
                            (symbol_a.upper() == pair[0] and symbol_b.upper() == pair[1]) or
                            (symbol_a.upper() == pair[1] and symbol_b.upper() == pair[0])
                            for pair in target_pairs
                        )
                        
                        if not pair_match:
                            continue
                        
                        # Extract pool data
                        pool_address = pool_info.get("id", "")
                        pool_type = pool_info.get("type", "")
                        
                        # Get reserves
                        mint_a_amount = float(pool_info.get("mintAmountA", 0))
                        mint_b_amount = float(pool_info.get("mintAmountB", 0))
                        
                        # Convert to human readable
                        decimals_a = mint_a.get("decimals", 6)
                        decimals_b = mint_b.get("decimals", 6)
                        
                        reserve_a = mint_a_amount / (10 ** decimals_a)
                        reserve_b = mint_b_amount / (10 ** decimals_b)
                        
                        # Calculate prices
                        price_a_to_b = reserve_b / reserve_a if reserve_a > 0 else 0
                        price_b_to_a = reserve_a / reserve_b if reserve_b > 0 else 0
                        
                        # Determine source type
                        if "CLMM" in pool_type.upper():
                            source = LPSource.RAYDIUM_CLMM
                        else:
                            source = LPSource.RAYDIUM_CPMM
                        
                        pool = LPPool(
                            source=source,
                            pool_address=pool_address,
                            token_a=mint_a.get("address", ""),
                            token_b=mint_b.get("address", ""),
                            token_a_symbol=symbol_a,
                            token_b_symbol=symbol_b,
                            token_a_reserve=reserve_a,
                            token_b_reserve=reserve_b,
                            price_a_to_b=price_a_to_b,
                            price_b_to_a=price_b_to_a,
                            tvl_usd=pool_info.get("tvl"),
                            fee_tier=pool_info.get("feeRate"),
                            volume_24h=pool_info.get("day", {}).get("volume"),
                            timestamp=datetime.now(),
                            raw_data=pool_info
                        )
                        
                        pools.append(pool)
                        
                    except Exception as e:
                        logger.debug("Error parsing Raydium pool", error=str(e))
                        continue
                        
        except Exception as e:
            logger.error("Error fetching Raydium pools", error=str(e))
        
        return pools
    
    async def fetch_meteora_pools(self) -> List[LPPool]:
        """Fetch pools from Meteora DLMM API."""
        pools = []
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Get all DLMM pairs
                response = await client.get(f"{self.meteora_dlmm_url}/pair/all")
                
                if response.status_code != 200:
                    logger.warning("Meteora API error", status_code=response.status_code)
                    return pools
                
                data = response.json()
                
                # Filter for stablecoin/SOL pairs
                for pair_info in data:
                    try:
                        mint_x = pair_info.get("mint_x", "")
                        mint_y = pair_info.get("mint_y", "")
                        
                        # Check if this involves our target tokens
                        token_x_symbol = self._get_symbol_from_mint(mint_x)
                        token_y_symbol = self._get_symbol_from_mint(mint_y)
                        
                        if not (token_x_symbol and token_y_symbol):
                            continue
                        
                        # Check for target pairs
                        target_symbols = {"SOL", "USDC", "USDT", "WSOL"}
                        if not (token_x_symbol in target_symbols and token_y_symbol in target_symbols):
                            continue
                        
                        # Get current price and reserves
                        current_price = float(pair_info.get("current_price", 0))
                        reserve_x = float(pair_info.get("reserve_x", 0)) / (10 ** pair_info.get("reserve_x_decimals", 9))
                        reserve_y = float(pair_info.get("reserve_y", 0)) / (10 ** pair_info.get("reserve_y_decimals", 6))
                        
                        pool = LPPool(
                            source=LPSource.METEORA_DLMM,
                            pool_address=pair_info.get("address", ""),
                            token_a=mint_x,
                            token_b=mint_y,
                            token_a_symbol=token_x_symbol,
                            token_b_symbol=token_y_symbol,
                            token_a_reserve=reserve_x,
                            token_b_reserve=reserve_y,
                            price_a_to_b=current_price,
                            price_b_to_a=1/current_price if current_price > 0 else 0,
                            tvl_usd=pair_info.get("liquidity_usd"),
                            fee_tier=pair_info.get("base_fee_percentage"),
                            volume_24h=pair_info.get("trade_volume_24h"),
                            timestamp=datetime.now(),
                            raw_data=pair_info
                        )
                        
                        pools.append(pool)
                        
                    except Exception as e:
                        logger.debug("Error parsing Meteora pool", error=str(e))
                        continue
                        
        except Exception as e:
            logger.error("Error fetching Meteora pools", error=str(e))
        
        return pools
    
    def _get_symbol_from_mint(self, mint_address: str) -> Optional[str]:
        """Get token symbol from mint address."""
        mint_to_symbol = {v: k for k, v in TOKENS.items()}
        return mint_to_symbol.get(mint_address)
    
    async def fetch_orca_pools(self) -> List[LPPool]:
        """Fetch Orca Whirlpool data via direct RPC calls."""
        pools = []
        
        # For now, we'll use a simplified approach since Orca requires more complex on-chain calls
        # In a production system, you'd use the Solana SDK to query on-chain data
        logger.info("Orca pool fetching would require on-chain queries - placeholder for now")
        
        return pools
    
    async def get_jupiter_prices(self) -> Dict[str, float]:
        """Get current market prices from Jupiter."""
        prices = {}
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.jupiter_price_url}/price?ids=SOL,USDC,USDT")
                
                if response.status_code == 200:
                    data = response.json()
                    for token, info in data.get("data", {}).items():
                        prices[token] = float(info.get("price", 0))
                        
        except Exception as e:
            logger.debug("Error fetching Jupiter prices", error=str(e))
        
        return prices
    
    async def analyze_lp_arbitrage(self, pools: List[LPPool]) -> List[Dict[str, Any]]:
        """Analyze arbitrage opportunities between LP pools."""
        opportunities = []
        
        # Group pools by token pair
        pair_pools = {}
        for pool in pools:
            # Normalize pair (always put alphabetically first token first)
            tokens = sorted([pool.token_a_symbol, pool.token_b_symbol])
            pair_key = f"{tokens[0]}/{tokens[1]}"
            
            if pair_key not in pair_pools:
                pair_pools[pair_key] = []
            pair_pools[pair_key].append(pool)
        
        # Analyze each pair
        for pair, pool_list in pair_pools.items():
            if len(pool_list) < 2:
                continue
            
            # Sort by price (token A to token B)
            pool_list.sort(key=lambda p: p.price_a_to_b)
            
            # Compare cheapest vs most expensive
            cheapest = pool_list[0]
            most_expensive = pool_list[-1]
            
            if cheapest.price_a_to_b > 0 and most_expensive.price_a_to_b > 0:
                price_diff_pct = ((most_expensive.price_a_to_b - cheapest.price_a_to_b) / cheapest.price_a_to_b) * 100
                
                if price_diff_pct > 0.1:  # 0.1% threshold
                    opportunity = {
                        "pair": pair,
                        "price_difference_pct": price_diff_pct,
                        "buy_from": {
                            "source": cheapest.source.value,
                            "pool_address": cheapest.pool_address,
                            "price": cheapest.price_a_to_b,
                            "tvl": cheapest.tvl_usd,
                            "reserves": f"{cheapest.token_a_reserve:.2f} {cheapest.token_a_symbol} / {cheapest.token_b_reserve:.2f} {cheapest.token_b_symbol}"
                        },
                        "sell_to": {
                            "source": most_expensive.source.value,
                            "pool_address": most_expensive.pool_address,
                            "price": most_expensive.price_a_to_b,
                            "tvl": most_expensive.tvl_usd,
                            "reserves": f"{most_expensive.token_a_reserve:.2f} {most_expensive.token_a_symbol} / {most_expensive.token_b_reserve:.2f} {most_expensive.token_b_symbol}"
                        },
                        "estimated_profit_per_1000": price_diff_pct * 10,  # Rough estimate
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    opportunities.append(opportunity)
        
        return opportunities
    
    async def run_single_scan(self):
        """Run a single LP monitoring scan."""
        print("🔍 LP Monitoring Scan")
        print("=" * 60)
        
        # Fetch pools from all sources in parallel
        print("📡 Fetching LP data from DEXes...")
        
        tasks = [
            self.fetch_raydium_pools(),
            self.fetch_meteora_pools(),
            # self.fetch_orca_pools(),  # Commented out until implemented
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_pools = []
        source_names = ["Raydium", "Meteora"]  # , "Orca"]
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"❌ {source_names[i]}: Error - {result}")
            else:
                all_pools.extend(result)
                print(f"✅ {source_names[i]}: {len(result)} pools fetched")
        
        print(f"\n📊 Total pools found: {len(all_pools)}")
        
        # Display pool summary
        if all_pools:
            print("\n💱 Pool Summary:")
            print("-" * 40)
            
            source_counts = {}
            for pool in all_pools:
                source = pool.source.value
                source_counts[source] = source_counts.get(source, 0) + 1
            
            for source, count in source_counts.items():
                print(f"   {source.upper()}: {count} pools")
            
            # Show sample pools
            print(f"\n🔍 Sample Pool Data:")
            for i, pool in enumerate(all_pools[:5]):  # Show first 5
                print(f"   {i+1}. {pool.token_a_symbol}/{pool.token_b_symbol} on {pool.source.value}")
                print(f"      Price: 1 {pool.token_a_symbol} = {pool.price_a_to_b:.6f} {pool.token_b_symbol}")
                print(f"      TVL: ${pool.tvl_usd:,.2f}" if pool.tvl_usd else "      TVL: N/A")
                print(f"      Reserves: {pool.token_a_reserve:.2f} {pool.token_a_symbol} / {pool.token_b_reserve:.2f} {pool.token_b_symbol}")
        
        # Analyze arbitrage opportunities
        print(f"\n🎯 Analyzing Arbitrage Opportunities...")
        opportunities = await self.analyze_lp_arbitrage(all_pools)
        
        if opportunities:
            print(f"\n💰 Found {len(opportunities)} Arbitrage Opportunities:")
            print("=" * 60)
            
            for i, opp in enumerate(opportunities, 1):
                print(f"\n{i}. {opp['pair']} - {opp['price_difference_pct']:.3f}% difference")
                print(f"   🟢 BUY from {opp['buy_from']['source'].upper()}")
                print(f"      Price: {opp['buy_from']['price']:.6f}")
                print(f"      TVL: ${opp['buy_from']['tvl']:,.2f}" if opp['buy_from']['tvl'] else "      TVL: N/A")
                print(f"   🔴 SELL to {opp['sell_to']['source'].upper()}")
                print(f"      Price: {opp['sell_to']['price']:.6f}")
                print(f"      TVL: ${opp['sell_to']['tvl']:,.2f}" if opp['sell_to']['tvl'] else "      TVL: N/A")
                print(f"   💵 Est. profit on $1000: ${opp['estimated_profit_per_1000']:.2f}")
        else:
            print(f"\n📊 No significant arbitrage opportunities found (threshold: 0.1%)")
        
        print(f"\n✅ LP scan complete at {datetime.now().strftime('%H:%M:%S')}")
    
    async def run_continuous_monitoring(self, interval: float = 30.0):
        """Run continuous LP monitoring."""
        print("🚀 Starting Continuous LP Monitoring")
        print("=" * 60)
        print(f"⏱️  Scan interval: {interval}s")
        print(f"🎯 Monitoring: Raydium, Meteora (Orca coming soon)")
        print("Press Ctrl+C to stop\n")
        
        iteration = 0
        
        try:
            while True:
                iteration += 1
                print(f"\n📡 Scan #{iteration} - {datetime.now().strftime('%H:%M:%S')}")
                print("-" * 40)
                
                await self.run_single_scan()
                
                print(f"\n💤 Waiting {interval}s until next scan...")
                await asyncio.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n👋 LP monitoring stopped by user")


async def main():
    """Main entry point."""
    monitor = LPMonitor()
    
    if len(sys.argv) > 1 and sys.argv[1] == "continuous":
        # Continuous monitoring mode
        interval = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
        await monitor.run_continuous_monitoring(interval)
    else:
        # Single scan mode
        await monitor.run_single_scan()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)