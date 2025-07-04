"""
Jupiter RFQ Arbitrage System

This module implements a focused arbitrage strategy that:
1. Uses Jupiter RFQ API exclusively for quotes
2. Compares RFQ quotes with direct DEX prices (Orca, Raydium, Meteora)
3. Factors in the 0.1% Jupiter RFQ fee
4. Executes arbitrage via bundle transactions
5. Focuses only on SOL/USDC and SOL/USDT pairs
"""

import asyncio
import time
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import httpx
import structlog
import json

from models import Quote, QuoteSource, Side, TokenPair, ArbitrageOpportunity, ExecutionResult
from config import config

logger = structlog.get_logger(__name__)

# Jupiter RFQ fixed fee
JUPITER_RFQ_FEE_BPS = 10  # 0.1% fee

# Supported token pairs for RFQ arbitrage
SUPPORTED_PAIRS = [
    TokenPair("SOL", "USDC"),
    TokenPair("SOL", "USDT")
]

@dataclass
class RFQQuote:
    """Enhanced quote structure specifically for RFQ operations."""
    token_pair: TokenPair
    side: Side
    input_amount: float
    output_amount: float
    effective_price: float  # Price after RFQ fees
    gross_price: float     # Price before RFQ fees
    rfq_fee_amount: float  # Actual fee amount in tokens
    route_info: Dict[str, Any]
    timestamp: datetime
    expires_at: datetime
    quote_id: str
    
    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at
    
    @property
    def time_to_expiry_seconds(self) -> float:
        return (self.expires_at - datetime.now()).total_seconds()


@dataclass
class DEXQuote:
    """Direct DEX quote structure."""
    source: QuoteSource
    token_pair: TokenPair
    side: Side
    input_amount: float
    output_amount: float
    price: float
    fee_bps: Optional[int]
    timestamp: datetime
    pool_address: Optional[str] = None
    liquidity: Optional[float] = None


@dataclass
class RFQArbitrageOpportunity:
    """RFQ-specific arbitrage opportunity."""
    rfq_quote: RFQQuote
    dex_quote: DEXQuote
    arbitrage_type: str  # "buy_rfq_sell_dex" or "buy_dex_sell_rfq"
    gross_profit_bps: int
    net_profit_bps: int  # After all fees
    profit_amount_usd: float
    roi_percentage: float
    execution_complexity: str  # "simple" or "complex"
    estimated_gas_cost: float
    min_capital_required: float
    timestamp: datetime
    
    @property
    def is_profitable(self) -> bool:
        return (
            self.net_profit_bps > 0 and
            not self.rfq_quote.is_expired and
            self.rfq_quote.time_to_expiry_seconds > 10  # At least 10 seconds to execute
        )


class JupiterRFQArbitrageClient:
    """Enhanced Jupiter RFQ client focused on arbitrage opportunities."""
    
    def __init__(self):
        self.base_url = "https://lite-api.jup.ag"  # Using free tier
        self.timeout = 5.0
        self.session = None
        
    async def __aenter__(self):
        self.session = httpx.AsyncClient(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.aclose()
    
    async def get_rfq_quote(
        self,
        token_pair: TokenPair,
        amount_usd: float,
        side: Side,
        restrict_intermediate_tokens: bool = True
    ) -> Optional[RFQQuote]:
        """
        Get a quote specifically from Jupiter RFQ providers.
        
        Args:
            token_pair: SOL/USDC or SOL/USDT
            amount_usd: Amount in USD terms
            side: BUY (buy SOL) or SELL (sell SOL)
            restrict_intermediate_tokens: Limit to direct routes
        """
        try:
            # Determine input/output based on side
            if side == Side.BUY:
                # Buying SOL with USDC/USDT
                input_token = token_pair.quote_token  # USDC or USDT
                output_token = token_pair.base_token  # SOL
                input_amount = amount_usd
            else:
                # Selling SOL for USDC/USDT
                input_token = token_pair.base_token   # SOL
                output_token = token_pair.quote_token # USDC or USDT
                # Convert USD amount to SOL amount (rough estimate)
                sol_price = await self._get_sol_price()
                input_amount = amount_usd / sol_price if sol_price else amount_usd / 100
            
            # Get token mint addresses
            input_mint = config.tokens.get(input_token)
            output_mint = config.tokens.get(output_token)
            
            if not input_mint or not output_mint:
                logger.error("Invalid tokens", input_token=input_token, output_token=output_token)
                return None
            
            # Convert to token units
            input_decimals = 9 if input_token == "SOL" else 6
            amount_in_units = int(input_amount * (10 ** input_decimals))
            
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount_in_units),
                "slippageBps": 50,
                "onlyDirectRoutes": restrict_intermediate_tokens,
                "excludeDexes": [],  # Don't exclude any DEXes to ensure RFQ inclusion
                "platformFeeBps": 0,  # No additional platform fees
                "maxAccounts": 20,   # Limit complexity
                "autoSlippage": False
            }
            
            response = await self.session.get(f"{self.base_url}/swap/v1/quote", params=params)
            
            if response.status_code != 200:
                logger.error("RFQ quote failed", status=response.status_code, text=response.text)
                return None
            
            data = response.json()
            return self._parse_rfq_quote(data, token_pair, side, amount_usd)
            
        except Exception as e:
            logger.error("Error getting RFQ quote", error=str(e))
            return None
    
    def _parse_rfq_quote(
        self,
        data: Dict[str, Any],
        token_pair: TokenPair,
        side: Side,
        original_amount_usd: float
    ) -> Optional[RFQQuote]:
        """Parse Jupiter quote response focusing on RFQ components."""
        try:
            input_amount = float(data.get("inAmount", 0))
            output_amount = float(data.get("outAmount", 0))
            
            if input_amount <= 0 or output_amount <= 0:
                return None
            
            # Adjust for token decimals
            input_decimals = 9 if side == Side.SELL else 6
            output_decimals = 6 if side == Side.SELL else 9
            
            input_amount_adjusted = input_amount / (10 ** input_decimals)
            output_amount_adjusted = output_amount / (10 ** output_decimals)
            
            # Calculate gross price (before RFQ fees)
            gross_price = output_amount_adjusted / input_amount_adjusted
            
            # Calculate RFQ fee (0.1% of input amount)
            rfq_fee_amount = input_amount_adjusted * (JUPITER_RFQ_FEE_BPS / 10000)
            
            # Calculate effective price after RFQ fees
            effective_input = input_amount_adjusted + rfq_fee_amount
            effective_price = output_amount_adjusted / effective_input
            
            # Generate quote ID for tracking
            quote_id = f"rfq_{int(time.time())}_{hash(str(data))}"
            
            # Quotes expire in 30 seconds (conservative estimate)
            expires_at = datetime.now() + timedelta(seconds=30)
            
            return RFQQuote(
                token_pair=token_pair,
                side=side,
                input_amount=input_amount_adjusted,
                output_amount=output_amount_adjusted,
                effective_price=effective_price,
                gross_price=gross_price,
                rfq_fee_amount=rfq_fee_amount,
                route_info=data,
                timestamp=datetime.now(),
                expires_at=expires_at,
                quote_id=quote_id
            )
            
        except Exception as e:
            logger.error("Error parsing RFQ quote", error=str(e))
            return None
    
    async def _get_sol_price(self) -> Optional[float]:
        """Get current SOL price for amount calculations."""
        try:
            # Simple price fetch from Jupiter
            response = await self.session.get(f"{self.base_url}/price/v2", params={"ids": "SOL"})
            if response.status_code == 200:
                data = response.json()
                return float(data.get("data", {}).get("SOL", {}).get("price", 100))
        except:
            pass
        return 100  # Fallback SOL price


class DirectDEXClient:
    """Client for fetching direct DEX quotes (bypassing Jupiter aggregation)."""
    
    def __init__(self):
        self.timeout = 5.0
        self.session = None
        self.meteora_url = "https://dlmm-api.meteora.ag"
        self._pool_cache = {}
        self._cache_timestamp = None
        self._cache_ttl = 60  # Cache pools for 60 seconds
    
    async def __aenter__(self):
        self.session = httpx.AsyncClient(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.aclose()
    
    def _safe_float(self, value, default=0.0):
        """Safely convert value to float."""
        try:
            if value is None:
                return default
            return float(value)
        except (ValueError, TypeError):
            return default
    
    async def _fetch_meteora_pools(self) -> Dict[str, Any]:
        """Fetch and cache Meteora pools."""
        now = datetime.now()
        
        # Check cache
        if (self._cache_timestamp and 
            (now - self._cache_timestamp).total_seconds() < self._cache_ttl and
            self._pool_cache):
            return self._pool_cache
        
        try:
            response = await self.session.get(f"{self.meteora_url}/pair/all")
            
            if response.status_code != 200:
                logger.error("Meteora API error", status=response.status_code)
                return {}
            
            pools_data = response.json()
            
            # Process and cache pools
            processed_pools = {}
            for pool_data in pools_data:
                mint_x = pool_data.get("mint_x", "")
                mint_y = pool_data.get("mint_y", "")
                
                # Create lookups for both directions
                key1 = f"{mint_x}-{mint_y}"
                key2 = f"{mint_y}-{mint_x}"
                
                processed_pools[key1] = pool_data
                processed_pools[key2] = pool_data
            
            self._pool_cache = processed_pools
            self._cache_timestamp = now
            
            logger.info("Meteora pools cached", count=len(pools_data))
            return processed_pools
            
        except Exception as e:
            logger.error("Error fetching Meteora pools", error=str(e))
            return {}
    
    async def get_meteora_quote(
        self,
        token_pair: TokenPair,
        amount_usd: float,
        side: Side
    ) -> Optional[DEXQuote]:
        """Get direct quote from Meteora DLMM using real API data."""
        try:
            # Get token mints
            base_mint = config.tokens.get(token_pair.base_token)  # SOL
            quote_mint = config.tokens.get(token_pair.quote_token)  # USDC/USDT
            
            if not base_mint or not quote_mint:
                logger.error("Invalid token pair", pair=str(token_pair))
                return None
            
            # Fetch pools
            pools = await self._fetch_meteora_pools()
            if not pools:
                return None
            
            # Determine input/output mints based on side
            if side == Side.BUY:
                # Buying SOL with USDC/USDT
                input_mint = quote_mint
                output_mint = base_mint
                input_amount = amount_usd
            else:
                # Selling SOL for USDC/USDT
                input_mint = base_mint
                output_mint = quote_mint
                # Estimate SOL amount (rough approximation)
                input_amount = amount_usd / 150.0  # Assume ~$150 SOL
            
            # Find best pool for this pair
            pool_key = f"{input_mint}-{output_mint}"
            pool_data = pools.get(pool_key)
            
            if not pool_data:
                logger.debug("No Meteora pool found", pair=str(token_pair), side=side.value)
                return None
            
            # Check if pool is valid
            if pool_data.get("is_blacklisted", False) or pool_data.get("hide", False):
                return None
            
            # Extract pool information
            liquidity_usd = self._safe_float(pool_data.get("liquidity", 0))
            if liquidity_usd < 1000:  # Require minimum liquidity
                return None
            
            current_price = self._safe_float(pool_data.get("current_price", 0))
            if current_price <= 0:
                return None
            
            # Calculate output amount based on pool price
            if side == Side.BUY:
                # Buying SOL with USDC/USDT
                # current_price is typically USDC per SOL
                output_amount = input_amount / current_price
            else:
                # Selling SOL for USDC/USDT
                output_amount = input_amount * current_price
            
            # Account for fees
            base_fee = self._safe_float(pool_data.get("base_fee_percentage", 0.003))  # Default 0.3%
            fee_bps = int(base_fee * 10000)
            
            # Apply fee to output
            output_amount_after_fee = output_amount * (1 - base_fee)
            
            # Calculate effective price
            effective_price = output_amount_after_fee / input_amount if input_amount > 0 else 0
            
            return DEXQuote(
                source=QuoteSource.METEORA,
                token_pair=token_pair,
                side=side,
                input_amount=input_amount,
                output_amount=output_amount_after_fee,
                price=effective_price,
                fee_bps=fee_bps,
                timestamp=datetime.now(),
                pool_address=pool_data.get("address", ""),
                liquidity=liquidity_usd
            )
            
        except Exception as e:
            logger.error("Error getting Meteora quote", error=str(e))
            return None
    
    async def get_raydium_quote(
        self,
        token_pair: TokenPair,
        amount_usd: float,
        side: Side
    ) -> Optional[DEXQuote]:
        """Get direct quote from Raydium."""
        # Similar implementation to Meteora
        # In practice, this would use actual Raydium pool data
        return None  # Placeholder
    
    async def get_orca_quote(
        self,
        token_pair: TokenPair,
        amount_usd: float,
        side: Side
    ) -> Optional[DEXQuote]:
        """Get direct quote from Orca Whirlpools."""
        # Similar implementation to Meteora
        # In practice, this would use actual Orca pool data
        return None  # Placeholder


class RFQArbitrageEngine:
    """Main engine for RFQ arbitrage detection and execution."""
    
    def __init__(self):
        self.rfq_client = JupiterRFQArbitrageClient()
        self.dex_client = DirectDEXClient()
        self.min_profit_bps = 25  # Minimum 0.25% profit after all fees
        self.trade_amounts = [100, 500, 1000, 2500]  # USD amounts to test
        
    async def scan_arbitrage_opportunities(self) -> List[RFQArbitrageOpportunity]:
        """Scan for arbitrage opportunities across all supported pairs and amounts."""
        opportunities = []
        
        async with self.rfq_client, self.dex_client:
            for token_pair in SUPPORTED_PAIRS:
                for amount_usd in self.trade_amounts:
                    pair_opportunities = await self._scan_pair_opportunities(token_pair, amount_usd)
                    opportunities.extend(pair_opportunities)
        
        # Sort by profitability
        opportunities.sort(key=lambda x: x.net_profit_bps, reverse=True)
        return opportunities
    
    async def _scan_pair_opportunities(
        self,
        token_pair: TokenPair,
        amount_usd: float
    ) -> List[RFQArbitrageOpportunity]:
        """Scan arbitrage opportunities for a specific pair and amount."""
        opportunities = []
        
        for side in [Side.BUY, Side.SELL]:
            # Get RFQ quote
            rfq_quote = await self.rfq_client.get_rfq_quote(token_pair, amount_usd, side)
            if not rfq_quote:
                continue
            
            # Get DEX quotes for comparison
            dex_quotes = await self._get_dex_quotes(token_pair, amount_usd, side)
            
            # Find arbitrage opportunities
            for dex_quote in dex_quotes:
                opp = self._analyze_arbitrage_opportunity(rfq_quote, dex_quote)
                if opp and opp.is_profitable and opp.net_profit_bps >= self.min_profit_bps:
                    opportunities.append(opp)
        
        return opportunities
    
    async def _get_dex_quotes(
        self,
        token_pair: TokenPair,
        amount_usd: float,
        side: Side
    ) -> List[DEXQuote]:
        """Get quotes from direct DEX sources."""
        tasks = [
            self.dex_client.get_meteora_quote(token_pair, amount_usd, side),
            # Add more DEX clients as they become available
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        quotes = []
        for result in results:
            if isinstance(result, DEXQuote):
                quotes.append(result)
        
        return quotes
    
    def _analyze_arbitrage_opportunity(
        self,
        rfq_quote: RFQQuote,
        dex_quote: DEXQuote
    ) -> Optional[RFQArbitrageOpportunity]:
        """Analyze potential arbitrage between RFQ and DEX quotes."""
        try:
            # Determine arbitrage direction
            if rfq_quote.side == dex_quote.side:
                # Both quotes are for the same direction, no arbitrage
                return None
            
            # Calculate arbitrage metrics
            if rfq_quote.side == Side.BUY:
                # Buy from RFQ, sell to DEX
                arbitrage_type = "buy_rfq_sell_dex"
                buy_price = rfq_quote.effective_price  # Price after RFQ fees
                sell_price = dex_quote.price
            else:
                # Buy from DEX, sell to RFQ  
                arbitrage_type = "buy_dex_sell_rfq"
                buy_price = dex_quote.price
                sell_price = rfq_quote.effective_price
            
            if buy_price <= 0 or sell_price <= 0:
                return None
            
            # Calculate gross profit (before DEX fees and gas)
            gross_profit_pct = (sell_price - buy_price) / buy_price
            gross_profit_bps = int(gross_profit_pct * 10000)
            
            # Calculate DEX fees
            dex_fee_bps = dex_quote.fee_bps or 30  # Default 0.3%
            
            # Estimate gas costs (in USD)
            estimated_gas_cost = 0.05  # ~$0.05 for bundle transaction
            
            # Calculate net profit after all fees
            net_profit_pct = gross_profit_pct - (dex_fee_bps / 10000) - (estimated_gas_cost / dex_quote.input_amount)
            net_profit_bps = int(net_profit_pct * 10000)
            
            # Calculate profit amount in USD
            trade_amount = min(rfq_quote.input_amount, dex_quote.input_amount)
            profit_amount_usd = trade_amount * net_profit_pct
            
            # Calculate ROI
            min_capital = max(rfq_quote.input_amount, dex_quote.input_amount)
            roi_percentage = (profit_amount_usd / min_capital) * 100 if min_capital > 0 else 0
            
            return RFQArbitrageOpportunity(
                rfq_quote=rfq_quote,
                dex_quote=dex_quote,
                arbitrage_type=arbitrage_type,
                gross_profit_bps=gross_profit_bps,
                net_profit_bps=net_profit_bps,
                profit_amount_usd=profit_amount_usd,
                roi_percentage=roi_percentage,
                execution_complexity="simple",  # Most RFQ arbitrage is straightforward
                estimated_gas_cost=estimated_gas_cost,
                min_capital_required=min_capital,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error("Error analyzing arbitrage opportunity", error=str(e))
            return None
    
    async def execute_arbitrage(self, opportunity: RFQArbitrageOpportunity) -> ExecutionResult:
        """Execute an arbitrage opportunity using bundle transactions."""
        logger.info(
            "Executing RFQ arbitrage",
            type=opportunity.arbitrage_type,
            profit_bps=opportunity.net_profit_bps,
            amount=opportunity.min_capital_required
        )
        
        try:
            # Check if opportunity is still valid
            if not opportunity.is_profitable:
                return ExecutionResult(
                    opportunity=None,  # Convert to regular opportunity if needed
                    success=False,
                    error_message="Opportunity no longer profitable or expired"
                )
            
            # Build bundle transaction
            bundle_tx = await self._build_bundle_transaction(opportunity)
            if not bundle_tx:
                return ExecutionResult(
                    opportunity=None,
                    success=False,
                    error_message="Failed to build bundle transaction"
                )
            
            # Execute bundle (placeholder - would use actual Solana transaction execution)
            signature = await self._execute_bundle(bundle_tx)
            
            if signature:
                logger.info("RFQ arbitrage executed successfully", signature=signature)
                return ExecutionResult(
                    opportunity=None,
                    success=True,
                    tx_signature=signature,
                    actual_profit=opportunity.profit_amount_usd
                )
            else:
                return ExecutionResult(
                    opportunity=None,
                    success=False,
                    error_message="Bundle execution failed"
                )
                
        except Exception as e:
            logger.error("Error executing RFQ arbitrage", error=str(e))
            return ExecutionResult(
                opportunity=None,
                success=False,
                error_message=str(e)
            )
    
    async def _build_bundle_transaction(self, opportunity: RFQArbitrageOpportunity) -> Optional[Dict[str, Any]]:
        """Build atomic bundle transaction for arbitrage execution."""
        # This would integrate with Solana transaction building
        # For now, return a placeholder structure
        return {
            "type": "bundle",
            "instructions": [
                {"type": "rfq_swap", "quote_id": opportunity.rfq_quote.quote_id},
                {"type": "dex_swap", "dex": opportunity.dex_quote.source.value}
            ],
            "compute_units": 400000,
            "priority_fee": 0.001
        }
    
    async def _execute_bundle(self, bundle_tx: Dict[str, Any]) -> Optional[str]:
        """Execute bundle transaction on Solana."""
        # Placeholder for actual transaction execution
        # Would integrate with Jito bundles or similar
        await asyncio.sleep(0.1)  # Simulate execution time
        return f"bundle_tx_{int(time.time())}"
    
    async def run_continuous_monitoring(self, interval_seconds: float = 2.0):
        """Run continuous arbitrage monitoring."""
        logger.info("Starting RFQ arbitrage monitoring", interval=interval_seconds)
        
        while True:
            try:
                start_time = time.time()
                
                opportunities = await self.scan_arbitrage_opportunities()
                
                if opportunities:
                    logger.info(
                        "Found RFQ arbitrage opportunities",
                        count=len(opportunities),
                        best_profit_bps=opportunities[0].net_profit_bps
                    )
                    
                    # Execute the best opportunity
                    best_opp = opportunities[0]
                    if best_opp.net_profit_bps >= self.min_profit_bps:
                        result = await self.execute_arbitrage(best_opp)
                        if result.success:
                            logger.info("Arbitrage executed", profit=result.actual_profit)
                        else:
                            logger.warning("Arbitrage execution failed", error=result.error_message)
                else:
                    logger.debug("No profitable RFQ arbitrage opportunities found")
                
                # Wait for next cycle
                elapsed = time.time() - start_time
                sleep_time = max(0, interval_seconds - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
            except KeyboardInterrupt:
                logger.info("RFQ arbitrage monitoring stopped by user")
                break
            except Exception as e:
                logger.error("Error in RFQ arbitrage monitoring", error=str(e))
                await asyncio.sleep(interval_seconds)


# Example usage
async def main():
    """Example usage of the RFQ arbitrage system."""
    engine = RFQArbitrageEngine()
    
    # Scan for opportunities once
    opportunities = await engine.scan_arbitrage_opportunities()
    
    if opportunities:
        print(f"Found {len(opportunities)} arbitrage opportunities:")
        for i, opp in enumerate(opportunities[:3], 1):
            print(f"\n{i}. {opp.arbitrage_type}")
            print(f"   Pair: {opp.rfq_quote.token_pair}")
            print(f"   Net Profit: {opp.net_profit_bps} bps (${opp.profit_amount_usd:.2f})")
            print(f"   ROI: {opp.roi_percentage:.2f}%")
            print(f"   RFQ Quote expires in: {opp.rfq_quote.time_to_expiry_seconds:.1f}s")
    else:
        print("No profitable arbitrage opportunities found")
    
    # Uncomment to run continuous monitoring
    # await engine.run_continuous_monitoring()


if __name__ == "__main__":
    asyncio.run(main())