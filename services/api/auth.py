"""Auth helpers for NetGuard demo multi-tenancy.

- bcrypt password hashing for users
- random API key (`ng_<token>`) issued per organization, bcrypt-hashed at rest
- prefix index for quick candidate lookup before bcrypt verify

Each org has a single raw API key. Because bcrypt is one-way, the raw key
cannot be recovered after signup; ``rotate_api_key`` issues a new key on each
successful password login (returned to the client and stored only as a hash).
"""

from __future__ import annotations

import re
import secrets
from typing import Optional

import bcrypt
from sqlalchemy.orm import Session

from services.database.models import Organization, User

API_KEY_PREFIX = "ng_"
API_KEY_PREFIX_LEN = 11  # len("ng_") + 8 chars of token

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.match((value or "").strip()))


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def generate_api_key() -> str:
    """Return a printable, unguessable API key (~32 bytes of entropy)."""
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_api_key(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_api_key(raw: str, hashed: str) -> bool:
    if not raw or not hashed:
        return False
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def api_key_prefix_for(raw: str) -> str:
    """Stable, indexable prefix used to narrow the bcrypt verification search."""
    return (raw or "")[:API_KEY_PREFIX_LEN]


def lookup_org_by_api_key(db: Session, raw_key: str) -> Optional[Organization]:
    if not raw_key or not raw_key.startswith(API_KEY_PREFIX):
        return None
    prefix = api_key_prefix_for(raw_key)
    candidates = (
        db.query(Organization)
        .filter(Organization.api_key_prefix == prefix)
        .all()
    )
    for org in candidates:
        if verify_api_key(raw_key, org.api_key_hash):
            return org
    return None


def issue_new_api_key(db: Session, org: Organization) -> str:
    """Generate a fresh raw API key for an org and persist its hash + prefix."""
    raw = generate_api_key()
    org.api_key_prefix = api_key_prefix_for(raw)
    org.api_key_hash = hash_api_key(raw)
    db.add(org)
    db.commit()
    db.refresh(org)
    return raw


def create_organization_with_user(
    db: Session,
    *,
    org_name: str,
    email: str,
    password: str,
) -> tuple[Organization, User, str]:
    """Create a new org + first user; return (org, user, raw_api_key)."""
    raw_key = generate_api_key()
    org = Organization(
        name=org_name.strip(),
        api_key_prefix=api_key_prefix_for(raw_key),
        api_key_hash=hash_api_key(raw_key),
    )
    db.add(org)
    db.flush()
    user = User(
        email=email.strip().lower(),
        password_hash=hash_password(password),
        org_id=org.id,
    )
    db.add(user)
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, user, raw_key
