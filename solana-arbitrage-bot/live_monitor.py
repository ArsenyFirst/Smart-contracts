"""
Live arbitrage monitoring script.
Continuously monitors price differences between DEXes.
"""
import asyncio
import sys
from datetime import datetime
import httpx
from typing import List, Optional


class LiveArbitrageMonitor:
    """Continuously monitors for arbitrage opportunities."""
    
    def __init__(self, interval_seconds: float = 2.0):
        self.interval = interval_seconds
        self.jupiter_url = "https://quote-api.jup.ag/v6"
        self.tokens = {
            "SOL": "So11111111111111111111111111111111111111112",
            "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
        }
        self.running = False
        self.timeout = 3.0
        
    def _convert_amount_to_units(self, amount: float, token: str) -> int:
        """Convert amount to token units."""
        decimals = 9 if token == "SOL" else 6
        return int(amount * (10 ** decimals))
    
    async def get_quote(self, input_token: str, output_token: str, amount: float) -> Optional[dict]:
        """Get quote from Jupiter."""
        try:
            input_mint = self.tokens.get(input_token)
            output_mint = self.tokens.get(output_token)
            
            if not input_mint or not output_mint:
                return None
            
            amount_in_units = self._convert_amount_to_units(amount, input_token)
            
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount_in_units),
                "slippageBps": 50,
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.jupiter_url}/quote", params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    return {
                        "input_token": input_token,
                        "output_token": output_token,
                        "input_amount": float(data.get("inAmount", 0)),
                        "output_amount": float(data.get("outAmount", 0)),
                        "timestamp": datetime.now()
                    }
                    
        except Exception as e:
            print(f"❌ Quote error: {e}")
            
        return None
    
    async def analyze_triangular_arbitrage(self, amount: float = 1.0) -> List[dict]:
        """Look for triangular arbitrage opportunities."""
        # Get quotes for SOL/USDC, USDC/USDT, USDT/SOL
        quotes = await asyncio.gather(
            self.get_quote("SOL", "USDC", amount),
            self.get_quote("USDC", "USDT", 146.0),  # Approximately what we get from 1 SOL
            self.get_quote("USDT", "SOL", 146.0),   # Try to get back to SOL
            return_exceptions=True
        )
        
        opportunities = []
        
        # Simple SOL -> USDC -> SOL round trip
        sol_to_usdc = await self.get_quote("SOL", "USDC", amount)
        if sol_to_usdc:
            usdc_amount = sol_to_usdc["output_amount"] / 1e6
            
            usdc_to_sol = await self.get_quote("USDC", "SOL", usdc_amount)
            if usdc_to_sol:
                final_sol = usdc_to_sol["output_amount"] / 1e9
                
                profit_loss = final_sol - amount
                profit_pct = (profit_loss / amount) * 100
                
                opportunities.append({
                    "path": "SOL -> USDC -> SOL",
                    "input_amount": amount,
                    "final_amount": final_sol,
                    "profit_loss": profit_loss,
                    "profit_pct": profit_pct,
                    "profitable": profit_pct > 0.1  # 0.1% threshold
                })
        
        return opportunities
    
    async def monitor_simple_pairs(self):
        """Monitor simple pair arbitrage opportunities."""
        pairs = [
            ("SOL", "USDC", 1.0),
            ("SOL", "USDT", 1.0),
        ]
        
        for input_token, output_token, amount in pairs:
            # Get forward and reverse quotes
            forward = await self.get_quote(input_token, output_token, amount)
            
                         if forward:
                 # Convert raw amounts to human-readable amounts
                 if input_token == "SOL":
                     # SOL -> USDC/USDT: output is in USDC/USDT units (6 decimals)
                     output_amount = forward["output_amount"] / 1e6
                 else:
                     # USDC/USDT -> SOL: output is in SOL units (9 decimals)
                     output_amount = forward["output_amount"] / 1e9
                 
                 reverse = await self.get_quote(output_token, input_token, output_amount)
                 
                 if reverse:
                     if output_token == "SOL":
                         # USDC/USDT -> SOL: final amount is in SOL units (9 decimals)
                         final_amount = reverse["output_amount"] / 1e9
                     else:
                         # SOL -> USDC/USDT: final amount is in USDC/USDT units (6 decimals)
                         final_amount = reverse["output_amount"] / 1e6
                     
                     profit_loss = final_amount - amount
                     profit_pct = (profit_loss / amount) * 100
                    
                    status = "🎯 PROFITABLE" if profit_pct > 0.1 else "📊 NORMAL"
                    
                    print(f"  {status} {input_token}/{output_token}: {profit_pct:.3f}% ({final_amount:.6f} vs {amount:.6f})")
    
    async def run_monitoring_loop(self):
        """Main monitoring loop."""
        print("🚀 Starting Live Arbitrage Monitor")
        print("=" * 50)
        print(f"⏱️  Monitoring interval: {self.interval}s")
        print(f"🎯 Profit threshold: 0.1%")
        print("Press Ctrl+C to stop\n")
        
        self.running = True
        iteration = 0
        
        while self.running:
            try:
                iteration += 1
                now = datetime.now().strftime("%H:%M:%S")
                
                print(f"📊 Scan #{iteration} at {now}")
                print("-" * 30)
                
                # Monitor simple pairs
                await self.monitor_simple_pairs()
                
                # Check triangular arbitrage
                triangular_opps = await self.analyze_triangular_arbitrage()
                
                for opp in triangular_opps:
                    status = "🎯 PROFITABLE" if opp["profitable"] else "📊 NORMAL"
                    print(f"  {status} {opp['path']}: {opp['profit_pct']:.3f}% profit")
                
                print()
                
                # Wait for next iteration
                await asyncio.sleep(self.interval)
                
            except KeyboardInterrupt:
                print("\n👋 Monitoring stopped by user")
                break
            except Exception as e:
                print(f"❌ Monitoring error: {e}")
                await asyncio.sleep(self.interval)
    
    async def single_scan(self):
        """Run a single arbitrage scan."""
        print("🔍 Single Arbitrage Scan")
        print("=" * 30)
        
        # Monitor pairs
        await self.monitor_simple_pairs()
        
        # Check triangular
        triangular_opps = await self.analyze_triangular_arbitrage()
        
        for opp in triangular_opps:
            status = "🎯 PROFITABLE" if opp["profitable"] else "📊 NORMAL"
            print(f"{status} {opp['path']}: {opp['profit_pct']:.3f}% profit")
        
        print("\n✅ Scan complete!")


async def main():
    """Main entry point."""
    monitor = LiveArbitrageMonitor()
    
    if len(sys.argv) > 1 and sys.argv[1] == "single":
        # Single scan mode
        await monitor.single_scan()
    else:
        # Continuous monitoring mode
        await monitor.run_monitoring_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)