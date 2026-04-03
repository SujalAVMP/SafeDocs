"""
Persistence helpers for Assignment 3 transaction durability and recovery.

The committed database state is checkpointed to a JSON snapshot, and each
transaction lifecycle event is appended to a JSONL journal.  The journal stores
the full committed B+ Tree-backed database image for each COMMIT so recovery can
reconstruct the latest durable state after a crash.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .db_manager import DatabaseManager


class SnapshotJournalStore:
    """Persist committed database states and recover the latest durable image."""

    def __init__(self, storage_dir):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_path = self.storage_dir / "snapshot.json"
        self.journal_path = self.storage_dir / "journal.jsonl"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_manager(self):
        """
        Load the most recent committed database image and recovery metadata.

        Recovery rule:
        - Start from the last checkpoint snapshot if one exists.
        - Replay the most recent committed state found in the journal.
        - Ignore transactions that have BEGIN but no COMMIT.
        """
        base_payload = self._load_snapshot_payload()
        latest_commit_state = None
        begun = set()
        committed = []
        rolled_back = set()
        ignored_lines = 0

        if self.journal_path.exists():
            with self.journal_path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        ignored_lines += 1
                        continue

                    tx_id = entry.get("tx_id")
                    entry_type = entry.get("type")

                    if entry_type == "BEGIN":
                        if tx_id:
                            begun.add(tx_id)
                    elif entry_type == "ROLLBACK":
                        if tx_id:
                            rolled_back.add(tx_id)
                    elif entry_type == "COMMIT" and tx_id:
                        begun.add(tx_id)
                        committed.append(tx_id)
                        latest_commit_state = entry.get("state")

        manager = DatabaseManager.from_dict(latest_commit_state or base_payload)
        incomplete = sorted(tx_id for tx_id in begun if tx_id not in committed and tx_id not in rolled_back)
        return manager, {
            "committed_transactions": committed,
            "incomplete_transactions": incomplete,
            "ignored_journal_lines": ignored_lines,
        }

    def record_begin(self, tx_id, description=None):
        """Append a transaction BEGIN entry to the journal."""
        self._append_entry({
            "type": "BEGIN",
            "tx_id": tx_id,
            "description": description,
        })

    def record_commit(self, tx_id, manager_payload, description=None):
        """Append a durable COMMIT entry containing the committed database image."""
        self._append_entry({
            "type": "COMMIT",
            "tx_id": tx_id,
            "description": description,
            "state": manager_payload,
        })

    def record_rollback(self, tx_id, reason=None):
        """Append a ROLLBACK entry to the journal."""
        self._append_entry({
            "type": "ROLLBACK",
            "tx_id": tx_id,
            "reason": reason,
        })

    def write_snapshot(self, manager_payload):
        """Atomically checkpoint the latest committed database image."""
        self._write_json_atomic(self.snapshot_path, manager_payload)

    def reset(self):
        """Delete persisted state for a clean test run."""
        for path in (self.snapshot_path, self.journal_path):
            if path.exists():
                path.unlink()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_snapshot_payload(self):
        if not self.snapshot_path.exists():
            return {"databases": {}}
        with self.snapshot_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _append_entry(self, payload):
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        with self.journal_path.open("a", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _write_json_atomic(self, path: Path, payload: Any):
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=True, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        self._fsync_directory(path.parent)

    @staticmethod
    def _fsync_directory(directory: Path):
        try:
            fd = os.open(directory, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
