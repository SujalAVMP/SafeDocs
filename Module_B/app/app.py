"""
SafeDocs Module B - Main Flask Application
CS 432 - Databases | Assignment 2 | Track 1
IIT Gandhinagar | Semester II (2025-2026)

Features:
  - JWT session-based authentication
  - Role-based access control (Admin, Manager, Editor, Viewer, Auditor)
  - Full CRUD API for Members and Documents
  - Web UI with Bootstrap 5
  - Dual audit logging (SecurityLog table + audit.log)
"""

import datetime
import os
from contextlib import contextmanager
from pathlib import Path

import pymysql
from flask import (
    Flask, request, jsonify, render_template,
    redirect, url_for, make_response, g, flash
)

try:
    from .auth import (
        hash_password, verify_password,
        create_session_token, verify_session_token, verify_session_token_detailed,
        _get_token_from_request,
        login_required, admin_required, log_action,
    )
except ImportError:
    from auth import (
        hash_password, verify_password,
        create_session_token, verify_session_token, verify_session_token_detailed,
        _get_token_from_request,
        login_required, admin_required, log_action,
    )

try:
    from .assignment3_console import Assignment3Console
except ImportError:
    from assignment3_console import Assignment3Console

# ===================================================================
# Flask app setup
# ===================================================================
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "safedocs-flask-secret-cs432")
MODULE_B_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE_B_DIR.parent
ASSIGNMENT3_CONSOLE = Assignment3Console(REPO_ROOT, MODULE_B_DIR)

DOCUMENT_SHARD_COUNT = 3
DOCUMENT_SHARD_TABLES = [f"shard_{idx}_document" for idx in range(DOCUMENT_SHARD_COUNT)]
ACCESSLOG_SHARD_TABLES = [f"shard_{idx}_accesslog" for idx in range(DOCUMENT_SHARD_COUNT)]
SHARD_MODE = os.environ.get("SAFEDOCS_SHARD_MODE", "local_tables").strip().lower()
REMOTE_DOCUMENT_TABLE = os.environ.get("SAFEDOCS_REMOTE_DOCUMENT_TABLE", "Document")
REMOTE_ACCESSLOG_TABLE = os.environ.get("SAFEDOCS_REMOTE_ACCESSLOG_TABLE", "AccessLog")


def _env_int(name, default):
    """Read an integer environment variable with a fallback."""
    value = os.environ.get(name)
    if value in (None, ""):
        return default
    return int(value)


def _env_list(name):
    """Split a comma-separated environment variable into trimmed values."""
    value = os.environ.get(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def _build_connection_config(
    prefix,
    *,
    default_host="localhost",
    default_user="safedocs",
    default_password="safedocs123",
    default_database="safedocs",
    default_port=3306,
    default_socket="/run/mysqld/mysqld.sock",
):
    """Build a PyMySQL connection config from prefixed environment variables."""
    config = {
        "host": os.environ.get(f"{prefix}HOST", default_host),
        "user": os.environ.get(f"{prefix}USER", default_user),
        "password": os.environ.get(f"{prefix}PASSWORD", default_password),
        "database": os.environ.get(f"{prefix}DATABASE", default_database),
        "port": _env_int(f"{prefix}PORT", default_port),
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
    }
    unix_socket = os.environ.get(f"{prefix}UNIX_SOCKET")
    if unix_socket is None:
        unix_socket = default_socket
    if unix_socket:
        config["unix_socket"] = unix_socket
    return config


COORDINATOR_DB_CONFIG = _build_connection_config("SAFEDOCS_DB_")


def _build_remote_shard_configs():
    """Resolve remote shard connection configs from environment variables."""
    base_host = os.environ.get("SAFEDOCS_SHARD_HOST", COORDINATOR_DB_CONFIG["host"])
    base_user = os.environ.get("SAFEDOCS_SHARD_USER", COORDINATOR_DB_CONFIG["user"])
    base_password = os.environ.get("SAFEDOCS_SHARD_PASSWORD", COORDINATOR_DB_CONFIG["password"])
    base_database = os.environ.get("SAFEDOCS_SHARD_DATABASE", COORDINATOR_DB_CONFIG["database"])
    base_port = _env_int("SAFEDOCS_SHARD_PORT", COORDINATOR_DB_CONFIG.get("port", 3306))
    base_socket = os.environ.get("SAFEDOCS_SHARD_UNIX_SOCKET", "")

    ports = _env_list("SAFEDOCS_SHARD_PORTS")
    databases = _env_list("SAFEDOCS_SHARD_DATABASES")

    if ports and len(ports) != DOCUMENT_SHARD_COUNT:
        raise ValueError(
            f"SAFEDOCS_SHARD_PORTS must contain {DOCUMENT_SHARD_COUNT} ports, "
            f"got {len(ports)}."
        )
    if databases and len(databases) != DOCUMENT_SHARD_COUNT:
        raise ValueError(
            f"SAFEDOCS_SHARD_DATABASES must contain {DOCUMENT_SHARD_COUNT} databases, "
            f"got {len(databases)}."
        )

    configs = []
    for shard_id in range(DOCUMENT_SHARD_COUNT):
        config = {
            "host": base_host,
            "user": base_user,
            "password": base_password,
            "database": databases[shard_id] if databases else base_database,
            "port": int(ports[shard_id]) if ports else base_port,
            "cursorclass": pymysql.cursors.DictCursor,
            "autocommit": False,
        }
        if base_socket:
            config["unix_socket"] = base_socket
        configs.append(config)
    return configs


REMOTE_SHARD_CONFIGS = _build_remote_shard_configs()

# ===================================================================
# Database connection helper
# ===================================================================

def get_db():
    """Return a PyMySQL connection to the coordinator database."""
    return pymysql.connect(**COORDINATOR_DB_CONFIG)


def get_shard_db(shard_id):
    """Return a connection to the target shard database."""
    if SHARD_MODE == "remote_databases":
        return pymysql.connect(**REMOTE_SHARD_CONFIGS[shard_id])
    return pymysql.connect(**COORDINATOR_DB_CONFIG)


def _get_transaction_shard_db(shard_id, coordinator_db):
    """Reuse the coordinator DB locally, otherwise open a writable shard DB."""
    if SHARD_MODE == "local_tables":
        return coordinator_db, False
    return get_shard_db(shard_id), True


@contextmanager
def _use_shard_db(shard_id, coordinator_db=None):
    """Reuse the coordinator DB locally, otherwise open a shard connection."""
    if SHARD_MODE == "local_tables" and coordinator_db is not None:
        yield coordinator_db
        return

    shard_db = get_shard_db(shard_id)
    try:
        yield shard_db
    finally:
        shard_db.close()

# ===================================================================
# Helper: fetch current user's role capabilities
# ===================================================================

def _get_role_caps(db, role_id):
    with db.cursor() as cur:
        cur.execute("SELECT * FROM Role WHERE RoleID = %s", (role_id,))
        return cur.fetchone()


def _document_shard_id(document_id):
    """Return the shard id for a document key using the chosen hash strategy."""
    return int(document_id) % DOCUMENT_SHARD_COUNT


def _document_table_name(document_id=None, shard_id=None):
    """Resolve the shard table that stores a document row."""
    resolved_shard_id = _document_shard_id(document_id) if shard_id is None else shard_id
    if SHARD_MODE == "remote_databases":
        return REMOTE_DOCUMENT_TABLE
    return DOCUMENT_SHARD_TABLES[resolved_shard_id]


def _accesslog_table_name(document_id=None, shard_id=None):
    """Resolve the shard table that stores document activity rows."""
    resolved_shard_id = _document_shard_id(document_id) if shard_id is None else shard_id
    if SHARD_MODE == "remote_databases":
        return REMOTE_ACCESSLOG_TABLE
    return ACCESSLOG_SHARD_TABLES[resolved_shard_id]


def _format_datetime_fields(rows, fields):
    """Convert datetime fields to JSON-friendly strings in-place."""
    if isinstance(rows, dict):
        rows = [rows]
    for row in rows:
        for field in fields:
            if row.get(field):
                row[field] = row[field].strftime("%Y-%m-%d %H:%M:%S")


def _reserve_document_id(cur):
    """Allocate a globally unique document id before choosing a shard."""
    cur.execute("INSERT INTO DocumentIdSequence (ReservedAt) VALUES (CURRENT_TIMESTAMP)")
    return cur.lastrowid


def _fetch_lookup_map(db, table_name, key_column, value_column, values):
    """Fetch a {id: label} lookup map from the coordinator database."""
    values = sorted({value for value in values if value is not None})
    if not values:
        return {}

    placeholders = ", ".join(["%s"] * len(values))
    query = (
        f"SELECT {key_column} AS lookup_id, {value_column} AS lookup_value "
        f"FROM {table_name} WHERE {key_column} IN ({placeholders})"
    )
    with db.cursor() as cur:
        cur.execute(query, values)
        return {row["lookup_id"]: row["lookup_value"] for row in cur.fetchall()}


def _enrich_document_rows(db, rows):
    """Attach coordinator-side uploader and folder labels to shard rows."""
    if not rows:
        return rows

    member_names = _fetch_lookup_map(db, "Member", "MemberID", "Name", (row.get("UploadedBy") for row in rows))
    folder_names = _fetch_lookup_map(
        db, "Folder", "FolderID", "FolderName", (row.get("FolderID") for row in rows)
    )
    for row in rows:
        uploaded_by = row.get("UploadedBy")
        folder_id = row.get("FolderID")
        if uploaded_by in member_names:
            row["UploaderName"] = member_names[uploaded_by]
        if folder_id in folder_names:
            row["FolderName"] = folder_names[folder_id]
    return rows


def _list_documents(db, title_filter=None, id_start=None, id_end=None):
    """Read documents across shards and merge them in Python."""
    documents = []
    for shard_id in range(DOCUMENT_SHARD_COUNT):
        table_name = _document_table_name(shard_id=shard_id)
        query = f"""
            SELECT d.DocumentID, d.Title, d.Description, d.FileSize,
                   d.IsConfidential, d.IsActive, d.CreatedAt, d.UpdatedAt,
                   d.UploadedBy, d.FolderID
            FROM {table_name} d
            WHERE d.IsActive = TRUE
        """
        params = []
        if title_filter:
            query += " AND d.Title = %s"
            params.append(title_filter)
        if id_start is not None:
            query += " AND d.DocumentID >= %s"
            params.append(id_start)
        if id_end is not None:
            query += " AND d.DocumentID <= %s"
            params.append(id_end)

        with _use_shard_db(shard_id, coordinator_db=db) as shard_db:
            with shard_db.cursor() as cur:
                cur.execute(query, params)
                shard_rows = cur.fetchall()

        for row in shard_rows:
            row["ShardID"] = shard_id
            documents.append(row)

    _enrich_document_rows(db, documents)
    if id_start is not None or id_end is not None:
        documents.sort(key=lambda row: row["DocumentID"])
    else:
        documents.sort(key=lambda row: row.get("CreatedAt") or datetime.datetime.min, reverse=True)
    return documents


def _list_recent_activity(db, limit, member_id=None):
    """Fetch recent activity across shards and decorate it with member names."""
    rows = []
    per_shard_limit = max(limit, 1)
    for shard_id in range(DOCUMENT_SHARD_COUNT):
        doc_table = _document_table_name(shard_id=shard_id)
        log_table = _accesslog_table_name(shard_id=shard_id)
        query = f"""
            SELECT al.Action, al.AccessTimestamp, al.MemberID, d.Title
            FROM {log_table} al
            JOIN {doc_table} d ON al.DocumentID = d.DocumentID
        """
        params = []
        if member_id is not None:
            query += " WHERE al.MemberID = %s"
            params.append(member_id)
        query += " ORDER BY al.AccessTimestamp DESC LIMIT %s"
        params.append(per_shard_limit)

        with _use_shard_db(shard_id, coordinator_db=db) as shard_db:
            with shard_db.cursor() as cur:
                cur.execute(query, params)
                rows.extend(cur.fetchall())

    member_names = _fetch_lookup_map(db, "Member", "MemberID", "Name", (row["MemberID"] for row in rows))
    for row in rows:
        row["Name"] = member_names.get(row["MemberID"], "Unknown Member")

    rows.sort(key=lambda row: row.get("AccessTimestamp") or datetime.datetime.min, reverse=True)
    return rows[:limit]


def _count_documents(db, uploaded_by=None):
    """Count active documents across all shards, optionally filtered by uploader."""
    total = 0
    for shard_id in range(DOCUMENT_SHARD_COUNT):
        table_name = _document_table_name(shard_id=shard_id)
        query = f"SELECT COUNT(*) AS cnt FROM {table_name} WHERE IsActive = TRUE"
        params = []
        if uploaded_by is not None:
            query += " AND UploadedBy = %s"
            params.append(uploaded_by)

        with _use_shard_db(shard_id, coordinator_db=db) as shard_db:
            with shard_db.cursor() as cur:
                cur.execute(query, params)
                total += cur.fetchone()["cnt"]
    return total


def _fetch_document(db, doc_id, select_columns, active_only=False):
    """Fetch one document row from its target shard and enrich it if needed."""
    shard_id = _document_shard_id(doc_id)
    table_name = _document_table_name(shard_id=shard_id)
    query = f"SELECT {select_columns} FROM {table_name} d WHERE d.DocumentID = %s"
    params = [doc_id]
    if active_only:
        query += " AND d.IsActive = TRUE"

    with _use_shard_db(shard_id, coordinator_db=db) as shard_db:
        with shard_db.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()

    if row is None:
        return None

    row["ShardID"] = shard_id
    _enrich_document_rows(db, [row])
    return row


def _wants_json_response():
    """Treat non-browser root requests as API requests."""
    return "text/html" not in request.headers.get("Accept", "").lower()


def _record_document_activity(db, document_id, action, shard_db=None):
    """Append a document-centric activity row for the current request."""
    shard_id = _document_shard_id(document_id)
    table_name = _accesslog_table_name(shard_id=shard_id)

    if shard_db is not None:
        with shard_db.cursor() as cur:
            cur.execute(
                f"""INSERT INTO {table_name}
                    (DocumentID, MemberID, Action, IPAddress, UserAgent)
                    VALUES (%s, %s, %s, %s, %s)""",
                (
                    document_id,
                    g.member_id,
                    action,
                    request.remote_addr,
                    request.headers.get("User-Agent"),
                ),
            )
        return

    with _use_shard_db(shard_id, coordinator_db=db) as target_db:
        with target_db.cursor() as cur:
            cur.execute(
                f"""INSERT INTO {table_name}
                    (DocumentID, MemberID, Action, IPAddress, UserAgent)
                    VALUES (%s, %s, %s, %s, %s)""",
                (
                    document_id,
                    g.member_id,
                    action,
                    request.remote_addr,
                    request.headers.get("User-Agent"),
                ),
            )


def _assignment3_permissions():
    return {
        "can_view": g.role_id in (1, 5),
        "can_run_module_a": g.role_id in (1, 5),
        "can_run_module_b": g.role_id == 1,
        "can_run_all": g.role_id == 1,
    }


def _assignment3_access_denied():
    if request.path.startswith("/api/"):
        return jsonify({"error": "Access denied"}), 403
    flash("Only Admin and Auditor users can access the Assignment 3 console.", "warning")
    return redirect(url_for("dashboard"))


def _require_assignment3_view_access():
    if not _assignment3_permissions()["can_view"]:
        return _assignment3_access_denied()
    return None

# ===================================================================
# AUTH ROUTES
# ===================================================================

@app.route("/")
def index():
    """Return API welcome JSON or redirect browsers into the UI."""
    if _wants_json_response():
        return jsonify({"message": "Welcome to test APIs"})
    token = _get_token_from_request()
    if token and verify_session_token(token):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login_page"))


@app.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login_submit():
    """Authenticate user via form or JSON, issue JWT session cookie."""
    # Accept both form data and JSON
    if request.is_json:
        data = request.get_json(silent=True) or {}
        username = data.get("user", "") or data.get("username", "")
        password = data.get("password", "")
    else:
        username = request.form.get("username", "")
        password = request.form.get("password", "")

    if not username or not password:
        if request.is_json:
            return jsonify({"error": "Missing parameters"}), 401
        flash("Username and password are required.", "warning")
        return redirect(url_for("login_page"))

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                """SELECT ul.MemberID, ul.PasswordHash,
                          m.Name, m.RoleID, r.RoleName
                   FROM UserLogin ul
                   JOIN Member m ON ul.MemberID = m.MemberID
                   JOIN Role r   ON m.RoleID    = r.RoleID
                   WHERE ul.Username = %s""",
                (username,),
            )
            user = cur.fetchone()

        if not user or not verify_password(password, user["PasswordHash"]):
            log_action(db, None, "LOGIN_FAILED", "UserLogin", None,
                       request.remote_addr, False, f"username={username}")
            if request.is_json:
                return jsonify({"error": "Invalid credentials"}), 401
            flash("Invalid username or password.", "danger")
            return redirect(url_for("login_page"))

        token = create_session_token(user["MemberID"], user["RoleID"], user["RoleName"], user["Name"])
        log_action(db, user["MemberID"], "LOGIN_SUCCESS", "UserLogin", user["MemberID"],
                   request.remote_addr, True, f"username={username}")

        if request.is_json:
            return jsonify({"message": "Login successful",
                            "session_token": token, "member_id": user["MemberID"],
                            "name": user["Name"], "role": user["RoleName"]})

        resp = make_response(redirect(url_for("dashboard")))
        resp.set_cookie("session_token", token, httponly=True, max_age=86400, samesite="Lax")
        return resp

    finally:
        db.close()


@app.route("/logout")
def logout():
    db = get_db()
    try:
        token = _get_token_from_request()
        payload = verify_session_token(token) if token else None
        mid = payload["member_id"] if payload else None
        log_action(db, mid, "LOGOUT", None, None, request.remote_addr, bool(payload))
    finally:
        db.close()
    resp = make_response(redirect(url_for("login_page")))
    resp.delete_cookie("session_token")
    return resp


@app.route("/isAuth")
def is_auth():
    """Check whether the current session is valid."""
    token = _get_token_from_request()
    if not token:
        return jsonify({"error": "No session found"}), 401
    payload, status = verify_session_token_detailed(token)
    if not payload:
        if status == "expired":
            return jsonify({"error": "Session expired"}), 401
        return jsonify({"error": "Invalid session token"}), 401
    return jsonify({
        "message": "User is authenticated",
        "username": payload.get("member_name", ""),
        "role": payload["role_name"],
        "expiry": datetime.datetime.utcfromtimestamp(payload["exp"]).strftime("%Y-%m-%d %H:%M:%S"),
    })

# ===================================================================
# WEB UI ROUTES
# ===================================================================

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    try:
        stats = {}
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM Member WHERE IsActive = TRUE")
            stats["total_members"] = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) AS cnt FROM Folder WHERE IsActive = TRUE")
            stats["total_folders"] = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) AS cnt FROM Department")
            stats["total_departments"] = cur.fetchone()["cnt"]
        stats["total_documents"] = _count_documents(db)
        stats["recent_logs"] = _list_recent_activity(db, limit=10)

        log_action(db, g.member_id, "VIEW_DASHBOARD", None, None,
                   request.remote_addr, True)
        return render_template("dashboard.html", stats=stats,
                               user_name=g.member_name, member_id=g.member_id,
                               role_name=g.role_name, role_id=g.role_id)
    finally:
        db.close()


@app.route("/portfolio")
@app.route("/portfolio/<int:member_id>")
@login_required
def portfolio(member_id=None):
    if member_id is None:
        member_id = g.member_id

    # Non-admin can only view own portfolio
    if g.role_id != 1 and member_id != g.member_id:
        flash("You can only view your own portfolio.", "warning")
        return redirect(url_for("portfolio"))

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                """SELECT m.*, d.DeptName, r.RoleName
                   FROM Member m
                   JOIN Department d ON m.DepartmentID = d.DepartmentID
                   JOIN Role r       ON m.RoleID       = r.RoleID
                   WHERE m.MemberID = %s""",
                (member_id,),
            )
            member = cur.fetchone()
            if not member:
                flash("Member not found.", "danger")
                return redirect(url_for("dashboard"))
        doc_count = _count_documents(db, uploaded_by=member_id)
        recent_activity = _list_recent_activity(db, limit=10, member_id=member_id)

        log_action(db, g.member_id, "VIEW_PORTFOLIO", "Member", member_id,
                   request.remote_addr, True)
        return render_template("portfolio.html", member=member,
                               doc_count=doc_count, recent_activity=recent_activity,
                               user_name=g.member_name, role_name=g.role_name,
                               role_id=g.role_id, member_id=g.member_id)
    finally:
        db.close()


@app.route("/members")
@login_required
def members_page():
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                """SELECT m.MemberID, m.Name, m.Email, m.ContactNumber, m.Age,
                          m.IsActive, d.DeptName, r.RoleName
                   FROM Member m
                   JOIN Department d ON m.DepartmentID = d.DepartmentID
                   JOIN Role r       ON m.RoleID       = r.RoleID
                   ORDER BY m.MemberID"""
            )
            members = cur.fetchall()

        log_action(db, g.member_id, "VIEW_MEMBERS_PAGE", "Member", None,
                   request.remote_addr, True)
        return render_template("members.html", members=members,
                               user_name=g.member_name, role_name=g.role_name,
                               role_id=g.role_id, member_id=g.member_id)
    finally:
        db.close()


@app.route("/members/edit/<int:mid>")
@login_required
def member_edit_page(mid):
    if g.role_id != 1 and mid != g.member_id:
        flash("You can only edit your own profile.", "warning")
        return redirect(url_for("members_page"))

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT * FROM Member WHERE MemberID = %s", (mid,))
            member = cur.fetchone()
            if not member:
                flash("Member not found.", "danger")
                return redirect(url_for("members_page"))
            cur.execute("SELECT * FROM Department ORDER BY DeptName")
            departments = cur.fetchall()
            cur.execute("SELECT * FROM Role ORDER BY RoleID")
            roles = cur.fetchall()
        return render_template("member_edit.html", member=member,
                               departments=departments, roles=roles,
                               user_name=g.member_name, role_name=g.role_name,
                               role_id=g.role_id, member_id=g.member_id)
    finally:
        db.close()


@app.route("/documents")
@login_required
def documents_page():
    db = get_db()
    try:
        documents = _list_documents(db)
        with db.cursor() as cur:
            cur.execute("SELECT FolderID, FolderName FROM Folder WHERE IsActive = TRUE ORDER BY FolderName")
            folders = cur.fetchall()

        log_action(db, g.member_id, "VIEW_DOCUMENTS_PAGE", "Document", None,
                   request.remote_addr, True)
        return render_template("documents.html", documents=documents,
                               folders=folders,
                               user_name=g.member_name, role_name=g.role_name,
                               role_id=g.role_id, member_id=g.member_id)
    finally:
        db.close()


@app.route("/documents/new")
@login_required
def document_new_page():
    # Check upload permission
    db = get_db()
    try:
        caps = _get_role_caps(db, g.role_id)
        if not caps or not caps.get("CanUpload"):
            flash("You do not have permission to create documents.", "warning")
            return redirect(url_for("documents_page"))

        with db.cursor() as cur:
            cur.execute("SELECT FolderID, FolderName FROM Folder WHERE IsActive = TRUE ORDER BY FolderName")
            folders = cur.fetchall()
        return render_template("document_edit.html", document=None,
                               folders=folders,
                               user_name=g.member_name, role_name=g.role_name,
                               role_id=g.role_id, member_id=g.member_id)
    finally:
        db.close()


@app.route("/documents/edit/<int:doc_id>")
@login_required
def document_edit_page(doc_id):
    db = get_db()
    try:
        document = _fetch_document(db, doc_id, "d.*", active_only=True)
        if not document:
            flash("Document not found.", "danger")
            return redirect(url_for("documents_page"))
        with db.cursor() as cur:
            cur.execute("SELECT FolderID, FolderName FROM Folder WHERE IsActive = TRUE ORDER BY FolderName")
            folders = cur.fetchall()
        return render_template("document_edit.html", document=document,
                               folders=folders,
                               user_name=g.member_name, role_name=g.role_name,
                               role_id=g.role_id, member_id=g.member_id)
    finally:
        db.close()

# ===================================================================
# ASSIGNMENT 3 VISUAL TEST CONSOLE
# ===================================================================


@app.route("/assignment3/tests")
@login_required
def assignment3_tests_page():
    access_response = _require_assignment3_view_access()
    if access_response:
        return access_response

    permissions = _assignment3_permissions()
    return render_template(
        "assignment3_tests.html",
        user_name=g.member_name,
        role_name=g.role_name,
        role_id=g.role_id,
        member_id=g.member_id,
        permissions=permissions,
        assignment3_jobs=ASSIGNMENT3_CONSOLE.snapshot(),
    )


@app.route("/api/assignment3/tests/status", methods=["GET"])
@login_required
def api_assignment3_tests_status():
    access_response = _require_assignment3_view_access()
    if access_response:
        return access_response

    return jsonify({
        "jobs": ASSIGNMENT3_CONSOLE.snapshot(),
        "permissions": _assignment3_permissions(),
    })


@app.route("/api/assignment3/tests/run/module-a", methods=["POST"])
@login_required
def api_assignment3_run_module_a():
    access_response = _require_assignment3_view_access()
    if access_response:
        return access_response

    permissions = _assignment3_permissions()
    if not permissions["can_run_module_a"]:
        return jsonify({"error": "You do not have permission to run Module A."}), 403

    started, message, jobs = ASSIGNMENT3_CONSOLE.start_module_a(g.role_name)
    return jsonify({
        "message": message,
        "jobs": jobs,
        "permissions": permissions,
    }), 202 if started else 409


@app.route("/api/assignment3/tests/run/module-b", methods=["POST"])
@login_required
def api_assignment3_run_module_b():
    access_response = _require_assignment3_view_access()
    if access_response:
        return access_response

    permissions = _assignment3_permissions()
    if not permissions["can_run_module_b"]:
        return jsonify({"error": "Only Admin users can run Module B from the visual console."}), 403

    started, message, jobs = ASSIGNMENT3_CONSOLE.start_module_b(g.role_name)
    return jsonify({
        "message": message,
        "jobs": jobs,
        "permissions": permissions,
    }), 202 if started else 409


@app.route("/api/assignment3/tests/run/all", methods=["POST"])
@login_required
def api_assignment3_run_all():
    access_response = _require_assignment3_view_access()
    if access_response:
        return access_response

    permissions = _assignment3_permissions()
    if not permissions["can_run_all"]:
        return jsonify({"error": "Only Admin users can run all Assignment 3 checks together."}), 403

    started, message, jobs = ASSIGNMENT3_CONSOLE.start_run_all(g.role_name)
    return jsonify({
        "message": message,
        "jobs": jobs,
        "permissions": permissions,
    }), 202 if started else 409

# ===================================================================
# CRUD API - MEMBERS
# ===================================================================

@app.route("/api/members", methods=["GET"])
@login_required
def api_list_members():
    db = get_db()
    try:
        with db.cursor() as cur:
            name_filter = (request.args.get("name") or "").strip()
            if g.role_id == 1:  # Admin sees all
                if name_filter:
                    cur.execute(
                        """SELECT m.MemberID, m.Name, m.Email, m.ContactNumber, m.Age,
                                  m.IsActive, m.CreatedAt, d.DeptName, r.RoleName
                           FROM Member m
                           JOIN Department d ON m.DepartmentID = d.DepartmentID
                           JOIN Role r       ON m.RoleID       = r.RoleID
                           WHERE m.Name = %s
                           ORDER BY m.MemberID""",
                        (name_filter,),
                    )
                else:
                    cur.execute(
                        """SELECT m.MemberID, m.Name, m.Email, m.ContactNumber, m.Age,
                                  m.IsActive, m.CreatedAt, d.DeptName, r.RoleName
                           FROM Member m
                           JOIN Department d ON m.DepartmentID = d.DepartmentID
                           JOIN Role r       ON m.RoleID       = r.RoleID
                           ORDER BY m.MemberID"""
                    )
            else:
                cur.execute(
                    """SELECT m.MemberID, m.Name, m.Email, m.ContactNumber, m.Age,
                              m.IsActive, m.CreatedAt, d.DeptName, r.RoleName
                       FROM Member m
                       JOIN Department d ON m.DepartmentID = d.DepartmentID
                       JOIN Role r       ON m.RoleID       = r.RoleID
                       WHERE m.MemberID = %s""",
                    (g.member_id,),
                )
            members = cur.fetchall()

        # Convert datetime objects to strings for JSON serialization
        for m in members:
            if m.get("CreatedAt"):
                m["CreatedAt"] = m["CreatedAt"].strftime("%Y-%m-%d %H:%M:%S")

        return jsonify(members)
    finally:
        db.close()


@app.route("/api/members/<int:mid>", methods=["GET"])
@login_required
def api_get_member(mid):
    if g.role_id not in (1, 2, 5) and mid != g.member_id:
        return jsonify({"error": "Access denied"}), 403

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                """SELECT m.MemberID, m.Name, m.Email, m.ContactNumber, m.Age,
                          m.Image, m.IsActive, m.CreatedAt,
                          d.DeptName, r.RoleName, m.DepartmentID, m.RoleID
                   FROM Member m
                   JOIN Department d ON m.DepartmentID = d.DepartmentID
                   JOIN Role r       ON m.RoleID       = r.RoleID
                   WHERE m.MemberID = %s""",
                (mid,),
            )
            member = cur.fetchone()
        if not member:
            return jsonify({"error": "Member not found"}), 404

        if member.get("CreatedAt"):
            member["CreatedAt"] = member["CreatedAt"].strftime("%Y-%m-%d %H:%M:%S")

        return jsonify(member)
    finally:
        db.close()


@app.route("/api/members", methods=["POST"])
@admin_required
def api_create_member():
    data = request.get_json()
    required = ["Name", "Email", "ContactNumber", "DepartmentID", "RoleID"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    db = get_db()
    try:
        password = data.get("Password", "changeme")
        pwd_hash = hash_password(password)
        with db.cursor() as cur:
            cur.execute(
                """INSERT INTO Member
                   (Name, Image, Age, Email, ContactNumber, DepartmentID, RoleID, PasswordHash, IsActive)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    data["Name"],
                    data.get("Image"),
                    data.get("Age"),
                    data["Email"],
                    data["ContactNumber"],
                    data["DepartmentID"],
                    data["RoleID"],
                    pwd_hash,
                    data.get("IsActive", True),
                ),
            )
            new_id = cur.lastrowid

            # Also create UserLogin so the new member can log in
            username = data.get("Username", data["Email"].split("@")[0])
            cur.execute(
                """INSERT INTO UserLogin (MemberID, Username, PasswordHash)
                   VALUES (%s, %s, %s)""",
                (new_id, username, pwd_hash),
            )
        db.commit()
        log_action(db, g.member_id, "API_CREATE_MEMBER", "Member", new_id,
                   request.remote_addr, True, f"name={data['Name']}")
        return jsonify({"message": "Member created", "MemberID": new_id, "Username": username}), 201
    except pymysql.IntegrityError as exc:
        db.rollback()
        return jsonify({"error": str(exc)}), 409
    finally:
        db.close()


@app.route("/api/members/<int:mid>", methods=["PUT"])
@login_required
def api_update_member(mid):
    # Admin can update anyone; others only themselves
    if g.role_id != 1 and mid != g.member_id:
        return jsonify({"error": "Access denied"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    allowed = ["Name", "Email", "ContactNumber", "Age", "Image", "IsActive"]
    if g.role_id == 1:
        allowed += ["DepartmentID", "RoleID"]

    sets, vals = [], []
    for col in allowed:
        if col in data:
            sets.append(f"{col} = %s")
            vals.append(data[col])

    if not sets:
        return jsonify({"error": "No valid fields to update"}), 400

    vals.append(mid)
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(f"UPDATE Member SET {', '.join(sets)} WHERE MemberID = %s", vals)
        db.commit()
        log_action(db, g.member_id, "API_UPDATE_MEMBER", "Member", mid,
                   request.remote_addr, True, f"fields={list(data.keys())}")
        return jsonify({"message": "Member updated"})
    except pymysql.IntegrityError as exc:
        db.rollback()
        return jsonify({"error": str(exc)}), 409
    finally:
        db.close()


@app.route("/api/members/<int:mid>", methods=["DELETE"])
@admin_required
def api_delete_member(mid):
    db = get_db()
    try:
        with db.cursor() as cur:
            # Check existence
            cur.execute("SELECT MemberID FROM Member WHERE MemberID = %s", (mid,))
            if not cur.fetchone():
                return jsonify({"error": "Member not found"}), 404

            # Delete related UserLogin first (CASCADE should handle it, but be explicit)
            cur.execute("DELETE FROM UserLogin WHERE MemberID = %s", (mid,))

            # Delete member (cascades will clean up Permissions, AccessLog, Notifications, etc.)
            cur.execute("DELETE FROM Member WHERE MemberID = %s", (mid,))
        db.commit()
        log_action(db, g.member_id, "API_DELETE_MEMBER", "Member", mid,
                   request.remote_addr, True)
        return jsonify({"message": "Member deleted"})
    except pymysql.IntegrityError as exc:
        db.rollback()
        return jsonify({"error": f"Cannot delete: {exc}"}), 409
    finally:
        db.close()

# ===================================================================
# CRUD API - DOCUMENTS
# ===================================================================

@app.route("/api/documents", methods=["GET"])
@login_required
def api_list_documents():
    db = get_db()
    try:
        title_filter = (request.args.get("title") or "").strip()
        id_start = request.args.get("id_start", type=int)
        id_end = request.args.get("id_end", type=int)
        docs = _list_documents(
            db,
            title_filter=title_filter or None,
            id_start=id_start,
            id_end=id_end,
        )

        _format_datetime_fields(docs, ("CreatedAt", "UpdatedAt"))

        return jsonify(docs)
    finally:
        db.close()


@app.route("/api/documents/<int:doc_id>", methods=["GET"])
@login_required
def api_get_document(doc_id):
    db = get_db()
    try:
        doc = _fetch_document(db, doc_id, "d.*", active_only=True)
        if not doc:
            return jsonify({"error": "Document not found"}), 404

        _format_datetime_fields(doc, ("CreatedAt", "UpdatedAt"))

        return jsonify(doc)
    finally:
        db.close()


@app.route("/api/documents", methods=["POST"])
@login_required
def api_create_document():
    db = get_db()
    shard_db = None
    try:
        caps = _get_role_caps(db, g.role_id)
        if not caps or not caps.get("CanUpload"):
            log_action(db, g.member_id, "API_CREATE_DOCUMENT_DENIED", "Document", None,
                       request.remote_addr, True, "role lacks CanUpload")
            return jsonify({"error": "You do not have upload permission"}), 403

        data = request.get_json(silent=True) or {}
        required = ["Title", "FolderID"]
        for field in required:
            if field not in data:
                return jsonify({"error": f"Missing field: {field}"}), 400

        with db.cursor() as cur:
            new_id = _reserve_document_id(cur)
        shard_id = _document_shard_id(new_id)
        table_name = _document_table_name(shard_id=shard_id)
        shard_db, _ = _get_transaction_shard_db(shard_id, db)

        with shard_db.cursor() as cur:
            cur.execute(
                f"""INSERT INTO {table_name}
                    (DocumentID, Title, Description, FilePath, FileSize, UploadedBy, FolderID, IsConfidential)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    new_id,
                    data["Title"],
                    data.get("Description", ""),
                    data.get("FilePath", f"/docs/{data['Title'].replace(' ', '_').lower()}.pdf"),
                    data.get("FileSize", 1024),
                    g.member_id,
                    data["FolderID"],
                    data.get("IsConfidential", False),
                ),
            )

        with db.cursor() as cur:
            cur.execute(
                """INSERT INTO DocumentShardDirectory (DocumentID, ShardID, Origin)
                   VALUES (%s, %s, %s)
                   ON DUPLICATE KEY UPDATE ShardID = VALUES(ShardID), Origin = VALUES(Origin)""",
                (new_id, shard_id, "live_insert"),
            )
        _record_document_activity(db, new_id, "UPLOAD", shard_db=shard_db)
        if shard_db is not db:
            shard_db.commit()
        db.commit()
        log_action(db, g.member_id, "API_CREATE_DOCUMENT", "Document", new_id,
                   request.remote_addr, True, f"title={data['Title']}; shard={shard_id}")
        return jsonify({"message": "Document created", "DocumentID": new_id, "ShardID": shard_id}), 201
    except pymysql.IntegrityError as exc:
        if shard_db is not None and shard_db is not db:
            shard_db.rollback()
        db.rollback()
        return jsonify({"error": str(exc)}), 409
    finally:
        if shard_db is not None and shard_db is not db:
            shard_db.close()
        db.close()


@app.route("/api/documents/<int:doc_id>", methods=["PUT"])
@login_required
def api_update_document(doc_id):
    db = get_db()
    shard_db = None
    try:
        existing_doc = _fetch_document(db, doc_id, "d.UploadedBy, d.IsActive")
        if not existing_doc or not existing_doc["IsActive"]:
            return jsonify({"error": "Document not found"}), 404

        # Check edit permission: Admin, Manager, Editor, or document owner
        caps = _get_role_caps(db, g.role_id)
        if not caps or not caps.get("CanUpload"):
            if existing_doc["UploadedBy"] != g.member_id:
                log_action(db, g.member_id, "API_UPDATE_DOCUMENT_DENIED", "Document", doc_id,
                           request.remote_addr, True, "role lacks CanUpload and not owner")
                return jsonify({"error": "You do not have edit permission"}), 403

        data = request.get_json(silent=True) or {}
        if not data:
            return jsonify({"error": "No data provided"}), 400

        allowed = ["Title", "Description", "IsConfidential", "FolderID"]
        sets, vals = [], []
        for col in allowed:
            if col in data:
                sets.append(f"{col} = %s")
                vals.append(data[col])

        if not sets:
            return jsonify({"error": "No valid fields to update"}), 400

        vals.append(doc_id)
        shard_id = _document_shard_id(doc_id)
        table_name = _document_table_name(shard_id=shard_id)
        shard_db, _ = _get_transaction_shard_db(shard_id, db)
        with shard_db.cursor() as cur:
            cur.execute(
                f"UPDATE {table_name} SET {', '.join(sets)} WHERE DocumentID = %s AND IsActive = TRUE",
                vals,
            )
            if cur.rowcount == 0:
                if shard_db is not db:
                    shard_db.rollback()
                db.rollback()
                return jsonify({"error": "Document not found"}), 404
        _record_document_activity(db, doc_id, "EDIT", shard_db=shard_db)
        if shard_db is db:
            db.commit()
        else:
            shard_db.commit()
            db.commit()
        log_action(db, g.member_id, "API_UPDATE_DOCUMENT", "Document", doc_id,
                   request.remote_addr, True, f"fields={list(data.keys())}")
        return jsonify({"message": "Document updated"})
    except pymysql.IntegrityError as exc:
        if shard_db is not None and shard_db is not db:
            shard_db.rollback()
        db.rollback()
        return jsonify({"error": str(exc)}), 409
    finally:
        if shard_db is not None and shard_db is not db:
            shard_db.close()
        db.close()


@app.route("/api/documents/<int:doc_id>", methods=["DELETE"])
@login_required
def api_delete_document(doc_id):
    db = get_db()
    shard_db = None
    try:
        caps = _get_role_caps(db, g.role_id)
        if not caps or not caps.get("CanDelete"):
            log_action(db, g.member_id, "API_DELETE_DOCUMENT_DENIED", "Document", doc_id,
                       request.remote_addr, True, "role lacks CanDelete")
            return jsonify({"error": "You do not have delete permission"}), 403

        shard_id = _document_shard_id(doc_id)
        table_name = _document_table_name(shard_id=shard_id)
        shard_db, _ = _get_transaction_shard_db(shard_id, db)
        with shard_db.cursor() as cur:
            cur.execute(
                f"UPDATE {table_name} SET IsActive = FALSE WHERE DocumentID = %s AND IsActive = TRUE",
                (doc_id,),
            )
            if cur.rowcount == 0:
                if shard_db is not db:
                    shard_db.rollback()
                db.rollback()
                return jsonify({"error": "Document not found"}), 404
        _record_document_activity(db, doc_id, "DELETE", shard_db=shard_db)
        if shard_db is db:
            db.commit()
        else:
            shard_db.commit()
            db.commit()
        log_action(db, g.member_id, "API_DELETE_DOCUMENT", "Document", doc_id,
                   request.remote_addr, True)
        return jsonify({"message": "Document deleted"})
    finally:
        if shard_db is not None and shard_db is not db:
            shard_db.close()
        db.close()

# ===================================================================
# CRUD API - DEPARTMENTS & FOLDERS (read-only helpers)
# ===================================================================

@app.route("/api/departments", methods=["GET"])
@login_required
def api_list_departments():
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT * FROM Department ORDER BY DeptName")
            depts = cur.fetchall()
        for d in depts:
            if d.get("CreatedAt"):
                d["CreatedAt"] = d["CreatedAt"].strftime("%Y-%m-%d %H:%M:%S")
        return jsonify(depts)
    finally:
        db.close()


@app.route("/api/folders", methods=["GET"])
@login_required
def api_list_folders():
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                """SELECT f.*, m.Name AS CreatorName
                   FROM Folder f
                   JOIN Member m ON f.CreatedBy = m.MemberID
                   WHERE f.IsActive = TRUE
                   ORDER BY f.FolderName"""
            )
            folders = cur.fetchall()
        for f in folders:
            if f.get("CreatedAt"):
                f["CreatedAt"] = f["CreatedAt"].strftime("%Y-%m-%d %H:%M:%S")
        return jsonify(folders)
    finally:
        db.close()

# ===================================================================
# SECURITY LOG API (Auditor / Admin)
# ===================================================================

@app.route("/api/security-logs", methods=["GET"])
@login_required
def api_security_logs():
    if g.role_id not in (1, 5):  # Admin or Auditor
        return jsonify({"error": "Access denied"}), 403
    db = get_db()
    try:
        session_valid_param = (request.args.get("session_valid") or "").strip().lower()
        with db.cursor() as cur:
            if session_valid_param in ("true", "false"):
                cur.execute(
                    """SELECT sl.*, m.Name AS MemberName
                       FROM SecurityLog sl
                       LEFT JOIN Member m ON sl.MemberID = m.MemberID
                       WHERE sl.SessionValid = %s
                       ORDER BY sl.CreatedAt DESC LIMIT 100""",
                    (session_valid_param == "true",),
                )
            else:
                cur.execute(
                    """SELECT sl.*, m.Name AS MemberName
                       FROM SecurityLog sl
                       LEFT JOIN Member m ON sl.MemberID = m.MemberID
                       ORDER BY sl.CreatedAt DESC LIMIT 100"""
                )
            logs = cur.fetchall()
        for l in logs:
            if l.get("CreatedAt"):
                l["CreatedAt"] = l["CreatedAt"].strftime("%Y-%m-%d %H:%M:%S")
        return jsonify(logs)
    finally:
        db.close()

# ===================================================================
# Entry point
# ===================================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
