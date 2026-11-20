import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True, repr=False)
class Settings:
    database_url: str
    password_hash: str
    origin: str
    local_http: bool = False
    brain_mode: str = "mock"
    mobile_sensitive_access: bool = False

    @classmethod
    def environment(cls):
        settings = cls(
            os.environ.get("YGGDRESS_DATABASE_URL", ""),
            os.environ.get("YGGDRESS_PASSWORD_HASH", ""),
            os.environ.get("YGGDRESS_ORIGIN", ""),
            os.environ.get("YGGDRESS_LOCAL_HTTP") == "1",
            os.environ.get("YGGDRESS_BRAIN_MODE", "mock"),
            os.environ.get("YGGDRESS_MOBILE_SENSITIVE_ACCESS") == "1",
        )
        settings.validate()
        return settings

    def validate(self):
        from .security import valid_hash

        if not self.database_url or not valid_hash(self.password_hash):
            raise ValueError("Application database and password hash must be configured privately.")
        origin = urlparse(self.origin)
        if (
            origin.scheme not in ("https", "http")
            or not origin.netloc
            or origin.path
            or origin.query
            or origin.fragment
            or origin.username
            or origin.password
        ):
            raise ValueError("Configure an exact application origin.")
        if self.local_http and (
            origin.scheme != "http" or origin.hostname not in ("127.0.0.1", "localhost", "::1")
        ):
            raise ValueError("Insecure cookies are permitted only for loopback HTTP development.")
        if origin.scheme != "https" and not (
            self.local_http and origin.hostname in ("127.0.0.1", "localhost", "::1")
        ):
            raise ValueError("HTTP sessions are permitted only for loopback development.")
        if type(self.mobile_sensitive_access) is not bool:
            raise ValueError("Mobile sensitive access requires an explicit owner setting.")
        if self.brain_mode not in ("mock", "unavailable"):
            raise ValueError("Real Brain integration is blocked pending Claude's contract.")
