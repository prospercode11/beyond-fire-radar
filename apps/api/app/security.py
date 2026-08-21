from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

MINIMUM_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    # Kept in step with the Credentials schema: the request model rejects a short
    # password with a 422 before reaching this point, so a mismatch here would only
    # turn an operator-chosen password into a 500 during bootstrap.
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MINIMUM_PASSWORD_LENGTH} characters")
    salt = secrets.token_bytes(16)
    iterations = 600_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt_encoded, digest_encoded = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_encoded.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_encoded.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def new_session_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
