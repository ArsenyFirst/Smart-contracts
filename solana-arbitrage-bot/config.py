"""
Configuration settings for the Solana arbitrage bot.
"""
import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Configuration for the arbitrage bot."""
    
    # Trading parameters
    asset_pair: str = "SOL/USDC"
    trade_amount: float = 1000.0  # USDC amount
    min_profit_threshold_bps: int = 10  # Minimum profit in basis points
    
    # API endpoints
    jupiter_rfq_url: str = "https://quote-api.jup.ag/v6"
    orca_api_url: str = "https://api.orca.so/v1"
    raydium_api_url: str = "https://api.raydium.io/v2"
    meteora_api_url: str = "https://dlmm-api.meteora.ag"
    
    # Solana RPC
    solana_rpc_url: str = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    private_key: Optional[str] = os.getenv("SOLANA_PRIVATE_KEY")
    
    # Bot settings
    loop_interval_seconds: float = 1.0
    request_timeout_seconds: float = 2.0
    max_retries: int = 3
    
    # Logging
    log_level: str = "INFO"
    log_to_file: bool = True
    log_file_path: str = "arbitrage_bot.log"
    
    # Token addresses (Solana mainnet)
    tokens: dict = None
    
    def __post_init__(self):
        if self.tokens is None:
            self.tokens = {
                "SOL": "So11111111111111111111111111111111111111112",
                "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
                "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
                "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
            }


# Global config instance
config = Config()