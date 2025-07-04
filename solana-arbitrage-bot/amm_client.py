"""
AMM clients for Orca, Raydium, and Meteora DEXes.
"""
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
import httpx
import structlog

from models import Quote, QuoteSource, Side, TokenPair
from config import config


logger = structlog.get_logger(__name__)


class BaseAMMClient:
    """Base class for AMM clients."""
    
    def __init__(self, source: QuoteSource):
        self.source = source
        self.timeout = config.request_timeout_seconds
        self.max_retries = config.max_retries
    
    def _get_token_mint(self, token_symbol: str) -> Optional[str]:
        """Get mint address for a token symbol."""
        return config.tokens.get(token_symbol)
    
    def _convert_amount_to_units(self, amount: float, mint_address: str) -> int:
        """Convert amount to token units considering decimals."""
        # For simplicity, assuming most tokens have 6 decimals except SOL (9)
        decimals = 9 if mint_address == config.tokens["SOL"] else 6
        return int(amount * (10 ** decimals))


class RaydiumClient(BaseAMMClient):
    """Client for Raydium AMM."""
    
    def __init__(self):
        super().__init__(QuoteSource.RAYDIUM)
        self.base_url = config.raydium_api_url
    
    async def get_quote(
        self,
        token_pair: TokenPair,
        amount: float,
        side: Side,
        slippage_bps: int = 50
    ) -> Optional[Quote]:
        """
        Get a quote from Raydium API.
        
        Args:
            token_pair: The token pair to get a quote for
            amount: The amount to swap
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
                logger.error("Invalid token pair for Raydium", token_pair=str(token_pair))
                return None
            
            # Convert amount to token units
            amount_in_units = self._convert_amount_to_units(amount, input_mint)
            
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount_in_units),
                "slippageBps": slippage_bps,
                "txVersion": "V0"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/compute/swap-base-in",
                    params=params
                )
                
                if response.status_code != 200:
                    logger.error(
                        "Raydium API error",
                        status_code=response.status_code,
                        response=response.text
                    )
                    return None
                
                data = response.json()
                return self._parse_quote_response(data, token_pair, side)
                
        except Exception as e:
            logger.error("Error getting Raydium quote", error=str(e))
            return None
    
    def _parse_quote_response(
        self,
        data: Dict[str, Any],
        token_pair: TokenPair,
        side: Side
    ) -> Quote:
        """Parse Raydium quote response into Quote object."""
        input_amount = float(data.get("inputAmount", 0))
        output_amount = float(data.get("outputAmount", 0))
        
        # Calculate price (output per input)
        price = output_amount / input_amount if input_amount > 0 else 0
        
        # Extract fee information
        price_impact = data.get("priceImpact", {})
        fee_info = data.get("fee", [])
        
        fee_bps = None
        if fee_info:
            fee_bps = int(fee_info[0].get("percent", 0) * 10000)  # Convert to basis points
        
        return Quote(
            source=self.source,
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
            ttl_ms=30000  # Raydium quotes are valid for ~30 seconds
        )
    
    async def get_quotes_for_pair(
        self,
        token_pair: TokenPair,
        amount: float,
        slippage_bps: int = 50
    ) -> List[Quote]:
        """Get both buy and sell quotes for a token pair."""
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


class MeteoraClient(BaseAMMClient):
    """Client for Meteora DLMM."""
    
    def __init__(self):
        super().__init__(QuoteSource.METEORA)
        self.base_url = config.meteora_api_url
    
    async def get_quote(
        self,
        token_pair: TokenPair,
        amount: float,
        side: Side,
        slippage_bps: int = 50
    ) -> Optional[Quote]:
        """
        Get a quote from Meteora DLMM API.
        
        Args:
            token_pair: The token pair to get a quote for
            amount: The amount to swap
            side: Whether this is a buy or sell
            slippage_bps: Slippage tolerance in basis points
            
        Returns:
            Quote object or None if failed
        """
        try:
            # First, get available pairs
            pairs = await self._get_pairs()
            if not pairs:
                logger.error("Could not fetch Meteora pairs")
                return None
            
            # Find the pair for our token pair
            pair_address = self._find_pair_address(pairs, token_pair)
            if not pair_address:
                logger.error("Meteora pair not found", token_pair=str(token_pair))
                return None
            
            # Convert token symbols to mint addresses
            input_mint = self._get_token_mint(token_pair.base_token if side == Side.SELL else token_pair.quote_token)
            output_mint = self._get_token_mint(token_pair.quote_token if side == Side.SELL else token_pair.base_token)
            
            if not input_mint or not output_mint:
                logger.error("Invalid token pair for Meteora", token_pair=str(token_pair))
                return None
            
            # Convert amount to token units
            amount_in_units = self._convert_amount_to_units(amount, input_mint)
            
            params = {
                "inToken": input_mint,
                "outToken": output_mint,
                "inAmount": str(amount_in_units),
                "slippage": slippage_bps / 10000.0,  # Convert to percentage
                "swapMode": "ExactIn"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/swap/quote",
                    params=params
                )
                
                if response.status_code != 200:
                    logger.error(
                        "Meteora API error",
                        status_code=response.status_code,
                        response=response.text
                    )
                    return None
                
                data = response.json()
                return self._parse_quote_response(data, token_pair, side)
                
        except Exception as e:
            logger.error("Error getting Meteora quote", error=str(e))
            return None
    
    async def _get_pairs(self) -> Optional[List[Dict[str, Any]]]:
        """Get all available pairs from Meteora."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/pair/all")
                
                if response.status_code != 200:
                    return None
                
                return response.json()
                
        except Exception as e:
            logger.error("Error fetching Meteora pairs", error=str(e))
            return None
    
    def _find_pair_address(
        self,
        pairs: List[Dict[str, Any]],
        token_pair: TokenPair
    ) -> Optional[str]:
        """Find the pair address for a given token pair."""
        base_mint = self._get_token_mint(token_pair.base_token)
        quote_mint = self._get_token_mint(token_pair.quote_token)
        
        for pair in pairs:
            mint_x = pair.get("mint_x")
            mint_y = pair.get("mint_y")
            
            if (mint_x == base_mint and mint_y == quote_mint) or \
               (mint_x == quote_mint and mint_y == base_mint):
                return pair.get("address")
        
        return None
    
    def _parse_quote_response(
        self,
        data: Dict[str, Any],
        token_pair: TokenPair,
        side: Side
    ) -> Quote:
        """Parse Meteora quote response into Quote object."""
        input_amount = float(data.get("inAmount", 0))
        output_amount = float(data.get("outAmount", 0))
        
        # Calculate price (output per input)
        price = output_amount / input_amount if input_amount > 0 else 0
        
        # Extract fee information
        fee_info = data.get("feeAmount", 0)
        fee_bps = int(fee_info * 10000) if fee_info else None
        
        return Quote(
            source=self.source,
            side=side,
            input_token=token_pair.base_token if side == Side.SELL else token_pair.quote_token,
            output_token=token_pair.quote_token if side == Side.SELL else token_pair.base_token,
            input_amount=input_amount,
            output_amount=output_amount,
            price=price,
            timestamp=datetime.now(),
            fee_bps=fee_bps,
            slippage_bps=int(data.get("slippage", 0.005) * 10000),
            route_info=data.get("route"),
            ttl_ms=60000  # Meteora quotes are valid for ~60 seconds
        )
    
    async def get_quotes_for_pair(
        self,
        token_pair: TokenPair,
        amount: float,
        slippage_bps: int = 50
    ) -> List[Quote]:
        """Get both buy and sell quotes for a token pair."""
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


class OrcaClient(BaseAMMClient):
    """Client for Orca Whirlpools."""
    
    def __init__(self):
        super().__init__(QuoteSource.ORCA)
        self.base_url = config.orca_api_url
    
    async def get_quote(
        self,
        token_pair: TokenPair,
        amount: float,
        side: Side,
        slippage_bps: int = 50
    ) -> Optional[Quote]:
        """
        Get a quote from Orca (simplified implementation).
        
        Note: Orca doesn't have a direct quote API like others,
        so this is a simplified implementation that would need
        on-chain data fetching in a real implementation.
        
        Args:
            token_pair: The token pair to get a quote for
            amount: The amount to swap
            side: Whether this is a buy or sell
            slippage_bps: Slippage tolerance in basis points
            
        Returns:
            Quote object or None if failed
        """
        try:
            # This is a simplified implementation
            # In a real implementation, you would need to:
            # 1. Find the Orca pool for this token pair
            # 2. Fetch pool state from on-chain data
            # 3. Calculate the swap quote using Orca SDK
            
            logger.warning(
                "Orca quote implementation is simplified - "
                "real implementation requires on-chain data fetching"
            )
            
            # For now, return None to indicate quote not available
            return None
                
        except Exception as e:
            logger.error("Error getting Orca quote", error=str(e))
            return None
    
    async def get_quotes_for_pair(
        self,
        token_pair: TokenPair,
        amount: float,
        slippage_bps: int = 50
    ) -> List[Quote]:
        """Get both buy and sell quotes for a token pair."""
        # Return empty list for now since get_quote returns None
        return []


class AMMClientManager:
    """Manager for all AMM clients."""
    
    def __init__(self):
        self.raydium = RaydiumClient()
        self.meteora = MeteoraClient()
        self.orca = OrcaClient()
        self.clients = [self.raydium, self.meteora]  # Excluding Orca for now
    
    async def get_all_quotes(
        self,
        token_pair: TokenPair,
        amount: float,
        slippage_bps: int = 50
    ) -> List[Quote]:
        """Get quotes from all AMM clients."""
        all_tasks = []
        
        for client in self.clients:
            all_tasks.extend([
                client.get_quote(token_pair, amount, Side.BUY, slippage_bps),
                client.get_quote(token_pair, amount, Side.SELL, slippage_bps)
            ])
        
        quotes = await asyncio.gather(*all_tasks, return_exceptions=True)
        
        # Filter out None results and exceptions
        valid_quotes = [
            quote for quote in quotes 
            if quote is not None and not isinstance(quote, Exception)
        ]
        
        return valid_quotes
    
    async def get_best_quotes(
        self,
        token_pair: TokenPair,
        amount: float,
        slippage_bps: int = 50
    ) -> Dict[Side, Optional[Quote]]:
        """Get the best buy and sell quotes from all AMMs."""
        all_quotes = await self.get_all_quotes(token_pair, amount, slippage_bps)
        
        buy_quotes = [q for q in all_quotes if q.side == Side.BUY]
        sell_quotes = [q for q in all_quotes if q.side == Side.SELL]
        
        best_buy = max(buy_quotes, key=lambda q: q.output_amount) if buy_quotes else None
        best_sell = max(sell_quotes, key=lambda q: q.output_amount) if sell_quotes else None
        
        return {
            Side.BUY: best_buy,
            Side.SELL: best_sell
        }