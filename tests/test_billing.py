"""Phase 7 — Subscription model + billing helper tests."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect

from billing import FREE_SCAN_LIMIT, PRO_STATUSES, is_pro, scans_used_this_month
from db_models import Scan, Subscription


# ── Schema invariants ────────────────────────────────────────────────────────

def test_subscriptions_table_present_on_engine(db_session):
    insp = inspect(db_session.get_bind())
    assert "subscriptions" in insp.get_table_names()


def test_subscriptions_has_expected_columns(db_session):
    insp = inspect(db_session.get_bind())
    cols = {c["name"] for c in insp.get_columns("subscriptions")}
    assert cols == {
        "user_id",
        "stripe_customer_id",
        "stripe_subscription_id",
        "plan",
        "status",
        "current_period_end",
        # Phase 7.7 (Codex P7 MED #1): last applied Stripe event timestamp.
        "last_event_at",
        "created_at",
        "updated_at",
    }


def test_subscriptions_user_id_is_primary_key(db_session):
    """Per-user Pro for v1: at most one sub per user."""
    insp = inspect(db_session.get_bind())
    pk = insp.get_pk_constraint("subscriptions")
    assert pk["constrained_columns"] == ["user_id"]


def test_subscriptions_stripe_customer_id_is_indexed(db_session):
    """Webhook fallback lookup goes by stripe_customer_id when metadata is missing."""
    insp = inspect(db_session.get_bind())
    indexed_cols = {tuple(ix["column_names"]) for ix in insp.get_indexes("subscriptions")}
    assert ("stripe_customer_id",) in indexed_cols


# ── is_pro ────────────────────────────────────────────────────────────────────

def _put_sub(db_session, *, user_id, status, period_end):
    db_session.add(
        Subscription(
            user_id=user_id,
            stripe_customer_id="cus_test",
            stripe_subscription_id="sub_test",
            plan="pro",
            status=status,
            current_period_end=period_end,
        )
    )
    db_session.commit()


def test_is_pro_false_when_no_subscription(db_session):
    assert is_pro("user_none", db_session) is False


def test_is_pro_true_when_active_and_period_in_future(db_session):
    _put_sub(
        db_session,
        user_id="user_active",
        status="active",
        period_end=datetime.now(timezone.utc) + timedelta(days=10),
    )
    assert is_pro("user_active", db_session) is True


def test_is_pro_true_when_trialing_and_period_in_future(db_session):
    _put_sub(
        db_session,
        user_id="user_trial",
        status="trialing",
        period_end=datetime.now(timezone.utc) + timedelta(days=5),
    )
    assert is_pro("user_trial", db_session) is True


def test_is_pro_false_when_status_past_due(db_session):
    _put_sub(
        db_session,
        user_id="user_past_due",
        status="past_due",
        period_end=datetime.now(timezone.utc) + timedelta(days=5),
    )
    assert is_pro("user_past_due", db_session) is False


def test_is_pro_false_when_status_canceled(db_session):
    """Conservative posture: a `canceled` status means access is over even if
    Stripe still shows current_period_end in the future (cancel-immediate flow)."""
    _put_sub(
        db_session,
        user_id="user_canceled",
        status="canceled",
        period_end=datetime.now(timezone.utc) + timedelta(days=10),
    )
    assert is_pro("user_canceled", db_session) is False


def test_is_pro_false_when_status_incomplete(db_session):
    _put_sub(
        db_session,
        user_id="user_inc",
        status="incomplete",
        period_end=None,
    )
    assert is_pro("user_inc", db_session) is False


def test_is_pro_false_when_period_end_has_passed(db_session):
    """Defensive: status stuck on `active` but the period ended yesterday."""
    _put_sub(
        db_session,
        user_id="user_lapsed",
        status="active",
        period_end=datetime.now(timezone.utc) - timedelta(days=1),
    )
    assert is_pro("user_lapsed", db_session) is False


def test_is_pro_false_when_period_end_is_null(db_session):
    _put_sub(
        db_session,
        user_id="user_null_end",
        status="active",
        period_end=None,
    )
    assert is_pro("user_null_end", db_session) is False


def test_is_pro_scopes_to_user_id(db_session):
    """One user's sub does not bleed into another's gate."""
    _put_sub(
        db_session,
        user_id="user_paying",
        status="active",
        period_end=datetime.now(timezone.utc) + timedelta(days=10),
    )
    assert is_pro("user_paying", db_session) is True
    assert is_pro("user_freeloader", db_session) is False


# ── scans_used_this_month ─────────────────────────────────────────────────────

def _persisted_scan(db_session, *, user_id, created_at, org_id=None):
    scan = Scan(
        user_id=user_id,
        org_id=org_id,
        filename="cv.pdf",
        risk_level="GREEN",
        risk_score=10,
        prompt_injection_findings=[],
        pii_findings=[],
        ai_text_likelihood="UNLIKELY",
        ai_text_score=0.1,
        safe_copy_text="clean",
        summary="clean",
        match_analysis={"summary": "ok"},
    )
    scan.created_at = created_at
    db_session.add(scan)
    db_session.commit()
    return scan


def test_scans_used_this_month_is_zero_when_user_has_none(db_session):
    assert scans_used_this_month("user_a", db_session) == 0


def test_scans_used_this_month_counts_current_month(db_session):
    now = datetime.now(timezone.utc)
    for _ in range(3):
        _persisted_scan(db_session, user_id="user_a", created_at=now)
    assert scans_used_this_month("user_a", db_session) == 3


def test_scans_used_this_month_excludes_last_month(db_session):
    """A scan from one second before this month started must not count."""
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    _persisted_scan(
        db_session,
        user_id="user_a",
        created_at=start_of_month - timedelta(seconds=1),
    )
    _persisted_scan(db_session, user_id="user_a", created_at=now)
    assert scans_used_this_month("user_a", db_session) == 1


def test_scans_used_this_month_scopes_to_creator_not_org_viewer(db_session):
    """Org-shared colleagues' scans are visible to me (Phase 5) but count
    against THEIR quota, not mine. Quota tracks who triggered the work."""
    now = datetime.now(timezone.utc)
    _persisted_scan(db_session, user_id="user_me", created_at=now, org_id="org_x")
    _persisted_scan(db_session, user_id="user_colleague", created_at=now, org_id="org_x")
    _persisted_scan(db_session, user_id="user_colleague", created_at=now, org_id="org_x")
    assert scans_used_this_month("user_me", db_session) == 1
    assert scans_used_this_month("user_colleague", db_session) == 2


# ── Constants ─────────────────────────────────────────────────────────────────

def test_free_scan_limit_is_ten():
    assert FREE_SCAN_LIMIT == 10


def test_pro_statuses_set_is_minimal():
    """active + trialing only. past_due / canceled / incomplete are NOT Pro."""
    assert PRO_STATUSES == frozenset({"active", "trialing"})


# ── Phase 7.4: Stripe billing module (stripe_billing.py) ─────────────────────

import pytest

from stripe_billing import (
    BillingError,
    create_checkout_session,
    create_portal_session,
    is_billing_configured,
)


def _set_billing_env(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_dummy")
    for k in ("APP_BASE_URL", "BILLING_SUCCESS_URL", "BILLING_CANCEL_URL",
              "BILLING_PORTAL_RETURN_URL"):
        monkeypatch.delenv(k, raising=False)


def test_is_billing_configured_false_when_nothing_set(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)
    assert is_billing_configured() is False


def test_is_billing_configured_false_when_only_secret(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)
    assert is_billing_configured() is False


def test_is_billing_configured_true_when_both_set(monkeypatch):
    _set_billing_env(monkeypatch)
    assert is_billing_configured() is True


def test_create_checkout_session_raises_when_unconfigured(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)
    with pytest.raises(BillingError):
        create_checkout_session(user_id="user_x")


def test_create_checkout_session_builds_subscription_session(monkeypatch):
    _set_billing_env(monkeypatch)
    import stripe

    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return type("S", (), {"url": "https://checkout.stripe.test/abc"})()

    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(fake_create))
    url = create_checkout_session(user_id="user_x")
    assert url == "https://checkout.stripe.test/abc"
    assert captured["mode"] == "subscription"
    assert captured["line_items"] == [{"price": "price_dummy", "quantity": 1}]
    assert captured["client_reference_id"] == "user_x"
    assert captured["metadata"] == {"user_id": "user_x"}
    assert captured["subscription_data"] == {"metadata": {"user_id": "user_x"}}
    # No existing customer id -> Stripe creates one; we must not send a customer key.
    assert "customer" not in captured
    # Redirect URLs are server-derived, never client input.
    assert captured["success_url"].startswith("http")
    assert captured["cancel_url"].startswith("http")


def test_create_checkout_session_reuses_customer_when_supplied(monkeypatch):
    _set_billing_env(monkeypatch)
    import stripe

    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return type("S", (), {"url": "https://checkout.stripe.test/abc"})()

    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(fake_create))
    create_checkout_session(user_id="user_x", customer_id="cus_existing")
    assert captured["customer"] == "cus_existing"


def test_create_checkout_session_masks_sdk_error(monkeypatch):
    _set_billing_env(monkeypatch)
    import stripe

    def boom(**kwargs):
        raise RuntimeError("stripe internal detail")

    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(boom))
    with pytest.raises(BillingError) as ei:
        create_checkout_session(user_id="user_x")
    # Generic public message -- no raw SDK detail leaks to the caller.
    assert "stripe internal detail" not in str(ei.value)


def test_create_portal_session_returns_url(monkeypatch):
    _set_billing_env(monkeypatch)
    import stripe

    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return type("S", (), {"url": "https://portal.stripe.test/xyz"})()

    monkeypatch.setattr(stripe.billing_portal.Session, "create",
                        staticmethod(fake_create))
    url = create_portal_session(customer_id="cus_existing")
    assert url == "https://portal.stripe.test/xyz"
    assert captured["customer"] == "cus_existing"
    assert captured["return_url"].startswith("http")


def test_create_portal_session_masks_sdk_error(monkeypatch):
    _set_billing_env(monkeypatch)
    import stripe

    def boom(**kwargs):
        raise RuntimeError("portal internal detail")

    monkeypatch.setattr(stripe.billing_portal.Session, "create", staticmethod(boom))
    with pytest.raises(BillingError):
        create_portal_session(customer_id="cus_existing")



# ── Phase 7.5: webhook signature verification + idempotency ledger ───────────

def test_webhook_events_table_present(db_session):
    insp = inspect(db_session.get_bind())
    assert "webhook_events" in insp.get_table_names()


def test_webhook_events_columns_and_pk(db_session):
    insp = inspect(db_session.get_bind())
    cols = {c["name"] for c in insp.get_columns("webhook_events")}
    assert cols == {"event_id", "event_type", "received_at"}
    pk = insp.get_pk_constraint("webhook_events")
    assert pk["constrained_columns"] == ["event_id"]


def test_verify_event_raises_billingerror_when_secret_unset(monkeypatch):
    from stripe_billing import verify_and_parse_event

    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    with pytest.raises(BillingError):
        verify_and_parse_event(b"{}", "t=1,v1=abc")


def test_verify_event_raises_webhookerror_when_signature_missing(monkeypatch):
    from stripe_billing import WebhookError, verify_and_parse_event

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_dummy")
    with pytest.raises(WebhookError):
        verify_and_parse_event(b"{}", None)


def test_verify_event_raises_webhookerror_on_invalid_signature(monkeypatch):
    import stripe

    from stripe_billing import WebhookError, verify_and_parse_event

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_dummy")

    def boom(payload, sig_header, secret):
        raise Exception("signature mismatch")

    monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(boom))
    with pytest.raises(WebhookError):
        verify_and_parse_event(b"{}", "t=1,v1=bad")


def test_verify_event_returns_parsed_event_and_forwards_args(monkeypatch):
    import stripe

    from stripe_billing import verify_and_parse_event

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_dummy")
    seen = {}

    def ok(payload, sig_header, secret):
        seen["args"] = (payload, sig_header, secret)
        return {"id": "evt_1", "type": "checkout.session.completed"}

    monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(ok))
    event = verify_and_parse_event(b'{"x":1}', "t=1,v1=ok")
    assert event["id"] == "evt_1"
    assert seen["args"] == (b'{"x":1}', "t=1,v1=ok", "whsec_dummy")
