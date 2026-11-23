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

    @property
    def origins(self) -> tuple[str, ...]:
        """The web apps allowed to call this backend (YGGDRESS_ORIGIN, comma-separated): e.g.
        the hosted web app and, while it is still in use, the laptop's own web app."""
        return tuple(o.strip().rstrip("/") for o in self.origin.split(",") if o.strip())

    def validate(self):
        from .security import valid_hash

        if not self.database_url or not valid_hash(self.password_hash):
            raise ValueError("Application database and password hash must be configured privately.")
        if not self.origins:
            raise ValueError("Configure an exact application origin.")
        for value in self.origins:
            origin = urlparse(value)
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
            loopback = origin.hostname in ("127.0.0.1", "localhost", "::1")
            if self.local_http and (origin.scheme != "http" or not loopback):
                raise ValueError(
                    "Insecure cookies are permitted only for loopback HTTP development."
                )
            # Plain HTTP only for a loopback web app (browsers treat it as a secure context,
            # so it also works beside an HTTPS one with secure cookies).
            if origin.scheme != "https" and not loopback:
                raise ValueError("HTTP sessions are permitted only for loopback development.")
        if type(self.mobile_sensitive_access) is not bool:
            raise ValueError("Mobile sensitive access requires an explicit owner setting.")
        if self.brain_mode not in ("mock", "unavailable"):
            raise ValueError("Real Brain integration is blocked pending Claude's contract.")
