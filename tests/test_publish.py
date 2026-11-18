import sqlite3

import pytest

from app import store
from app.config import DATA_DIR
from app.errors import BusinessError
from app.pipeline import run, sample_text

GAP = "GAP1,CAD,,2026-11-18T01:00:00+00:00,2026-11-18T02:00:00+00:00,gap,1,0\n"
COVER = "COV1,CAD,,2026-11-18T01:00:00+00:00,2026-11-18T02:00:00+00:00,coverage,2,0\n"


@pytest.fixture(autouse=True)
def clean_store():
    for suffix in ("runs.sqlite", "runs.sqlite-wal", "runs.sqlite-shm"):
        (DATA_DIR / suffix).unlink(missing_ok=True)
    yield


def publish_gap():
    text = sample_text() + GAP
    return store.save(text, run(text))


def test_gap_splits_confirmed_and_pending():
    item = publish_gap()
    assert item["conclusion"]["pending_segments"] > 0
    assert item["conclusion"]["confirmed_segments"] > 0


def test_supplement_publishes_next_version():
    base = publish_gap()
    merged = sample_text() + GAP + COVER
    new = store.supplement(base["id"], merged, run(merged))
    assert new["publish_no"] == base["publish_no"] + 1
    assert new["parent_id"] == base["id"]
    assert new["conclusion"]["pending_segments"] == 0


def test_supplement_retry_does_not_republish():
    base = publish_gap()
    merged = sample_text() + GAP + COVER
    first = store.supplement(base["id"], merged, run(merged))
    again = store.supplement(base["id"], merged, run(merged))
    assert again["id"] == first["id"] and again["publish_no"] == first["publish_no"]
    assert len([v for v in store.history(base["id"]) if v["publish_no"] > 0]) == 1


def test_unchanged_input_does_not_publish():
    base = publish_gap()
    same = store.supplement(base["id"], store.latest_input(base["id"]), run(sample_text() + GAP))
    assert same["id"] == base["id"] and same["publish_no"] == 0
    assert same.get("unchanged") is True


def test_failed_update_keeps_old_version():
    base = publish_gap()
    before = store.get(base["id"])
    merged = sample_text() + GAP + COVER
    db = store.connect()
    db.execute("CREATE TRIGGER block_insert BEFORE INSERT ON runs BEGIN SELECT RAISE(ABORT,'disk full'); END")
    db.commit()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            store.supplement(base["id"], merged, run(merged))
    finally:
        db.execute("DROP TRIGGER block_insert")
        db.commit()
        db.close()
    after = store.get(base["id"])
    assert after["result"] == before["result"]
    assert after["conclusion"] == before["conclusion"]
    assert [v["id"] for v in store.history(base["id"])] == [base["id"]]


def test_recalculation_lists_affected_windows():
    base = publish_gap()
    merged = sample_text() + GAP + COVER
    new = store.supplement(base["id"], merged, run(merged))
    changes = new["result"]["recalculated"]["changes"]
    assert changes and all(c["proof_before"] != c["proof_after"] or c["excess_before"] != c["excess_after"] for c in changes)
    assert {c["proof_after"] for c in changes} == {"CONFIRMED"}


def test_recalculation_handles_resplit_windows():
    base = store.save(PENDING_ONLY, run(PENDING_ONLY))
    release = "L3,CAD,u3,2026-11-18T00:30:00+00:00,,release,1,1\n"
    merged = PENDING_ONLY + release
    new = store.supplement(base["id"], merged, run(merged))
    changes = new["result"]["recalculated"]["changes"]
    assert any(c["excess_before"] > c["excess_after"] for c in changes)
    assert any(c["excess_after"] < c["excess_before"] for c in changes)


def test_published_conclusion_remains_queryable():
    base = publish_gap()
    merged = sample_text() + GAP + COVER
    store.supplement(base["id"], merged, run(merged))
    old = store.get(base["id"])
    assert old["conclusion"]["pending_segments"] > 0
    assert old["result"]["final"]


def test_review_still_blocks_confirmed_overuse():
    item = publish_gap()
    with pytest.raises(BusinessError):
        store.review(item["id"], item["revision"], "通过")


PENDING_ONLY = """lease_id,product,user,start,end,kind,version,seats
C1,CAD,,2026-11-18T00:00:00+00:00,2026-11-18T12:00:00+00:00,capacity,1,2
L1,CAD,u1,2026-11-18T00:00:00+00:00,2026-11-18T02:00:00+00:00,online,1,1
L2,CAD,u2,2026-11-18T00:00:00+00:00,2026-11-18T02:00:00+00:00,online,1,1
L3,CAD,u3,2026-11-18T00:00:00+00:00,2026-11-18T02:00:00+00:00,online,1,1
G1,CAD,,2026-11-18T00:00:00+00:00,2026-11-18T02:00:00+00:00,gap,1,0
"""


def test_pending_only_does_not_block_release():
    item = store.save(PENDING_ONLY, run(PENDING_ONLY))
    assert item["conclusion"]["status"] == "PENDING_EVIDENCE"
    assert item["result"]["blocked"] is False
    assert store.review(item["id"], item["revision"], "通过")["decision"] == "通过"


def test_late_release_recalculates_after_supplement():
    base = store.save(PENDING_ONLY, run(PENDING_ONLY))
    assert base["conclusion"]["pending_seat_hours"] == "2.0"
    release = "L3,CAD,u3,2026-11-18T00:30:00+00:00,,release,1,1\n"
    merged = PENDING_ONLY + release
    new = store.supplement(base["id"], merged, run(merged))
    assert new["conclusion"]["pending_seat_hours"] == "0.5"
    assert new["result"]["recalculated"]["changes"]
    assert store.get(base["id"])["conclusion"]["pending_seat_hours"] == "2.0"


def test_second_supplement_chains_from_latest():
    base = store.save(PENDING_ONLY, run(PENDING_ONLY))
    first_text = PENDING_ONLY + "L3,CAD,u3,2026-11-18T00:30:00+00:00,,release,1,1\n"
    first = store.supplement(base["id"], first_text, run(first_text))
    second_text = first_text + "L2,CAD,u2,2026-11-18T01:00:00+00:00,,release,1,1\n"
    second = store.supplement(base["id"], second_text, run(second_text))
    assert second["publish_no"] == 2 and second["parent_id"] == first["id"]


def test_split_preserves_total_excess():
    without_gap = "\n".join(line for line in PENDING_ONLY.splitlines() if ",gap," not in line) + "\n"
    plain = run(without_gap)
    with_gap = run(PENDING_ONLY)
    def seat_seconds(result):
        return sum(r["excess"] * (float(r["b"]) - float(r["a"])) for r in result["usage"])
    assert seat_seconds(plain) == seat_seconds(with_gap)
    assert all(r["proof"] == "CONFIRMED" for r in plain["usage"])
    assert all(r["proof"] == "PENDING" for r in with_gap["usage"] if r["excess"] > 0)


def test_api_supplement_flow():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    base = client.post("/api/run", json={"text": PENDING_ONLY}).json()
    release = "L3,CAD,u3,2026-11-18T00:30:00+00:00,,release,1,1\n"
    first = client.post("/api/run", json={"text": release, "base_id": base["id"]})
    assert first.status_code == 200
    body = first.json()
    assert body["publish_no"] == 1 and body["conclusion"]["pending_seat_hours"] == "0.5"
    retry = client.post("/api/run", json={"text": release, "base_id": base["id"]}).json()
    assert retry["id"] == body["id"] and retry.get("unchanged") is True
    versions = client.get(f"/api/runs/{base['id']}/versions").json()["versions"]
    assert [v["publish_no"] for v in versions] == [1, 0]
    exported = client.get(f"/api/export/{body['id']}").text
    assert "recalculated" in exported and "conclusion" in exported
