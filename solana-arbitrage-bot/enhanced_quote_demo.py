"""
Enhanced quote fetching demo with multiple DEX sources and fallback endpoints.
"""
import asyncio
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional
import httpx
import structlog
from dataclasses import dataclass
from enum import Enum


class QuoteSource(Enum):
    JUPITER_RFQ = "jupiter_rfq"
    JUPITER_V6 = "jupiter_v6"
    RAYDIUM_V3 = "raydium_v3"
    METEORA = "meteora"
    ORCA = "orca"


class Side(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Quote:
    source: QuoteSource
    side: Side
    input_token: str
    output_token: str
    input_amount: float
    output_amount: float
    price: float
    timestamp: datetime
    rate_usd: Optional[float] = None
    raw_response: Dict[str, Any] = None


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


TOKENS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
}


class MultiDEXQuoteFetcher:
    """Enhanced quote fetcher supporting multiple DEXes."""
    
    def __init__(self):
        self.timeout = 8.0
        self.jupiter_urls = [
            "https://quote-api.jup.ag/v6",
            "https://lite-api.jup.ag/swap/v1"
        ]
        self.raydium_urls = [
            "https://api-v3.raydium.io",
            "https://api.raydium.io/v2", 
            "https://transaction-v1.raydium.io"
        ]
    
    def _convert_amount_to_units(self, amount: float, token: str) -> int:
        decimals = 9 if token == "SOL" else 6
        return int(amount * (10 ** decimals))
    
    async def get_jupiter_quote(self, input_token: str, output_token: str, amount: float) -> Optional[Quote]:
        """Get quote from Jupiter with multiple endpoint fallbacks."""
        input_mint = TOKENS.get(input_token)
        output_mint = TOKENS.get(output_token)
        
        if not input_mint or not output_mint:
            return None
        
        amount_in_units = self._convert_amount_to_units(amount, input_token)
        
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount_in_units),
            "slippageBps": 50,
            "swapMode": "ExactIn"
        }
        
        for i, base_url in enumerate(self.jupiter_urls):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(f"{base_url}/quote", params=params)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        input_amount = float(data.get("inAmount", 0))
                        output_amount = float(data.get("outAmount", 0))
                        price = output_amount / input_amount if input_amount > 0 else 0
                        
                        side = Side.SELL if input_token == "SOL" else Side.BUY
                        source = QuoteSource.JUPITER_RFQ if i == 0 else QuoteSource.JUPITER_V6
                        
                        return Quote(
                            source=source,
                            side=side,
                            input_token=input_token,
                            output_token=output_token,
                            input_amount=input_amount,
                            output_amount=output_amount,
                            price=price,
                            timestamp=datetime.now(),
                            raw_response=data
                        )
                    else:
                        logger.debug(f"Jupiter endpoint {i+1} failed", status_code=response.status_code)
                        
            except Exception as e:
                logger.debug(f"Jupiter endpoint {i+1} error", error=str(e))
                continue
        
        return None
    
    async def get_raydium_quote(self, input_token: str, output_token: str, amount: float) -> Optional[Quote]:
        """Get quote from Raydium with multiple endpoint attempts."""
        input_mint = TOKENS.get(input_token)
        output_mint = TOKENS.get(output_token)
        
        if not input_mint or not output_mint:
            return None
        
        amount_in_units = self._convert_amount_to_units(amount, input_token)
        
        # Try different endpoint patterns
        endpoints = [
            "/compute/swap-base-in",
            "/quote", 
            "/v2/quote",
            "/compute/quote"
        ]
        
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount_in_units),
            "slippageBps": 50,
        }
        
        for base_url in self.raydium_urls:
            for endpoint in endpoints:
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        response = await client.get(f"{base_url}{endpoint}", params=params)
                        
                        if response.status_code == 200:
                            data = response.json()
                            
                            # Try different response formats
                            input_amount = float(data.get("inputAmount", data.get("inAmount", 0)))
                            output_amount = float(data.get("outputAmount", data.get("outAmount", 0)))
                            
                            if input_amount > 0 and output_amount > 0:
                                price = output_amount / input_amount
                                side = Side.SELL if input_token == "SOL" else Side.BUY
                                
                                return Quote(
                                    source=QuoteSource.RAYDIUM_V3,
                                    side=side,
                                    input_token=input_token,
                                    output_token=output_token,
                                    input_amount=input_amount,
                                    output_amount=output_amount,
                                    price=price,
                                    timestamp=datetime.now(),
                                    raw_response=data
                                )
                        
                except Exception as e:
                    continue
        
        return None
    
    async def get_meteora_quote(self, input_token: str, output_token: str, amount: float) -> Optional[Quote]:
        """Get quote from Meteora DLMM."""
        try:
            # First get available pairs
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                pairs_response = await client.get("https://dlmm-api.meteora.ag/pair/all")
                
                if pairs_response.status_code != 200:
                    return None
                
                pairs = pairs_response.json()
                
                # Find our token pair
                input_mint = TOKENS.get(input_token)
                output_mint = TOKENS.get(output_token)
                
                pair_address = None
                for pair in pairs:
                    mint_x = pair.get("mint_x")
                    mint_y = pair.get("mint_y")
                    
                    if (mint_x == input_mint and mint_y == output_mint) or \
                       (mint_x == output_mint and mint_y == input_mint):
                        pair_address = pair.get("address")
                        break
                
                if not pair_address:
                    return None
                
                # Get quote
                amount_in_units = self._convert_amount_to_units(amount, input_token)
                
                params = {
                    "inToken": input_mint,
                    "outToken": output_mint,
                    "inAmount": str(amount_in_units),
                    "slippage": 0.005,  # 0.5%
                    "swapMode": "ExactIn"
                }
                
                quote_response = await client.get("https://dlmm-api.meteora.ag/swap/quote", params=params)
                
                if quote_response.status_code == 200:
                    data = quote_response.json()
                    
                    input_amount = float(data.get("inAmount", 0))
                    output_amount = float(data.get("outAmount", 0))
                    
                    if input_amount > 0 and output_amount > 0:
                        price = output_amount / input_amount
                        side = Side.SELL if input_token == "SOL" else Side.BUY
                        
                        return Quote(
                            source=QuoteSource.METEORA,
                            side=side,
                            input_token=input_token,
                            output_token=output_token,
                            input_amount=input_amount,
                            output_amount=output_amount,
                            price=price,
                            timestamp=datetime.now(),
                            raw_response=data
                        )
                
        except Exception as e:
            logger.debug("Meteora error", error=str(e))
            
        return None
    
    async def get_all_quotes(self, input_token: str, output_token: str, amount: float) -> List[Quote]:
        """Get quotes from all available sources in parallel."""
        tasks = [
            self.get_jupiter_quote(input_token, output_token, amount),
            self.get_raydium_quote(input_token, output_token, amount),
            self.get_meteora_quote(input_token, output_token, amount),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        quotes = []
        for result in results:
            if isinstance(result, Quote):
                quotes.append(result)
            elif isinstance(result, Exception):
                logger.debug("Quote fetch error", error=str(result))
        
        return quotes


async def analyze_arbitrage(quotes: List[Quote], pair_name: str):
    """Analyze arbitrage opportunities between quotes."""
    if len(quotes) < 2:
        print("   📉 Need at least 2 quotes for arbitrage analysis")
        return
    
    # Calculate price differences
    prices = [(q.output_amount / q.input_amount, q.source.value) for q in quotes]
    prices.sort(key=lambda x: x[0])
    
    lowest_price, lowest_source = prices[0]
    highest_price, highest_source = prices[-1]
    
    price_diff = highest_price - lowest_price
    price_diff_pct = (price_diff / lowest_price) * 100
    
    print(f"\n   💰 Arbitrage Analysis for {pair_name}:")
    print(f"   Lowest price: {lowest_price:.6f} ({lowest_source})")
    print(f"   Highest price: {highest_price:.6f} ({highest_source})")
    print(f"   Difference: {price_diff_pct:.3f}%")
    
    if price_diff_pct > 0.1:  # 0.1% threshold
        profit_estimate = price_diff_pct / 100 * 1000  # On $1000 trade
        print(f"   🎯 ARBITRAGE OPPORTUNITY!")
        print(f"   Strategy: Buy from {lowest_source}, sell to {highest_source}")
        print(f"   Estimated profit on $1000 trade: ${profit_estimate:.2f}")
    else:
        print(f"   📊 No significant arbitrage (threshold: 0.1%)")


async def main():
    """Run enhanced quote fetching demo."""
    print("🚀 Enhanced Solana DEX Quote Fetching Demo")
    print("=" * 60)
    print("Testing multiple DEXes with fallback endpoints")
    print("No private keys required - live market data only\n")
    
    fetcher = MultiDEXQuoteFetcher()
    
    test_pairs = [
        ("SOL", "USDC", 1.0),
        ("USDC", "SOL", 200.0),
        ("SOL", "USDT", 0.5),
    ]
    
    for input_token, output_token, amount in test_pairs:
        pair_name = f"{input_token}/{output_token}"
        print(f"📊 Testing {amount} {input_token} → {output_token}")
        print("-" * 50)
        
        # Get quotes from all sources
        quotes = await fetcher.get_all_quotes(input_token, output_token, amount)
        
        if not quotes:
            print("❌ No quotes available from any source")
            continue
        
        # Display results
        for quote in quotes:
            # Convert to human-readable amounts
            if input_token == "SOL":
                readable_input = quote.input_amount / 1e9
                readable_output = quote.output_amount / 1e6
            else:
                readable_input = quote.input_amount / 1e6
                readable_output = quote.output_amount / 1e9
            
            rate = readable_output / readable_input
            
            print(f"✅ {quote.source.value.upper()}:")
            print(f"   Input: {readable_input:.6f} {input_token}")
            print(f"   Output: {readable_output:.6f} {output_token}")
            print(f"   Rate: {rate:.6f} {output_token}/{input_token}")
        
        # Analyze arbitrage opportunities
        await analyze_arbitrage(quotes, pair_name)
        print()
    
    print("=" * 60)
    print("✅ Enhanced demo completed!")
    print("\n📊 Summary:")
    print("- Jupiter RFQ: Primary quote source (most reliable)")
    print("- Raydium: Multiple endpoint attempts")
    print("- Meteora: DLMM pools for concentrated liquidity")
    print("\n🎯 Look for price differences > 0.1% for arbitrage opportunities!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Demo stopped by user")
    except Exception as e:
        print(f"\n❌ Demo crashed: {e}")
        sys.exit(1)