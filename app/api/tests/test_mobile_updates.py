import base64
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from yggdress_app.mobile_updates import mobile_update_router

ORIGIN = "https://app.example.test"
RUNTIME = "a" * 40


@pytest.fixture
def updates(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Invented test updates")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    path = tmp_path / "public.pem"
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    def session(request: Request):
        if request.headers.get("authorization") != "Bearer invented-owner":
            raise HTTPException(401)

    app = FastAPI()
    app.include_router(mobile_update_router(session, root=tmp_path, certificate=path))
    return TestClient(app), key, tmp_path


def archive(
    key,
    data=b"invented JavaScript",
    native=False,
    tamper=False,
    extra=False,
    identifier=None,
    asset_key=None,
):
    digest = hashlib.sha256(data).digest()
    hex_digest = digest.hex()
    asset = {
        "key": asset_key or hex_digest,
        "hash": base64.urlsafe_b64encode(digest).decode().rstrip("="),
        "url": ORIGIN + "/api/mobile-updates/assets/" + hex_digest,
        "contentType": "application/javascript",
    }
    if native:
        record = {
            "kind": "android",
            "package": "app.yggdras.mobile",
            "version": "0.3.2",
            "versionCode": 2,
            "sha256": hex_digest,
            "hash": asset["hash"],
            "url": ORIGIN + "/api/mobile-updates/apk/" + hex_digest + ".apk",
        }
    else:
        record = {
            "id": identifier or str(uuid4()),
            "createdAt": datetime.now(UTC).isoformat(),
            "runtimeVersion": RUNTIME,
            "launchAsset": asset,
            "assets": [],
            "metadata": {"channel": "production"},
        }
    body = json.dumps(record).encode()
    sig = key.sign(body, padding.PKCS1v15(), hashes.SHA256())
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as zipped:
        zipped.writestr("release.json", body)
        zipped.writestr("release.sig", base64.b64encode(sig))
        zipped.writestr("assets/" + hex_digest, b"modified bytes" if tamper else data)
        if extra:
            zipped.writestr("../private-key.pem", b"must never be extracted")
    return output.getvalue(), record


def upload(client, content, signed_in=True):
    return client.post(
        "/v1/mobile-updates/publish",
        content=content,
        headers={"Authorization": "Bearer invented-owner"} if signed_in else {},
    )


def test_owner_publish_and_signature_verified_for_matching_native_runtime(updates):
    client, key, _ = updates
    content, record = archive(key)
    assert upload(client, content).status_code == 200
    headers = {"expo-platform": "android", "expo-runtime-version": RUNTIME}
    response = client.get("/v1/mobile-updates/manifest", headers=headers)
    assert response.status_code == 200 and response.json() == record
    signature = response.headers["expo-signature"].split('"')[1]
    key.public_key().verify(
        base64.b64decode(signature), response.content, padding.PKCS1v15(), hashes.SHA256()
    )
    assert (
        client.get("/v1/mobile-updates/assets/" + record["launchAsset"]["key"]).content
        == b"invented JavaScript"
    )
    assert (
        client.get(
            "/v1/mobile-updates/manifest", headers={**headers, "expo-runtime-version": "b" * 40}
        ).status_code
        == 204
    )
    assert (
        client.get(
            "/v1/mobile-updates/manifest",
            headers={**headers, "expo-current-update-id": record["id"]},
        ).status_code
        == 204
    )


def test_unsigned_access_tampering_and_archive_traversal_cannot_publish(updates):
    client, key, root = updates
    content, _ = archive(key)
    assert upload(client, content, signed_in=False).status_code == 401
    assert upload(client, archive(key, tamper=True)[0]).status_code == 400
    assert upload(client, archive(key, extra=True)[0]).status_code == 400
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert upload(client, archive(other)[0]).status_code == 400
    assert not (root / "mobile-updates/channels").exists()


def test_previous_assets_survive_new_publication_and_update_ids_are_immutable(updates):
    client, key, _ = updates
    first, record = archive(key)
    assert upload(client, first).status_code == 200
    modified, _ = archive(key, data=b"different", identifier=record["id"])
    assert upload(client, modified).status_code == 400
    second, _ = archive(key, data=b"new compatible screen")
    assert upload(client, second).status_code == 200
    assert upload(client, modified).status_code == 400
    assert (
        client.get("/v1/mobile-updates/assets/" + record["launchAsset"]["key"]).status_code == 200
    )


def test_native_release_is_downloadable_and_does_not_enter_screen_channel(updates):
    client, key, _ = updates
    assert client.get("/v1/mobile-updates/android").json() == {"release": None}
    content, record = archive(key, data=b"invented APK transport fixture", native=True)
    assert upload(client, content).status_code == 200
    assert client.get("/v1/mobile-updates/android").json()["release"]["versionCode"] == 2
    response = client.get("/v1/mobile-updates/apk/" + record["sha256"] + ".apk")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.android.package-archive"
    assert "Yggdress-OS-0.3.2.apk" in response.headers["content-disposition"]
    assert (
        client.get(
            "/v1/mobile-updates/manifest",
            headers={"expo-platform": "android", "expo-runtime-version": RUNTIME},
        ).status_code
        == 204
    )


def test_metro_asset_keys_are_preserved_separately_from_download_integrity_hashes(updates):
    client, key, _ = updates
    content, record = archive(key, asset_key="b" * 32)
    assert upload(client, content).status_code == 200
    response = client.get(
        "/v1/mobile-updates/manifest",
        headers={
            "expo-platform": "android",
            "expo-runtime-version": RUNTIME,
        },
    )
    assert response.json()["launchAsset"]["key"] == "b" * 32
    digest = record["launchAsset"]["url"].rsplit("/", 1)[-1]
    assert client.get("/v1/mobile-updates/assets/" + digest).content == b"invented JavaScript"
