"""
Debug script to understand Meteora pool data structure and available tokens.
"""
import asyncio
import httpx
from collections import Counter
import json


TOKENS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "WSOL": "So11111111111111111111111111111111111111112",
}

MINT_TO_SYMBOL = {v: k for k, v in TOKENS.items()}


async def debug_meteora_data():
    """Debug Meteora API data structure."""
    print("🔍 Debugging Meteora DLMM API")
    print("=" * 50)
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get("https://dlmm-api.meteora.ag/pair/all")
            
            if response.status_code != 200:
                print(f"❌ API Error: {response.status_code}")
                return
            
            data = response.json()
            print(f"✅ Fetched {len(data)} pools")
            
            # Analyze first few pools
            print(f"\n📊 Sample Pool Data (first 3 pools):")
            for i, pool in enumerate(data[:3]):
                print(f"\nPool {i+1}:")
                print(f"  Address: {pool.get('address', 'N/A')}")
                print(f"  Name: {pool.get('name', 'N/A')}")
                print(f"  Mint X: {pool.get('mint_x', 'N/A')}")
                print(f"  Mint Y: {pool.get('mint_y', 'N/A')}")
                print(f"  Liquidity: ${pool.get('liquidity', 0)}")
                print(f"  Current Price: {pool.get('current_price', 0)}")
                print(f"  Hide: {pool.get('hide', False)}")
                print(f"  Blacklisted: {pool.get('is_blacklisted', False)}")
            
            # Check for our target tokens
            print(f"\n🔍 Looking for our target tokens...")
            sol_pools = []
            usdc_pools = []
            usdt_pools = []
            
            for pool in data:
                mint_x = pool.get('mint_x', '')
                mint_y = pool.get('mint_y', '')
                
                if mint_x == TOKENS['SOL'] or mint_y == TOKENS['SOL']:
                    sol_pools.append(pool)
                
                if mint_x == TOKENS['USDC'] or mint_y == TOKENS['USDC']:
                    usdc_pools.append(pool)
                
                if mint_x == TOKENS['USDT'] or mint_y == TOKENS['USDT']:
                    usdt_pools.append(pool)
            
            print(f"🌟 SOL pools found: {len(sol_pools)}")
            print(f"💵 USDC pools found: {len(usdc_pools)}")
            print(f"💰 USDT pools found: {len(usdt_pools)}")
            
            # Find SOL/USDC pairs specifically
            sol_usdc_pools = []
            for pool in data:
                mint_x = pool.get('mint_x', '')
                mint_y = pool.get('mint_y', '')
                
                if ((mint_x == TOKENS['SOL'] and mint_y == TOKENS['USDC']) or 
                    (mint_x == TOKENS['USDC'] and mint_y == TOKENS['SOL'])):
                    sol_usdc_pools.append(pool)
            
            print(f"\n🎯 SOL/USDC pairs found: {len(sol_usdc_pools)}")
            
            if sol_usdc_pools:
                print(f"\n📋 SOL/USDC Pool Details:")
                for i, pool in enumerate(sol_usdc_pools[:5]):  # Show first 5
                    liquidity = pool.get('liquidity', 0)
                    print(f"  {i+1}. {pool.get('name', 'N/A')}")
                    print(f"     Address: {pool.get('address', 'N/A')}")
                    print(f"     Liquidity: ${liquidity:,.0f}" if liquidity else "     Liquidity: N/A")
                    print(f"     Price: {pool.get('current_price', 0)}")
                    print(f"     Hidden: {pool.get('hide', False)}")
                    print(f"     Blacklisted: {pool.get('is_blacklisted', False)}")
                    print(f"     Fee: {pool.get('base_fee_percentage', 0)*100:.2f}%")
            
            # Check token distribution
            print(f"\n📊 Token Analysis:")
            mint_x_counter = Counter()
            mint_y_counter = Counter()
            
            for pool in data:
                mint_x = pool.get('mint_x', '')
                mint_y = pool.get('mint_y', '')
                
                if mint_x:
                    mint_x_counter[mint_x] += 1
                if mint_y:
                    mint_y_counter[mint_y] += 1
            
            print(f"Most common mint_x tokens:")
            for mint, count in mint_x_counter.most_common(10):
                symbol = MINT_TO_SYMBOL.get(mint, mint[:8] + "...")
                print(f"  {symbol}: {count} pools")
            
            print(f"\nMost common mint_y tokens:")
            for mint, count in mint_y_counter.most_common(10):
                symbol = MINT_TO_SYMBOL.get(mint, mint[:8] + "...")
                print(f"  {symbol}: {count} pools")
            
            # Test filtering logic
            print(f"\n🧪 Testing Filter Logic:")
            target_tokens = set(TOKENS.keys())
            filtered_count = 0
            high_liquidity_count = 0
            
            for pool in data:
                mint_x = pool.get('mint_x', '')
                mint_y = pool.get('mint_y', '')
                
                symbol_x = MINT_TO_SYMBOL.get(mint_x)
                symbol_y = MINT_TO_SYMBOL.get(mint_y)
                
                if symbol_x and symbol_y:
                    if symbol_x in target_tokens and symbol_y in target_tokens:
                        if not (pool.get('is_blacklisted', False) or pool.get('hide', False)):
                            liquidity = pool.get('liquidity', 0)
                            if liquidity and liquidity >= 1000:
                                filtered_count += 1
                                if liquidity >= 10000:
                                    high_liquidity_count += 1
            
            print(f"  Pools passing all filters: {filtered_count}")
            print(f"  Pools with >$10k liquidity: {high_liquidity_count}")
            
            # Show some pools that pass the filter
            if filtered_count > 0:
                print(f"\n✅ Example Filtered Pools:")
                shown = 0
                for pool in data:
                    if shown >= 5:
                        break
                        
                    mint_x = pool.get('mint_x', '')
                    mint_y = pool.get('mint_y', '')
                    
                    symbol_x = MINT_TO_SYMBOL.get(mint_x)
                    symbol_y = MINT_TO_SYMBOL.get(mint_y)
                    
                    if symbol_x and symbol_y:
                        if symbol_x in target_tokens and symbol_y in target_tokens:
                            if not (pool.get('is_blacklisted', False) or pool.get('hide', False)):
                                liquidity = pool.get('liquidity', 0)
                                if liquidity and liquidity >= 1000:
                                    print(f"  {shown+1}. {symbol_x}/{symbol_y}")
                                    print(f"     TVL: ${liquidity:,.0f}")
                                    print(f"     Price: {pool.get('current_price', 0)}")
                                    shown += 1
    
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(debug_meteora_data())
    except KeyboardInterrupt:
        print("\n👋 Debug stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")