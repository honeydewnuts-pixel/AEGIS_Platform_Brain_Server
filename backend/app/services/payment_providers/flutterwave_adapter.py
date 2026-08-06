"""
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : payment_providers/flutterwave_adapter.py

Flutterwave webhook verification is a simple equality check: the
'verif-hash' header must match the secret hash string YOU configure
in the Flutterwave dashboard (not an HMAC of the body).
Docs: https://developer.flutterwave.com/docs/integration-guides/webhooks
"""

from __future__ import annotations

import hmac
import json
import uuid
from datetime import datetime

import httpx

from app.config import settings
from app.core.logging import configure_logging
from app.services.payment_providers.base import (
    CheckoutSession,
    PaymentEvent,
    PaymentEventType,
    PaymentProviderAdapter,
)

FLUTTERWAVE_BASE_URL = "https://api.flutterwave.com/v3"

PLAN_AMOUNTS_NGN = {
    "monthly": 5000,   # adjust to your real pricing
}


class FlutterwaveAdapter(PaymentProviderAdapter):
    name = "flutterwave"

    def __init__(self) -> None:
        self.logger = configure_logging(__name__)
        self.secret_key = settings.FLUTTERWAVE_SECRET_KEY
        self.webhook_hash = settings.FLUTTERWAVE_WEBHOOK_HASH

    def verify_webhook_signature(self, raw_body: bytes, headers: dict[str, str]) -> bool:
        received = headers.get("verif-hash", "")
        return hmac.compare_digest(received, self.webhook_hash)

    def parse_webhook_event(self, raw_body: bytes) -> PaymentEvent:
        payload = json.loads(raw_body)
        event = payload.get("event", "")
        data = payload.get("data", {})
        meta = data.get("meta", {}) or {}
        status = (data.get("status") or "").lower()

        if event.startswith("charge.") and status == "successful":
            event_type = PaymentEventType.PAYMENT_SUCCEEDED
        elif event.startswith("charge.") and status in ("failed", "cancelled"):
            event_type = PaymentEventType.PAYMENT_FAILED
        elif "subscription" in event and "cancel" in event:
            event_type = PaymentEventType.SUBSCRIPTION_CANCELED
        else:
            event_type = PaymentEventType.UNKNOWN

        return PaymentEvent(
            provider=self.name,
            provider_event_id=str(data.get("id") or data.get("tx_ref") or uuid.uuid4()),
            event_type=event_type,
            account_id=meta.get("account_id", ""),
            provider_customer_id=(data.get("customer") or {}).get("id"),
            provider_subscription_id=data.get("plan"),
            current_period_end=None,   # Flutterwave doesn't send this in the charge webhook - track via subscription.get if needed
            raw_payload=payload,
        )

    async def create_checkout_session(self, account_id: str, email: str, plan: str) -> CheckoutSession:
        tx_ref = f"aegis-{account_id}-{uuid.uuid4().hex[:10]}"
        amount = PLAN_AMOUNTS_NGN.get(plan, PLAN_AMOUNTS_NGN["monthly"])

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{FLUTTERWAVE_BASE_URL}/payments",
                headers={"Authorization": f"Bearer {self.secret_key}"},
                json={
                    "tx_ref": tx_ref,
                    "amount": amount,
                    "currency": "NGN",
                    "redirect_url": "https://your-domain.example/subscription/callback",
                    "customer": {"email": email},
                    "meta": {"account_id": account_id, "plan": plan},
                },
                timeout=15,
            )
            resp.raise_for_status()
            body = resp.json()

        return CheckoutSession(
            checkout_url=body["data"]["link"],
            reference=tx_ref,
        )

    async def cancel_subscription(self, provider_subscription_id: str) -> bool:
        self.logger.warning(
            "FlutterwaveAdapter.cancel_subscription is a stub - Flutterwave's cancel "
            "endpoint needs the numeric subscription id, not the plan code stored here. "
            "Wire up subscription tracking from the initial charge response first."
        )
        return False
