"""
Jupiter RFQ API client for fetching swap quotes.
"""
import asyncio
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
import httpx
import structlog

from models import Quote, QuoteSource, Side, TokenPair
from config import config


logger = structlog.get_logger(__name__)


class JupiterRFQClient:
    """Client for Jupiter RFQ API."""
    
    def __init__(self):
        self.base_url = config.jupiter_rfq_url
        self.timeout = config.request_timeout_seconds
        self.max_retries = config.max_retries
        
    async def get_quote(
        self,
        token_pair: TokenPair,
        amount: float,
        side: Side,
        slippage_bps: int = 50
    ) -> Optional[Quote]:
        """
        Get a quote from Jupiter RFQ API.
        
        Args:
            token_pair: The token pair to get a quote for
            amount: The amount to swap (in base units)
            side: Whether this is a buy or sell
            slippage_bps: Slippage tolerance in basis points
            
        Returns:
            Quote object or None if failed
        """
        try:
            # Convert token symbols to mint addresses
            input_mint = self._get_token_mint(token_pair.base_token if side == Side.SELL else token_pair.quote_token)
            output_mint = self._get_token_mint(token_pair.quote_token if side == Side.SELL else token_pair.base_token)
            
            if not input_mint or not output_mint:
                logger.error("Invalid token pair", token_pair=str(token_pair))
                return None
            
            # Convert amount to token units (considering decimals)
            amount_in_units = self._convert_amount_to_units(amount, input_mint)
            
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount_in_units),
                "slippageBps": slippage_bps,
                "swapMode": "ExactIn"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/quote",
                    params=params
                )
                
                if response.status_code != 200:
                    logger.error(
                        "Jupiter RFQ API error", 
                        status_code=response.status_code,
                        response=response.text
                    )
                    return None
                
                data = response.json()
                return self._parse_quote_response(data, token_pair, side)
                
        except Exception as e:
            logger.error("Error getting Jupiter RFQ quote", error=str(e))
            return None
    
    async def get_swap_instructions(
        self,
        quote_response: Dict[str, Any],
        user_public_key: str,
        wrap_unwrap_sol: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Get swap instructions for execution.
        
        Args:
            quote_response: Response from the quote API
            user_public_key: User's public key
            wrap_unwrap_sol: Whether to wrap/unwrap SOL
            
        Returns:
            Swap instructions or None if failed
        """
        try:
            payload = {
                "userPublicKey": user_public_key,
                "wrapAndUnwrapSol": wrap_unwrap_sol,
                "useSharedAccounts": True,
                "feeAccount": None,
                "computeUnitPriceMicroLamports": None,
                "asLegacyTransaction": False,
                "useTokenLedger": False,
                "destinationTokenAccount": None,
                "dynamicComputeUnitLimit": True,
                "prioritizationFeeLamports": 0,
                "quoteResponse": quote_response
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/swap-instructions",
                    json=payload
                )
                
                if response.status_code != 200:
                    logger.error(
                        "Jupiter swap instructions error",
                        status_code=response.status_code,
                        response=response.text
                    )
                    return None
                
                return response.json()
                
        except Exception as e:
            logger.error("Error getting Jupiter swap instructions", error=str(e))
            return None
    
    def _get_token_mint(self, token_symbol: str) -> Optional[str]:
        """Get mint address for a token symbol."""
        return config.tokens.get(token_symbol)
    
    def _convert_amount_to_units(self, amount: float, mint_address: str) -> int:
        """Convert amount to token units considering decimals."""
        # For simplicity, assuming most tokens have 6 decimals except SOL (9)
        decimals = 9 if mint_address == config.tokens["SOL"] else 6
        return int(amount * (10 ** decimals))
    
    def _parse_quote_response(
        self,
        data: Dict[str, Any],
        token_pair: TokenPair,
        side: Side
    ) -> Quote:
        """Parse Jupiter quote response into Quote object."""
        input_amount = float(data.get("inAmount", 0))
        output_amount = float(data.get("outAmount", 0))
        
        # Calculate price (output per input)
        price = output_amount / input_amount if input_amount > 0 else 0
        
        # Extract fee information
        route_plan = data.get("routePlan", [])
        fee_bps = None
        if route_plan:
            # Get fee from the first route step
            swap_info = route_plan[0].get("swapInfo", {})
            fee_bps = swap_info.get("feeAmount", 0)
        
        return Quote(
            source=QuoteSource.JUPITER_RFQ,
            side=side,
            input_token=token_pair.base_token if side == Side.SELL else token_pair.quote_token,
            output_token=token_pair.quote_token if side == Side.SELL else token_pair.base_token,
            input_amount=input_amount,
            output_amount=output_amount,
            price=price,
            timestamp=datetime.now(),
            fee_bps=fee_bps,
            slippage_bps=data.get("slippageBps", 50),
            route_info=data.get("routePlan"),
            ttl_ms=120000  # Jupiter quotes are valid for ~2 minutes
        )
    
    async def get_quotes_for_pair(
        self,
        token_pair: TokenPair,
        amount: float,
        slippage_bps: int = 50
    ) -> List[Quote]:
        """
        Get both buy and sell quotes for a token pair.
        
        Args:
            token_pair: The token pair to get quotes for
            amount: The amount to swap
            slippage_bps: Slippage tolerance in basis points
            
        Returns:
            List of Quote objects
        """
        tasks = [
            self.get_quote(token_pair, amount, Side.BUY, slippage_bps),
            self.get_quote(token_pair, amount, Side.SELL, slippage_bps)
        ]
        
        quotes = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out None results and exceptions
        valid_quotes = [
            quote for quote in quotes 
            if quote is not None and not isinstance(quote, Exception)
        ]
        
        return valid_quotes