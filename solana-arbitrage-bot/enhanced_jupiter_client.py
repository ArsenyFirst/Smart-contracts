"""
Enhanced Jupiter RFQ API Client

This module provides an improved Jupiter RFQ client with:
- Proper rate limiting and error handling
- Jupiter Pro API support
- Comprehensive logging and metrics
- Webhook-style event system
- Connection pooling and caching
"""

import asyncio
import time
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import httpx
import structlog
from cachetools import TTLCache
import json
from enum import Enum

from models import TokenPair, Side
from config import config

logger = structlog.get_logger(__name__)


class JupiterAPIError(Exception):
    """Base exception for Jupiter API errors."""
    pass


class RateLimitError(JupiterAPIError):
    """Raised when rate limit is exceeded."""
    pass


class QuoteExpiredError(JupiterAPIError):
    """Raised when quote has expired."""
    pass


class APITier(Enum):
    """Jupiter API tier levels."""
    LITE = "lite"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass
class JupiterConfig:
    """Configuration for Jupiter API client."""
    api_key: Optional[str] = None
    tier: APITier = APITier.LITE
    timeout: float = 5.0
    max_retries: int = 3
    rate_limit_per_second: int = 10
    base_url: Optional[str] = None
    enable_caching: bool = True
    cache_ttl_seconds: int = 30
    user_agent: str = "Jupiter-RFQ-Arbitrage/2.0"
    
    def __post_init__(self):
        if self.base_url is None:
            if self.tier == APITier.PRO and self.api_key:
                self.base_url = "https://api.jup.ag"
            else:
                self.base_url = "https://lite-api.jup.ag"


@dataclass
class QuoteParams:
    """Parameters for quote requests."""
    input_mint: str
    output_mint: str
    amount: int
    slippage_bps: int = 50
    only_direct_routes: bool = False
    exclude_dexes: List[str] = field(default_factory=list)
    max_accounts: Optional[int] = None
    platform_fee_bps: Optional[int] = None
    as_legacy_transaction: bool = False
    dynamic_compute_unit_limit: bool = True
    restrict_intermediate_tokens: bool = True


@dataclass
class EnhancedRFQQuote:
    """Enhanced RFQ quote with additional metadata."""
    input_mint: str
    output_mint: str
    input_amount: int
    output_amount: int
    other_amount_threshold: int
    swap_mode: str
    slippage_bps: int
    platform_fee: Optional[Dict[str, Any]]
    price_impact_pct: str
    route_plan: List[Dict[str, Any]]
    context_slot: int
    time_taken: float
    timestamp: datetime
    expires_at: datetime
    quote_id: str
    effective_price: float
    rfq_fee_amount: float
    
    @property
    def is_expired(self) -> bool:
        """Check if quote has expired."""
        return datetime.now() > self.expires_at
    
    @property
    def time_to_expiry_seconds(self) -> float:
        """Get time until expiry in seconds."""
        return max(0, (self.expires_at - datetime.now()).total_seconds())


class AsyncRateLimiter:
    """Async rate limiter for API calls."""
    
    def __init__(self, max_calls: int, period_seconds: float):
        self.max_calls = max_calls
        self.period = period_seconds
        self.calls = []
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire rate limit permission."""
        async with self._lock:
            now = time.time()
            # Remove old calls outside the period
            self.calls = [call_time for call_time in self.calls if now - call_time < self.period]
            
            if len(self.calls) >= self.max_calls:
                # Calculate wait time
                oldest_call = min(self.calls)
                wait_time = self.period - (now - oldest_call)
                if wait_time > 0:
                    logger.warning("Rate limit reached, waiting", wait_seconds=wait_time)
                    await asyncio.sleep(wait_time)
                    return await self.acquire()  # Retry after waiting
            
            self.calls.append(now)


class JupiterEventSystem:
    """Event system for Jupiter RFQ operations."""
    
    def __init__(self):
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.webhook_urls: List[str] = []
        self.metrics = {
            "quotes_requested": 0,
            "quotes_successful": 0,
            "quotes_failed": 0,
            "api_errors": 0,
            "rate_limits_hit": 0
        }
    
    def on(self, event_type: str, handler: Callable):
        """Register event handler."""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
    
    async def emit(self, event_type: str, data: Dict[str, Any]):
        """Emit event to all registered handlers."""
        handlers = self.event_handlers.get(event_type, [])
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error("Event handler error", event=event_type, error=str(e))
        
        # Send to webhooks
        if self.webhook_urls:
            await self._send_webhook_notification(event_type, data)
    
    async def _send_webhook_notification(self, event_type: str, data: Dict[str, Any]):
        """Send notification to webhook URLs."""
        payload = {
            "event_type": event_type,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        
        async with httpx.AsyncClient() as client:
            for webhook_url in self.webhook_urls:
                try:
                    await client.post(
                        webhook_url,
                        json=payload,
                        timeout=5.0
                    )
                except Exception as e:
                    logger.error("Webhook notification failed", url=webhook_url, error=str(e))
    
    def add_webhook_url(self, url: str):
        """Add webhook URL for notifications."""
        self.webhook_urls.append(url)
    
    def update_metric(self, metric_name: str, increment: int = 1):
        """Update metrics counter."""
        if metric_name in self.metrics:
            self.metrics[metric_name] += increment


class EnhancedJupiterClient:
    """Enhanced Jupiter RFQ client with improved features."""
    
    def __init__(self, config: JupiterConfig):
        self.config = config
        self.session: Optional[httpx.AsyncClient] = None
        self.rate_limiter = AsyncRateLimiter(config.rate_limit_per_second, 1.0)
        self.quote_cache = TTLCache(maxsize=1000, ttl=config.cache_ttl_seconds) if config.enable_caching else None
        self.event_system = JupiterEventSystem()
        self._setup_default_event_handlers()
    
    def _setup_default_event_handlers(self):
        """Setup default event handlers for logging and metrics."""
        
        @self.event_system.on("quote_requested")
        async def log_quote_request(data):
            logger.info("Quote requested", **data)
            self.event_system.update_metric("quotes_requested")
        
        @self.event_system.on("quote_received")
        async def log_quote_received(data):
            logger.info("Quote received", quote_id=data.get("quote_id"), time_taken=data.get("time_taken"))
            self.event_system.update_metric("quotes_successful")
        
        @self.event_system.on("quote_failed")
        async def log_quote_failed(data):
            logger.error("Quote failed", error=data.get("error"))
            self.event_system.update_metric("quotes_failed")
        
        @self.event_system.on("api_error")
        async def log_api_error(data):
            logger.error("API error", status_code=data.get("status_code"), error=data.get("error"))
            self.event_system.update_metric("api_errors")
        
        @self.event_system.on("rate_limit_hit")
        async def log_rate_limit(data):
            logger.warning("Rate limit hit", wait_time=data.get("wait_time"))
            self.event_system.update_metric("rate_limits_hit")
    
    async def __aenter__(self):
        """Async context manager entry."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.config.user_agent,
        }
        
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        
        self.session = httpx.AsyncClient(
            timeout=self.config.timeout,
            headers=headers,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.aclose()
    
    async def get_quote(self, params: QuoteParams) -> Optional[EnhancedRFQQuote]:
        """
        Get enhanced RFQ quote with proper error handling and caching.
        
        Args:
            params: Quote parameters
            
        Returns:
            Enhanced RFQ quote or None if failed
        """
        # Check cache first
        cache_key = self._generate_cache_key(params)
        if self.quote_cache and cache_key in self.quote_cache:
            cached_quote = self.quote_cache[cache_key]
            if not cached_quote.is_expired:
                await self.event_system.emit("quote_cache_hit", {
                    "cache_key": cache_key,
                    "quote_id": cached_quote.quote_id
                })
                return cached_quote
        
        # Emit quote request event
        await self.event_system.emit("quote_requested", {
            "input_mint": params.input_mint,
            "output_mint": params.output_mint,
            "amount": params.amount,
            "slippage_bps": params.slippage_bps
        })
        
        try:
            # Apply rate limiting
            await self.rate_limiter.acquire()
            
            # Build request parameters
            request_params = {
                "inputMint": params.input_mint,
                "outputMint": params.output_mint,
                "amount": str(params.amount),
                "slippageBps": params.slippage_bps,
                "onlyDirectRoutes": params.only_direct_routes,
                "restrictIntermediateTokens": params.restrict_intermediate_tokens,
                "asLegacyTransaction": params.as_legacy_transaction,
                "dynamicComputeUnitLimit": params.dynamic_compute_unit_limit
            }
            
            if params.exclude_dexes:
                request_params["excludeDexes"] = ",".join(params.exclude_dexes)
            
            if params.max_accounts:
                request_params["maxAccounts"] = params.max_accounts
            
            if params.platform_fee_bps:
                request_params["platformFeeBps"] = params.platform_fee_bps
            
            # Make API request with retries
            for attempt in range(self.config.max_retries):
                try:
                    response = await self.session.get(
                        f"{self.config.base_url}/swap/v1/quote",
                        params=request_params
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        quote = self._parse_quote_response(data, params)
                        
                        # Cache the quote
                        if self.quote_cache and quote:
                            self.quote_cache[cache_key] = quote
                        
                        # Emit success event
                        await self.event_system.emit("quote_received", {
                            "quote_id": quote.quote_id if quote else None,
                            "time_taken": data.get("timeTaken", 0),
                            "attempt": attempt + 1
                        })
                        
                        return quote
                    
                    elif response.status_code == 429:
                        # Rate limit hit
                        wait_time = 2 ** attempt  # Exponential backoff
                        await self.event_system.emit("rate_limit_hit", {"wait_time": wait_time})
                        await asyncio.sleep(wait_time)
                        continue
                    
                    else:
                        # API error
                        await self.event_system.emit("api_error", {
                            "status_code": response.status_code,
                            "error": response.text,
                            "attempt": attempt + 1
                        })
                        
                        if attempt == self.config.max_retries - 1:
                            raise JupiterAPIError(f"API error: {response.status_code} - {response.text}")
                        
                        await asyncio.sleep(1)  # Brief wait before retry
                
                except httpx.RequestError as e:
                    if attempt == self.config.max_retries - 1:
                        raise JupiterAPIError(f"Request error: {str(e)}")
                    await asyncio.sleep(1)
            
            return None
            
        except Exception as e:
            await self.event_system.emit("quote_failed", {"error": str(e)})
            logger.error("Error getting Jupiter quote", error=str(e))
            return None
    
    def _generate_cache_key(self, params: QuoteParams) -> str:
        """Generate cache key for quote parameters."""
        return f"{params.input_mint}-{params.output_mint}-{params.amount}-{params.slippage_bps}"
    
    def _parse_quote_response(self, data: Dict[str, Any], params: QuoteParams) -> Optional[EnhancedRFQQuote]:
        """Parse Jupiter quote response into enhanced quote object."""
        try:
            input_amount = int(data.get("inAmount", 0))
            output_amount = int(data.get("outAmount", 0))
            
            if input_amount <= 0 or output_amount <= 0:
                return None
            
            # Calculate effective price considering decimals
            input_decimals = 9 if params.input_mint == config.tokens["SOL"] else 6
            output_decimals = 9 if params.output_mint == config.tokens["SOL"] else 6
            
            input_normalized = input_amount / (10 ** input_decimals)
            output_normalized = output_amount / (10 ** output_decimals)
            
            effective_price = output_normalized / input_normalized if input_normalized > 0 else 0
            
            # Calculate RFQ fee (0.1% of input amount)
            rfq_fee_amount = input_normalized * 0.001  # 0.1%
            
            # Generate quote ID and expiry
            quote_id = f"enhanced_rfq_{int(time.time())}_{hash(str(data))}"
            expires_at = datetime.now() + timedelta(seconds=30)  # 30-second expiry
            
            return EnhancedRFQQuote(
                input_mint=data.get("inputMint", ""),
                output_mint=data.get("outputMint", ""),
                input_amount=input_amount,
                output_amount=output_amount,
                other_amount_threshold=int(data.get("otherAmountThreshold", 0)),
                swap_mode=data.get("swapMode", "ExactIn"),
                slippage_bps=data.get("slippageBps", params.slippage_bps),
                platform_fee=data.get("platformFee"),
                price_impact_pct=data.get("priceImpactPct", "0"),
                route_plan=data.get("routePlan", []),
                context_slot=data.get("contextSlot", 0),
                time_taken=data.get("timeTaken", 0),
                timestamp=datetime.now(),
                expires_at=expires_at,
                quote_id=quote_id,
                effective_price=effective_price,
                rfq_fee_amount=rfq_fee_amount
            )
            
        except Exception as e:
            logger.error("Error parsing quote response", error=str(e))
            return None
    
    async def get_swap_instructions(
        self,
        quote: EnhancedRFQQuote,
        user_public_key: str,
        wrap_unwrap_sol: bool = True,
        priority_fee_lamports: int = 0
    ) -> Optional[Dict[str, Any]]:
        """Get swap instructions for enhanced quote."""
        try:
            if quote.is_expired:
                raise QuoteExpiredError("Quote has expired")
            
            await self.rate_limiter.acquire()
            
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
                "prioritizationFeeLamports": priority_fee_lamports,
                "quoteResponse": {
                    "inputMint": quote.input_mint,
                    "inAmount": str(quote.input_amount),
                    "outputMint": quote.output_mint,
                    "outAmount": str(quote.output_amount),
                    "otherAmountThreshold": str(quote.other_amount_threshold),
                    "swapMode": quote.swap_mode,
                    "slippageBps": quote.slippage_bps,
                    "platformFee": quote.platform_fee,
                    "priceImpactPct": quote.price_impact_pct,
                    "routePlan": quote.route_plan,
                    "contextSlot": quote.context_slot,
                    "timeTaken": quote.time_taken
                }
            }
            
            response = await self.session.post(
                f"{self.config.base_url}/swap/v1/swap-instructions",
                json=payload
            )
            
            if response.status_code == 200:
                instructions = response.json()
                
                await self.event_system.emit("swap_instructions_received", {
                    "quote_id": quote.quote_id,
                    "user_public_key": user_public_key,
                    "instruction_count": len(instructions.get("instructions", []))
                })
                
                return instructions
            else:
                await self.event_system.emit("swap_instructions_failed", {
                    "quote_id": quote.quote_id,
                    "status_code": response.status_code,
                    "error": response.text
                })
                return None
                
        except Exception as e:
            await self.event_system.emit("swap_instructions_error", {
                "quote_id": quote.quote_id,
                "error": str(e)
            })
            logger.error("Error getting swap instructions", error=str(e))
            return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get client metrics."""
        return {
            **self.event_system.metrics,
            "cache_size": len(self.quote_cache) if self.quote_cache else 0,
            "config": {
                "tier": self.config.tier.value,
                "rate_limit": self.config.rate_limit_per_second,
                "timeout": self.config.timeout,
                "caching_enabled": self.config.enable_caching
            }
        }


# Example usage and testing
async def test_enhanced_client():
    """Test the enhanced Jupiter client."""
    
    # Configure client
    jupiter_config = JupiterConfig(
        api_key=None,  # Use None for lite tier
        tier=APITier.LITE,
        rate_limit_per_second=5,  # Conservative rate limit
        enable_caching=True
    )
    
    async with EnhancedJupiterClient(jupiter_config) as client:
        # Setup webhook for testing (optional)
        # client.event_system.add_webhook_url("https://your-webhook-url.com/jupiter-events")
        
        # Get a quote
        params = QuoteParams(
            input_mint=config.tokens["SOL"],
            output_mint=config.tokens["USDC"],
            amount=100_000_000,  # 0.1 SOL
            slippage_bps=50,
            restrict_intermediate_tokens=True
        )
        
        quote = await client.get_quote(params)
        
        if quote:
            print(f"Quote received: {quote.quote_id}")
            print(f"Input: {quote.input_amount} -> Output: {quote.output_amount}")
            print(f"Effective price: {quote.effective_price}")
            print(f"RFQ fee: {quote.rfq_fee_amount}")
            print(f"Expires in: {quote.time_to_expiry_seconds:.1f} seconds")
            
            # Get swap instructions
            instructions = await client.get_swap_instructions(
                quote, 
                "2AQdpHJ2JpcEgPiATUXjQxA8QmafFegfQwSLWSprPicm",  # Test wallet
                priority_fee_lamports=1000
            )
            
            if instructions:
                print(f"Swap instructions received: {len(instructions.get('instructions', []))} instructions")
        
        # Print metrics
        metrics = client.get_metrics()
        print(f"Client metrics: {metrics}")


if __name__ == "__main__":
    asyncio.run(test_enhanced_client())