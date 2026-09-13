from __future__ import annotations
import hashlib, hmac, secrets
from datetime import datetime, timezone, timedelta
from .db import connect

SESSION_HOURS = 24

def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 200_000)
    return f'pbkdf2_sha256$200000${salt.hex()}${digest.hex()}'

def verify_password(password: str, encoded: str) -> bool:
    try:
        _, rounds, salt_hex, digest_hex = encoded.split('$')
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False

def create_user(c, user_id: str, org_id: str, name: str, role: str, password: str):
    c.execute('INSERT INTO users(id,organization_id,name,role,password_hash,created_at) VALUES (?,?,?,?,?,?)',
              (user_id, org_id, name, role, hash_password(password), datetime.now(timezone.utc).isoformat()))

def authenticate(username: str, password: str):
    with connect() as c:
        row = c.execute('SELECT * FROM users WHERE id=?', (username,)).fetchone()
        if not row or not verify_password(password, row['password_hash']):
            return None
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
        c.execute('INSERT INTO sessions(token,user_id,organization_id,created_at,expires_at) VALUES (?,?,?,?,?)',
                  (token, row['id'], row['organization_id'], datetime.now(timezone.utc).isoformat(), expires.isoformat()))
        return {'token': token, 'user_id': row['id'], 'organization_id': row['organization_id'], 'role': row['role'], 'expires_at': expires.isoformat()}

def revoke_session(token: str | None) -> bool:
    if not token:
        return False
    with connect() as c:
        cur = c.execute('DELETE FROM sessions WHERE token=?', (token,))
        return cur.rowcount == 1

def revoke_user_sessions(user_id: str) -> int:
    with connect() as c:
        cur = c.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
        return cur.rowcount

def cleanup_expired_sessions() -> int:
    with connect() as c:
        cur = c.execute('DELETE FROM sessions WHERE expires_at<=?', (datetime.now(timezone.utc).isoformat(),))
        return cur.rowcount

def require_session(token: str | None):
    if not token:
        raise PermissionError('authentication required')
    with connect() as c:
        row = c.execute('''SELECT s.*, u.role FROM sessions s JOIN users u ON u.id=s.user_id
                           WHERE s.token=? AND s.expires_at>?''', (token, datetime.now(timezone.utc).isoformat())).fetchone()
        if not row:
            raise PermissionError('invalid or expired session')
        return dict(row)

def require_membership(session, org_id: str):
    if session['organization_id'] != org_id:
        raise PermissionError('workspace access denied')
    return session
