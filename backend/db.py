"""
db.py
--------
Local SQLite storage for applications + admin overrides.

This module now includes a simple but real password/session model for:
- student login/signup
- admin login
- role-based access
- password reset flow
- session tracking
- appeal requests
"""

import hashlib
import json
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = str(Path(__file__).resolve().parent / "applications.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str) -> str:
    salt = secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000)
    return f"{salt}:{digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash or ":" not in stored_hash:
        return False
    salt, digest_hex = stored_hash.split(":", 1)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000)
    return digest.hex() == digest_hex


def _ensure_column(conn, table_name: str, column_name: str, column_sql: str):
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    if not any(col[1] == column_name for col in columns):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            reset_token TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            applicant_data TEXT NOT NULL,
            model_decision TEXT NOT NULL,
            final_decision TEXT NOT NULL,
            confidence REAL NOT NULL,
            top_reasons TEXT NOT NULL,
            override_applied TEXT,
            status TEXT NOT NULL,
            admin_final_decision TEXT,
            admin_comment TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    _ensure_column(conn, "applications", "user_id", "user_id TEXT")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS appeals (
            id TEXT PRIMARY KEY,
            application_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(application_id) REFERENCES applications(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS document_anomalies (
            id TEXT PRIMARY KEY,
            application_id TEXT NOT NULL,
            document_id TEXT,
            anomaly_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            anomaly_score REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'DETECTED',
            reason TEXT NOT NULL,
            details TEXT,
            detected_at TEXT NOT NULL,
            resolved_at TEXT,
            resolved_by TEXT,
            FOREIGN KEY(application_id) REFERENCES applications(id)
        )
    """)

    conn.commit()
    ensure_demo_accounts()
    conn.close()


def ensure_demo_accounts():
    conn = get_conn()
    for email, password, role, name in [
        ("admin@janniti.ai", "admin123", "admin", "Janniti Admin"),
        ("student2@gmail.com", "student123", "student", "Student Demo")
    ]:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not existing:
            user_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO users (id, name, email, password_hash, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, name, email, hash_password(password), role, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()),
            )
    conn.commit()
    conn.close()


def create_user(name: str, email: str, password: str, role: str = "student", phone: str = None):
    conn = get_conn()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
    if existing:
        conn.close()
        raise ValueError("User already exists")

    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users (id, name, email, phone, password_hash, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, name.strip(), email.lower().strip(), phone, hash_password(password), role, now, now),
    )
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(user)


def get_user_by_email(email: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_session(user_id: str):
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).isoformat()
    expires_at = (datetime.now(timezone.utc).timestamp() + 7 * 24 * 60 * 60)
    expires_iso = datetime.fromtimestamp(expires_at, timezone.utc).isoformat()

    conn = get_conn()
    conn.execute(
        "INSERT INTO sessions (id, user_id, token, created_at, expires_at, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, token, now, expires_iso, now),
    )
    conn.commit()
    conn.close()
    return token


def get_session_by_token(token: str):
    if not token:
        return None
    conn = get_conn()
    row = conn.execute("SELECT * FROM sessions WHERE token = ?", (token,)).fetchone()
    conn.close()
    if not row:
        return None
    session = dict(row)
    expires_at = datetime.fromisoformat(session["expires_at"])
    if expires_at < datetime.now(timezone.utc):
        delete_session(token)
        return None
    return session


def delete_session(token: str):
    conn = get_conn()
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def set_reset_token(email: str, token: str):
    conn = get_conn()
    conn.execute("UPDATE users SET reset_token = ?, updated_at = ? WHERE email = ?", (token, datetime.now(timezone.utc).isoformat(), email.lower().strip()))
    conn.commit()
    conn.close()


def reset_password_with_token(token: str, new_password: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE reset_token = ?", (token,)).fetchone()
    if not row:
        conn.close()
        return False
    conn.execute(
        "UPDATE users SET password_hash = ?, reset_token = NULL, updated_at = ? WHERE id = ?",
        (hash_password(new_password), datetime.now(timezone.utc).isoformat(), row["id"]),
    )
    conn.commit()
    conn.close()
    return True


def insert_application(applicant_data: dict, ml_result: dict, user_id: str = None) -> str:
    app_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = get_conn()
    conn.execute(
        """INSERT INTO applications
           (id, user_id, applicant_data, model_decision, final_decision, confidence,
            top_reasons, override_applied, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            app_id,
            user_id,
            json.dumps(applicant_data),
            ml_result["model_decision"],
            ml_result["final_decision"],
            ml_result["confidence"],
            json.dumps(ml_result["top_reasons"]),
            ml_result["override_applied"],
            "PENDING",
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return app_id


def _row_to_dict(row):
    d = dict(row)
    d["applicant_data"] = json.loads(d["applicant_data"])
    d["top_reasons"] = json.loads(d["top_reasons"])
    return d


def get_application(app_id: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def get_user_applications(user_id: str):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM applications WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def list_applications(status_filter: str = None):
    conn = get_conn()
    if status_filter:
        rows = conn.execute(
            "SELECT * FROM applications WHERE final_decision = ? ORDER BY created_at DESC",
            (status_filter,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM applications ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def apply_override(app_id: str, admin_decision: str, admin_comment: str):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    conn.execute(
        """UPDATE applications
           SET admin_final_decision = ?, admin_comment = ?, status = ?, updated_at = ?
           WHERE id = ?""",
        (admin_decision, admin_comment, "ADMIN_REVIEWED", now, app_id),
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    conn.close()
    return _row_to_dict(updated) if updated else None


def create_appeal(application_id: str, user_id: str, reason: str):
    conn = get_conn()
    appeal_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO appeals (id, application_id, user_id, reason, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (appeal_id, application_id, user_id, reason.strip(), "OPEN", now, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM appeals WHERE id = ?", (appeal_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_appeals_for_user(user_id: str):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM appeals WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_document_anomalies(application_id: str, anomalies: list) -> list:
    """
    Save detected document anomalies for an application.
    Deletes existing DETECTED anomalies for this application to ensure idempotence.
    """
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    # Remove previous unresolved detections to prevent uncontrolled duplicates on re-runs
    conn.execute(
        "DELETE FROM document_anomalies WHERE application_id = ? AND status = 'DETECTED'",
        (application_id,)
    )

    saved_records = []
    for item in anomalies:
        rec_id = str(uuid.uuid4())
        details_str = json.dumps(item.get("details") or {})
        score_val = float(item.get("score_weight") if item.get("score_weight") is not None else item.get("score", 0.0))
        conn.execute(
            """INSERT INTO document_anomalies
               (id, application_id, document_id, anomaly_type, severity, anomaly_score, status, reason, details, detected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rec_id,
                application_id,
                item.get("document_id"),
                item.get("type", "ANOMALY_DETECTED"),
                item.get("severity", "MEDIUM"),
                score_val,
                item.get("status", "DETECTED"),
                item.get("message", "Anomaly detected"),
                details_str,
                now,
            )
        )
        saved_records.append({
            "id": rec_id,
            "application_id": application_id,
            "document_id": item.get("document_id"),
            "anomaly_type": item.get("type"),
            "severity": item.get("severity"),
            "anomaly_score": score_val,
            "status": item.get("status", "DETECTED"),
            "reason": item.get("message"),
            "details": item.get("details"),
            "detected_at": now,
        })

    conn.commit()
    conn.close()
    return saved_records


def get_document_anomalies_for_app(application_id: str) -> list:
    """
    Fetch all document anomaly records for an application.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM document_anomalies WHERE application_id = ? ORDER BY detected_at DESC",
        (application_id,)
    ).fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        if d.get("details"):
            try:
                d["details"] = json.loads(d["details"])
            except Exception:
                pass
        results.append(d)
    return results


def resolve_document_anomaly(anomaly_id: str, resolved_by: str, resolution_status: str = "RESOLVED") -> dict:
    """
    Resolve a document anomaly (e.g. RESOLVED or FALSE_POSITIVE).
    """
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE document_anomalies
           SET status = ?, resolved_at = ?, resolved_by = ?
           WHERE id = ?""",
        (resolution_status, now, resolved_by, anomaly_id)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM document_anomalies WHERE id = ?", (anomaly_id,)).fetchone()
    conn.close()
    if row:
        d = dict(row)
        if d.get("details"):
            try:
                d["details"] = json.loads(d["details"])
            except Exception:
                pass
        return d
    return None
