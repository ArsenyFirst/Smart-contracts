"""
Jupiter RFQ Webhook Server

HTTP сервер для приема webhook уведомлений от Jupiter RFQ маркетмейкеров.
Этот endpoint нужно зарегистрировать у Jupiter для получения котировок.
"""

import asyncio
import json
import hmac
import hashlib
import time
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError
import uvicorn
import structlog
import os
from pathlib import Path

from rfq_monitoring_system import RFQMonitoringSystem, EventType, AlertLevel
from enhanced_rfq_arbitrage import EnhancedRFQArbitrageEngine
from enhanced_jupiter_client import JupiterConfig, APITier

logger = structlog.get_logger(__name__)

# Jupiter RFQ Webhook payload models
class JupiterRFQQuote(BaseModel):
    """Jupiter RFQ quote structure."""
    quote_id: str
    input_mint: str
    output_mint: str
    input_amount: str
    output_amount: str
    maker_address: str
    expires_at: int  # Unix timestamp
    fee_bps: Optional[int] = None
    slippage_bps: Optional[int] = None
    created_at: int
    signature: Optional[str] = None

class JupiterWebhookPayload(BaseModel):
    """Jupiter webhook payload structure."""
    event_type: str  # "rfq_quote_received", "rfq_quote_expired", etc.
    timestamp: int
    data: JupiterRFQQuote
    signature: Optional[str] = None

class JupiterWebhookServer:
    """HTTP сервер для приема Jupiter RFQ webhooks."""
    
    def __init__(self, 
                 host: str = "0.0.0.0",
                 port: int = 8080,
                 webhook_secret: Optional[str] = None,
                 enable_signature_verification: bool = True):
        self.host = host
        self.port = port
        self.webhook_secret = webhook_secret or os.getenv("JUPITER_WEBHOOK_SECRET")
        self.enable_signature_verification = enable_signature_verification
        
        # Инициализация компонентов
        self.monitoring = RFQMonitoringSystem(log_file_path="jupiter_webhooks.log")
        self.arbitrage_engine = None
        self.received_quotes = []
        self.stats = {
            "quotes_received": 0,
            "quotes_processed": 0,
            "quotes_expired": 0,
            "signature_failures": 0,
            "processing_errors": 0,
            "uptime_start": datetime.now()
        }
        
        # FastAPI app
        self.app = FastAPI(
            title="Jupiter RFQ Webhook Server",
            description="Webhook endpoint для приема RFQ котировок от Jupiter",
            version="1.0.0"
        )
        
        # CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        self._setup_routes()
    
    def _setup_routes(self):
        """Настройка маршрутов FastAPI."""
        
        @self.app.get("/")
        async def health_check():
            """Health check endpoint."""
            uptime_seconds = (datetime.now() - self.stats["uptime_start"]).total_seconds()
            return {
                "status": "healthy",
                "service": "Jupiter RFQ Webhook Server",
                "uptime_seconds": uptime_seconds,
                "stats": self.stats,
                "timestamp": datetime.now().isoformat()
            }
        
        @self.app.get("/stats")
        async def get_stats():
            """Статистика работы webhook сервера."""
            uptime_seconds = (datetime.now() - self.stats["uptime_start"]).total_seconds()
            
            return {
                "webhook_stats": self.stats,
                "uptime_hours": uptime_seconds / 3600,
                "recent_quotes": self.received_quotes[-10:],  # Последние 10 котировок
                "arbitrage_engine_status": "running" if self.arbitrage_engine else "stopped",
                "monitoring_active": self.monitoring.monitoring_active if hasattr(self.monitoring, 'monitoring_active') else False
            }
        
        @self.app.post("/webhook/jupiter/rfq")
        async def jupiter_rfq_webhook(
            request: Request,
            background_tasks: BackgroundTasks
        ):
            """
            Основной webhook endpoint для Jupiter RFQ.
            Этот URL нужно предоставить Jupiter для регистрации.
            """
            try:
                # Получаем raw body для проверки подписи
                body = await request.body()
                headers = dict(request.headers)
                
                logger.info(
                    "Received Jupiter RFQ webhook",
                    content_length=len(body),
                    headers=headers
                )
                
                # Проверка подписи (если включена)
                if self.enable_signature_verification and self.webhook_secret:
                    if not self._verify_signature(body, headers):
                        self.stats["signature_failures"] += 1
                        await self.monitoring.emit_event(
                            EventType.API_ERROR,
                            {"error": "Invalid webhook signature", "source": "jupiter_webhook"},
                            AlertLevel.ERROR
                        )
                        raise HTTPException(status_code=401, detail="Invalid signature")
                
                # Парсинг JSON payload
                try:
                    payload_data = json.loads(body.decode('utf-8'))
                    webhook_payload = JupiterWebhookPayload(**payload_data)
                except (json.JSONDecodeError, ValidationError) as e:
                    self.stats["processing_errors"] += 1
                    logger.error("Invalid webhook payload", error=str(e))
                    raise HTTPException(status_code=400, detail=f"Invalid payload: {str(e)}")
                
                # Обработка webhook в фоне
                background_tasks.add_task(
                    self._process_webhook_payload,
                    webhook_payload
                )
                
                self.stats["quotes_received"] += 1
                
                return {
                    "status": "received",
                    "quote_id": webhook_payload.data.quote_id,
                    "event_type": webhook_payload.event_type,
                    "timestamp": datetime.now().isoformat()
                }
                
            except HTTPException:
                raise
            except Exception as e:
                self.stats["processing_errors"] += 1
                logger.error("Webhook processing error", error=str(e))
                await self.monitoring.emit_event(
                    EventType.API_ERROR,
                    {"error": str(e), "source": "webhook_processing"},
                    AlertLevel.ERROR
                )
                raise HTTPException(status_code=500, detail="Internal server error")
        
        @self.app.post("/webhook/test")
        async def test_webhook():
            """Test endpoint для проверки webhook."""
            test_payload = {
                "event_type": "test",
                "timestamp": int(time.time()),
                "data": {
                    "quote_id": "test_quote_123",
                    "input_mint": "So11111111111111111111111111111111111111112",
                    "output_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    "input_amount": "100000000",
                    "output_amount": "14750000",
                    "maker_address": "test_maker_address",
                    "expires_at": int(time.time()) + 30,
                    "created_at": int(time.time())
                }
            }
            
            # Симулируем обработку тестового payload
            await self._process_webhook_payload(JupiterWebhookPayload(**test_payload))
            
            return {
                "status": "test_completed",
                "message": "Test webhook processed successfully"
            }
        
        @self.app.get("/webhook/config")
        async def get_webhook_config():
            """Конфигурация webhook для регистрации у Jupiter."""
            return {
                "webhook_url": f"http://{self.host}:{self.port}/webhook/jupiter/rfq",
                "supported_events": [
                    "rfq_quote_received",
                    "rfq_quote_updated", 
                    "rfq_quote_expired",
                    "rfq_quote_filled"
                ],
                "signature_verification": self.enable_signature_verification,
                "content_type": "application/json",
                "timeout_seconds": 30,
                "retry_policy": "exponential_backoff"
            }
    
    def _verify_signature(self, body: bytes, headers: Dict[str, str]) -> bool:
        """Проверка подписи webhook от Jupiter."""
        if not self.webhook_secret:
            return True
        
        signature_header = headers.get("x-jupiter-signature") or headers.get("x-webhook-signature")
        if not signature_header:
            return False
        
        # Вычисляем ожидаемую подпись
        expected_signature = hmac.new(
            self.webhook_secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()
        
        # Сравниваем подписи
        received_signature = signature_header.replace("sha256=", "")
        return hmac.compare_digest(expected_signature, received_signature)
    
    async def _process_webhook_payload(self, payload: JupiterWebhookPayload):
        """Обработка полученного webhook payload."""
        try:
            logger.info(
                "Processing Jupiter webhook",
                event_type=payload.event_type,
                quote_id=payload.data.quote_id,
                maker=payload.data.maker_address
            )
            
            # Сохраняем котировку
            quote_info = {
                "quote_id": payload.data.quote_id,
                "event_type": payload.event_type,
                "input_mint": payload.data.input_mint,
                "output_mint": payload.data.output_mint,
                "input_amount": int(payload.data.input_amount),
                "output_amount": int(payload.data.output_amount),
                "maker_address": payload.data.maker_address,
                "expires_at": payload.data.expires_at,
                "received_at": time.time(),
                "processed": False
            }
            
            self.received_quotes.append(quote_info)
            
            # Ограничиваем размер истории
            if len(self.received_quotes) > 1000:
                self.received_quotes = self.received_quotes[-500:]
            
            # Обработка по типу события
            if payload.event_type == "rfq_quote_received":
                await self._handle_new_quote(payload.data)
            elif payload.event_type == "rfq_quote_expired":
                await self._handle_quote_expired(payload.data)
            elif payload.event_type == "rfq_quote_filled":
                await self._handle_quote_filled(payload.data)
            
            # Отправляем событие в систему мониторинга
            await self.monitoring.emit_event(
                EventType.OPPORTUNITY_FOUND,
                {
                    "source": "jupiter_webhook",
                    "event_type": payload.event_type,
                    "quote_id": payload.data.quote_id,
                    "input_amount": int(payload.data.input_amount),
                    "output_amount": int(payload.data.output_amount),
                    "maker_address": payload.data.maker_address,
                    "expires_in_seconds": payload.data.expires_at - int(time.time())
                },
                AlertLevel.INFO
            )
            
            self.stats["quotes_processed"] += 1
            
            # Отмечаем как обработанную
            quote_info["processed"] = True
            
        except Exception as e:
            self.stats["processing_errors"] += 1
            logger.error("Error processing webhook payload", error=str(e))
            
            await self.monitoring.emit_event(
                EventType.API_ERROR,
                {
                    "error": str(e),
                    "source": "webhook_payload_processing",
                    "quote_id": payload.data.quote_id
                },
                AlertLevel.ERROR
            )
    
    async def _handle_new_quote(self, quote: JupiterRFQQuote):
        """Обработка новой котировки от маркетмейкера."""
        logger.info(
            "New RFQ quote received",
            quote_id=quote.quote_id,
            maker=quote.maker_address,
            expires_in=quote.expires_at - int(time.time())
        )
        
        # Здесь можно добавить логику анализа арбитража
        # с новой котировкой от маркетмейкера
        
        # Например, сравнить с текущими DEX ценами
        if self.arbitrage_engine:
            # Запустить анализ арбитража с новой RFQ котировкой
            pass
    
    async def _handle_quote_expired(self, quote: JupiterRFQQuote):
        """Обработка истекшей котировки."""
        logger.info("RFQ quote expired", quote_id=quote.quote_id)
        self.stats["quotes_expired"] += 1
    
    async def _handle_quote_filled(self, quote: JupiterRFQQuote):
        """Обработка исполненной котировки."""
        logger.info("RFQ quote filled", quote_id=quote.quote_id)
    
    async def start_server(self):
        """Запуск webhook сервера."""
        logger.info(f"Starting Jupiter RFQ webhook server on {self.host}:{self.port}")
        
        # Запуск системы мониторинга
        if hasattr(self.monitoring, 'start_health_monitoring'):
            health_task = asyncio.create_task(
                self.monitoring.start_health_monitoring(60)
            )
        
        # Настройка uvicorn
        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=True
        )
        
        server = uvicorn.Server(config)
        
        try:
            await server.serve()
        except KeyboardInterrupt:
            logger.info("Shutting down webhook server")
        finally:
            if 'health_task' in locals():
                health_task.cancel()
    
    def set_arbitrage_engine(self, engine: EnhancedRFQArbitrageEngine):
        """Подключение движка арбитража к webhook серверу."""
        self.arbitrage_engine = engine
        logger.info("Arbitrage engine connected to webhook server")


# Utility функции для развертывания
def create_nginx_config(domain: str, port: int = 8080) -> str:
    """Создание конфигурации Nginx для проксирования webhook."""
    return f"""
server {{
    listen 80;
    listen 443 ssl;
    server_name {domain};
    
    # SSL configuration (если используете HTTPS)
    # ssl_certificate /path/to/your/certificate.crt;
    # ssl_certificate_key /path/to/your/private.key;
    
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Увеличиваем таймауты для webhook
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }}
    
    location /webhook/ {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Специальные настройки для webhook
        proxy_buffering off;
        proxy_cache off;
    }}
}}
"""

def create_systemd_service(
    user: str = "jupiter",
    working_directory: str = "/opt/jupiter-rfq",
    python_path: str = "/opt/jupiter-rfq/venv/bin/python"
) -> str:
    """Создание systemd service для автозапуска."""
    return f"""
[Unit]
Description=Jupiter RFQ Webhook Server
After=network.target

[Service]
Type=simple
User={user}
WorkingDirectory={working_directory}
Environment=PATH={working_directory}/venv/bin
ExecStart={python_path} jupiter_webhook_server.py
Restart=always
RestartSec=5

# Логирование
StandardOutput=journal
StandardError=journal
SyslogIdentifier=jupiter-rfq-webhook

# Безопасность
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths={working_directory}

[Install]
WantedBy=multi-user.target
"""

def create_docker_compose() -> str:
    """Создание Docker Compose конфигурации."""
    return """
version: '3.8'

services:
  jupiter-webhook:
    build: .
    ports:
      - "8080:8080"
    environment:
      - JUPITER_WEBHOOK_SECRET=${JUPITER_WEBHOOK_SECRET}
      - SOLANA_RPC_URL=${SOLANA_RPC_URL}
      - SOLANA_PRIVATE_KEY=${SOLANA_PRIVATE_KEY}
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/"]
      interval: 30s
      timeout: 10s
      retries: 3

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - jupiter-webhook
    restart: unless-stopped
"""

# Запуск сервера
async def main():
    """Главная функция для запуска webhook сервера."""
    
    # Настройки из переменных окружения
    host = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.getenv("WEBHOOK_PORT", "8080"))
    webhook_secret = os.getenv("JUPITER_WEBHOOK_SECRET")
    
    # Создание и запуск сервера
    server = JupiterWebhookServer(
        host=host,
        port=port,
        webhook_secret=webhook_secret,
        enable_signature_verification=bool(webhook_secret)
    )
    
    # Опционально: подключение движка арбитража
    jupiter_config = JupiterConfig(
        api_key=os.getenv("JUPITER_API_KEY"),
        tier=APITier.PRO if os.getenv("JUPITER_API_KEY") else APITier.LITE,
        rate_limit_per_second=10,
        enable_caching=True
    )
    
    arbitrage_engine = EnhancedRFQArbitrageEngine(jupiter_config)
    server.set_arbitrage_engine(arbitrage_engine)
    
    await server.start_server()

if __name__ == "__main__":
    asyncio.run(main())