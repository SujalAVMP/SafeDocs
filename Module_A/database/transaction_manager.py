"""
Transaction manager for Assignment 3.

This layer wraps the existing DatabaseManager/Table/B+ Tree stack with:
- BEGIN / COMMIT / ROLLBACK
- serialized transaction execution via a global re-entrant lock
- durable commit journaling and checkpoint snapshots
- restart recovery from the latest durable committed state
"""

from __future__ import annotations

import threading
import uuid

from .db_manager import DatabaseManager
from .persistence import SnapshotJournalStore


class TransactionError(RuntimeError):
    """Base error for transaction-management failures."""


class ConstraintViolation(TransactionError):
    """Raised when a transaction would violate a business/data invariant."""


class TransactionClosedError(TransactionError):
    """Raised when an operation is attempted on a closed transaction."""


class SimulatedCrashError(TransactionError):
    """Raised to emulate a crash immediately after the journaled commit."""


class Transaction:
    """A staged multi-table transaction working on a cloned database image."""

    def __init__(self, coordinator, tx_id, working_manager, description=None):
        self._coordinator = coordinator
        self.tx_id = tx_id
        self.description = description
        self._working_manager = working_manager
        self._active = True

    def _ensure_active(self):
        if not self._active:
            raise TransactionClosedError("Transaction is no longer active")

    def create_database(self, db_name):
        self._ensure_active()
        return self._working_manager.create_database(db_name)

    def create_table(self, db_name, table_name, schema, order=8, search_key=None):
        self._ensure_active()
        return self._working_manager.create_table(
            db_name,
            table_name,
            schema,
            order=order,
            search_key=search_key,
        )

    def get_table(self, db_name, table_name):
        self._ensure_active()
        table, message = self._working_manager.get_table(db_name, table_name)
        if table is None:
            raise TransactionError(message)
        return table

    def insert(self, db_name, table_name, record):
        table = self.get_table(db_name, table_name)
        ok, message = table.insert(record)
        if not ok:
            raise TransactionError(message)
        return message

    def update(self, db_name, table_name, record_id, new_record):
        table = self.get_table(db_name, table_name)
        ok, message = table.update(record_id, new_record)
        if not ok:
            raise TransactionError(message)
        return message

    def delete(self, db_name, table_name, record_id):
        table = self.get_table(db_name, table_name)
        ok, message = table.delete(record_id)
        if not ok:
            raise TransactionError(message)
        return message

    def get(self, db_name, table_name, record_id):
        table = self.get_table(db_name, table_name)
        return table.get(record_id)

    def require(self, condition, message):
        """Abort the transaction if a consistency rule is violated."""
        if not condition:
            raise ConstraintViolation(message)

    def commit(self, simulate_crash_after_journal=False):
        """Commit the staged database image."""
        self._ensure_active()
        self._coordinator._commit_transaction(
            self,
            simulate_crash_after_journal=simulate_crash_after_journal,
        )

    def rollback(self, reason=None):
        """Discard the staged database image."""
        if self._active:
            self._coordinator._rollback_transaction(self, reason=reason)

    def __enter__(self):
        self._ensure_active()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is not None and self._active:
            self.rollback(reason=str(exc))
            return False
        if self._active:
            self.rollback(reason="context exited without commit")
        return False


class TransactionCoordinator:
    """
    Durable transaction coordinator for the B+ Tree-backed database manager.

    Isolation strategy:
    - one transaction at a time via a global RLock
    - each transaction works on a cloned database image
    - live state changes only when COMMIT succeeds
    """

    def __init__(self, storage_dir):
        self._lock = threading.RLock()
        self._store = SnapshotJournalStore(storage_dir)
        self._database_manager, self.last_recovery = self._store.load_manager()

    @property
    def database_manager(self):
        """Expose the current live database manager."""
        return self._database_manager

    def snapshot(self):
        """Return a safe cloned view of the current live state."""
        with self._lock:
            return self._database_manager.clone()

    def begin(self, description=None):
        """
        Begin a new serialized transaction and return its staged view.

        The lock is held until COMMIT or ROLLBACK so concurrent transactions
        are serialized, which satisfies the assignment's isolation requirement.
        """
        self._lock.acquire()
        tx_id = uuid.uuid4().hex
        try:
            self._store.record_begin(tx_id, description=description)
            staged_manager = self._database_manager.clone()
            return Transaction(self, tx_id, staged_manager, description=description)
        except Exception:
            self._lock.release()
            raise

    def recover(self):
        """Reload the latest durable committed state from disk."""
        with self._lock:
            self._database_manager, self.last_recovery = self._store.load_manager()
            return self.last_recovery

    def reset_storage(self):
        """Clear durable state and reset the live database to empty."""
        with self._lock:
            self._store.reset()
            self._database_manager = DatabaseManager()
            self.last_recovery = {
                "committed_transactions": [],
                "incomplete_transactions": [],
                "ignored_journal_lines": 0,
            }

    # ------------------------------------------------------------------
    # DDL helpers outside explicit transactions
    # ------------------------------------------------------------------

    def create_database(self, db_name):
        with self._lock:
            ok, message = self._database_manager.create_database(db_name)
            if ok:
                self._store.write_snapshot(self._database_manager.to_dict())
            return ok, message

    def create_table(self, db_name, table_name, schema, order=8, search_key=None):
        with self._lock:
            ok, message = self._database_manager.create_table(
                db_name,
                table_name,
                schema,
                order=order,
                search_key=search_key,
            )
            if ok:
                self._store.write_snapshot(self._database_manager.to_dict())
            return ok, message

    def get_table(self, db_name, table_name):
        with self._lock:
            return self._database_manager.get_table(db_name, table_name)

    def list_databases(self):
        with self._lock:
            return self._database_manager.list_databases()

    def list_tables(self, db_name):
        with self._lock:
            return self._database_manager.list_tables(db_name)

    # ------------------------------------------------------------------
    # Internal commit/rollback machinery
    # ------------------------------------------------------------------

    def _commit_transaction(self, transaction, simulate_crash_after_journal=False):
        state = transaction._working_manager.to_dict()
        try:
            self._store.record_commit(
                transaction.tx_id,
                state,
                description=transaction.description,
            )
        except Exception:
            try:
                self._store.record_rollback(
                    transaction.tx_id,
                    reason="commit_failed_before_durable_write",
                )
            except Exception:
                pass
            transaction._active = False
            self._lock.release()
            raise

        self._database_manager = transaction._working_manager
        transaction._active = False

        try:
            if simulate_crash_after_journal:
                raise SimulatedCrashError(
                    "Simulated crash triggered after durable journal commit"
                )
            self._store.write_snapshot(state)
        finally:
            self._lock.release()

    def _rollback_transaction(self, transaction, reason=None):
        try:
            self._store.record_rollback(transaction.tx_id, reason=reason)
        finally:
            transaction._active = False
            self._lock.release()
