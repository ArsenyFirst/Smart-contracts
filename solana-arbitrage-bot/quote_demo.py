"""
Simplified demo for testing quote fetching functionality.
This script demonstrates Jupiter RFQ and AMM quote fetching
without requiring solana-py or transaction capabilities.
"""
import asyncio
import sys
from datetime import datetime
from typing import List, Dict, Any
import httpx
import structlog
from dataclasses import dataclass
from enum import Enum


# Simplified models for quote fetching only
class QuoteSource(Enum):
    """Enum for quote sources."""
    JUPITER_RFQ = "jupiter_rfq"
    RAYDIUM = "raydium"
    METEORA = "meteora"


class Side(Enum):
    """Enum for buy/sell sides."""
    BUY = "buy"
    SELL = "sell"


@dataclass
class Quote:
    """Simplified quote structure."""
    source: QuoteSource
    side: Side
    input_token: str
    output_token: str
    input_amount: float
    output_amount: float
    price: float
    timestamp: datetime
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


# Token configurations
TOKENS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
}

# API URLs
JUPITER_RFQ_URL = "https://quote-api.jup.ag/v6"
RAYDIUM_API_URL = "https://api-v3.raydium.io"
METEORA_API_URL = "https://dlmm-api.meteora.ag"


class JupiterQuoteFetcher:
    """Fetches quotes from Jupiter RFQ API."""
    
    def __init__(self):
        self.base_url = JUPITER_RFQ_URL
        self.timeout = 5.0
    
    def _convert_amount_to_units(self, amount: float, token: str) -> int:
        """Convert amount to token units considering decimals."""
        decimals = 9 if token == "SOL" else 6
        return int(amount * (10 ** decimals))
    
    async def get_quote(self, input_token: str, output_token: str, amount: float) -> Quote:
        """Get a quote from Jupiter."""
        try:
            input_mint = TOKENS.get(input_token)
            output_mint = TOKENS.get(output_token)
            
            if not input_mint or not output_mint:
                raise ValueError(f"Unsupported tokens: {input_token}/{output_token}")
            
            amount_in_units = self._convert_amount_to_units(amount, input_token)
            
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount_in_units),
                "slippageBps": 50,
                "swapMode": "ExactIn"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/quote", params=params)
                
                if response.status_code != 200:
                    logger.error("Jupiter API error", status_code=response.status_code, response=response.text)
                    return None
                
                data = response.json()
                
                input_amount = float(data.get("inAmount", 0))
                output_amount = float(data.get("outAmount", 0))
                price = output_amount / input_amount if input_amount > 0 else 0
                
                # Determine side based on tokens
                side = Side.SELL if input_token == "SOL" else Side.BUY
                
                return Quote(
                    source=QuoteSource.JUPITER_RFQ,
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
            logger.error("Error getting Jupiter quote", error=str(e))
            return None


class RaydiumQuoteFetcher:
    """Fetches quotes from Raydium API."""
    
    def __init__(self):
        self.base_url = RAYDIUM_API_URL
        self.timeout = 5.0
    
    def _convert_amount_to_units(self, amount: float, token: str) -> int:
        """Convert amount to token units considering decimals."""
        decimals = 9 if token == "SOL" else 6
        return int(amount * (10 ** decimals))
    
    async def get_quote(self, input_token: str, output_token: str, amount: float) -> Quote:
        """Get a quote from Raydium."""
        try:
            input_mint = TOKENS.get(input_token)
            output_mint = TOKENS.get(output_token)
            
            if not input_mint or not output_mint:
                raise ValueError(f"Unsupported tokens: {input_token}/{output_token}")
            
            amount_in_units = self._convert_amount_to_units(amount, input_token)
            
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount_in_units),
                "slippageBps": 50,
                "txVersion": "V0"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/compute/swap-base-in", params=params)
                
                if response.status_code != 200:
                    logger.error("Raydium API error", status_code=response.status_code, response=response.text)
                    return None
                
                data = response.json()
                
                input_amount = float(data.get("inputAmount", 0))
                output_amount = float(data.get("outputAmount", 0))
                price = output_amount / input_amount if input_amount > 0 else 0
                
                # Determine side based on tokens
                side = Side.SELL if input_token == "SOL" else Side.BUY
                
                return Quote(
                    source=QuoteSource.RAYDIUM,
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
            logger.error("Error getting Raydium quote", error=str(e))
            return None


async def test_quote_fetching():
    """Test quote fetching from multiple sources."""
    print("🚀 Solana Arbitrage Bot - Quote Fetching Demo")
    print("=" * 60)
    
    # Initialize fetchers
    jupiter = JupiterQuoteFetcher()
    raydium = RaydiumQuoteFetcher()
    
    # Test parameters
    test_pairs = [
        ("SOL", "USDC", 1.0),  # 1 SOL to USDC
        ("USDC", "SOL", 200.0),  # 200 USDC to SOL
    ]
    
    for input_token, output_token, amount in test_pairs:
        print(f"\n📊 Testing {amount} {input_token} → {output_token}")
        print("-" * 40)
        
        # Fetch quotes in parallel
        tasks = [
            jupiter.get_quote(input_token, output_token, amount),
            raydium.get_quote(input_token, output_token, amount),
        ]
        
        quotes = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Display results
        for i, quote in enumerate(quotes):
            source_name = ["Jupiter RFQ", "Raydium"][i]
            
            if isinstance(quote, Exception):
                print(f"❌ {source_name}: Error - {quote}")
            elif quote is None:
                print(f"❌ {source_name}: No quote available")
            else:
                # Convert back to human-readable amounts
                if input_token == "SOL":
                    readable_input = quote.input_amount / 1e9
                    readable_output = quote.output_amount / 1e6
                else:
                    readable_input = quote.input_amount / 1e6
                    readable_output = quote.output_amount / 1e9
                
                print(f"✅ {source_name}:")
                print(f"   Input: {readable_input:.6f} {input_token}")
                print(f"   Output: {readable_output:.6f} {output_token}")
                print(f"   Rate: {readable_output/readable_input:.6f} {output_token}/{input_token}")
        
        # Check for arbitrage opportunity
        valid_quotes = [q for q in quotes if q and not isinstance(q, Exception)]
        if len(valid_quotes) >= 2:
            # Simple arbitrage check
            prices = [q.output_amount / q.input_amount for q in valid_quotes]
            price_diff = max(prices) - min(prices)
            price_diff_pct = (price_diff / min(prices)) * 100
            
            print(f"\n💰 Arbitrage Analysis:")
            print(f"   Price difference: {price_diff_pct:.3f}%")
            if price_diff_pct > 0.1:  # 0.1% threshold
                print(f"   🎯 Potential arbitrage opportunity!")
            else:
                print(f"   📉 No significant arbitrage opportunity")


async def test_individual_apis():
    """Test individual API responses."""
    print("\n🔍 Individual API Testing")
    print("=" * 60)
    
    jupiter = JupiterQuoteFetcher()
    
    # Test Jupiter with SOL/USDC
    print("\n🪐 Testing Jupiter RFQ API...")
    quote = await jupiter.get_quote("SOL", "USDC", 1.0)
    
    if quote:
        print(f"✅ Jupiter Response:")
        print(f"   Source: {quote.source.value}")
        print(f"   {quote.input_amount/1e9:.6f} SOL → {quote.output_amount/1e6:.6f} USDC")
        print(f"   Rate: {(quote.output_amount/1e6)/(quote.input_amount/1e9):.2f} USDC/SOL")
        
        # Show raw response structure
        if quote.raw_response:
            print(f"   Raw response keys: {list(quote.raw_response.keys())}")
    else:
        print("❌ Jupiter: No quote received")
    
    print("\n🌊 Testing Raydium API...")
    raydium = RaydiumQuoteFetcher()
    quote = await raydium.get_quote("SOL", "USDC", 1.0)
    
    if quote:
        print(f"✅ Raydium Response:")
        print(f"   Source: {quote.source.value}")
        print(f"   {quote.input_amount/1e9:.6f} SOL → {quote.output_amount/1e6:.6f} USDC")
        print(f"   Rate: {(quote.output_amount/1e6)/(quote.input_amount/1e9):.2f} USDC/SOL")
        
        # Show raw response structure
        if quote.raw_response:
            print(f"   Raw response keys: {list(quote.raw_response.keys())}")
    else:
        print("❌ Raydium: No quote received")


async def main():
    """Run all demos."""
    print("🎯 Welcome to the Solana Quote Fetching Demo!")
    print("This demo tests live quote fetching from DEX APIs.")
    print("No private keys or transactions required.\n")
    
    try:
        # Test individual APIs first
        await test_individual_apis()
        
        # Test quote comparison
        await test_quote_fetching()
        
        print("\n" + "=" * 60)
        print("✅ Demo completed successfully!")
        print("\n📚 Next Steps:")
        print("1. Review the quote differences between DEXes")
        print("2. Look for arbitrage opportunities (>0.1% price difference)")
        print("3. Set up a Solana wallet to execute trades")
        print("\n⚠️  Remember: This is for educational purposes only!")
        
    except Exception as e:
        logger.error("Demo failed", error=str(e))
        print(f"\n❌ Demo failed: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Demo stopped by user")
    except Exception as e:
        print(f"\n❌ Demo crashed: {e}")
        sys.exit(1)