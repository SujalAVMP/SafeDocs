"""
Assignment 3 concurrency, rollback, and load test harness for Module B.

Run after starting the Flask app:
    cd Module_B
    python3 stress/assignment3_stress.py
"""

from __future__ import annotations

import json
import os
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


BASE_URL = os.environ.get("SAFEDOCS_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
REQUEST_TIMEOUT = 15


class ApiError(RuntimeError):
    """Raised when the local SafeDocs API cannot be reached or parsed."""


def log_step(message):
    """Print a single human-readable progress line."""
    print(f"    - {message}")


def api_request(method, path, token=None, payload=None, query=None):
    """Perform a JSON API request and return status, body, and elapsed time."""
    url = f"{BASE_URL}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"

    data = None
    headers = {
        "Accept": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            raw_body = response.read().decode("utf-8")
            elapsed_ms = (time.perf_counter() - start) * 1000
            body = json.loads(raw_body) if raw_body else None
            return response.status, body, elapsed_ms
    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8")
        elapsed_ms = (time.perf_counter() - start) * 1000
        try:
            body = json.loads(raw_body) if raw_body else None
        except json.JSONDecodeError:
            body = {"error": raw_body}
        return exc.code, body, elapsed_ms
    except urllib.error.URLError as exc:
        raise ApiError(f"Could not reach SafeDocs at {BASE_URL}: {exc}") from exc


def login(username, password):
    """Authenticate and return a bearer token."""
    status, body, _ = api_request(
        "POST",
        "/login",
        payload={"user": username, "password": password},
    )
    if status != 200 or not body or "session_token" not in body:
        raise ApiError(f"Login failed for {username}: status={status}, body={body}")
    return body["session_token"]


def percentile(values, p):
    """Return a simple nearest-rank percentile from a non-empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((p / 100) * (len(ordered) - 1))))
    return ordered[index]


def fetch_first_folder_id(token):
    """Use the folders API to find an active target folder for document tests."""
    status, body, _ = api_request("GET", "/api/folders", token=token)
    if status != 200 or not body:
        raise ApiError(f"Unable to fetch folders: status={status}, body={body}")
    return body[0]["FolderID"]


def create_temp_document(token, folder_id, title):
    """Create a temporary document and return its DocumentID."""
    status, body, _ = api_request(
        "POST",
        "/api/documents",
        token=token,
        payload={
            "Title": title,
            "Description": "Assignment 3 stress-test document",
            "FolderID": folder_id,
            "FileSize": 2048,
        },
    )
    if status != 201:
        raise ApiError(f"Document creation failed: status={status}, body={body}")
    return body["DocumentID"]


def rollback_scenario(admin_token):
    """
    Trigger a mid-request failure in /api/members.

    The route inserts into Member first and then UserLogin.  Reusing the
    existing 'admin' username causes the second insert to fail, which should
    rollback the first insert and leave no partial member row behind.
    """
    print("\n[Rollback Integrity] Preparing duplicate-username rollback scenario.")
    unique_name = f"RollbackCandidate_{int(time.time() * 1000)}"
    unique_email = f"{unique_name.lower()}@example.com"
    log_step(f"Generated temporary member identity: name={unique_name}, email={unique_email}.")

    before_status, before_body, _ = api_request(
        "GET",
        "/api/members",
        token=admin_token,
        query={"name": unique_name},
    )
    if before_status != 200 or before_body != []:
        raise ApiError(f"Unexpected precondition for rollback test: {before_status}, {before_body}")
    log_step("Pre-check complete: no matching member exists before the create request.")

    status, body, elapsed_ms = api_request(
        "POST",
        "/api/members",
        token=admin_token,
        payload={
            "Name": unique_name,
            "Email": unique_email,
            "ContactNumber": "9999999999",
            "DepartmentID": 1,
            "RoleID": 2,
            "Username": "admin",
            "Password": "temp123",
            "Age": 28,
        },
    )
    log_step(
        f"Create request completed in {round(elapsed_ms, 2)} ms with status={status} "
        "after reusing the existing username 'admin'."
    )
    if isinstance(body, dict) and body.get("error"):
        log_step(f"API reported: {body['error']}.")

    after_status, after_body, _ = api_request(
        "GET",
        "/api/members",
        token=admin_token,
        query={"name": unique_name},
    )
    log_step(
        f"Post-check complete: matching members after rollback={len(after_body) if isinstance(after_body, list) else 'n/a'}."
    )

    success = status == 409 and after_status == 200 and after_body == []
    return {
        "name": "rollback_integrity",
        "success": success,
        "status": status,
        "elapsed_ms": round(elapsed_ms, 2),
        "response": body,
        "post_check_count": len(after_body) if isinstance(after_body, list) else None,
    }


def delete_race_scenario(admin_token, folder_id, workers=8):
    """
    Race many concurrent delete requests against the same document.

    Correct behaviour:
    - exactly one request succeeds with 200
    - the remaining requests observe the already-deleted document and fail cleanly
    """
    print("\n[Delete Race] Preparing concurrent delete scenario.")
    log_step(f"Creating a temporary document in folder {folder_id} for the delete race.")
    document_id = create_temp_document(
        admin_token,
        folder_id,
        title=f"RaceDelete_{int(time.time() * 1000)}",
    )
    log_step(f"Temporary document created with DocumentID={document_id}.")
    log_step(f"Launching {workers} concurrent delete requests against the same document.")

    def delete_once():
        status, body, elapsed_ms = api_request(
            "DELETE",
            f"/api/documents/{document_id}",
            token=admin_token,
        )
        return {"status": status, "body": body, "elapsed_ms": round(elapsed_ms, 2)}

    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(delete_once) for _ in range(workers)]
        for future in as_completed(futures):
            results.append(future.result())

    final_status, final_body, _ = api_request(
        "GET",
        f"/api/documents/{document_id}",
        token=admin_token,
    )

    success_count = sum(1 for item in results if item["status"] == 200)
    not_found_count = sum(1 for item in results if item["status"] == 404)
    success = success_count == 1 and success_count + not_found_count == len(results) and final_status == 404
    log_step(
        f"Delete race finished: 200 responses={success_count}, 404 responses={not_found_count}, "
        f"other responses={len(results) - success_count - not_found_count}."
    )
    log_step(f"Final GET returned status={final_status}, confirming the document is no longer active.")

    return {
        "name": "delete_race",
        "success": success,
        "document_id": document_id,
        "workers": workers,
        "status_breakdown": {
            "200": success_count,
            "404": not_found_count,
        },
        "final_get_status": final_status,
        "final_get_body": final_body,
    }


def load_scenario(admin_token, viewer_token, total_requests=240, workers=24):
    """
    Generate sustained mixed API load and summarize latency and correctness.

    The mix intentionally leans read-heavy so the test can scale to hundreds of
    requests without filling the database with temporary rows.
    """
    print("\n[Mixed Load] Preparing read-heavy API load scenario.")
    request_plan = []
    for i in range(total_requests):
        mod = i % 4
        if mod == 0:
            request_plan.append(("GET", "/api/documents", admin_token, None))
        elif mod == 1:
            request_plan.append(("GET", "/api/members", admin_token, None))
        elif mod == 2:
            request_plan.append(("GET", "/api/folders", viewer_token, None))
        else:
            request_plan.append(("GET", "/api/security-logs", admin_token, {"session_valid": "true"}))
    log_step(
        f"Prepared {total_requests} total requests across {workers} workers "
        "with a repeated mix of documents, members, folders, and security logs."
    )
    log_step("Starting concurrent load execution.")

    latencies = []
    statuses = {}
    failures = []

    def do_request(entry):
        method, path, token, query = entry
        return api_request(method, path, token=token, query=query)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(do_request, item) for item in request_plan]
        for future in as_completed(futures):
            status, body, elapsed_ms = future.result()
            latencies.append(elapsed_ms)
            statuses[status] = statuses.get(status, 0) + 1
            if status >= 500:
                failures.append({"status": status, "body": body})
    wall_clock_ms = (time.perf_counter() - started) * 1000
    average_latency_ms = round(statistics.mean(latencies), 2)
    median_latency_ms = round(statistics.median(latencies), 2)
    p95_latency_ms = round(percentile(latencies, 95), 2)
    max_latency_ms = round(max(latencies), 2)
    log_step(f"Load execution finished with status breakdown={statuses} and server_failures={len(failures)}.")
    log_step(
        "Latency summary: "
        f"avg={average_latency_ms} ms, median={median_latency_ms} ms, "
        f"p95={p95_latency_ms} ms, max={max_latency_ms} ms, wall_clock={round(wall_clock_ms, 2)} ms."
    )

    return {
        "name": "mixed_load",
        "success": failures == [] and sum(statuses.values()) == total_requests,
        "total_requests": total_requests,
        "workers": workers,
        "status_breakdown": statuses,
        "average_latency_ms": average_latency_ms,
        "median_latency_ms": median_latency_ms,
        "p95_latency_ms": p95_latency_ms,
        "max_latency_ms": max_latency_ms,
        "wall_clock_ms": round(wall_clock_ms, 2),
        "server_failures": failures,
    }


def print_result(result):
    status = "PASS" if result["success"] else "FAIL"
    print(f"[{status}] {result['name']}")
    print(json.dumps(result, indent=2, sort_keys=True))


def main():
    print(f"SafeDocs Assignment 3 stress harness")
    print(f"Target base URL: {BASE_URL}")
    log_step("Authenticating admin user.")
    admin_token = login("admin", "admin123")
    log_step("Admin session token acquired.")
    log_step("Authenticating viewer user.")
    viewer_token = login("priya", "priya123")
    log_step("Viewer session token acquired.")
    log_step("Fetching an active folder for document scenarios.")
    folder_id = fetch_first_folder_id(admin_token)
    log_step(f"Using FolderID={folder_id} for document-based tests.")

    print("=" * 60)
    results = []
    scenario_runners = [
        lambda: rollback_scenario(admin_token),
        lambda: delete_race_scenario(admin_token, folder_id),
        lambda: load_scenario(admin_token, viewer_token),
    ]
    for run_scenario in scenario_runners:
        result = run_scenario()
        results.append(result)
        print_result(result)
        print("-" * 60)

    overall = all(result["success"] for result in results)
    print(f"Overall result: {'PASS' if overall else 'FAIL'}")
    if not overall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
