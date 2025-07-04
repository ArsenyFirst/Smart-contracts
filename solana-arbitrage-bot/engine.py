"""
Core arbitrage engine for detecting and executing opportunities.
"""
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
import structlog

from models import (
    Quote, ArbitrageOpportunity, ExecutionResult, 
    Side, TokenPair, PnLTracker
)
from config import config
from rfq_client import JupiterRFQClient
from amm_client import AMMClientManager
from tx_builder import TransactionBuilder


logger = structlog.get_logger(__name__)


class ArbitrageEngine:
    """Core arbitrage engine."""
    
    def __init__(self):
        self.rfq_client = JupiterRFQClient()
        self.amm_manager = AMMClientManager()
        self.tx_builder = TransactionBuilder()
        self.pnl_tracker = PnLTracker()
        self.running = False
        
    async def start(self, token_pair: TokenPair):
        """Start the arbitrage bot."""
        logger.info("Starting arbitrage engine", token_pair=str(token_pair))
        self.running = True
        
        try:
            while self.running:
                await self._run_arbitrage_cycle(token_pair)
                await asyncio.sleep(config.loop_interval_seconds)
        except KeyboardInterrupt:
            logger.info("Arbitrage engine stopped by user")
        except Exception as e:
            logger.error("Arbitrage engine error", error=str(e))
        finally:
            self.running = False
    
    def stop(self):
        """Stop the arbitrage bot."""
        logger.info("Stopping arbitrage engine")
        self.running = False
    
    async def _run_arbitrage_cycle(self, token_pair: TokenPair):
        """Run a single arbitrage cycle."""
        try:
            # Fetch quotes from all sources
            rfq_quotes, amm_quotes = await asyncio.gather(
                self._get_rfq_quotes(token_pair),
                self._get_amm_quotes(token_pair)
            )
            
            if not rfq_quotes or not amm_quotes:
                logger.debug("Insufficient quotes to check arbitrage")
                return
            
            # Find arbitrage opportunities
            opportunities = self._find_arbitrage_opportunities(
                rfq_quotes, amm_quotes
            )
            
            if not opportunities:
                logger.debug("No arbitrage opportunities found")
                return
            
            # Log opportunities
            for opp in opportunities:
                logger.info(
                    "Arbitrage opportunity found",
                    profit_bps=opp.profit_bps,
                    profit_amount=opp.profit_amount,
                    buy_source=opp.buy_quote.source.value,
                    sell_source=opp.sell_quote.source.value
                )
            
            # Execute the best opportunity
            best_opportunity = max(opportunities, key=lambda o: o.profit_bps)
            
            if best_opportunity.profit_bps >= config.min_profit_threshold_bps:
                await self._execute_arbitrage(best_opportunity)
            else:
                logger.debug(
                    "Opportunity below threshold",
                    profit_bps=best_opportunity.profit_bps,
                    threshold=config.min_profit_threshold_bps
                )
                
        except Exception as e:
            logger.error("Error in arbitrage cycle", error=str(e))
    
    async def _get_rfq_quotes(self, token_pair: TokenPair) -> List[Quote]:
        """Get quotes from Jupiter RFQ."""
        try:
            quotes = await self.rfq_client.get_quotes_for_pair(
                token_pair, 
                config.trade_amount
            )
            logger.debug("Retrieved RFQ quotes", count=len(quotes))
            return quotes
        except Exception as e:
            logger.error("Error getting RFQ quotes", error=str(e))
            return []
    
    async def _get_amm_quotes(self, token_pair: TokenPair) -> List[Quote]:
        """Get quotes from AMM DEXes."""
        try:
            quotes = await self.amm_manager.get_all_quotes(
                token_pair,
                config.trade_amount
            )
            logger.debug("Retrieved AMM quotes", count=len(quotes))
            return quotes
        except Exception as e:
            logger.error("Error getting AMM quotes", error=str(e))
            return []
    
    def _find_arbitrage_opportunities(
        self,
        rfq_quotes: List[Quote],
        amm_quotes: List[Quote]
    ) -> List[ArbitrageOpportunity]:
        """Find arbitrage opportunities between RFQ and AMM quotes."""
        opportunities = []
        
        # Get active (non-expired) quotes
        active_rfq = [q for q in rfq_quotes if not q.is_expired]
        active_amm = [q for q in amm_quotes if not q.is_expired]
        
        if not active_rfq or not active_amm:
            return opportunities
        
        # Strategy 1: Buy from AMM, Sell via RFQ
        amm_buy_quotes = [q for q in active_amm if q.side == Side.BUY]
        rfq_sell_quotes = [q for q in active_rfq if q.side == Side.SELL]
        
        for amm_buy in amm_buy_quotes:
            for rfq_sell in rfq_sell_quotes:
                if self._quotes_compatible(amm_buy, rfq_sell):
                    opp = self._calculate_arbitrage_profit(amm_buy, rfq_sell)
                    if opp and opp.profit_bps > 0:
                        opportunities.append(opp)
        
        # Strategy 2: Buy via RFQ, Sell to AMM
        rfq_buy_quotes = [q for q in active_rfq if q.side == Side.BUY]
        amm_sell_quotes = [q for q in active_amm if q.side == Side.SELL]
        
        for rfq_buy in rfq_buy_quotes:
            for amm_sell in amm_sell_quotes:
                if self._quotes_compatible(rfq_buy, amm_sell):
                    opp = self._calculate_arbitrage_profit(rfq_buy, amm_sell)
                    if opp and opp.profit_bps > 0:
                        opportunities.append(opp)
        
        return opportunities
    
    def _quotes_compatible(self, buy_quote: Quote, sell_quote: Quote) -> bool:
        """Check if two quotes are compatible for arbitrage."""
        # Check that we're buying and selling the same tokens
        return (
            buy_quote.output_token == sell_quote.input_token and
            buy_quote.input_token == sell_quote.output_token
        )
    
    def _calculate_arbitrage_profit(
        self,
        buy_quote: Quote,
        sell_quote: Quote
    ) -> Optional[ArbitrageOpportunity]:
        """Calculate potential arbitrage profit."""
        try:
            # Simplistic calculation - in reality you'd need to account for:
            # - Exact input/output amounts
            # - Gas fees
            # - Slippage
            # - Market impact
            
            buy_price = buy_quote.price
            sell_price = sell_quote.price
            
            if buy_price <= 0 or sell_price <= 0:
                return None
            
            # Calculate profit in basis points
            profit_percentage = (sell_price - buy_price) / buy_price
            profit_bps = int(profit_percentage * 10000)
            
            # Estimate profit amount (simplified)
            trade_amount = min(buy_quote.input_amount, sell_quote.input_amount)
            profit_amount = trade_amount * profit_percentage
            
            # Subtract estimated fees (gas + DEX fees)
            estimated_gas_cost = 0.01  # ~0.01 SOL for gas
            estimated_dex_fees = trade_amount * 0.003  # ~0.3% DEX fees
            net_profit = profit_amount - estimated_gas_cost - estimated_dex_fees
            
            # Recalculate profit bps after fees
            net_profit_bps = int((net_profit / trade_amount) * 10000) if trade_amount > 0 else 0
            
            if net_profit_bps <= 0:
                return None
            
            return ArbitrageOpportunity(
                buy_quote=buy_quote,
                sell_quote=sell_quote,
                profit_bps=net_profit_bps,
                profit_amount=net_profit,
                profit_percentage=net_profit / trade_amount if trade_amount > 0 else 0,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error("Error calculating arbitrage profit", error=str(e))
            return None
    
    async def _execute_arbitrage(self, opportunity: ArbitrageOpportunity):
        """Execute an arbitrage opportunity."""
        logger.info(
            "Executing arbitrage",
            profit_bps=opportunity.profit_bps,
            buy_source=opportunity.buy_quote.source.value,
            sell_source=opportunity.sell_quote.source.value
        )
        
        start_time = datetime.now()
        
        try:
            # Check if opportunity is still valid
            if not opportunity.is_profitable:
                logger.warning("Opportunity expired before execution")
                return
            
            # Build the atomic transaction
            transaction = await self.tx_builder.build_arbitrage_transaction(
                opportunity
            )
            
            if not transaction:
                logger.error("Failed to build arbitrage transaction")
                result = ExecutionResult(
                    opportunity=opportunity,
                    success=False,
                    error_message="Failed to build transaction"
                )
                self.pnl_tracker.add_execution(result)
                return
            
            # Execute the transaction
            signature = await self.tx_builder.execute_transaction(transaction)
            
            if signature:
                execution_time = (datetime.now() - start_time).total_seconds() * 1000
                
                result = ExecutionResult(
                    opportunity=opportunity,
                    success=True,
                    tx_signature=signature,
                    actual_profit=opportunity.profit_amount,  # Simplified
                    execution_time_ms=int(execution_time)
                )
                
                logger.info(
                    "Arbitrage executed successfully",
                    signature=signature,
                    profit=opportunity.profit_amount,
                    execution_time_ms=execution_time
                )
            else:
                result = ExecutionResult(
                    opportunity=opportunity,
                    success=False,
                    error_message="Transaction failed to execute"
                )
                
                logger.error("Arbitrage execution failed")
            
            self.pnl_tracker.add_execution(result)
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            
            result = ExecutionResult(
                opportunity=opportunity,
                success=False,
                error_message=str(e),
                execution_time_ms=int(execution_time)
            )
            
            self.pnl_tracker.add_execution(result)
            logger.error("Error executing arbitrage", error=str(e))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get bot statistics."""
        return {
            "total_trades": self.pnl_tracker.total_trades,
            "successful_trades": self.pnl_tracker.successful_trades,
            "failed_trades": self.pnl_tracker.failed_trades,
            "success_rate": self.pnl_tracker.success_rate,
            "total_profit": self.pnl_tracker.total_profit,
            "average_profit_per_trade": self.pnl_tracker.average_profit_per_trade,
            "total_fees": self.pnl_tracker.total_fees,
            "uptime_hours": (datetime.now() - self.pnl_tracker.start_time).total_seconds() / 3600
        }
    
    async def run_single_check(self, token_pair: TokenPair) -> Dict[str, Any]:
        """Run a single arbitrage check (for testing/manual operation)."""
        rfq_quotes, amm_quotes = await asyncio.gather(
            self._get_rfq_quotes(token_pair),
            self._get_amm_quotes(token_pair)
        )
        
        opportunities = self._find_arbitrage_opportunities(rfq_quotes, amm_quotes)
        
        best_opportunity = None
        if opportunities:
            best_opportunity = max(opportunities, key=lambda o: o.profit_bps)
        
        return {
            "rfq_quotes_count": len(rfq_quotes),
            "amm_quotes_count": len(amm_quotes),
            "opportunities_found": len(opportunities),
            "best_opportunity": {
                "profit_bps": best_opportunity.profit_bps,
                "profit_amount": best_opportunity.profit_amount,
                "buy_source": best_opportunity.buy_quote.source.value,
                "sell_source": best_opportunity.sell_quote.source.value
            } if best_opportunity else None,
            "executable": best_opportunity and best_opportunity.profit_bps >= config.min_profit_threshold_bps
        }