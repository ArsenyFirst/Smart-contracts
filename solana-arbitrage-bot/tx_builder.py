"""
Transaction builder for Solana arbitrage operations.
"""
import base64
from typing import Optional, Dict, Any, List
import structlog
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solana.keypair import Keypair
from solana.transaction import Transaction
from solana.system_program import TransferParams, transfer
from solana.publickey import PublicKey
from solana.rpc.types import TxOpts

from models import ArbitrageOpportunity, QuoteSource
from config import config
from rfq_client import JupiterRFQClient


logger = structlog.get_logger(__name__)


class TransactionBuilder:
    """Builder for Solana transactions."""
    
    def __init__(self):
        self.solana_client = AsyncClient(config.solana_rpc_url)
        self.rfq_client = JupiterRFQClient()
        
        # Initialize wallet keypair if private key is provided
        self.wallet = None
        if config.private_key:
            try:
                # Decode base58 private key
                import base58
                private_key_bytes = base58.b58decode(config.private_key)
                self.wallet = Keypair.from_secret_key(private_key_bytes)
                logger.info("Wallet initialized", public_key=str(self.wallet.public_key))
            except Exception as e:
                logger.error("Failed to initialize wallet", error=str(e))
    
    async def build_arbitrage_transaction(
        self,
        opportunity: ArbitrageOpportunity
    ) -> Optional[Transaction]:
        """
        Build an atomic transaction for arbitrage execution.
        
        Args:
            opportunity: The arbitrage opportunity to execute
            
        Returns:
            Transaction object or None if failed
        """
        if not self.wallet:
            logger.error("Wallet not initialized")
            return None
        
        try:
            logger.info(
                "Building arbitrage transaction",
                buy_source=opportunity.buy_quote.source.value,
                sell_source=opportunity.sell_quote.source.value
            )
            
            # For this prototype, we'll build separate transactions for each leg
            # In a production system, you'd want to bundle these atomically
            
            buy_tx = await self._build_swap_transaction(
                opportunity.buy_quote, 
                is_buy_leg=True
            )
            
            if not buy_tx:
                logger.error("Failed to build buy transaction")
                return None
            
            sell_tx = await self._build_swap_transaction(
                opportunity.sell_quote,
                is_buy_leg=False
            )
            
            if not sell_tx:
                logger.error("Failed to build sell transaction")
                return None
            
            # For simplicity, return the buy transaction first
            # In production, you'd want to bundle these or use a more sophisticated approach
            return buy_tx
            
        except Exception as e:
            logger.error("Error building arbitrage transaction", error=str(e))
            return None
    
    async def _build_swap_transaction(
        self,
        quote,
        is_buy_leg: bool
    ) -> Optional[Transaction]:
        """Build a swap transaction for a given quote."""
        try:
            if quote.source == QuoteSource.JUPITER_RFQ:
                return await self._build_jupiter_transaction(quote)
            elif quote.source == QuoteSource.RAYDIUM:
                return await self._build_raydium_transaction(quote)
            elif quote.source == QuoteSource.METEORA:
                return await self._build_meteora_transaction(quote)
            elif quote.source == QuoteSource.ORCA:
                return await self._build_orca_transaction(quote)
            else:
                logger.error("Unsupported quote source", source=quote.source.value)
                return None
                
        except Exception as e:
            logger.error("Error building swap transaction", error=str(e))
            return None
    
    async def _build_jupiter_transaction(self, quote) -> Optional[Transaction]:
        """Build a Jupiter swap transaction."""
        try:
            # Get swap instructions from Jupiter
            # Note: This is simplified - you'd need the actual quote response
            quote_response = quote.route_info  # This should contain the original quote response
            
            if not quote_response:
                logger.error("No route info in Jupiter quote")
                return None
            
            swap_instructions = await self.rfq_client.get_swap_instructions(
                quote_response,
                str(self.wallet.public_key)
            )
            
            if not swap_instructions:
                logger.error("Failed to get Jupiter swap instructions")
                return None
            
            # Build transaction from instructions
            # This is a simplified implementation
            transaction = Transaction()
            
            # In a real implementation, you'd parse the instructions and add them to the transaction
            logger.warning("Jupiter transaction building is simplified in this prototype")
            
            return transaction
            
        except Exception as e:
            logger.error("Error building Jupiter transaction", error=str(e))
            return None
    
    async def _build_raydium_transaction(self, quote) -> Optional[Transaction]:
        """Build a Raydium swap transaction."""
        try:
            # This would use Raydium's transaction API
            logger.warning("Raydium transaction building not implemented in this prototype")
            return None
            
        except Exception as e:
            logger.error("Error building Raydium transaction", error=str(e))
            return None
    
    async def _build_meteora_transaction(self, quote) -> Optional[Transaction]:
        """Build a Meteora swap transaction."""
        try:
            # This would use Meteora's SDK to build transactions
            logger.warning("Meteora transaction building not implemented in this prototype")
            return None
            
        except Exception as e:
            logger.error("Error building Meteora transaction", error=str(e))
            return None
    
    async def _build_orca_transaction(self, quote) -> Optional[Transaction]:
        """Build an Orca swap transaction."""
        try:
            # This would use Orca's SDK to build transactions
            logger.warning("Orca transaction building not implemented in this prototype")
            return None
            
        except Exception as e:
            logger.error("Error building Orca transaction", error=str(e))
            return None
    
    async def execute_transaction(self, transaction: Transaction) -> Optional[str]:
        """
        Execute a transaction on Solana.
        
        Args:
            transaction: The transaction to execute
            
        Returns:
            Transaction signature or None if failed
        """
        if not self.wallet:
            logger.error("Wallet not initialized")
            return None
        
        try:
            # Sign the transaction
            transaction.sign(self.wallet)
            
            # Send the transaction
            response = await self.solana_client.send_transaction(
                transaction,
                opts=TxOpts(
                    skip_preflight=False,
                    preflight_commitment=Confirmed
                )
            )
            
            if response['result']:
                signature = response['result']
                logger.info("Transaction sent", signature=signature)
                
                # Wait for confirmation
                confirmed = await self._wait_for_confirmation(signature)
                
                if confirmed:
                    logger.info("Transaction confirmed", signature=signature)
                    return signature
                else:
                    logger.error("Transaction failed to confirm", signature=signature)
                    return None
            else:
                logger.error("Failed to send transaction", response=response)
                return None
                
        except Exception as e:
            logger.error("Error executing transaction", error=str(e))
            return None
    
    async def _wait_for_confirmation(
        self, 
        signature: str, 
        timeout: int = 30
    ) -> bool:
        """Wait for transaction confirmation."""
        try:
            import asyncio
            
            for _ in range(timeout):
                status = await self.solana_client.get_signature_status(signature)
                
                if status['result'] and status['result']['value']:
                    confirmation_status = status['result']['value']
                    if confirmation_status['confirmationStatus'] in ['confirmed', 'finalized']:
                        return True
                    elif confirmation_status['err']:
                        logger.error(
                            "Transaction failed",
                            signature=signature,
                            error=confirmation_status['err']
                        )
                        return False
                
                await asyncio.sleep(1)
            
            logger.warning("Transaction confirmation timeout", signature=signature)
            return False
            
        except Exception as e:
            logger.error("Error waiting for confirmation", error=str(e))
            return False
    
    async def get_balance(self, token_mint: Optional[str] = None) -> float:
        """
        Get wallet balance for SOL or a specific token.
        
        Args:
            token_mint: Mint address for token balance, None for SOL
            
        Returns:
            Balance in native units
        """
        if not self.wallet:
            logger.error("Wallet not initialized")
            return 0.0
        
        try:
            if token_mint is None:
                # Get SOL balance
                response = await self.solana_client.get_balance(self.wallet.public_key)
                if response['result']:
                    return response['result']['value'] / 1e9  # Convert lamports to SOL
            else:
                # Get token balance
                # This would require finding the associated token account and getting its balance
                logger.warning("Token balance checking not implemented in this prototype")
                return 0.0
            
            return 0.0
            
        except Exception as e:
            logger.error("Error getting balance", error=str(e))
            return 0.0
    
    async def estimate_gas_cost(self, transaction: Transaction) -> float:
        """
        Estimate gas cost for a transaction.
        
        Args:
            transaction: The transaction to estimate
            
        Returns:
            Estimated gas cost in SOL
        """
        try:
            # Simplified gas estimation
            # In reality, you'd simulate the transaction to get accurate gas costs
            
            # Base transaction fee
            base_fee = 5000  # 5000 lamports
            
            # Estimate compute units based on instruction count
            instruction_count = len(transaction.instructions)
            estimated_compute_units = instruction_count * 10000  # Rough estimate
            
            # Get current priority fee
            # This would require calling a priority fee API
            priority_fee_per_cu = 1  # 1 micro-lamport per compute unit
            
            total_cost_lamports = base_fee + (estimated_compute_units * priority_fee_per_cu)
            total_cost_sol = total_cost_lamports / 1e9
            
            return total_cost_sol
            
        except Exception as e:
            logger.error("Error estimating gas cost", error=str(e))
            return 0.01  # Default estimate
    
    def create_demo_transaction(self) -> Optional[Transaction]:
        """Create a demo transaction for testing (transfers 0.001 SOL to self)."""
        if not self.wallet:
            logger.error("Wallet not initialized")
            return None
        
        try:
            transaction = Transaction()
            
            # Add a small transfer instruction
            transfer_instruction = transfer(
                TransferParams(
                    from_pubkey=self.wallet.public_key,
                    to_pubkey=self.wallet.public_key,
                    lamports=1000000  # 0.001 SOL
                )
            )
            
            transaction.add(transfer_instruction)
            
            return transaction
            
        except Exception as e:
            logger.error("Error creating demo transaction", error=str(e))
            return None
    
    async def close(self):
        """Close the Solana client connection."""
        try:
            await self.solana_client.close()
        except Exception as e:
            logger.error("Error closing Solana client", error=str(e))