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

import os
import datetime

import pymysql
from flask import (
    Flask, request, jsonify, render_template,
    redirect, url_for, make_response, g, flash
)

try:
    from .auth import (
        hash_password, verify_password,
        create_session_token, verify_session_token, verify_session_token_detailed,
        login_required, admin_required, log_action, log_document_activity,
    )
except ImportError:
    from auth import (
        hash_password, verify_password,
        create_session_token, verify_session_token, verify_session_token_detailed,
        login_required, admin_required, log_action, log_document_activity,
    )

# ===================================================================
# Flask app setup
# ===================================================================
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "safedocs-flask-secret-cs432")

# ===================================================================
# Database connection helper
# ===================================================================

def get_db():
    """Return a PyMySQL connection to the safedocs database."""
    return pymysql.connect(
        host="localhost",
        user="safedocs",
        password="safedocs123",
        database="safedocs",
        cursorclass=pymysql.cursors.DictCursor,
        unix_socket="/run/mysqld/mysqld.sock",
        autocommit=False,
    )

# ===================================================================
# Helper: fetch current user's role capabilities
# ===================================================================

def _get_role_caps(db, role_id):
    with db.cursor() as cur:
        cur.execute("SELECT * FROM Role WHERE RoleID = %s", (role_id,))
        return cur.fetchone()


def _wants_json_response():
    """Treat non-browser root requests as API requests."""
    return "text/html" not in request.headers.get("Accept", "").lower()


def _record_document_activity(db, document_id, action):
    """Append a document-centric activity row for the current request."""
    log_document_activity(
        db,
        document_id=document_id,
        member_id=g.member_id,
        action=action,
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
        commit=False,
    )

# ===================================================================
# AUTH ROUTES
# ===================================================================

@app.route("/")
def index():
    """Return API welcome JSON or redirect browsers into the UI."""
    if _wants_json_response():
        return jsonify({"message": "Welcome to test APIs"})
    from auth import _get_token_from_request
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
        from auth import _get_token_from_request
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
    from auth import _get_token_from_request
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

            cur.execute("SELECT COUNT(*) AS cnt FROM Document WHERE IsActive = TRUE")
            stats["total_documents"] = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) AS cnt FROM Folder WHERE IsActive = TRUE")
            stats["total_folders"] = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) AS cnt FROM Department")
            stats["total_departments"] = cur.fetchone()["cnt"]
            
            cur.execute(
                """SELECT al.Action, al.AccessTimestamp, m.Name, d.Title
                   FROM AccessLog al
                   JOIN Member m ON al.MemberID = m.MemberID
                   JOIN Document d ON al.DocumentID = d.DocumentID
                   ORDER BY al.AccessTimestamp DESC LIMIT 10"""
            )
            stats["recent_logs"] = cur.fetchall()

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

            cur.execute(
                "SELECT COUNT(*) AS cnt FROM Document WHERE UploadedBy = %s AND IsActive = TRUE",
                (member_id,),
            )
            doc_count = cur.fetchone()["cnt"]

            cur.execute(
                """SELECT recent.Action, recent.AccessTimestamp, doc.Title
                   FROM (
                        SELECT DocumentID, Action, AccessTimestamp
                        FROM AccessLog
                        WHERE MemberID = %s
                        ORDER BY AccessTimestamp DESC
                        LIMIT 10
                   ) AS recent
                   JOIN Document doc ON recent.DocumentID = doc.DocumentID
                   ORDER BY recent.AccessTimestamp DESC""",
                (member_id,),
            )
            recent_activity = cur.fetchall()

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
        with db.cursor() as cur:
            cur.execute(
                """SELECT d.DocumentID, d.Title, d.Description, d.FileSize,
                          d.IsConfidential, d.IsActive, d.CreatedAt,
                          m.Name AS UploaderName, f.FolderName
                   FROM Document d
                   JOIN Member m ON d.UploadedBy = m.MemberID
                   JOIN Folder f ON d.FolderID   = f.FolderID
                   WHERE d.IsActive = TRUE
                   ORDER BY d.CreatedAt DESC"""
            )
            documents = cur.fetchall()

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
        with db.cursor() as cur:
            cur.execute(
                "SELECT * FROM Document WHERE DocumentID = %s AND IsActive = TRUE",
                (doc_id,),
            )
            document = cur.fetchone()
            if not document:
                flash("Document not found.", "danger")
                return redirect(url_for("documents_page"))
            cur.execute("SELECT FolderID, FolderName FROM Folder WHERE IsActive = TRUE ORDER BY FolderName")
            folders = cur.fetchall()
        return render_template("document_edit.html", document=document,
                               folders=folders,
                               user_name=g.member_name, role_name=g.role_name,
                               role_id=g.role_id, member_id=g.member_id)
    finally:
        db.close()

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
        with db.cursor() as cur:
            title_filter = (request.args.get("title") or "").strip()
            query = """
                SELECT d.DocumentID, d.Title, d.Description, d.FileSize,
                       d.IsConfidential, d.IsActive, d.CreatedAt, d.UpdatedAt,
                       m.Name AS UploaderName, f.FolderName, d.FolderID
                FROM Document d
                JOIN Member m ON d.UploadedBy = m.MemberID
                JOIN Folder f ON d.FolderID   = f.FolderID
                WHERE d.IsActive = TRUE
            """
            params = []
            if title_filter:
                query += " AND d.Title = %s"
                params.append(title_filter)
            query += " ORDER BY d.CreatedAt DESC"
            cur.execute(query, params)
            docs = cur.fetchall()

        for d in docs:
            for key in ("CreatedAt", "UpdatedAt"):
                if d.get(key):
                    d[key] = d[key].strftime("%Y-%m-%d %H:%M:%S")

        return jsonify(docs)
    finally:
        db.close()


@app.route("/api/documents/<int:doc_id>", methods=["GET"])
@login_required
def api_get_document(doc_id):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                """SELECT d.*, m.Name AS UploaderName, f.FolderName
                   FROM Document d
                   JOIN Member m ON d.UploadedBy = m.MemberID
                   JOIN Folder f ON d.FolderID   = f.FolderID
                   WHERE d.DocumentID = %s AND d.IsActive = TRUE""",
                (doc_id,),
            )
            doc = cur.fetchone()
        if not doc:
            return jsonify({"error": "Document not found"}), 404

        for key in ("CreatedAt", "UpdatedAt"):
            if doc.get(key):
                doc[key] = doc[key].strftime("%Y-%m-%d %H:%M:%S")

        return jsonify(doc)
    finally:
        db.close()


@app.route("/api/documents", methods=["POST"])
@login_required
def api_create_document():
    db = get_db()
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
            cur.execute(
                """INSERT INTO Document
                   (Title, Description, FilePath, FileSize, UploadedBy, FolderID, IsConfidential)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    data["Title"],
                    data.get("Description", ""),
                    data.get("FilePath", f"/docs/{data['Title'].replace(' ', '_').lower()}.pdf"),
                    data.get("FileSize", 1024),
                    g.member_id,
                    data["FolderID"],
                    data.get("IsConfidential", False),
                ),
            )
            new_id = cur.lastrowid
        _record_document_activity(db, new_id, "UPLOAD")
        db.commit()
        log_action(db, g.member_id, "API_CREATE_DOCUMENT", "Document", new_id,
                   request.remote_addr, True, f"title={data['Title']}")
        return jsonify({"message": "Document created", "DocumentID": new_id}), 201
    except pymysql.IntegrityError as exc:
        db.rollback()
        return jsonify({"error": str(exc)}), 409
    finally:
        db.close()


@app.route("/api/documents/<int:doc_id>", methods=["PUT"])
@login_required
def api_update_document(doc_id):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT UploadedBy, IsActive FROM Document WHERE DocumentID = %s",
                (doc_id,),
            )
            existing_doc = cur.fetchone()
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
        with db.cursor() as cur:
            cur.execute(f"UPDATE Document SET {', '.join(sets)} WHERE DocumentID = %s", vals)
        _record_document_activity(db, doc_id, "EDIT")
        db.commit()
        log_action(db, g.member_id, "API_UPDATE_DOCUMENT", "Document", doc_id,
                   request.remote_addr, True, f"fields={list(data.keys())}")
        return jsonify({"message": "Document updated"})
    except pymysql.IntegrityError as exc:
        db.rollback()
        return jsonify({"error": str(exc)}), 409
    finally:
        db.close()


@app.route("/api/documents/<int:doc_id>", methods=["DELETE"])
@login_required
def api_delete_document(doc_id):
    db = get_db()
    try:
        caps = _get_role_caps(db, g.role_id)
        if not caps or not caps.get("CanDelete"):
            log_action(db, g.member_id, "API_DELETE_DOCUMENT_DENIED", "Document", doc_id,
                       request.remote_addr, True, "role lacks CanDelete")
            return jsonify({"error": "You do not have delete permission"}), 403

        with db.cursor() as cur:
            cur.execute(
                "SELECT DocumentID, IsActive FROM Document WHERE DocumentID = %s",
                (doc_id,),
            )
            doc = cur.fetchone()
            if not doc or not doc["IsActive"]:
                return jsonify({"error": "Document not found"}), 404
            cur.execute("UPDATE Document SET IsActive = FALSE WHERE DocumentID = %s", (doc_id,))
        _record_document_activity(db, doc_id, "DELETE")
        db.commit()
        log_action(db, g.member_id, "API_DELETE_DOCUMENT", "Document", doc_id,
                   request.remote_addr, True)
        return jsonify({"message": "Document deleted"})
    finally:
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
