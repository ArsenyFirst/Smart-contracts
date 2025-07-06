#!/usr/bin/env python3
"""
Test script for Jupiter RFQ Webhook System

Этот скрипт тестирует все компоненты webhook системы:
- Health check endpoint
- Webhook endpoints
- Signature verification
- Integration testing
"""

import asyncio
import aiohttp
import json
import time
import hmac
import hashlib
from typing import Dict, Any, Optional
import sys
import argparse
from datetime import datetime

class WebhookSystemTester:
    """Тестер для webhook системы Jupiter RFQ."""
    
    def __init__(self, base_url: str, webhook_secret: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.webhook_secret = webhook_secret
        self.results = {
            "health_check": False,
            "stats_endpoint": False,
            "webhook_config": False,
            "webhook_test": False,
            "signature_verification": False,
            "load_test": False,
            "errors": []
        }
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Запуск всех тестов."""
        print("🚀 Запуск тестирования Jupiter RFQ Webhook System")
        print(f"🌐 Base URL: {self.base_url}")
        print("=" * 60)
        
        async with aiohttp.ClientSession() as session:
            await self.test_health_check(session)
            await self.test_stats_endpoint(session)
            await self.test_webhook_config(session)
            await self.test_webhook_test(session)
            
            if self.webhook_secret:
                await self.test_signature_verification(session)
            
            await self.test_load_testing(session)
        
        self.print_results()
        return self.results
    
    async def test_health_check(self, session: aiohttp.ClientSession):
        """Тест health check endpoint."""
        print("🏥 Тестирование health check endpoint...")
        
        try:
            async with session.get(f"{self.base_url}/") as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "healthy":
                        self.results["health_check"] = True
                        print("✅ Health check прошел успешно")
                        print(f"   Uptime: {data.get('uptime_seconds', 0):.1f} секунд")
                        return
                    
                print(f"❌ Health check вернул неожиданный ответ: {data}")
                
        except Exception as e:
            error_msg = f"Health check endpoint недоступен: {str(e)}"
            print(f"❌ {error_msg}")
            self.results["errors"].append(error_msg)
    
    async def test_stats_endpoint(self, session: aiohttp.ClientSession):
        """Тест stats endpoint."""
        print("📊 Тестирование stats endpoint...")
        
        try:
            async with session.get(f"{self.base_url}/stats") as response:
                if response.status == 200:
                    data = await response.json()
                    if "webhook_stats" in data:
                        self.results["stats_endpoint"] = True
                        print("✅ Stats endpoint работает")
                        
                        stats = data["webhook_stats"]
                        print(f"   Котировок получено: {stats.get('quotes_received', 0)}")
                        print(f"   Котировок обработано: {stats.get('quotes_processed', 0)}")
                        print(f"   Ошибок обработки: {stats.get('processing_errors', 0)}")
                        return
                    
                print(f"❌ Stats endpoint вернул неожиданную структуру: {data}")
                
        except Exception as e:
            error_msg = f"Stats endpoint недоступен: {str(e)}"
            print(f"❌ {error_msg}")
            self.results["errors"].append(error_msg)
    
    async def test_webhook_config(self, session: aiohttp.ClientSession):
        """Тест webhook config endpoint."""
        print("⚙️ Тестирование webhook config endpoint...")
        
        try:
            async with session.get(f"{self.base_url}/webhook/config") as response:
                if response.status == 200:
                    data = await response.json()
                    if "webhook_url" in data and "supported_events" in data:
                        self.results["webhook_config"] = True
                        print("✅ Webhook config endpoint работает")
                        print(f"   Webhook URL: {data.get('webhook_url')}")
                        print(f"   Поддерживаемые события: {len(data.get('supported_events', []))}")
                        print(f"   Верификация подписи: {data.get('signature_verification', False)}")
                        return
                    
                print(f"❌ Webhook config вернул неожиданную структуру: {data}")
                
        except Exception as e:
            error_msg = f"Webhook config endpoint недоступен: {str(e)}"
            print(f"❌ {error_msg}")
            self.results["errors"].append(error_msg)
    
    async def test_webhook_test(self, session: aiohttp.ClientSession):
        """Тест webhook test endpoint."""
        print("🧪 Тестирование webhook test endpoint...")
        
        try:
            async with session.post(f"{self.base_url}/webhook/test") as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "test_completed":
                        self.results["webhook_test"] = True
                        print("✅ Webhook test endpoint работает")
                        print(f"   Сообщение: {data.get('message')}")
                        return
                    
                print(f"❌ Webhook test вернул неожиданный ответ: {data}")
                
        except Exception as e:
            error_msg = f"Webhook test endpoint недоступен: {str(e)}"
            print(f"❌ {error_msg}")
            self.results["errors"].append(error_msg)
    
    async def test_signature_verification(self, session: aiohttp.ClientSession):
        """Тест верификации подписи webhook."""
        print("🔐 Тестирование верификации подписи...")
        
        # Создаем тестовый payload
        test_payload = {
            "event_type": "rfq_quote_received",
            "timestamp": int(time.time()),
            "data": {
                "quote_id": "test_signature_verification",
                "input_mint": "So11111111111111111111111111111111111111112",
                "output_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "input_amount": "100000000",
                "output_amount": "14750000",
                "maker_address": "test_maker_signature",
                "expires_at": int(time.time()) + 30,
                "created_at": int(time.time())
            }
        }
        
        payload_json = json.dumps(test_payload)
        
        # Создаем правильную подпись
        signature = hmac.new(
            self.webhook_secret.encode('utf-8'),
            payload_json.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            'Content-Type': 'application/json',
            'X-Jupiter-Signature': f'sha256={signature}'
        }
        
        try:
            # Тест с правильной подписью
            async with session.post(
                f"{self.base_url}/webhook/jupiter/rfq",
                data=payload_json,
                headers=headers
            ) as response:
                if response.status == 200:
                    print("✅ Верификация подписи работает (правильная подпись)")
                    
                    # Тест с неправильной подписью
                    wrong_headers = headers.copy()
                    wrong_headers['X-Jupiter-Signature'] = 'sha256=wrong_signature'
                    
                    async with session.post(
                        f"{self.base_url}/webhook/jupiter/rfq",
                        data=payload_json,
                        headers=wrong_headers
                    ) as wrong_response:
                        if wrong_response.status == 401:
                            self.results["signature_verification"] = True
                            print("✅ Верификация подписи корректно отклоняет неправильные подписи")
                        else:
                            print(f"❌ Неправильная подпись не была отклонена (status: {wrong_response.status})")
                else:
                    print(f"❌ Webhook с правильной подписью вернул статус: {response.status}")
                    
        except Exception as e:
            error_msg = f"Ошибка при тестировании верификации подписи: {str(e)}"
            print(f"❌ {error_msg}")
            self.results["errors"].append(error_msg)
    
    async def test_load_testing(self, session: aiohttp.ClientSession):
        """Простой нагрузочный тест."""
        print("🚀 Проведение нагрузочного тестирования...")
        
        async def single_request():
            try:
                async with session.get(f"{self.base_url}/") as response:
                    return response.status == 200
            except:
                return False
        
        # Запускаем 20 параллельных запросов
        start_time = time.time()
        tasks = [single_request() for _ in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()
        
        successful_requests = sum(1 for r in results if r is True)
        total_time = end_time - start_time
        
        if successful_requests >= 18:  # 90% успешных запросов
            self.results["load_test"] = True
            print(f"✅ Нагрузочный тест прошел успешно")
            print(f"   Успешных запросов: {successful_requests}/20")
            print(f"   Время выполнения: {total_time:.2f} секунд")
            print(f"   RPS: {20/total_time:.1f}")
        else:
            print(f"❌ Нагрузочный тест не прошел")
            print(f"   Успешных запросов: {successful_requests}/20")
    
    def print_results(self):
        """Вывод итоговых результатов."""
        print("\n" + "=" * 60)
        print("📋 ИТОГОВЫЕ РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
        print("=" * 60)
        
        total_tests = len([k for k in self.results.keys() if k != "errors"])
        passed_tests = sum(1 for k, v in self.results.items() if k != "errors" and v)
        
        print(f"🎯 Пройдено тестов: {passed_tests}/{total_tests}")
        print(f"📊 Процент успеха: {(passed_tests/total_tests)*100:.1f}%")
        
        print("\n📝 Детальные результаты:")
        test_names = {
            "health_check": "Health Check Endpoint",
            "stats_endpoint": "Stats Endpoint", 
            "webhook_config": "Webhook Config Endpoint",
            "webhook_test": "Webhook Test Endpoint",
            "signature_verification": "Signature Verification",
            "load_test": "Load Testing"
        }
        
        for key, name in test_names.items():
            status = "✅ ПРОШЕЛ" if self.results[key] else "❌ НЕ ПРОШЕЛ"
            print(f"   {name}: {status}")
        
        if self.results["errors"]:
            print("\n🔴 Ошибки:")
            for error in self.results["errors"]:
                print(f"   - {error}")
        
        print("\n" + "=" * 60)
        
        if passed_tests == total_tests:
            print("🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
            print("✅ Система готова к регистрации у Jupiter")
        else:
            print("⚠️ Некоторые тесты не прошли")
            print("🔧 Проверьте конфигурацию и исправьте ошибки")
        
        print("=" * 60)

async def main():
    """Главная функция."""
    parser = argparse.ArgumentParser(description="Test Jupiter RFQ Webhook System")
    parser.add_argument("--url", default="http://localhost:8080", 
                       help="Base URL webhook сервера")
    parser.add_argument("--secret", 
                       help="Webhook secret для тестирования подписи")
    parser.add_argument("--timeout", type=int, default=30,
                       help="Таймаут для HTTP запросов")
    
    args = parser.parse_args()
    
    print("🧪 Jupiter RFQ Webhook System Tester")
    print(f"📅 Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    tester = WebhookSystemTester(args.url, args.secret)
    
    try:
        results = await tester.run_all_tests()
        
        # Возвращаем код ошибки если не все тесты прошли
        total_tests = len([k for k in results.keys() if k != "errors"])
        passed_tests = sum(1 for k, v in results.items() if k != "errors" and v)
        
        if passed_tests == total_tests:
            print("\n🎊 Готово к production!")
            sys.exit(0)
        else:
            print(f"\n⚠️ Требуется доработка ({passed_tests}/{total_tests} тестов прошли)")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⏹️ Тестирование прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Критическая ошибка: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())