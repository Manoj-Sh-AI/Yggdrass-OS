"""Signed, immutable Android updates stored on the existing backend volume."""

import asyncio
import base64
import hashlib
import json
import os
import re
import tempfile
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse

MAX_RELEASE = 100 * 1024 * 1024
DIGEST = re.compile(r"[a-f0-9]{64}\Z")
RUNTIME = re.compile(r"(?:[a-f0-9]{40}|[a-f0-9]{64})\Z")
CERTIFICATE = Path(__file__).with_name("mobile-update-certificate.pem")


class MobileUpdates:
    def __init__(self, root: Path, certificate: Path = CERTIFICATE):
        self.root, self.certificate = root, certificate
        self.lock = threading.Lock()

    def latest(self, runtime: str):
        if not RUNTIME.fullmatch(runtime):
            return None
        path = self.root / "channels" / (runtime + ".json")
        return json.loads(path.read_bytes()) if path.is_file() else None

    def native(self):
        path = self.root / "android.json"
        return json.loads(path.read_bytes()) if path.is_file() else None

    def publish(self, archive: Path):
        try:
            with zipfile.ZipFile(archive) as release:
                files = release.infolist()
                names = [f.filename for f in files]
                if (
                    len(files) > 2000
                    or len(names) != len(set(names))
                    or sum(f.file_size for f in files) > MAX_RELEASE
                    or any(
                        not (
                            n in ("release.json", "release.sig")
                            or re.fullmatch(r"assets/[a-f0-9]{64}", n)
                        )
                        for n in names
                    )
                ):
                    raise ValueError()
                body = release.read("release.json")
                if len(body) > 512000:
                    raise ValueError()
                signature = base64.b64decode(release.read("release.sig"), validate=True)
                cert = x509.load_pem_x509_certificate(self.certificate.read_bytes())
                cert.public_key().verify(signature, body, padding.PKCS1v15(), hashes.SHA256())
                record = json.loads(body)
                native = record.get("kind") == "android"
                if native:
                    if (
                        record.get("package") != "app.yggdras.mobile"
                        or type(record.get("versionCode")) is not int
                        or record["versionCode"] < 1
                        or not re.fullmatch(r"\d+\.\d+\.\d+", record.get("version", ""))
                    ):
                        raise ValueError()
                    assets = [
                        {"key": record["sha256"], "hash": record["hash"], "url": record["url"]}
                    ]
                    target = self.root / "android.json"
                else:
                    identifier = str(UUID(record["id"]))
                    if identifier != record["id"] or not RUNTIME.fullmatch(
                        record["runtimeVersion"]
                    ):
                        raise ValueError()
                    when = datetime.fromisoformat(record["createdAt"])
                    if when.utcoffset() is None:
                        raise ValueError()
                    assets = [record["launchAsset"], *record["assets"]]
                    target = self.root / "channels" / (record["runtimeVersion"] + ".json")
                verified = {}
                for asset in assets:
                    key = asset["key"]
                    if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{32,64}", key):
                        raise ValueError()
                    url = urlsplit(asset["url"])
                    blob = key if native else url.path.rsplit("/", 1)[-1]
                    if not DIGEST.fullmatch(blob):
                        raise ValueError()
                    expected = (
                        f"/api/mobile-updates/apk/{blob}.apk"
                        if native
                        else f"/api/mobile-updates/assets/{blob}"
                    )
                    if (
                        url.scheme != "https"
                        or not url.hostname
                        or url.path != expected
                        or url.query
                        or url.fragment
                        or url.username
                        or url.password
                    ):
                        raise ValueError()
                    data = release.read("assets/" + blob)
                    digest = hashlib.sha256(data).digest()
                    if (
                        digest.hex() != blob
                        or base64.urlsafe_b64encode(digest).decode().rstrip("=") != asset["hash"]
                    ):
                        raise ValueError()
                    verified[blob] = data
                if set(names) != {
                    "release.json",
                    "release.sig",
                    *("assets/" + k for k in verified),
                }:
                    raise ValueError()
                saved = {"body": body.decode(), "signature": base64.b64encode(signature).decode()}
                with self.lock:
                    if not native:
                        identity = self.root / "manifests" / (record["id"] + ".json")
                        if identity.is_file() and json.loads(identity.read_bytes()) != saved:
                            raise ValueError()
                        prior = self.latest(record["runtimeVersion"])
                        if prior:
                            previous = json.loads(prior["body"])
                            if previous["id"] == record["id"] and prior != saved:
                                raise ValueError()
                            if previous["createdAt"] > record["createdAt"]:
                                raise ValueError()
                    elif self.native():
                        previous = json.loads(self.native()["body"])
                        if previous["versionCode"] > record["versionCode"] or (
                            previous["versionCode"] == record["versionCode"] and previous != record
                        ):
                            raise ValueError()
                    blobs = self.root / "assets"
                    blobs.mkdir(parents=True, exist_ok=True)
                    for key, data in verified.items():
                        if not (blobs / key).is_file():
                            self._atomic(blobs / key, data)
                    if not native:
                        self._atomic(identity, json.dumps(saved).encode())
                    self._atomic(target, json.dumps(saved).encode())
                return {
                    "published": True,
                    "kind": "android" if native else "screens",
                    "version": record.get("version") or record["runtimeVersion"],
                }
        except (ValueError, KeyError, TypeError, zipfile.BadZipFile, InvalidSignature, OSError):
            raise HTTPException(
                400, "Release signature, compatibility or asset validation failed."
            ) from None

    @staticmethod
    def _atomic(path: Path, data: bytes):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
                temporary = Path(file.name)
                file.write(data)
                file.flush()
            temporary.replace(path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)


def mobile_update_router(session, root=None, certificate=CERTIFICATE):
    router = APIRouter(prefix="/v1/mobile-updates")
    authenticated = Depends(session)
    store = MobileUpdates(
        Path(root or os.environ.get("YGGDRAS_HOME", ".local-data")) / "mobile-updates", certificate
    )

    @router.get("/manifest")
    def manifest(request: Request):
        headers = {
            "expo-protocol-version": "1",
            "expo-sfv-version": "0",
            "expo-manifest-filters": 'channel="production"',
        }
        if request.headers.get("expo-platform") != "android":
            raise HTTPException(400, "Android updates only.")
        if request.headers.get("expo-protocol-version", "1") != "1":
            raise HTTPException(406, "Unsupported updates protocol.")
        saved = store.latest(request.headers.get("expo-runtime-version", ""))
        if not saved or json.loads(saved["body"])["id"] == request.headers.get(
            "expo-current-update-id"
        ):
            return Response(status_code=204, headers=headers)
        headers["expo-signature"] = (
            f'sig="{saved["signature"]}", keyid="main", alg="rsa-v1_5-sha256"'
        )
        return Response(saved["body"], headers=headers, media_type="application/expo+json")

    @router.get("/android")
    def android():
        value = store.native()
        return {"release": json.loads(value["body"]) if value else None}

    @router.get("/assets/{digest}")
    def asset(digest: str):
        if not DIGEST.fullmatch(digest) or not (store.root / "assets" / digest).is_file():
            raise HTTPException(404, "Asset unavailable.")
        return FileResponse(store.root / "assets" / digest, media_type="application/octet-stream")

    @router.get("/apk/{name}")
    def apk(name: str):
        digest = name.removesuffix(".apk")
        if not name.endswith(".apk") or not DIGEST.fullmatch(digest):
            raise HTTPException(404, "App update unavailable.")
        saved = store.native()
        if not saved or json.loads(saved["body"])["sha256"] != digest:
            raise HTTPException(404, "App update unavailable.")
        record = json.loads(saved["body"])
        return FileResponse(
            store.root / "assets" / digest,
            media_type="application/vnd.android.package-archive",
            filename=f"Yggdress-OS-{record['version']}.apk",
        )

    @router.post("/publish")
    async def publish(request: Request, _auth=authenticated):
        store.root.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=store.root, suffix=".zip", delete=False) as file:
                temporary = Path(file.name)
                size = 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_RELEASE:
                        raise HTTPException(413, "Release is too large.")
                    file.write(chunk)
            return await asyncio.to_thread(store.publish, temporary)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    return router
