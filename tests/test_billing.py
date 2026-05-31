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
