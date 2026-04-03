"""
Assignment 3 ACID and recovery demonstration for Module A.

Run from the Module_A directory:
    python3 assignment3_demo.py
"""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

from database import (
    ConstraintViolation,
    SimulatedCrashError,
    TransactionCoordinator,
    TransactionError,
)


BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = BASE_DIR / "runtime" / "assignment3"


def scenario_dir(name: str) -> Path:
    path = RUNTIME_DIR / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def bootstrap_engine(storage_dir: Path, initial_stock: int = 5) -> TransactionCoordinator:
    engine = TransactionCoordinator(storage_dir)
    engine.reset_storage()
    engine.create_database("shop")
    engine.create_table(
        "shop",
        "users",
        schema={"user_id": int, "name": str, "balance": float},
        order=4,
        search_key="user_id",
    )
    engine.create_table(
        "shop",
        "products",
        schema={"product_id": int, "name": str, "stock": int, "price": float},
        order=4,
        search_key="product_id",
    )
    engine.create_table(
        "shop",
        "orders",
        schema={"order_id": int, "user_id": int, "product_id": int, "quantity": int, "total": float},
        order=4,
        search_key="order_id",
    )

    with engine.begin("seed initial records") as tx:
        tx.insert("shop", "users", {"user_id": 1, "name": "Alice", "balance": 1000.0})
        tx.insert("shop", "users", {"user_id": 2, "name": "Bob", "balance": 1000.0})
        tx.insert(
            "shop",
            "products",
            {"product_id": 101, "name": "Laptop", "stock": initial_stock, "price": 250.0},
        )
        tx.insert(
            "shop",
            "products",
            {"product_id": 102, "name": "Phone", "stock": 10, "price": 125.0},
        )
        tx.commit()

    return engine


def get_record(engine: TransactionCoordinator, table_name: str, record_id: int):
    snapshot = engine.snapshot()
    table, _ = snapshot.get_table("shop", table_name)
    return table.get(record_id)


def get_table_rows(engine: TransactionCoordinator, table_name: str):
    snapshot = engine.snapshot()
    table, _ = snapshot.get_table("shop", table_name)
    return table.get_all()


def purchase_product(
    engine: TransactionCoordinator,
    order_id: int,
    user_id: int,
    product_id: int,
    quantity: int,
    simulate_failure: str | None = None,
    simulate_crash_after_journal: bool = False,
):
    with engine.begin(f"purchase order {order_id}") as tx:
        user = tx.get("shop", "users", user_id)
        product = tx.get("shop", "products", product_id)

        tx.require(user is not None, f"user {user_id} does not exist")
        tx.require(product is not None, f"product {product_id} does not exist")
        tx.require(quantity > 0, "quantity must be positive")

        total = float(quantity) * float(product["price"])
        tx.require(user["balance"] >= total, "insufficient balance")
        tx.require(product["stock"] >= quantity, "insufficient stock")

        tx.update("shop", "users", user_id, {"balance": float(user["balance"]) - total})
        if simulate_failure == "after_balance":
            raise RuntimeError("Injected failure after updating user balance")

        tx.update("shop", "products", product_id, {"stock": int(product["stock"]) - quantity})
        if simulate_failure == "after_stock":
            raise RuntimeError("Injected failure after updating product stock")

        tx.insert(
            "shop",
            "orders",
            {
                "order_id": order_id,
                "user_id": user_id,
                "product_id": product_id,
                "quantity": quantity,
                "total": total,
            },
        )
        tx.commit(simulate_crash_after_journal=simulate_crash_after_journal)


def atomicity_demo():
    engine = bootstrap_engine(scenario_dir("atomicity"))
    before_user = get_record(engine, "users", 1)
    before_product = get_record(engine, "products", 101)

    try:
        purchase_product(
            engine,
            order_id=5001,
            user_id=1,
            product_id=101,
            quantity=1,
            simulate_failure="after_balance",
        )
    except RuntimeError:
        pass

    after_user = get_record(engine, "users", 1)
    after_product = get_record(engine, "products", 101)
    orders = get_table_rows(engine, "orders")

    assert before_user == after_user, "Atomicity failed: user balance changed after rollback"
    assert before_product == after_product, "Atomicity failed: product stock changed after rollback"
    assert orders == [], "Atomicity failed: order row persisted after rollback"
    return "Atomicity verified: injected mid-transaction failure leaves all three tables unchanged."


def consistency_demo():
    engine = bootstrap_engine(scenario_dir("consistency"))
    before_user = get_record(engine, "users", 1)
    before_product = get_record(engine, "products", 101)

    try:
        purchase_product(
            engine,
            order_id=5002,
            user_id=1,
            product_id=101,
            quantity=99,
        )
    except ConstraintViolation as exc:
        message = str(exc)
    else:
        raise AssertionError("Consistency check failed: invalid purchase unexpectedly committed")

    after_user = get_record(engine, "users", 1)
    after_product = get_record(engine, "products", 101)
    assert before_user == after_user, "Consistency failed: user record changed after rejected transaction"
    assert before_product == after_product, "Consistency failed: product record changed after rejected transaction"
    assert get_table_rows(engine, "orders") == [], "Consistency failed: order inserted for invalid transaction"
    return f"Consistency verified: invalid transaction rejected with '{message}'."


def isolation_demo():
    engine = bootstrap_engine(scenario_dir("isolation"), initial_stock=1)
    barrier = threading.Barrier(3)
    results = []
    results_lock = threading.Lock()

    def worker(order_id, user_id):
        barrier.wait()
        start = time.perf_counter()
        try:
            purchase_product(engine, order_id, user_id, 101, 1)
            result = {"order_id": order_id, "status": "committed"}
        except ConstraintViolation as exc:
            result = {"order_id": order_id, "status": "rolled_back", "reason": str(exc)}
        except TransactionError as exc:
            result = {"order_id": order_id, "status": "error", "reason": str(exc)}
        result["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 2)
        with results_lock:
            results.append(result)

    threads = [
        threading.Thread(target=worker, args=(6001, 1), name="buyer-1"),
        threading.Thread(target=worker, args=(6002, 2), name="buyer-2"),
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    committed = [item for item in results if item["status"] == "committed"]
    rolled_back = [item for item in results if item["status"] == "rolled_back"]
    final_product = get_record(engine, "products", 101)
    final_orders = get_table_rows(engine, "orders")

    assert len(committed) == 1, f"Isolation failed: expected 1 commit, saw {results}"
    assert len(rolled_back) == 1, f"Isolation failed: expected 1 rollback, saw {results}"
    assert final_product["stock"] == 0, "Isolation failed: stock was oversold"
    assert len(final_orders) == 1, "Isolation failed: more than one order committed for stock=1"
    return (
        "Isolation verified: concurrent buyers are serialized, "
        f"with one commit and one rollback ({results})."
    )


def durability_demo():
    storage_dir = scenario_dir("durability")
    engine = bootstrap_engine(storage_dir)
    purchase_product(engine, order_id=7001, user_id=1, product_id=101, quantity=2)

    recovered_engine = TransactionCoordinator(storage_dir)
    recovered_user = get_record(recovered_engine, "users", 1)
    recovered_product = get_record(recovered_engine, "products", 101)
    recovered_order = get_record(recovered_engine, "orders", 7001)

    assert recovered_user["balance"] == 500.0, "Durability failed: committed balance change was lost"
    assert recovered_product["stock"] == 3, "Durability failed: committed stock change was lost"
    assert recovered_order is not None, "Durability failed: committed order row was lost"
    return "Durability verified: committed purchase survives a fresh engine restart."


def recovery_of_incomplete_demo():
    storage_dir = scenario_dir("recovery_incomplete")
    engine = bootstrap_engine(storage_dir)

    tx = engine.begin("incomplete transaction")
    tx.update("shop", "users", 1, {"balance": 10.0})
    tx.update("shop", "products", 101, {"stock": 0})
    tx.insert(
        "shop",
        "orders",
        {"order_id": 8001, "user_id": 1, "product_id": 101, "quantity": 1, "total": 250.0},
    )

    recovered_engine = TransactionCoordinator(storage_dir)
    recovery_info = recovered_engine.last_recovery
    user = get_record(recovered_engine, "users", 1)
    product = get_record(recovered_engine, "products", 101)
    order = get_record(recovered_engine, "orders", 8001)

    assert user["balance"] == 1000.0, "Recovery failed: incomplete transaction changed user balance"
    assert product["stock"] == 5, "Recovery failed: incomplete transaction changed product stock"
    assert order is None, "Recovery failed: incomplete transaction inserted an order"
    assert recovery_info["incomplete_transactions"], "Recovery metadata missed the incomplete transaction"
    return "Recovery verified: BEGIN without COMMIT is ignored after restart."


def recovery_from_journal_demo():
    storage_dir = scenario_dir("journal_recovery")
    engine = bootstrap_engine(storage_dir)

    try:
        purchase_product(
            engine,
            order_id=9001,
            user_id=1,
            product_id=101,
            quantity=1,
            simulate_crash_after_journal=True,
        )
    except SimulatedCrashError:
        pass

    recovered_engine = TransactionCoordinator(storage_dir)
    user = get_record(recovered_engine, "users", 1)
    product = get_record(recovered_engine, "products", 101)
    order = get_record(recovered_engine, "orders", 9001)

    assert user["balance"] == 750.0, "Journal recovery failed: committed balance change was not recovered"
    assert product["stock"] == 4, "Journal recovery failed: committed stock change was not recovered"
    assert order is not None, "Journal recovery failed: committed order row was not recovered"
    return "Recovery verified: journaled COMMIT is replayed even if the snapshot write is interrupted."


def main():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    demos = [
        ("Atomicity", atomicity_demo),
        ("Consistency", consistency_demo),
        ("Isolation", isolation_demo),
        ("Durability", durability_demo),
        ("Recovery - Incomplete Transaction", recovery_of_incomplete_demo),
        ("Recovery - Journal Replay", recovery_from_journal_demo),
    ]

    print("Assignment 3 Module A demonstration")
    print("=" * 44)

    for title, demo in demos:
        message = demo()
        print(f"[PASS] {title}: {message}")

    print("=" * 44)
    print(f"Runtime artifacts stored in: {RUNTIME_DIR}")


if __name__ == "__main__":
    main()
