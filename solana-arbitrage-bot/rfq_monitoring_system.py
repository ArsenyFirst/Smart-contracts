"""
RFQ Monitoring & Webhook System

Advanced monitoring and notification system for Jupiter RFQ arbitrage with:
- Real-time performance metrics
- Webhook notifications for key events
- Dashboard-style monitoring
- Alert system for errors and opportunities
- Historical data tracking
"""

import asyncio
import time
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
import httpx
import structlog
import json
from collections import defaultdict, deque
from enum import Enum
import aiofiles
from pathlib import Path

logger = structlog.get_logger(__name__)


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventType(Enum):
    """Types of events in the system."""
    OPPORTUNITY_FOUND = "opportunity_found"
    TRADE_EXECUTED = "trade_executed"
    TRADE_FAILED = "trade_failed"
    API_ERROR = "api_error"
    RATE_LIMIT_HIT = "rate_limit_hit"
    PROFIT_REALIZED = "profit_realized"
    SYSTEM_HEALTH = "system_health"
    CONFIGURATION_CHANGED = "configuration_changed"


@dataclass
class ArbitrageEvent:
    """Event structure for arbitrage operations."""
    event_type: EventType
    timestamp: datetime
    alert_level: AlertLevel
    data: Dict[str, Any]
    event_id: str = field(default_factory=lambda: f"evt_{int(time.time() * 1000)}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "alert_level": self.alert_level.value,
            "data": self.data
        }


@dataclass 
class PerformanceMetrics:
    """Performance tracking metrics."""
    opportunities_detected: int = 0
    trades_executed: int = 0
    trades_successful: int = 0
    trades_failed: int = 0
    total_profit_usd: float = 0.0
    total_volume_usd: float = 0.0
    average_profit_bps: float = 0.0
    api_calls_made: int = 0
    api_errors: int = 0
    rate_limits_hit: int = 0
    average_response_time_ms: float = 0.0
    uptime_seconds: float = 0.0
    last_successful_trade: Optional[datetime] = None
    last_api_error: Optional[datetime] = None
    
    def success_rate(self) -> float:
        """Calculate trade success rate."""
        if self.trades_executed == 0:
            return 0.0
        return (self.trades_successful / self.trades_executed) * 100
    
    def api_reliability(self) -> float:
        """Calculate API reliability percentage."""
        if self.api_calls_made == 0:
            return 100.0
        return ((self.api_calls_made - self.api_errors) / self.api_calls_made) * 100


class WebhookManager:
    """Manager for webhook notifications."""
    
    def __init__(self):
        self.webhook_urls: List[str] = []
        self.webhook_configs: Dict[str, Dict[str, Any]] = {}
        self.failed_webhook_attempts = defaultdict(int)
        self.max_retry_attempts = 3
        
    def add_webhook(
        self,
        url: str,
        event_filters: Optional[List[EventType]] = None,
        alert_level_filter: Optional[AlertLevel] = None,
        custom_headers: Optional[Dict[str, str]] = None
    ):
        """Add webhook URL with optional filtering."""
        self.webhook_urls.append(url)
        self.webhook_configs[url] = {
            "event_filters": event_filters or list(EventType),
            "alert_level_filter": alert_level_filter,
            "custom_headers": custom_headers or {},
            "enabled": True
        }
        logger.info("Webhook added", url=url, filters=len(event_filters or []))
    
    async def send_notification(self, event: ArbitrageEvent):
        """Send event notification to all configured webhooks."""
        if not self.webhook_urls:
            return
        
        tasks = []
        for webhook_url in self.webhook_urls:
            if self._should_send_to_webhook(webhook_url, event):
                tasks.append(self._send_to_webhook(webhook_url, event))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    def _should_send_to_webhook(self, webhook_url: str, event: ArbitrageEvent) -> bool:
        """Check if event should be sent to specific webhook."""
        config = self.webhook_configs.get(webhook_url, {})
        
        if not config.get("enabled", True):
            return False
        
        # Check event type filter
        event_filters = config.get("event_filters", [])
        if event_filters and event.event_type not in event_filters:
            return False
        
        # Check alert level filter
        alert_filter = config.get("alert_level_filter")
        if alert_filter and event.alert_level != alert_filter:
            return False
        
        return True
    
    async def _send_to_webhook(self, webhook_url: str, event: ArbitrageEvent):
        """Send event to specific webhook with retry logic."""
        config = self.webhook_configs.get(webhook_url, {})
        custom_headers = config.get("custom_headers", {})
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Jupiter-RFQ-Monitor/1.0",
            **custom_headers
        }
        
        payload = {
            "webhook_version": "1.0",
            "source": "jupiter_rfq_arbitrage",
            "event": event.to_dict()
        }
        
        for attempt in range(self.max_retry_attempts):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        webhook_url,
                        json=payload,
                        headers=headers
                    )
                    
                    if response.status_code in [200, 201, 202]:
                        # Reset failed attempts on success
                        self.failed_webhook_attempts[webhook_url] = 0
                        logger.debug("Webhook notification sent", url=webhook_url, event_type=event.event_type.value)
                        return
                    else:
                        logger.warning(
                            "Webhook responded with error",
                            url=webhook_url,
                            status=response.status_code,
                            attempt=attempt + 1
                        )
                        
            except Exception as e:
                logger.error(
                    "Webhook notification failed",
                    url=webhook_url,
                    error=str(e),
                    attempt=attempt + 1
                )
            
            # Exponential backoff
            if attempt < self.max_retry_attempts - 1:
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
        
        # Mark webhook as problematic after max retries
        self.failed_webhook_attempts[webhook_url] += 1
        if self.failed_webhook_attempts[webhook_url] >= 5:
            logger.error("Webhook disabled due to repeated failures", url=webhook_url)
            self.webhook_configs[webhook_url]["enabled"] = False


class MetricsCollector:
    """Collector for system metrics and analytics."""
    
    def __init__(self, max_history_items: int = 1000):
        self.metrics = PerformanceMetrics()
        self.start_time = datetime.now()
        self.max_history_items = max_history_items
        
        # Time-series data
        self.response_times = deque(maxlen=max_history_items)
        self.profit_history = deque(maxlen=max_history_items)
        self.volume_history = deque(maxlen=max_history_items)
        self.opportunity_timeline = deque(maxlen=max_history_items)
        
        # Error tracking
        self.recent_errors = deque(maxlen=100)
        self.error_counts = defaultdict(int)
    
    def record_opportunity(self, opportunity_data: Dict[str, Any]):
        """Record detected arbitrage opportunity."""
        self.metrics.opportunities_detected += 1
        self.opportunity_timeline.append({
            "timestamp": datetime.now().isoformat(),
            "profit_bps": opportunity_data.get("profit_bps", 0),
            "volume_usd": opportunity_data.get("volume_usd", 0),
            "token_pair": opportunity_data.get("token_pair", "unknown")
        })
    
    def record_trade_execution(self, success: bool, profit_usd: float = 0, volume_usd: float = 0):
        """Record trade execution result."""
        self.metrics.trades_executed += 1
        
        if success:
            self.metrics.trades_successful += 1
            self.metrics.total_profit_usd += profit_usd
            self.metrics.last_successful_trade = datetime.now()
            
            self.profit_history.append({
                "timestamp": datetime.now().isoformat(),
                "profit_usd": profit_usd
            })
        else:
            self.metrics.trades_failed += 1
        
        self.metrics.total_volume_usd += volume_usd
        self.volume_history.append({
            "timestamp": datetime.now().isoformat(),
            "volume_usd": volume_usd
        })
        
        # Update average profit
        if self.metrics.trades_successful > 0:
            total_profitable_volume = sum(p["profit_usd"] for p in self.profit_history)
            self.metrics.average_profit_bps = (total_profitable_volume / self.metrics.total_volume_usd) * 10000
    
    def record_api_call(self, success: bool, response_time_ms: float):
        """Record API call metrics."""
        self.metrics.api_calls_made += 1
        
        if not success:
            self.metrics.api_errors += 1
            self.metrics.last_api_error = datetime.now()
        
        self.response_times.append({
            "timestamp": datetime.now().isoformat(),
            "response_time_ms": response_time_ms
        })
        
        # Update average response time
        if self.response_times:
            total_time = sum(r["response_time_ms"] for r in self.response_times)
            self.metrics.average_response_time_ms = total_time / len(self.response_times)
    
    def record_rate_limit(self):
        """Record rate limit hit."""
        self.metrics.rate_limits_hit += 1
    
    def record_error(self, error_type: str, error_message: str):
        """Record system error."""
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": error_type,
            "message": error_message
        }
        self.recent_errors.append(error_entry)
        self.error_counts[error_type] += 1
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current system metrics."""
        self.metrics.uptime_seconds = (datetime.now() - self.start_time).total_seconds()
        
        return {
            "performance": asdict(self.metrics),
            "recent_opportunities": list(self.opportunity_timeline)[-10:],
            "recent_profits": list(self.profit_history)[-10:],
            "recent_errors": list(self.recent_errors)[-5:],
            "error_summary": dict(self.error_counts),
            "health_status": self._calculate_health_status()
        }
    
    def _calculate_health_status(self) -> Dict[str, Any]:
        """Calculate overall system health status."""
        # API health
        api_health = "good"
        if self.metrics.api_reliability() < 95:
            api_health = "degraded"
        elif self.metrics.api_reliability() < 90:
            api_health = "poor"
        
        # Trading health
        trading_health = "good"
        if self.metrics.success_rate() < 80:
            trading_health = "degraded"
        elif self.metrics.success_rate() < 60:
            trading_health = "poor"
        
        # Recent activity check
        recent_activity = "active"
        if self.metrics.last_successful_trade:
            time_since_last_trade = (datetime.now() - self.metrics.last_successful_trade).total_seconds()
            if time_since_last_trade > 3600:  # 1 hour
                recent_activity = "inactive"
        
        return {
            "overall": "healthy" if all(h == "good" for h in [api_health, trading_health]) and recent_activity == "active" else "degraded",
            "api_health": api_health,
            "trading_health": trading_health,
            "recent_activity": recent_activity,
            "uptime_hours": self.metrics.uptime_seconds / 3600
        }


class RFQMonitoringSystem:
    """Complete monitoring system for RFQ arbitrage operations."""
    
    def __init__(self, log_file_path: Optional[str] = None):
        self.webhook_manager = WebhookManager()
        self.metrics_collector = MetricsCollector()
        self.event_handlers: Dict[EventType, List[Callable]] = defaultdict(list)
        self.log_file_path = Path(log_file_path) if log_file_path else None
        self.monitoring_active = False
        
        # Setup default handlers
        self._setup_default_handlers()
    
    def _setup_default_handlers(self):
        """Setup default event handlers."""
        
        @self.on_event(EventType.OPPORTUNITY_FOUND)
        async def handle_opportunity(event_data):
            self.metrics_collector.record_opportunity(event_data)
        
        @self.on_event(EventType.TRADE_EXECUTED)
        async def handle_trade_executed(event_data):
            success = event_data.get("success", False)
            profit = event_data.get("profit_usd", 0)
            volume = event_data.get("volume_usd", 0)
            self.metrics_collector.record_trade_execution(success, profit, volume)
        
        @self.on_event(EventType.API_ERROR)
        async def handle_api_error(event_data):
            response_time = event_data.get("response_time_ms", 0)
            self.metrics_collector.record_api_call(False, response_time)
            self.metrics_collector.record_error("api_error", event_data.get("error", "Unknown API error"))
        
        @self.on_event(EventType.RATE_LIMIT_HIT)
        async def handle_rate_limit(event_data):
            self.metrics_collector.record_rate_limit()
    
    def on_event(self, event_type: EventType):
        """Decorator for registering event handlers."""
        def decorator(func: Callable):
            self.event_handlers[event_type].append(func)
            return func
        return decorator
    
    async def emit_event(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        alert_level: AlertLevel = AlertLevel.INFO
    ):
        """Emit event through the monitoring system."""
        event = ArbitrageEvent(
            event_type=event_type,
            timestamp=datetime.now(),
            alert_level=alert_level,
            data=data
        )
        
        # Log to file if configured
        if self.log_file_path:
            await self._log_event_to_file(event)
        
        # Execute registered handlers
        handlers = self.event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error("Event handler error", event_type=event_type.value, error=str(e))
        
        # Send webhook notifications
        await self.webhook_manager.send_notification(event)
        
        logger.info("Event emitted", event_type=event_type.value, alert_level=alert_level.value)
    
    async def _log_event_to_file(self, event: ArbitrageEvent):
        """Log event to file asynchronously."""
        try:
            log_entry = json.dumps(event.to_dict()) + "\n"
            async with aiofiles.open(self.log_file_path, mode="a") as f:
                await f.write(log_entry)
        except Exception as e:
            logger.error("Failed to log event to file", error=str(e))
    
    def add_webhook(self, url: str, **kwargs):
        """Add webhook URL to the system."""
        self.webhook_manager.add_webhook(url, **kwargs)
    
    async def start_health_monitoring(self, interval_seconds: int = 60):
        """Start periodic health monitoring."""
        self.monitoring_active = True
        
        while self.monitoring_active:
            try:
                metrics = self.metrics_collector.get_current_metrics()
                health_status = metrics["health_status"]
                
                # Emit health event
                await self.emit_event(
                    EventType.SYSTEM_HEALTH,
                    {
                        "health_status": health_status,
                        "metrics_summary": {
                            "trades_executed": metrics["performance"]["trades_executed"],
                            "success_rate": metrics["performance"]["success_rate"](),
                            "total_profit_usd": metrics["performance"]["total_profit_usd"],
                            "api_reliability": metrics["performance"]["api_reliability"]()
                        }
                    },
                    AlertLevel.INFO if health_status["overall"] == "healthy" else AlertLevel.WARNING
                )
                
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error("Health monitoring error", error=str(e))
                await asyncio.sleep(interval_seconds)
    
    def stop_health_monitoring(self):
        """Stop health monitoring."""
        self.monitoring_active = False
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive dashboard data."""
        return {
            "timestamp": datetime.now().isoformat(),
            "system_metrics": self.metrics_collector.get_current_metrics(),
            "webhook_status": {
                "active_webhooks": len([url for url, config in self.webhook_manager.webhook_configs.items() if config.get("enabled", True)]),
                "total_webhooks": len(self.webhook_manager.webhook_urls),
                "failed_webhooks": len([url for url, count in self.webhook_manager.failed_webhook_attempts.items() if count > 0])
            },
            "monitoring_status": {
                "active": self.monitoring_active,
                "log_file": str(self.log_file_path) if self.log_file_path else None
            }
        }


# Example usage and testing
async def test_monitoring_system():
    """Test the monitoring system."""
    
    # Initialize monitoring system
    monitor = RFQMonitoringSystem(log_file_path="arbitrage_events.log")
    
    # Add a test webhook (replace with real URL)
    # monitor.add_webhook(
    #     "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK",
    #     event_filters=[EventType.OPPORTUNITY_FOUND, EventType.TRADE_EXECUTED],
    #     alert_level_filter=AlertLevel.INFO
    # )
    
    # Start health monitoring in background
    health_task = asyncio.create_task(monitor.start_health_monitoring(30))
    
    # Simulate some events
    await monitor.emit_event(
        EventType.OPPORTUNITY_FOUND,
        {
            "token_pair": "SOL/USDC",
            "profit_bps": 25,
            "volume_usd": 1000,
            "arbitrage_type": "buy_rfq_sell_dex"
        },
        AlertLevel.INFO
    )
    
    await monitor.emit_event(
        EventType.TRADE_EXECUTED,
        {
            "success": True,
            "profit_usd": 2.50,
            "volume_usd": 1000,
            "execution_time_ms": 1200
        },
        AlertLevel.INFO
    )
    
    await monitor.emit_event(
        EventType.API_ERROR,
        {
            "error": "Rate limit exceeded",
            "status_code": 429,
            "response_time_ms": 500
        },
        AlertLevel.WARNING
    )
    
    # Wait a bit for events to process
    await asyncio.sleep(2)
    
    # Get dashboard data
    dashboard = monitor.get_dashboard_data()
    print(json.dumps(dashboard, indent=2, default=str))
    
    # Stop monitoring
    monitor.stop_health_monitoring()
    health_task.cancel()


if __name__ == "__main__":
    asyncio.run(test_monitoring_system())