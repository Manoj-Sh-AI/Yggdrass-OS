import base64
import hashlib
import hmac
import secrets


def password_hash(password: str) -> str:
    if not 12 <= len(password) <= 1024:
        raise ValueError("Use a personal password of 12 to 1024 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, maxmem=67108864)
    return (
        "scrypt$32768$8$1$"
        + base64.b64encode(salt).decode()
        + "$"
        + base64.b64encode(digest).decode()
    )


def valid_hash(value: str) -> bool:
    try:
        kind, n, r, p, salt, digest = value.split("$")
        return (
            (kind, n, r, p) == ("scrypt", "32768", "8", "1")
            and len(base64.b64decode(salt, validate=True)) == 16
            and len(base64.b64decode(digest, validate=True)) == 64
        )
    except (ValueError, TypeError):
        return False


def verify_password(password: str, encoded: str) -> bool:
    if not valid_hash(encoded) or not isinstance(password, str) or len(password) > 1024:
        return False
    _, n, r, p, salt, digest = encoded.split("$")
    actual = hashlib.scrypt(
        password.encode(),
        salt=base64.b64decode(salt),
        n=int(n),
        r=int(r),
        p=int(p),
        maxmem=67108864,
    )
    return hmac.compare_digest(actual, base64.b64decode(digest))


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
