"""
Webhook Notifications for Synapse A2A.

Provides push notifications when tasks complete.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Environment variables
ENV_WEBHOOK_SECRET = "SYNAPSE_WEBHOOK_SECRET"  # noqa: S105 (env var name)
ENV_WEBHOOK_TIMEOUT = "SYNAPSE_WEBHOOK_TIMEOUT"
ENV_WEBHOOK_MAX_RETRIES = "SYNAPSE_WEBHOOK_MAX_RETRIES"


@dataclass
class WebhookConfig:
    """Configuration for a webhook."""

    url: str
    events: list[str] = field(default_factory=lambda: ["task.completed", "task.failed"])
    secret: str | None = None
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WebhookEvent:
    """A webhook event to be delivered."""

    event_type: str
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class WebhookDelivery:
    """Record of a webhook delivery attempt."""

    webhook_url: str
    event: WebhookEvent
    status_code: int | None = None
    response_body: str | None = None
    error: str | None = None
    attempts: int = 0
    delivered_at: datetime | None = None
    success: bool = False


class WebhookRegistry:
    """Registry for managing webhooks."""

    def __init__(self) -> None:
        self._webhooks: dict[str, WebhookConfig] = {}
        self._deliveries: list[WebhookDelivery] = []

    def register(
        self,
        url: str,
        events: list[str] | None = None,
        secret: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WebhookConfig:
        """Register a new webhook."""
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid webhook URL: {url}")

        webhook = WebhookConfig(
            url=url,
            events=events or ["task.completed", "task.failed"],
            secret=secret or os.environ.get(ENV_WEBHOOK_SECRET),
            metadata=metadata or {},
        )

        self._webhooks[url] = webhook
        logger.info(f"Registered webhook: {url} for events: {webhook.events}")
        return webhook

    def unregister(self, url: str) -> bool:
        """Unregister a webhook."""
        if url in self._webhooks:
            del self._webhooks[url]
            logger.info(f"Unregistered webhook: {url}")
            return True
        return False

    def get(self, url: str) -> WebhookConfig | None:
        """Get a webhook by URL."""
        return self._webhooks.get(url)

    def list_webhooks(self) -> list[WebhookConfig]:
        """List all registered webhooks."""
        return list(self._webhooks.values())

    def get_webhooks_for_event(self, event_type: str) -> list[WebhookConfig]:
        """Get all webhooks subscribed to an event type."""
        return [
            w for w in self._webhooks.values() if w.enabled and event_type in w.events
        ]

    def add_delivery(self, delivery: WebhookDelivery) -> None:
        """Record a delivery attempt."""
        self._deliveries.append(delivery)
        # Keep only last 100 deliveries
        if len(self._deliveries) > 100:
            self._deliveries = self._deliveries[-100:]

    def get_recent_deliveries(self, limit: int = 20) -> list[WebhookDelivery]:
        """Get recent delivery attempts."""
        return self._deliveries[-limit:]


def compute_signature(payload: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature for webhook payload."""
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


async def deliver_webhook(
    webhook: WebhookConfig,
    event: WebhookEvent,
    max_retries: int = 3,
    timeout: float = 10.0,
    registry: WebhookRegistry | None = None,
) -> WebhookDelivery:
    """
    Deliver a webhook event to a URL.

    Args:
        webhook: Webhook configuration
        event: Event to deliver
        max_retries: Maximum retry attempts
        timeout: Request timeout in seconds
        registry: Optional registry to record delivery

    Returns:
        WebhookDelivery record
    """
    delivery = WebhookDelivery(
        webhook_url=webhook.url,
        event=event,
    )

    payload = {
        "event": event.event_type,
        "event_id": event.id,
        "timestamp": event.timestamp.isoformat(),
        "data": event.payload,
    }
    payload_json = json.dumps(payload)

    headers = {
        "Content-Type": "application/json",
        "X-Synapse-Event": event.event_type,
        "X-Synapse-Event-Id": event.id,
        "X-Synapse-Timestamp": event.timestamp.isoformat(),
    }

    # Add signature if secret is configured
    if webhook.secret:
        signature = compute_signature(payload_json, webhook.secret)
        headers["X-Synapse-Signature"] = f"sha256={signature}"

    # Retry with exponential backoff
    retry_delays = [1, 2, 4]  # seconds

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(max_retries):
            delivery.attempts = attempt + 1

            try:
                response = await client.post(
                    webhook.url,
                    content=payload_json,
                    headers=headers,
                )

                delivery.status_code = response.status_code
                delivery.response_body = response.text[:500]  # Truncate

                if 200 <= response.status_code < 300:
                    delivery.success = True
                    delivery.delivered_at = datetime.now(timezone.utc)
                    logger.info(
                        f"Webhook delivered: {webhook.url} ({event.event_type})"
                    )
                    break
                else:
                    logger.warning(
                        f"Webhook failed: {webhook.url} status={response.status_code}"
                    )

            except httpx.TimeoutException:
                delivery.error = "Request timed out"
                logger.warning(f"Webhook timeout: {webhook.url}")

            except httpx.RequestError as e:
                delivery.error = str(e)
                logger.warning(f"Webhook error: {webhook.url} - {e}")

            # Wait before retry (except on last attempt)
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delays[min(attempt, len(retry_delays) - 1)])

    if registry:
        registry.add_delivery(delivery)

    return delivery


async def dispatch_event(
    registry: WebhookRegistry,
    event_type: str,
    payload: dict[str, Any],
    max_retries: int = 3,
) -> list[WebhookDelivery]:
    """
    Dispatch an event to all subscribed webhooks.

    Args:
        registry: Webhook registry
        event_type: Type of event (e.g., "task.completed")
        payload: Event payload data
        max_retries: Maximum retry attempts per webhook

    Returns:
        List of delivery records
    """
    event = WebhookEvent(event_type=event_type, payload=payload)
    webhooks = registry.get_webhooks_for_event(event_type)

    if not webhooks:
        logger.debug(f"No webhooks registered for event: {event_type}")
        return []

    # Get config from environment
    timeout = float(os.environ.get(ENV_WEBHOOK_TIMEOUT, "10"))
    max_retries = int(os.environ.get(ENV_WEBHOOK_MAX_RETRIES, str(max_retries)))

    # Deliver to all webhooks concurrently
    tasks = [
        deliver_webhook(webhook, event, max_retries, timeout, registry)
        for webhook in webhooks
    ]

    # Use return_exceptions=True to ensure all webhooks are attempted
    # even if one fails
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions, keeping only successful deliveries, and log errors
    deliveries = []
    for r in results:
        if isinstance(r, WebhookDelivery):
            deliveries.append(r)
        elif isinstance(r, Exception):
            logger.error(
                f"Webhook delivery raised unexpected exception: {r}", exc_info=r
            )

    return deliveries


# Global registry instance
_webhook_registry: WebhookRegistry | None = None


def get_webhook_registry() -> WebhookRegistry:
    """Get the global webhook registry instance."""
    global _webhook_registry
    if _webhook_registry is None:
        _webhook_registry = WebhookRegistry()
    return _webhook_registry


def reset_webhook_registry() -> None:
    """Reset the global webhook registry (for testing)."""
    global _webhook_registry
    _webhook_registry = None
