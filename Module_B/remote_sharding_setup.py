"""
Provision and migrate the document shard data into separate shard databases.

Usage:
    cd Module_B
    SAFEDOCS_SHARD_MODE=remote_databases ../.venv/bin/python remote_sharding_setup.py

This script treats the coordinator database as the source of truth for the
legacy unsharded Document / AccessLog tables and copies those rows into the
configured shard databases according to DocumentID % 3.
"""

from __future__ import annotations

from collections import defaultdict

from app.app import (
    DOCUMENT_SHARD_COUNT,
    SHARD_MODE,
    get_db,
    get_shard_db,
    _document_shard_id,
    _document_table_name,
    _accesslog_table_name,
)


DOCUMENT_COLUMNS = (
    "DocumentID",
    "Title",
    "Description",
    "FilePath",
    "FileSize",
    "MimeType",
    "UploadedBy",
    "FolderID",
    "IsConfidential",
    "IsActive",
    "CreatedAt",
    "UpdatedAt",
)
ACCESSLOG_COLUMNS = (
    "LogID",
    "DocumentID",
    "MemberID",
    "Action",
    "IPAddress",
    "UserAgent",
    "AccessTimestamp",
)


def ensure_coordinator_tables(db):
    """Create the coordinator-side helper tables used by the shard router."""
    with db.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS DocumentIdSequence (
                DocumentID INT PRIMARY KEY AUTO_INCREMENT,
                ReservedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS DocumentShardDirectory (
                DocumentID INT PRIMARY KEY,
                ShardID TINYINT NOT NULL,
                Origin VARCHAR(20) NOT NULL DEFAULT 'migration',
                RoutedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                KEY idx_doc_directory_shard (ShardID, DocumentID)
            )
            """
        )


def ensure_shard_tables(db, shard_id):
    """Create the shard-local document and access-log tables."""
    document_table = _document_table_name(shard_id=shard_id)
    accesslog_table = _accesslog_table_name(shard_id=shard_id)
    with db.cursor() as cur:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {document_table} (
                DocumentID INT PRIMARY KEY,
                Title VARCHAR(200) NOT NULL,
                Description VARCHAR(500),
                FilePath VARCHAR(500) NOT NULL,
                FileSize BIGINT NOT NULL,
                MimeType VARCHAR(50) NOT NULL DEFAULT 'application/pdf',
                UploadedBy INT NOT NULL,
                FolderID INT NOT NULL,
                IsConfidential BOOLEAN NOT NULL DEFAULT FALSE,
                IsActive BOOLEAN NOT NULL DEFAULT TRUE,
                CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                KEY idx_doc_title (Title),
                KEY idx_doc_created (CreatedAt),
                KEY idx_doc_uploaded_active (UploadedBy, IsActive)
            )
            """
        )
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {accesslog_table} (
                LogID INT PRIMARY KEY AUTO_INCREMENT,
                DocumentID INT NOT NULL,
                MemberID INT NOT NULL,
                Action ENUM('VIEW','DOWNLOAD','UPLOAD','EDIT','DELETE','SHARE','PERMISSION_CHANGE') NOT NULL,
                IPAddress VARCHAR(45),
                UserAgent VARCHAR(255),
                AccessTimestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_{accesslog_table}_document
                    FOREIGN KEY (DocumentID) REFERENCES {document_table}(DocumentID)
                    ON UPDATE CASCADE ON DELETE CASCADE,
                KEY idx_log_member_ts (MemberID, AccessTimestamp),
                KEY idx_log_doc_ts (DocumentID, AccessTimestamp)
            )
            """
        )


def fetch_legacy_rows(db, table_name, columns):
    """Load the legacy rows that need to be redistributed onto the shards."""
    column_sql = ", ".join(columns)
    with db.cursor() as cur:
        cur.execute(f"SELECT {column_sql} FROM {table_name}")
        return cur.fetchall()


def group_rows_by_shard(rows):
    """Group rows using the assignment's hash rule on DocumentID."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[_document_shard_id(row["DocumentID"])].append(row)
    return grouped


def insert_rows(db, table_name, columns, rows):
    """Bulk insert rows idempotently."""
    if not rows:
        return

    placeholders = ", ".join(["%s"] * len(columns))
    column_sql = ", ".join(columns)
    values = [tuple(row[column] for column in columns) for row in rows]
    with db.cursor() as cur:
        cur.executemany(
            f"INSERT IGNORE INTO {table_name} ({column_sql}) VALUES ({placeholders})",
            values,
        )


def backfill_directory_and_sequence(db, document_rows):
    """Populate the coordinator-side shard directory and ID sequence."""
    with db.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO DocumentShardDirectory (DocumentID, ShardID, Origin)
            VALUES (%s, %s, 'migration')
            ON DUPLICATE KEY UPDATE ShardID = VALUES(ShardID), Origin = VALUES(Origin)
            """,
            [(row["DocumentID"], _document_shard_id(row["DocumentID"])) for row in document_rows],
        )
        cur.executemany(
            "INSERT IGNORE INTO DocumentIdSequence (DocumentID) VALUES (%s)",
            [(row["DocumentID"],) for row in document_rows],
        )


def print_distribution(coordinator_db):
    """Summarize the final document count on each shard."""
    print("Shard document distribution")
    total = 0
    for shard_id in range(DOCUMENT_SHARD_COUNT):
        document_table = _document_table_name(shard_id=shard_id)
        shard_db = get_shard_db(shard_id)
        try:
            with shard_db.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) AS cnt FROM {document_table}")
                count = cur.fetchone()["cnt"]
        finally:
            shard_db.close()
        total += count
        print(f"  Shard {shard_id}: {count} documents")

    with coordinator_db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS cnt FROM Document")
        legacy_count = cur.fetchone()["cnt"]
    print(f"  Total across shards: {total}")
    print(f"  Legacy coordinator count: {legacy_count}")


def main():
    if SHARD_MODE != "remote_databases":
        raise SystemExit(
            "remote_sharding_setup.py is intended for SAFEDOCS_SHARD_MODE=remote_databases. "
            "For the local logical-table simulation, use Module_B/sql/sharding_setup.sql instead."
        )

    coordinator_db = get_db()
    shard_dbs = [get_shard_db(shard_id) for shard_id in range(DOCUMENT_SHARD_COUNT)]
    try:
        ensure_coordinator_tables(coordinator_db)
        for shard_id, shard_db in enumerate(shard_dbs):
            ensure_shard_tables(shard_db, shard_id)

        document_rows = fetch_legacy_rows(coordinator_db, "Document", DOCUMENT_COLUMNS)
        accesslog_rows = fetch_legacy_rows(coordinator_db, "AccessLog", ACCESSLOG_COLUMNS)

        grouped_documents = group_rows_by_shard(document_rows)
        grouped_logs = group_rows_by_shard(accesslog_rows)

        for shard_id, shard_db in enumerate(shard_dbs):
            insert_rows(
                shard_db,
                _document_table_name(shard_id=shard_id),
                DOCUMENT_COLUMNS,
                grouped_documents[shard_id],
            )
            insert_rows(
                shard_db,
                _accesslog_table_name(shard_id=shard_id),
                ACCESSLOG_COLUMNS,
                grouped_logs[shard_id],
            )

        backfill_directory_and_sequence(coordinator_db, document_rows)

        for shard_db in shard_dbs:
            shard_db.commit()
        coordinator_db.commit()

        print("Remote shard setup completed successfully.")
        print_distribution(coordinator_db)
    except Exception:
        for shard_db in shard_dbs:
            shard_db.rollback()
        coordinator_db.rollback()
        raise
    finally:
        for shard_db in shard_dbs:
            shard_db.close()
        coordinator_db.close()


if __name__ == "__main__":
    main()
