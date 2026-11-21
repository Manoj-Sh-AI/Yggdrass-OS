"""Package and publish signed screen updates or Android APKs to the existing host.

Run with app/api's Python (cryptography installed). No private key enters an export.
"""

import argparse
import base64
import getpass
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
KEY = REPO / "local-data/mobile-update-signing/private-key.pem"
CERT = ROOT / "certs/update-certificate.pem"
SERVER_CERT = REPO / "app/api/src/yggdress_app/mobile-update-certificate.pem"
DEFAULT_ORIGIN = "https://web-production-7c89ea1a.up.railway.app"


def initialize():
    if KEY.exists():
        key = serialization.load_pem_private_key(KEY.read_bytes(), password=None)
        if not CERT.is_file():
            raise SystemExit(
                "Signing certificate missing. Restore the certificate; do not rotate silently."
            )
        cert = x509.load_pem_x509_certificate(CERT.read_bytes())
        if cert.public_key().public_numbers() != key.public_key().public_numbers():
            raise SystemExit("Signing key does not match the installed certificate.")
        SERVER_CERT.write_bytes(CERT.read_bytes())
        print("Reusing existing update signing identity.")
        return
    if CERT.exists() or SERVER_CERT.exists():
        raise SystemExit("Signing key missing. Restore it before publishing to existing apps.")
    KEY.parent.mkdir(parents=True, exist_ok=True)
    CERT.parent.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Yggdras mobile updates")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CODE_SIGNING]), critical=False)
        .sign(key, hashes.SHA256())
    )
    with KEY.open("xb") as file:
        file.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    os.chmod(KEY, 0o600)
    public = cert.public_bytes(serialization.Encoding.PEM)
    CERT.write_bytes(public)
    SERVER_CERT.write_bytes(public)
    print("Created update signing identity. Back up local-data/mobile-update-signing privately.")


def node(*arguments, capture=False):
    env = {
        **os.environ,
        "EXPO_NO_TELEMETRY": "1",
        "CI": "1",
        "NODE_ENV": "production",
        "EXPO_HOME": str(ROOT / ".cache/expo"),
    }
    result = subprocess.run(
        ["node", *map(str, arguments)],
        cwd=ROOT,
        env=env,
        check=True,
        stdout=subprocess.PIPE if capture else None,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout) if capture else None


def expo(*arguments, capture=False):
    return node(ROOT / "node_modules/expo/bin/cli", *arguments, capture=capture)


def save(record, files, output):
    key = serialization.load_pem_private_key(KEY.read_bytes(), password=None)
    body = json.dumps(record, separators=(",", ":"), sort_keys=True).encode()
    signature = key.sign(body, padding.PKCS1v15(), hashes.SHA256())
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("release.json", body)
        archive.writestr("release.sig", base64.b64encode(signature))
        for digest, path in files.items():
            archive.write(path, "assets/" + digest)
    print("Signed release:", output)
    return output


def hashed(path):
    digest = hashlib.sha256(path.read_bytes()).digest()
    return digest.hex(), base64.urlsafe_b64encode(digest).decode().rstrip("=")


def screens(origin):
    folder = ROOT / ".cache/screen-export"
    expo("export", "--platform", "android", "--output-dir", folder)
    runtime = node(
        ROOT / "node_modules/expo-updates/bin/cli.js",
        "runtimeversion:resolve",
        "--platform",
        "android",
        "--workflow",
        "managed",
        capture=True,
    )
    runtime = runtime["runtimeVersion"] if isinstance(runtime, dict) else runtime
    if not isinstance(runtime, str) or not re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", runtime):
        raise SystemExit("Expected Expo's native fingerprint runtime version.")
    config = expo("config", "--type", "public", "--json", capture=True)
    metadata = json.loads((folder / "metadata.json").read_text())["fileMetadata"]["android"]
    files = {}

    def asset(relative, extension, launch=False):
        path = (folder / relative).resolve()
        if not path.is_relative_to(folder.resolve()) or not path.is_file():
            raise SystemExit("Invalid exported asset path.")
        digest, encoded = hashed(path)
        files[digest] = path
        return {
            # Expo Asset resolves images by Metro's original key, while the
            # URL and integrity hash address the actual content with SHA-256.
            "key": digest if launch else path.name,
            "hash": encoded,
            "fileExtension": "." + extension,
            "contentType": mimetypes.guess_type("file." + extension)[0]
            or "application/octet-stream",
            "url": origin + "/api/mobile-updates/assets/" + digest,
        }

    launch = asset(metadata["bundle"], "js", launch=True)
    launch["contentType"] = "application/javascript"
    record = {
        "id": str(uuid4()),
        "createdAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "runtimeVersion": runtime,
        "launchAsset": launch,
        "assets": [asset(a["path"], a["ext"]) for a in metadata["assets"]],
        "metadata": {"channel": "production"},
        "extra": {
            "expoClient": {
                "name": config["name"],
                "slug": config["slug"],
                "version": config["version"],
                "sdkVersion": config["sdkVersion"],
                "runtimeVersion": runtime,
                "extra": config.get("extra", {}),
            }
        },
    }
    return save(record, files, ROOT / "dist" / ("screens-" + record["id"] + ".zip"))


# The public React Native/Expo template debug key. Anyone can sign with it, so an
# APK carrying it is never offered to phones.
PUBLIC_DEBUG_SIGNER = "fac61745dc0903786fb9ede62a962b399f7348f0bb6f899b8332667591033b9c"


def apk_signers(apk):
    tools = ROOT / ".cache/android-tools"
    apksigner = sorted((tools / "sdk/build-tools").glob("*/apksigner.bat"))[-1]
    java = next((tools / "java").glob("jdk-*"))
    result = subprocess.run(
        ["cmd.exe", "/c", str(apksigner), "verify", "--print-certs", str(apk)],
        env={**os.environ, "JAVA_HOME": str(java)},
        check=True,
        capture_output=True,
        text=True,
    )
    return re.findall(r"certificate SHA-256 digest: ([0-9a-f]{64})", result.stdout)


def check_signers(signers):
    if not signers:
        raise SystemExit("The APK has no verifiable signature.")
    if PUBLIC_DEBUG_SIGNER in signers:
        raise SystemExit("The APK is signed with the public debug key; rebuild with your own key.")


def android(origin, apk):
    metadata = json.loads((apk.parent / "output-metadata.json").read_text())["elements"][0]
    if metadata["outputFile"] != apk.name:
        raise SystemExit("Choose the APK beside its Android build metadata.")
    check_signers(apk_signers(apk))
    digest, encoded = hashed(apk)
    record = {
        "kind": "android",
        "package": "app.yggdras.mobile",
        "sha256": digest,
        "hash": encoded,
        "version": metadata["versionName"],
        "versionCode": metadata["versionCode"],
        "url": origin + "/api/mobile-updates/apk/" + digest + ".apk",
    }
    return save(record, {digest: apk}, ROOT / "dist" / f"android-{record['version']}.zip")


def publish(origin, archive):
    import httpx

    password = getpass.getpass("Yggdras password (not saved): ")
    with httpx.Client(timeout=120, follow_redirects=False) as client:
        response = client.post(
            origin + "/api/backend/mobile/auth/login",
            headers={"Origin": origin},
            json={"password": password},
        )
        password = None
        if response.status_code != 200:
            raise SystemExit("Sign-in failed; no release was uploaded.")
        token = response.json()["token"]
        headers = {"Authorization": "Bearer " + token, "Origin": origin}
        try:
            with archive.open("rb") as file:
                response = client.post(
                    origin + "/api/mobile-updates/publish",
                    content=file,
                    headers={
                        **headers,
                        "Content-Type": "application/zip",
                        "Content-Length": str(archive.stat().st_size),
                    },
                )
            if response.status_code != 200:
                raise SystemExit(
                    f"Publishing failed (HTTP {response.status_code}). No update was activated."
                )
            print("Release published successfully.")
        finally:
            client.post(origin + "/api/backend/auth/logout", headers=headers)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init-signing", "screens", "android", "publish"])
    parser.add_argument("--origin", default=DEFAULT_ORIGIN)
    parser.add_argument(
        "--apk", type=Path, default=ROOT / "android/app/build/outputs/apk/release/app-release.apk"
    )
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    parsed = urlsplit(args.origin)
    if (
        parsed.scheme != "https"
        or parsed.path not in ("", "/")
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise SystemExit("Use the application's HTTPS origin without a path or credentials.")
    origin = args.origin.rstrip("/")
    if args.command == "init-signing":
        initialize()
        return
    if not KEY.is_file():
        raise SystemExit("Initialize signing once before building the APK or publishing updates.")
    archive = (
        screens(origin)
        if args.command == "screens"
        else android(origin, args.apk)
        if args.command == "android"
        else args.archive
    )
    if not archive or not archive.is_file():
        raise SystemExit("Select a signed release archive with --archive.")
    if args.publish or args.command == "publish":
        publish(origin, archive)


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError) as error:
        raise SystemExit("Mobile release stopped: " + type(error).__name__) from None
