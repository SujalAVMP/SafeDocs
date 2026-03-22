"""
SafeDocs Module B - Authentication & Session Management
CS 432 - Databases | IIT Gandhinagar

Provides:
- SHA-256 password hashing and verification
- JWT-based session tokens
- login_required / admin_required decorators
- Dual audit logging (SecurityLog table + audit.log file)
"""

import hashlib
import datetime
import os
import logging
from functools import wraps

import jwt
from flask import request, jsonify, redirect, url_for, g

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
JWT_SECRET = os.environ.get("JWT_SECRET", "safedocs-secret-key-cs432-2026-default")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

# ---------------------------------------------------------------------------
# Audit file logger
# ---------------------------------------------------------------------------
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "audit.log")

_file_logger = logging.getLogger("safedocs_audit")
_file_logger.setLevel(logging.INFO)
if not _file_logger.handlers:
    _fh = logging.FileHandler(LOG_FILE)
    _fh.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    _file_logger.addHandler(_fh)

# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Return the SHA-256 hex digest of *password* (matches MySQL SHA2(x,256))."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Return True when the SHA-256 digest of *password* equals *hashed*."""
    return hash_password(password) == hashed

# ---------------------------------------------------------------------------
# JWT session tokens
# ---------------------------------------------------------------------------

def create_session_token(member_id: int, role_id: int, role_name: str, member_name: str = "") -> str:
    """Create a JWT containing the member's identity and role."""
    payload = {
        "member_id": member_id,
        "role_id": role_id,
        "role_name": role_name,
        "member_name": member_name,
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_session_token(token: str) -> dict | None:
    """Decode and verify a JWT.  Returns the payload dict or None."""
    payload, _ = verify_session_token_detailed(token)
    return payload


def verify_session_token_detailed(token: str) -> tuple[dict | None, str]:
    """Decode a JWT and return (payload, status)."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM]), "ok"
    except jwt.ExpiredSignatureError:
        return None, "expired"
    except jwt.InvalidTokenError:
        return None, "invalid"

# ---------------------------------------------------------------------------
# Helper: extract token from request
# ---------------------------------------------------------------------------

def _get_token_from_request():
    """Try cookie first, then Authorization header."""
    token = request.cookies.get("session_token")
    if token:
        return token
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None

# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def login_required(f):
    """Protect a route so that only authenticated users can access it."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _get_token_from_request()
        if not token:
            # If it's an API call return JSON; otherwise redirect.
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("login_page"))

        payload, status = verify_session_token_detailed(token)
        if payload is None:
            if request.path.startswith("/api/"):
                if status == "expired":
                    return jsonify({"error": "Session expired"}), 401
                return jsonify({"error": "Invalid session token"}), 401
            return redirect(url_for("login_page"))

        # Attach user info to Flask's request-scoped g object
        g.member_id = payload["member_id"]
        g.role_id = payload["role_id"]
        g.role_name = payload["role_name"]
        g.member_name = payload.get("member_name", "")
        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    """Protect a route so that only Admin users (RoleID=1) can access it."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if g.role_id != 1:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Admin access required"}), 403
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)

    return decorated

# ---------------------------------------------------------------------------
# Audit logging (dual: DB + file)
# ---------------------------------------------------------------------------

def log_action(db_conn, member_id, action, table_name=None, record_id=None,
               ip=None, session_valid=True, details=None):
    """Write an entry to both the SecurityLog table and the audit.log file."""
    # --- Database ---
    try:
        with db_conn.cursor() as cur:
            cur.execute(
                """INSERT INTO SecurityLog
                   (MemberID, Action, TableName, RecordID, IPAddress, SessionValid, Details)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (member_id, action, table_name, record_id, ip, session_valid, details),
            )
        db_conn.commit()
    except Exception as exc:
        # If the DB write fails, log to file and continue
        _file_logger.error(f"DB log failed: {exc}")

    # --- File ---
    parts = [
        f"member_id={member_id}",
        f"action={action}",
        f"table={table_name}",
        f"record_id={record_id}",
        f"ip={ip}",
        f"session_valid={session_valid}",
        f"details={details}",
    ]
    _file_logger.info(" | ".join(parts))


def log_document_activity(db_conn, document_id, member_id, action,
                          ip=None, user_agent=None, commit=True):
    """Write a document-centric activity row to AccessLog."""
    try:
        with db_conn.cursor() as cur:
            cur.execute(
                """INSERT INTO AccessLog
                   (DocumentID, MemberID, Action, IPAddress, UserAgent)
                   VALUES (%s, %s, %s, %s, %s)""",
                (document_id, member_id, action, ip, user_agent),
            )
        if commit:
            db_conn.commit()
    except Exception as exc:
        _file_logger.error(f"AccessLog write failed: {exc}")
