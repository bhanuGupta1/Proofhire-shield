"""API tests for the pipeline + shortlist router (platform Phase 2)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from conftest import OTHER_USER_ID, TEST_ORG_ID


def _make_job(client, title="Backend Engineer"):
    return client.post("/jobs", json={"title": title}).json()


def _make_candidate(client, name="Ada Lovelace"):
    return client.post("/candidates", json={"full_name": name}).json()


# ── Board seeding ────────────────────────────────────────────────────────────

def test_board_seeds_default_stages(client_with_db_and_auth):
    job = _make_job(client_with_db_and_auth)
    r = client_with_db_and_auth.get(f"/jobs/{job['id']}/pipeline")
    assert r.status_code == 200, r.text
    board = r.json()
    names = [s["name"] for s in board["stages"]]
    assert names == ["Applied", "Screening", "Interview", "Offer", "Hired"]
    assert all(s["candidates"] == [] for s in board["stages"])


def test_board_is_stable_across_calls(client_with_db_and_auth):
    job = _make_job(client_with_db_and_auth)
    first = client_with_db_and_auth.get(f"/jobs/{job['id']}/pipeline").json()
    second = client_with_db_and_auth.get(f"/jobs/{job['id']}/pipeline").json()
    assert [s["id"] for s in first["stages"]] == [s["id"] for s in second["stages"]]


def test_board_cross_tenant_is_404(client_with_db_and_auth, db_session):
    from db_models import Job

    other = Job(user_id=OTHER_USER_ID, title="Theirs")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    r = client_with_db_and_auth.get(f"/jobs/{other.id}/pipeline")
    assert r.status_code == 404


# ── Placements ───────────────────────────────────────────────────────────────

def test_add_candidate_to_pipeline_defaults_to_first_stage(client_with_db_and_auth):
    job = _make_job(client_with_db_and_auth)
    cand = _make_candidate(client_with_db_and_auth)
    r = client_with_db_and_auth.post(
        f"/jobs/{job['id']}/placements", json={"candidate_id": cand["id"]}
    )
    assert r.status_code == 201, r.text
    board = client_with_db_and_auth.get(f"/jobs/{job['id']}/pipeline").json()
    applied = next(s for s in board["stages"] if s["name"] == "Applied")
    assert [c["candidate_id"] for c in applied["candidates"]] == [cand["id"]]


def test_cannot_add_same_candidate_twice(client_with_db_and_auth):
    job = _make_job(client_with_db_and_auth)
    cand = _make_candidate(client_with_db_and_auth)
    client_with_db_and_auth.post(
        f"/jobs/{job['id']}/placements", json={"candidate_id": cand["id"]}
    )
    r = client_with_db_and_auth.post(
        f"/jobs/{job['id']}/placements", json={"candidate_id": cand["id"]}
    )
    assert r.status_code == 409


def test_move_candidate_between_stages(client_with_db_and_auth):
    job = _make_job(client_with_db_and_auth)
    cand = _make_candidate(client_with_db_and_auth)
    placement = client_with_db_and_auth.post(
        f"/jobs/{job['id']}/placements", json={"candidate_id": cand["id"]}
    ).json()
    board = client_with_db_and_auth.get(f"/jobs/{job['id']}/pipeline").json()
    interview = next(s for s in board["stages"] if s["name"] == "Interview")

    r = client_with_db_and_auth.patch(
        f"/pipeline/placements/{placement['placement_id']}",
        json={"stage_id": interview["id"]},
    )
    assert r.status_code == 200, r.text
    board2 = client_with_db_and_auth.get(f"/jobs/{job['id']}/pipeline").json()
    interview2 = next(s for s in board2["stages"] if s["name"] == "Interview")
    assert [c["candidate_id"] for c in interview2["candidates"]] == [cand["id"]]


def test_move_to_other_jobs_stage_is_404(client_with_db_and_auth):
    job_a = _make_job(client_with_db_and_auth, "A")
    job_b = _make_job(client_with_db_and_auth, "B")
    cand = _make_candidate(client_with_db_and_auth)
    placement = client_with_db_and_auth.post(
        f"/jobs/{job_a['id']}/placements", json={"candidate_id": cand["id"]}
    ).json()
    board_b = client_with_db_and_auth.get(f"/jobs/{job_b['id']}/pipeline").json()
    foreign_stage = board_b["stages"][0]["id"]
    r = client_with_db_and_auth.patch(
        f"/pipeline/placements/{placement['placement_id']}",
        json={"stage_id": foreign_stage},
    )
    assert r.status_code == 404


def test_remove_placement(client_with_db_and_auth):
    job = _make_job(client_with_db_and_auth)
    cand = _make_candidate(client_with_db_and_auth)
    placement = client_with_db_and_auth.post(
        f"/jobs/{job['id']}/placements", json={"candidate_id": cand["id"]}
    ).json()
    r = client_with_db_and_auth.delete(
        f"/pipeline/placements/{placement['placement_id']}"
    )
    assert r.status_code == 204
    board = client_with_db_and_auth.get(f"/jobs/{job['id']}/pipeline").json()
    assert all(s["candidates"] == [] for s in board["stages"])


def test_add_placement_for_other_tenants_candidate_is_404(
    client_with_db_and_auth, db_session
):
    from db_models import Candidate

    job = _make_job(client_with_db_and_auth)
    other = Candidate(user_id=OTHER_USER_ID, full_name="Theirs", source="manual")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    r = client_with_db_and_auth.post(
        f"/jobs/{job['id']}/placements", json={"candidate_id": str(other.id)}
    )
    assert r.status_code == 404


# ── Stages ───────────────────────────────────────────────────────────────────

def test_add_custom_stage(client_with_db_and_auth):
    job = _make_job(client_with_db_and_auth)
    client_with_db_and_auth.get(f"/jobs/{job['id']}/pipeline")  # seed defaults
    r = client_with_db_and_auth.post(
        f"/jobs/{job['id']}/stages", json={"name": "Reference Check"}
    )
    assert r.status_code == 201, r.text
    board = client_with_db_and_auth.get(f"/jobs/{job['id']}/pipeline").json()
    assert "Reference Check" in [s["name"] for s in board["stages"]]


def test_delete_stage_reassigns_its_candidates(client_with_db_and_auth):
    job = _make_job(client_with_db_and_auth)
    cand = _make_candidate(client_with_db_and_auth)
    board = client_with_db_and_auth.get(f"/jobs/{job['id']}/pipeline").json()
    screening = next(s for s in board["stages"] if s["name"] == "Screening")
    client_with_db_and_auth.post(
        f"/jobs/{job['id']}/placements",
        json={"candidate_id": cand["id"], "stage_id": screening["id"]},
    )
    r = client_with_db_and_auth.delete(f"/pipeline/stages/{screening['id']}")
    assert r.status_code == 204
    board2 = client_with_db_and_auth.get(f"/jobs/{job['id']}/pipeline").json()
    names = [s["name"] for s in board2["stages"]]
    assert "Screening" not in names
    # The candidate survived — reassigned into a remaining stage.
    all_cards = [c["candidate_id"] for s in board2["stages"] for c in s["candidates"]]
    assert cand["id"] in all_cards


def test_cannot_delete_last_stage(client_with_db_and_auth):
    job = _make_job(client_with_db_and_auth)
    board = client_with_db_and_auth.get(f"/jobs/{job['id']}/pipeline").json()
    # Delete down to one stage.
    for s in board["stages"][1:]:
        client_with_db_and_auth.delete(f"/pipeline/stages/{s['id']}")
    last = client_with_db_and_auth.get(f"/jobs/{job['id']}/pipeline").json()["stages"]
    assert len(last) == 1
    r = client_with_db_and_auth.delete(f"/pipeline/stages/{last[0]['id']}")
    assert r.status_code == 409


# ── Shortlist ────────────────────────────────────────────────────────────────

def test_shortlist_add_list_remove(client_with_db_and_auth):
    job = _make_job(client_with_db_and_auth)
    cand = _make_candidate(client_with_db_and_auth)
    add = client_with_db_and_auth.post(
        f"/jobs/{job['id']}/shortlist", json={"candidate_id": cand["id"]}
    )
    assert add.status_code == 201, add.text
    listed = client_with_db_and_auth.get(f"/jobs/{job['id']}/shortlist").json()
    assert [c["id"] for c in listed] == [cand["id"]]
    rm = client_with_db_and_auth.delete(
        f"/jobs/{job['id']}/shortlist/{cand['id']}"
    )
    assert rm.status_code == 204
    assert client_with_db_and_auth.get(f"/jobs/{job['id']}/shortlist").json() == []


def test_shortlist_dedupes(client_with_db_and_auth):
    job = _make_job(client_with_db_and_auth)
    cand = _make_candidate(client_with_db_and_auth)
    client_with_db_and_auth.post(
        f"/jobs/{job['id']}/shortlist", json={"candidate_id": cand["id"]}
    )
    r = client_with_db_and_auth.post(
        f"/jobs/{job['id']}/shortlist", json={"candidate_id": cand["id"]}
    )
    assert r.status_code == 409


# ── Org sharing + cascade ────────────────────────────────────────────────────

def test_org_member_sees_org_job_board(client_with_db_auth_and_org, db_session):
    from db_models import Job

    shared = Job(user_id=OTHER_USER_ID, org_id=TEST_ORG_ID, title="Org Job")
    db_session.add(shared)
    db_session.commit()
    db_session.refresh(shared)
    r = client_with_db_auth_and_org.get(f"/jobs/{shared.id}/pipeline")
    assert r.status_code == 200


def test_pipeline_fks_declare_cascade():
    """Deleting a job/candidate must take its pipeline rows with it. SQLite in
    tests doesn't enforce ON DELETE, so (matching test_db.py) we assert the
    declaration; Postgres enforces it in production."""
    from db_models import Placement, PipelineStage, ShortlistEntry

    def _ondelete(model, target_table):
        for fk in model.__table__.foreign_keys:
            if fk.column.table.name == target_table:
                return (fk.ondelete or "").upper()
        return None

    assert _ondelete(PipelineStage, "jobs") == "CASCADE"
    assert _ondelete(Placement, "jobs") == "CASCADE"
    assert _ondelete(Placement, "candidates") == "CASCADE"
    # A deleted stage must not destroy the placement — it re-buckets instead.
    assert _ondelete(Placement, "pipeline_stages") == "SET NULL"
    assert _ondelete(ShortlistEntry, "jobs") == "CASCADE"
    assert _ondelete(ShortlistEntry, "candidates") == "CASCADE"


def test_placement_unique_per_job_candidate():
    from db_models import Placement

    uniques = [
        c for c in Placement.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    ]
    cols = {tuple(sorted(col.name for col in u.columns)) for u in uniques}
    assert ("candidate_id", "job_id") in cols
