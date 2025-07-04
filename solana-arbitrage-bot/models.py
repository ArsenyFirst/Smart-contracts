"""
Data models for the Solana arbitrage bot.
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class QuoteSource(Enum):
    """Enum for quote sources."""
    JUPITER_RFQ = "jupiter_rfq"
    ORCA = "orca"
    RAYDIUM = "raydium"
    METEORA = "meteora"


class Side(Enum):
    """Enum for buy/sell sides."""
    BUY = "buy"
    SELL = "sell"


@dataclass
class Quote:
    """Normalized quote structure."""
    source: QuoteSource
    side: Side
    input_token: str
    output_token: str
    input_amount: float
    output_amount: float
    price: float  # output_amount / input_amount
    timestamp: datetime
    fee_bps: Optional[int] = None
    slippage_bps: Optional[int] = None
    route_info: Optional[Dict[str, Any]] = None
    ttl_ms: Optional[int] = None  # Time to live in milliseconds
    
    @property
    def is_expired(self) -> bool:
        """Check if quote is expired based on TTL."""
        if not self.ttl_ms:
            return False
        elapsed = (datetime.now() - self.timestamp).total_seconds() * 1000
        return elapsed > self.ttl_ms


@dataclass
class ArbitrageOpportunity:
    """Arbitrage opportunity structure."""
    buy_quote: Quote
    sell_quote: Quote
    profit_bps: int
    profit_amount: float
    profit_percentage: float
    timestamp: datetime
    
    @property
    def is_profitable(self) -> bool:
        """Check if opportunity is still profitable."""
        return not self.buy_quote.is_expired and not self.sell_quote.is_expired


@dataclass
class ExecutionResult:
    """Result of arbitrage execution."""
    opportunity: ArbitrageOpportunity
    success: bool
    tx_signature: Optional[str] = None
    error_message: Optional[str] = None
    actual_profit: Optional[float] = None
    gas_cost: Optional[float] = None
    execution_time_ms: Optional[int] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class TokenPair:
    """Token pair structure."""
    base_token: str
    quote_token: str
    
    def __str__(self) -> str:
        return f"{self.base_token}/{self.quote_token}"
    
    @classmethod
    def from_string(cls, pair_str: str) -> "TokenPair":
        """Create TokenPair from string like 'SOL/USDC'."""
        base, quote = pair_str.split('/')
        return cls(base_token=base, quote_token=quote)


@dataclass
class PnLTracker:
    """P&L tracking structure."""
    total_profit: float = 0.0
    total_trades: int = 0
    successful_trades: int = 0
    failed_trades: int = 0
    total_fees: float = 0.0
    start_time: datetime = None
    
    def __post_init__(self):
        if self.start_time is None:
            self.start_time = datetime.now()
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_trades == 0:
            return 0.0
        return (self.successful_trades / self.total_trades) * 100
    
    @property
    def average_profit_per_trade(self) -> float:
        """Calculate average profit per successful trade."""
        if self.successful_trades == 0:
            return 0.0
        return self.total_profit / self.successful_trades
    
    def add_execution(self, result: ExecutionResult):
        """Add execution result to P&L tracking."""
        self.total_trades += 1
        if result.success:
            self.successful_trades += 1
            if result.actual_profit:
                self.total_profit += result.actual_profit
        else:
            self.failed_trades += 1
        
        if result.gas_cost:
            self.total_fees += result.gas_cost