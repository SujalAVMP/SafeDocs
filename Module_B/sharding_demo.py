"""
Assignment 4 sharding verification and demo helper for Module B.

Usage:
    cd Module_B
    ../.venv/bin/python sharding_demo.py

The script uses Flask's test client, so the web server does not need to be
running separately. It works with both the default local shard-table setup and
the remote-database shard mode configured through environment variables.
"""

from __future__ import annotations

import uuid

from app.app import (
    DOCUMENT_SHARD_COUNT,
    app,
    get_db,
    get_shard_db,
    _accesslog_table_name,
    _document_table_name,
)


def _query_one(db, sql, params=None):
    with db.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def _query_all(db, sql, params=None):
    with db.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def _fetch_document_count(shard_id):
    shard_db = get_shard_db(shard_id)
    try:
        row = _query_one(shard_db, f"SELECT COUNT(*) AS cnt FROM {_document_table_name(shard_id=shard_id)}")
        return row["cnt"]
    finally:
        shard_db.close()


def _fetch_log_rows(shard_id):
    shard_db = get_shard_db(shard_id)
    try:
        return _query_all(
            shard_db,
            f"""
            SELECT LogID, DocumentID, MemberID, Action, AccessTimestamp
            FROM {_accesslog_table_name(shard_id=shard_id)}
            """,
        )
    finally:
        shard_db.close()


def _fetch_doc_placement(document_id):
    placement = {}
    for shard_id in range(DOCUMENT_SHARD_COUNT):
        shard_db = get_shard_db(shard_id)
        try:
            row = _query_one(
                shard_db,
                f"SELECT COUNT(*) AS cnt FROM {_document_table_name(shard_id=shard_id)} WHERE DocumentID = %s",
                (document_id,),
            )
            placement[f"s{shard_id}"] = row["cnt"]
        finally:
            shard_db.close()
    return placement


def _cleanup_demo_document(document_id, shard_id):
    """Remove the demo-only inserted document so repeated runs stay tidy."""
    coordinator_db = get_db()
    shard_db = get_shard_db(shard_id)
    try:
        with shard_db.cursor() as cur:
            cur.execute(f"DELETE FROM {_accesslog_table_name(shard_id=shard_id)} WHERE DocumentID = %s", (document_id,))
            cur.execute(f"DELETE FROM {_document_table_name(shard_id=shard_id)} WHERE DocumentID = %s", (document_id,))
        with coordinator_db.cursor() as cur:
            cur.execute("DELETE FROM DocumentShardDirectory WHERE DocumentID = %s", (document_id,))
            cur.execute("DELETE FROM SecurityLog WHERE RecordID = %s", (document_id,))
        shard_db.commit()
        coordinator_db.commit()
    except Exception:
        shard_db.rollback()
        coordinator_db.rollback()
        raise
    finally:
        shard_db.close()
        coordinator_db.close()


def login(client):
    response = client.post("/login", json={"user": "admin", "password": "admin123"})
    if response.status_code != 200:
        raise RuntimeError(f"Login failed: {response.status_code} {response.get_data(as_text=True)}")
    token = response.get_json()["session_token"]
    return {"Authorization": f"Bearer {token}"}


def print_distribution():
    print("Document distribution across shards")
    for shard_id in range(DOCUMENT_SHARD_COUNT):
        print(f"  Shard {shard_id}: {_fetch_document_count(shard_id)} documents")


def verify_migration_counts():
    coordinator_db = get_db()
    try:
        legacy_docs = _query_one(coordinator_db, "SELECT COUNT(*) AS cnt FROM Document")["cnt"]
        migrated_docs = _query_one(
            coordinator_db,
            "SELECT COUNT(*) AS cnt FROM DocumentShardDirectory WHERE Origin = 'migration'",
        )["cnt"]
        live_insert_docs = _query_one(
            coordinator_db,
            "SELECT COUNT(*) AS cnt FROM DocumentShardDirectory WHERE Origin = 'live_insert'",
        )["cnt"]
        legacy_logs = _query_one(coordinator_db, "SELECT COUNT(*) AS cnt FROM AccessLog")["cnt"]
        legacy_log_rows = _query_all(
            coordinator_db,
            "SELECT LogID, DocumentID, MemberID, Action, AccessTimestamp FROM AccessLog",
        )
    finally:
        coordinator_db.close()

    total_sharded_docs = sum(_fetch_document_count(shard_id) for shard_id in range(DOCUMENT_SHARD_COUNT))
    shard_log_rows = []
    for shard_id in range(DOCUMENT_SHARD_COUNT):
        shard_log_rows.extend(_fetch_log_rows(shard_id))

    legacy_log_set = {
        (
            row["LogID"],
            row["DocumentID"],
            row["MemberID"],
            row["Action"],
            row["AccessTimestamp"],
        )
        for row in legacy_log_rows
    }
    shard_log_set = {
        (
            row["LogID"],
            row["DocumentID"],
            row["MemberID"],
            row["Action"],
            row["AccessTimestamp"],
        )
        for row in shard_log_rows
    }
    missing_legacy_logs = legacy_log_set - shard_log_set

    print("Migration verification")
    print(f"  Legacy documents: {legacy_docs}")
    print(f"  Migrated documents present on shards: {migrated_docs}")
    print(f"  Routed inserts tracked in directory: {live_insert_docs}")
    print(f"  Total sharded documents (migration + routed inserts): {total_sharded_docs}")
    print(f"  Legacy access logs: {legacy_logs}")
    print(f"  Total sharded access logs (migration + routed inserts): {len(shard_log_rows)}")
    print(f"  Missing migrated legacy logs: {len(missing_legacy_logs)}")

    if migrated_docs != legacy_docs:
        raise RuntimeError("Migrated document count does not match the legacy Document table")
    if missing_legacy_logs:
        raise RuntimeError("At least one legacy AccessLog row is missing from the shard tables")


def verify_routed_queries():
    client = app.test_client()
    headers = login(client)

    doc_response = client.get("/api/documents/1", headers=headers)
    if doc_response.status_code != 200:
        raise RuntimeError(
            f"Single document lookup failed: {doc_response.status_code} {doc_response.get_data(as_text=True)}"
        )
    doc = doc_response.get_json()
    print("Single-key routing")
    print(f"  Document {doc['DocumentID']} returned from shard {doc['ShardID']}")

    range_response = client.get("/api/documents?id_start=1&id_end=12", headers=headers)
    if range_response.status_code != 200:
        raise RuntimeError(
            f"Range query failed: {range_response.status_code} {range_response.get_data(as_text=True)}"
        )
    docs = range_response.get_json()
    shard_ids = sorted({row["ShardID"] for row in docs})
    print("Cross-shard range query")
    print(f"  Returned {len(docs)} documents spanning shards {shard_ids}")

    title = f"Shard Demo Verification {uuid.uuid4().hex[:8]}"
    create_response = client.post(
        "/api/documents",
        headers=headers,
        json={"Title": title, "FolderID": 1, "Description": "assignment4-demo"},
    )
    if create_response.status_code != 201:
        raise RuntimeError(
            f"Document insert failed: {create_response.status_code} {create_response.get_data(as_text=True)}"
        )
    created = create_response.get_json()
    document_id = created["DocumentID"]
    shard_id = created["ShardID"]

    coordinator_db = get_db()
    try:
        placement = _fetch_doc_placement(document_id)
        directory_shard = _query_one(
            coordinator_db,
            "SELECT ShardID FROM DocumentShardDirectory WHERE DocumentID = %s",
            (document_id,),
        )["ShardID"]
    finally:
        coordinator_db.close()

    print("Insert routing")
    print(f"  New document {document_id} was routed to shard {shard_id}")
    print(
        "  Physical placement: "
        f"s0={placement['s0']}, s1={placement['s1']}, s2={placement['s2']}, "
        f"directory={directory_shard}"
    )

    expected = {"s0": 0, "s1": 0, "s2": 0}
    expected[f"s{shard_id}"] = 1
    if any(placement[key] != expected[key] for key in ("s0", "s1", "s2")):
        raise RuntimeError("Inserted document did not land on exactly one shard")
    if directory_shard != shard_id:
        raise RuntimeError("DocumentShardDirectory recorded the wrong shard")

    _cleanup_demo_document(document_id, shard_id)
    print("  Demo cleanup: removed the verification document from the shard and directory")


def main():
    print("Assignment 4 sharding demo")
    print("=" * 32)
    verify_migration_counts()
    print_distribution()
    print("-" * 32)
    verify_routed_queries()
    print("=" * 32)
    print("Sharding demo completed successfully.")


if __name__ == "__main__":
    main()
