"""
Stripe billing integration — Phase 7 monetisation.

A thin, boring wrapper over the Stripe SDK for the two hosted flows the API
needs in 7.4:
- create_checkout_session: start a Pro subscription (Stripe Checkout, hosted).
- create_portal_session: let an existing customer manage / cancel (Billing Portal).
(Webhook signature verification lands in 7.5 — not here, to keep this step surgical.)

Security posture (treated as a HIGH-RISK path per the project's backend security rules):
- Every secret comes from an environment variable ONLY — never logged, echoed, or
  committed:
    * STRIPE_SECRET_KEY  — sk_... server key, authorises all SDK calls.
    * STRIPE_PRICE_ID    — price_... the recurring Pro price the checkout subscribes to.
- Redirect URLs are SERVER-controlled (BILLING_SUCCESS_URL / BILLING_CANCEL_URL /
  BILLING_PORTAL_RETURN_URL, falling back to APP_BASE_URL). They are NEVER accepted
  from the client — a client-supplied redirect would be an open-redirect / phishing
  vector.
- is_billing_configured() gates the endpoints: unconfigured → the route returns 503
  (same degrade-loud-not-silent contract the assessment LLM path uses).
- The Stripe SDK is imported lazily inside each call, so the rest of the app — and the
  whole test suite — imports cleanly even when `stripe` is not installed.
- Upstream SDK failures are masked into a single generic BillingError; specifics are
  logged server-side at WARNING. The route maps BillingError to HTTP 503.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

PRO_PLAN = "pro"
_DEFAULT_BASE_URL = "http://localhost:5173"


class BillingError(Exception):
    """Stripe is unconfigured or an upstream Stripe call failed. Endpoint → HTTP 503."""


def _secret_key() -> str | None:
    return os.environ.get("STRIPE_SECRET_KEY")


def _price_id() -> str | None:
    return os.environ.get("STRIPE_PRICE_ID")


def is_billing_configured() -> bool:
    """True only when BOTH the secret key and the Pro price id are set — both are
    required to create a Checkout Session, so the feature is "on" only with both."""
    return bool(_secret_key() and _price_id())


def _base_url() -> str:
    return os.environ.get("APP_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def _success_url() -> str:
    return os.environ.get("BILLING_SUCCESS_URL") or f"{_base_url()}/?billing=success"


def _cancel_url() -> str:
    return os.environ.get("BILLING_CANCEL_URL") or f"{_base_url()}/?billing=cancel"


def _portal_return_url() -> str:
    return os.environ.get("BILLING_PORTAL_RETURN_URL") or f"{_base_url()}/"


def _load_stripe() -> Any:
    """Lazy-import the SDK and set the api key from the env. Raises BillingError
    (→ 503) when the key is missing or the package is not installed."""
    key = _secret_key()
    if not key:
        logger.warning("STRIPE_SECRET_KEY is not configured")
        raise BillingError("Billing is not configured.")
    try:
        import stripe  # type: ignore
    except ImportError as exc:
        logger.warning("stripe SDK is not installed", exc_info=True)
        raise BillingError("Billing is not configured.") from exc
    stripe.api_key = key
    return stripe


def _session_url(session: Any) -> str:
    """Stripe resources support both attribute and mapping access depending on
    SDK version; read defensively and fail loud if no URL came back."""
    url = getattr(session, "url", None)
    if not url and hasattr(session, "get"):
        url = session.get("url")
    if not url:
        raise BillingError("Stripe did not return a redirect URL.")
    return url


def create_checkout_session(*, user_id: str, customer_id: str | None = None) -> str:
    """Create a subscription Checkout Session for `user_id` and return its hosted URL.

    `user_id` (the verified Clerk sub) is stamped onto both the session
    (client_reference_id + metadata) and the resulting subscription
    (subscription_data.metadata) so the 7.5 webhook can map the event back to our
    user even if the customer object is created fresh by Stripe. When we already
    know the user's Stripe customer id we reuse it so a re-subscribe does not
    create a duplicate customer.
    """
    price = _price_id()
    if not price:
        logger.warning("STRIPE_PRICE_ID is not configured")
        raise BillingError("Billing is not configured.")
    stripe = _load_stripe()
    params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price, "quantity": 1}],
        "success_url": _success_url(),
        "cancel_url": _cancel_url(),
        "client_reference_id": user_id,
        "metadata": {"user_id": user_id},
        "subscription_data": {"metadata": {"user_id": user_id}},
    }
    if customer_id:
        params["customer"] = customer_id
    try:
        session = stripe.checkout.Session.create(**params)
    except Exception as exc:
        logger.warning("Stripe checkout session creation failed", exc_info=True)
        raise BillingError("Could not start checkout.") from exc
    return _session_url(session)


def create_portal_session(*, customer_id: str) -> str:
    """Create a Billing Portal session for an existing customer and return its URL."""
    stripe = _load_stripe()
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=_portal_return_url(),
        )
    except Exception as exc:
        logger.warning("Stripe billing portal session creation failed", exc_info=True)
        raise BillingError("Could not open the billing portal.") from exc
    return _session_url(session)
