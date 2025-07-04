"""
Live arbitrage monitoring script with corrected decimal handling.
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
        self.timeout = 5.0
        
    def _convert_amount_to_units(self, amount: float, token: str) -> int:
        """Convert human-readable amount to token units."""
        decimals = 9 if token == "SOL" else 6
        return int(amount * (10 ** decimals))
    
    def _convert_units_to_amount(self, units: int, token: str) -> float:
        """Convert token units to human-readable amount."""
        decimals = 9 if token == "SOL" else 6
        return float(units) / (10 ** decimals)
    
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
                    
                    input_units = int(data.get("inAmount", 0))
                    output_units = int(data.get("outAmount", 0))
                    
                    # Convert back to human-readable amounts
                    input_amount = self._convert_units_to_amount(input_units, input_token)
                    output_amount = self._convert_units_to_amount(output_units, output_token)
                    
                    return {
                        "input_token": input_token,
                        "output_token": output_token,
                        "input_amount": input_amount,
                        "output_amount": output_amount,
                        "rate": output_amount / input_amount if input_amount > 0 else 0,
                        "timestamp": datetime.now(),
                        "raw_data": data
                    }
                else:
                    print(f"❌ Quote API error: {response.status_code}")
                    
        except Exception as e:
            print(f"❌ Quote error: {e}")
            
        return None
    
    async def analyze_round_trip(self, base_token: str, quote_token: str, amount: float):
        """Analyze round-trip arbitrage: token A -> token B -> token A."""
        print(f"  🔄 Round-trip: {base_token} -> {quote_token} -> {base_token}")
        
        # Step 1: Convert base_token to quote_token
        quote1 = await self.get_quote(base_token, quote_token, amount)
        if not quote1:
            print(f"    ❌ Failed to get {base_token} -> {quote_token} quote")
            return
        
        intermediate_amount = quote1["output_amount"]
        print(f"    📊 Step 1: {amount:.6f} {base_token} -> {intermediate_amount:.6f} {quote_token}")
        
        # Step 2: Convert quote_token back to base_token
        quote2 = await self.get_quote(quote_token, base_token, intermediate_amount)
        if not quote2:
            print(f"    ❌ Failed to get {quote_token} -> {base_token} quote")
            return
        
        final_amount = quote2["output_amount"]
        print(f"    📊 Step 2: {intermediate_amount:.6f} {quote_token} -> {final_amount:.6f} {base_token}")
        
        # Calculate profit/loss
        profit_loss = final_amount - amount
        profit_pct = (profit_loss / amount) * 100
        
        if profit_pct > 0.1:
            print(f"    🎯 PROFITABLE: {profit_pct:.3f}% profit (+{profit_loss:.6f} {base_token})")
        elif profit_pct < -0.1:
            print(f"    📉 LOSS: {profit_pct:.3f}% loss ({profit_loss:.6f} {base_token})")
        else:
            print(f"    📊 BREAKEVEN: {profit_pct:.3f}% ({profit_loss:.6f} {base_token})")
        
        return {
            "path": f"{base_token} -> {quote_token} -> {base_token}",
            "input_amount": amount,
            "final_amount": final_amount,
            "profit_loss": profit_loss,
            "profit_pct": profit_pct,
            "profitable": profit_pct > 0.1
        }
    
    async def compare_direct_rates(self):
        """Compare direct exchange rates between tokens."""
        print("  💱 Direct Rate Comparison")
        
        # Get SOL/USDC rate
        sol_usdc = await self.get_quote("SOL", "USDC", 1.0)
        if sol_usdc:
            print(f"    📊 SOL/USDC: 1 SOL = {sol_usdc['output_amount']:.2f} USDC")
        
        # Get SOL/USDT rate
        sol_usdt = await self.get_quote("SOL", "USDT", 1.0)
        if sol_usdt:
            print(f"    📊 SOL/USDT: 1 SOL = {sol_usdt['output_amount']:.2f} USDT")
        
        # Get USDC/USDT rate
        usdc_usdt = await self.get_quote("USDC", "USDT", 1.0)
        if usdc_usdt:
            print(f"    📊 USDC/USDT: 1 USDC = {usdc_usdt['output_amount']:.6f} USDT")
        
        # Compare rates if we have both SOL quotes
        if sol_usdc and sol_usdt:
            usdc_rate = sol_usdc["output_amount"]
            usdt_rate = sol_usdt["output_amount"]
            
            rate_diff = abs(usdc_rate - usdt_rate)
            rate_diff_pct = (rate_diff / min(usdc_rate, usdt_rate)) * 100
            
            print(f"    📊 SOL price difference: {rate_diff:.2f} ({rate_diff_pct:.3f}%)")
            
            if rate_diff_pct > 0.1:
                cheaper_token = "USDC" if usdc_rate < usdt_rate else "USDT"
                expensive_token = "USDT" if usdc_rate < usdt_rate else "USDC"
                print(f"    🎯 Potential arbitrage: SOL cheaper in {cheaper_token}, expensive in {expensive_token}")
    
    async def single_scan(self):
        """Run a single arbitrage scan."""
        print("🔍 Single Arbitrage Scan")
        print("=" * 50)
        
        # Compare direct rates
        await self.compare_direct_rates()
        
        print()
        
        # Test round-trip arbitrage
        test_amount = 1.0
        
        # SOL -> USDC -> SOL
        await self.analyze_round_trip("SOL", "USDC", test_amount)
        
        print()
        
        # SOL -> USDT -> SOL
        await self.analyze_round_trip("SOL", "USDT", test_amount)
        
        print()
        
        # USDC -> USDT -> USDC (smaller test amount)
        await self.analyze_round_trip("USDC", "USDT", 100.0)
        
        print("\n✅ Scan complete!")
    
    async def run_monitoring_loop(self):
        """Main monitoring loop."""
        print("🚀 Starting Live Arbitrage Monitor")
        print("=" * 50)
        print(f"⏱️  Monitoring interval: {self.interval}s")
        print(f"🎯 Profit threshold: 0.1%")
        print("Press Ctrl+C to stop\n")
        
        self.running = True
        iteration = 0
        
        try:
            while self.running:
                iteration += 1
                now = datetime.now().strftime("%H:%M:%S")
                
                print(f"📊 Scan #{iteration} at {now}")
                print("-" * 30)
                
                # Run arbitrage analysis
                await self.single_scan()
                
                print()
                
                # Wait for next iteration
                await asyncio.sleep(self.interval)
                
        except KeyboardInterrupt:
            print("\n👋 Monitoring stopped by user")
            self.running = False


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