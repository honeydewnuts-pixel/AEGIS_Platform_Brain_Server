"""
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : subscription_router.py
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

from app.security import verify_api_key, require_account_match, require_admin, AuthContext
from app.services.payment_providers.paystack_adapter import PaystackAdapter
from app.services.payment_providers.flutterwave_adapter import FlutterwaveAdapter
from app.services.payment_providers.stripe_adapter import StripeAdapter

router = APIRouter(prefix="/api/subscriptions", tags=["Subscriptions"])

ADAPTERS = {
    "paystack": PaystackAdapter,
    "flutterwave": FlutterwaveAdapter,
    "stripe": StripeAdapter,
}


class CheckoutRequest(BaseModel):
    account_id: str
    email: EmailStr
    plan: str = "monthly"


def get_subscription_service(request: Request):
    return request.app.state.subscription_service


@router.post("/checkout/{provider}")
async def create_checkout(provider: str, request: CheckoutRequest):
    """
    Deliberately NOT behind verify_api_key: a brand-new subscriber has no
    AEGIS API key yet (keys are issued on first successful activation -
    see SubscriptionService.apply_event), so there's nothing to check them
    against at this point in the flow. This just creates a payment
    provider checkout session/URL - no AEGIS account data is exposed by
    letting an anonymous caller do that.

    GAP: no rate limiting exists anywhere in this codebase yet. This
    endpoint is the one most exposed to abuse (someone could spam-create
    checkout sessions) - add rate limiting (e.g. slowapi, or your reverse
    proxy's) before this is public on the open internet.
    """
    adapter_cls = ADAPTERS.get(provider)
    if adapter_cls is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    adapter = adapter_cls()
    session = await adapter.create_checkout_session(request.account_id, request.email, request.plan)
    return {"checkout_url": session.checkout_url, "reference": session.reference}


@router.post("/webhook/{provider}")
async def receive_webhook(provider: str, request: Request):
    """
    No verify_api_key here either - these are called by the payment
    provider, not your clients. Authenticity is established by the
    provider-specific signature check instead (see each adapter's
    verify_webhook_signature).
    """
    adapter_cls = ADAPTERS.get(provider)
    if adapter_cls is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    adapter = adapter_cls()
    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    if not adapter.verify_webhook_signature(raw_body, headers):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")

    event = adapter.parse_webhook_event(raw_body)

    subscription_service = request.app.state.subscription_service
    if await subscription_service.already_processed(event.provider, event.provider_event_id):
        return {"status": "already_processed"}

    await subscription_service.apply_event(event)

    # If payment failed or subscription was canceled, immediately try to
    # disconnect any live MT5 worker rather than waiting for the next
    # background sweep cycle.
    if event.account_id and event.event_type.name in ("PAYMENT_FAILED", "SUBSCRIPTION_CANCELED"):
        worker_pool = request.app.state.worker_pool
        if await worker_pool.is_running(event.account_id) and not await subscription_service.is_active(event.account_id):
            await worker_pool.stop_worker(event.account_id)

    return {"status": "processed"}


@router.get("/status/{account_id}")
async def get_subscription_status(
    account_id: str,
    subscription_service=Depends(get_subscription_service),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, account_id)
    record = await subscription_service.get_status(account_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No subscription found for this account.")
    record["is_active"] = await subscription_service.is_active(account_id)
    return record


@router.get("")
async def list_subscriptions(
    subscription_service=Depends(get_subscription_service),
    auth: AuthContext = Depends(verify_api_key),
):
    """Admin-facing: every subscription, for the admin dashboard."""
    require_admin(auth)
    return await subscription_service.list_all()
