"""Tests for webhook notifications module."""

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest

from synapse.webhooks import (
    WebhookConfig,
    WebhookDelivery,
    WebhookEvent,
    WebhookRegistry,
    compute_signature,
    deliver_webhook,
    dispatch_event,
    get_webhook_registry,
    reset_webhook_registry,
)


def run_async(coro):
    """Helper to run async functions in sync tests."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset webhook registry before each test."""
    reset_webhook_registry()
    yield
    reset_webhook_registry()


class TestWebhookConfig:
    """Tests for WebhookConfig dataclass."""

    def test_default_events(self):
        config = WebhookConfig(url="https://example.com/hook")
        assert "task.completed" in config.events
        assert "task.failed" in config.events

    def test_custom_events(self):
        config = WebhookConfig(
            url="https://example.com/hook", events=["task.completed"]
        )
        assert config.events == ["task.completed"]

    def test_enabled_by_default(self):
        config = WebhookConfig(url="https://example.com/hook")
        assert config.enabled is True


class TestWebhookRegistry:
    """Tests for WebhookRegistry."""

    def test_register_webhook(self):
        registry = WebhookRegistry()
        webhook = registry.register("https://example.com/hook")

        assert webhook.url == "https://example.com/hook"
        assert webhook.enabled is True

    def test_register_with_events(self):
        registry = WebhookRegistry()
        webhook = registry.register(
            "https://example.com/hook", events=["task.completed"]
        )

        assert webhook.events == ["task.completed"]

    def test_register_invalid_url_raises(self):
        registry = WebhookRegistry()

        with pytest.raises(ValueError):
            registry.register("not-a-url")

    def test_unregister_webhook(self):
        registry = WebhookRegistry()
        registry.register("https://example.com/hook")

        assert registry.unregister("https://example.com/hook") is True
        assert registry.get("https://example.com/hook") is None

    def test_unregister_nonexistent(self):
        registry = WebhookRegistry()
        assert registry.unregister("https://example.com/hook") is False

    def test_list_webhooks(self):
        registry = WebhookRegistry()
        registry.register("https://example.com/hook1")
        registry.register("https://example.com/hook2")

        webhooks = registry.list_webhooks()
        assert len(webhooks) == 2

    def test_get_webhooks_for_event(self):
        registry = WebhookRegistry()
        registry.register("https://example.com/hook1", events=["task.completed"])
        registry.register("https://example.com/hook2", events=["task.failed"])

        completed_hooks = registry.get_webhooks_for_event("task.completed")
        assert len(completed_hooks) == 1
        assert completed_hooks[0].url == "https://example.com/hook1"

    def test_disabled_webhook_not_returned(self):
        registry = WebhookRegistry()
        webhook = registry.register("https://example.com/hook")
        webhook.enabled = False

        assert len(registry.get_webhooks_for_event("task.completed")) == 0


class TestComputeSignature:
    """Tests for signature computation."""

    def test_signature_is_hex_string(self):
        sig = compute_signature('{"test": true}', "secret")
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA-256 hex

    def test_signature_deterministic(self):
        payload = '{"task_id": "123"}'
        secret = "my-secret"
        assert compute_signature(payload, secret) == compute_signature(payload, secret)

    def test_different_secrets_different_signatures(self):
        payload = '{"task_id": "123"}'
        sig1 = compute_signature(payload, "secret1")
        sig2 = compute_signature(payload, "secret2")
        assert sig1 != sig2


class TestDeliverWebhook:
    """Tests for webhook delivery."""

    def test_successful_delivery(self):
        webhook = WebhookConfig(url="https://example.com/hook")
        event = WebhookEvent(event_type="task.completed", payload={"task_id": "123"})

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_post.return_value = mock_response

            delivery = run_async(deliver_webhook(webhook, event))

            assert delivery.success is True
            assert delivery.status_code == 200
            assert delivery.attempts == 1

    def test_failed_delivery_retries(self):
        webhook = WebhookConfig(url="https://example.com/hook")
        event = WebhookEvent(event_type="task.completed", payload={"task_id": "123"})

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Server Error"
            mock_post.return_value = mock_response

            delivery = run_async(deliver_webhook(webhook, event, max_retries=3))

            assert delivery.success is False
            assert delivery.status_code == 500
            assert delivery.attempts == 3

    def test_timeout_error(self):
        webhook = WebhookConfig(url="https://example.com/hook")
        event = WebhookEvent(event_type="task.completed", payload={"task_id": "123"})

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Timeout")

            delivery = run_async(deliver_webhook(webhook, event, max_retries=1))

            assert delivery.success is False
            assert delivery.error == "Request timed out"

    def test_includes_signature_when_secret_set(self):
        webhook = WebhookConfig(url="https://example.com/hook", secret="my-secret")
        event = WebhookEvent(event_type="task.completed", payload={"task_id": "123"})

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_post.return_value = mock_response

            run_async(deliver_webhook(webhook, event))

            # Check that signature header was included
            call_args = mock_post.call_args
            headers = call_args.kwargs["headers"]
            assert "X-Synapse-Signature" in headers
            assert headers["X-Synapse-Signature"].startswith("sha256=")


class TestDispatchEvent:
    """Tests for event dispatching."""

    def test_dispatch_to_subscribed_webhooks(self):
        registry = WebhookRegistry()
        registry.register("https://example.com/hook1", events=["task.completed"])
        registry.register("https://example.com/hook2", events=["task.completed"])

        with patch("synapse.webhooks.deliver_webhook") as mock_deliver:
            mock_deliver.return_value = WebhookDelivery(
                webhook_url="",
                event=WebhookEvent(event_type="task.completed", payload={}),
                success=True,
            )

            deliveries = run_async(
                dispatch_event(registry, "task.completed", {"task_id": "123"})
            )

            assert len(deliveries) == 2
            assert mock_deliver.call_count == 2

    def test_dispatch_only_to_matching_events(self):
        registry = WebhookRegistry()
        registry.register("https://example.com/hook1", events=["task.completed"])
        registry.register("https://example.com/hook2", events=["task.failed"])

        with patch("synapse.webhooks.deliver_webhook") as mock_deliver:
            mock_deliver.return_value = WebhookDelivery(
                webhook_url="",
                event=WebhookEvent(event_type="task.completed", payload={}),
                success=True,
            )

            deliveries = run_async(
                dispatch_event(registry, "task.completed", {"task_id": "123"})
            )

            assert len(deliveries) == 1

    def test_dispatch_no_webhooks(self):
        registry = WebhookRegistry()

        deliveries = run_async(
            dispatch_event(registry, "task.completed", {"task_id": "123"})
        )

        assert len(deliveries) == 0


class TestGlobalRegistry:
    """Tests for global registry functions."""

    def test_get_webhook_registry_singleton(self):
        registry1 = get_webhook_registry()
        registry2 = get_webhook_registry()
        assert registry1 is registry2

    def test_reset_webhook_registry(self):
        registry1 = get_webhook_registry()
        registry1.register("https://example.com/hook")

        reset_webhook_registry()

        registry2 = get_webhook_registry()
        assert len(registry2.list_webhooks()) == 0


class TestDeliveryRecording:
    """Tests for delivery recording."""

    def test_add_delivery(self):
        registry = WebhookRegistry()
        event = WebhookEvent(event_type="task.completed", payload={})
        delivery = WebhookDelivery(
            webhook_url="https://example.com/hook", event=event, success=True
        )

        registry.add_delivery(delivery)
        recent = registry.get_recent_deliveries()

        assert len(recent) == 1
        assert recent[0].success is True

    def test_delivery_limit(self):
        registry = WebhookRegistry()
        event = WebhookEvent(event_type="task.completed", payload={})

        # Add more than 100 deliveries
        for i in range(120):
            delivery = WebhookDelivery(
                webhook_url=f"https://example.com/hook{i}", event=event, success=True
            )
            registry.add_delivery(delivery)

        # Should keep only last 100
        recent = registry.get_recent_deliveries(limit=200)
        assert len(recent) == 100
