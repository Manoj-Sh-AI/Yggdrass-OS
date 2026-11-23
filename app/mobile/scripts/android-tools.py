"""Project-local Android tools. No machine-wide installation or private credentials."""

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "android-tools"
# The owner's APK upload key. Git-ignored; back it up privately. Losing it means
# the next APK cannot install over the current one (uninstall + reinstall).
SIGNING = ROOT.parents[1] / "local-data" / "android-signing"


def android_key():
    """Create the release upload key once. Never overwrites an existing key."""
    keystore = SIGNING / "yggdras-upload.p12"
    properties = SIGNING / "signing.properties"
    if keystore.exists() or properties.exists():
        raise RuntimeError("An Android signing key already exists; it is never replaced.")
    SIGNING.mkdir(parents=True, exist_ok=True)
    password = secrets.token_urlsafe(32)
    keytool = next((CACHE / "java").glob("jdk-*")) / "bin" / "keytool.exe"
    subprocess.run(
        [
            str(keytool),
            "-genkeypair",
            "-storetype",
            "PKCS12",
            "-keystore",
            str(keystore),
            "-alias",
            "yggdras-upload",
            "-keyalg",
            "RSA",
            "-keysize",
            "4096",
            "-validity",
            "10000",
            "-dname",
            "CN=Yggdras Android",
            "-storepass:env",
            "YGGDRAS_KEY_PASSWORD",
            "-keypass:env",
            "YGGDRAS_KEY_PASSWORD",
        ],
        env={**os.environ, "YGGDRAS_KEY_PASSWORD": password},
        check=True,
        capture_output=True,
    )
    # Java properties: backslashes must be escaped; forward slashes avoid that.
    properties.write_text(
        f"storeFile={keystore.as_posix()}\nstorePassword={password}\n"
        f"keyAlias=yggdras-upload\nkeyPassword={password}\n"
    )
    print("Created the Android upload key in local-data/android-signing. Back it up privately.")


def short_root():
    """A drive alias refers to this project only; no tool files leave the project."""
    pointer = CACHE / "drive.txt"
    if pointer.exists():
        drive = pointer.read_text().strip()
        target = Path(drive + "\\") / ROOT.name
        if target.is_dir() and os.path.samefile(target, ROOT):
            return target
        if os.path.isdir(drive + "\\") and os.path.samefile(drive + "\\", ROOT):
            # Upgrade our own earlier root alias: Expo's find-up excludes drive roots.
            subprocess.run(["subst", drive, "/d"], check=True, capture_output=True)
            subprocess.run(["subst", drive, str(ROOT.parent)], check=True, capture_output=True)
            if not os.path.samefile(target, ROOT):
                raise RuntimeError("Build alias does not resolve to the project.")
            return target
    for letter in "YZXWVU":
        drive = letter + ":"
        if os.path.exists(drive + "\\"):
            continue
        subprocess.run(["subst", drive, str(ROOT.parent)], check=True, capture_output=True)
        target = Path(drive + "\\") / ROOT.name
        if not os.path.samefile(target, ROOT):
            raise RuntimeError("Build drive alias did not resolve to this project.")
        pointer.write_text(drive)
        return target
    raise RuntimeError("No free drive alias is available for the local Android build.")


def download(url, destination, checksum, algorithm="sha256"):
    if (
        destination.exists()
        and hashlib.new(algorithm, destination.read_bytes()).hexdigest() == checksum
    ):
        return
    request = urllib.request.Request(url, headers={"User-Agent": "Yggdras-local-Android-build"})
    with urllib.request.urlopen(request, timeout=90) as source, destination.open("wb") as target:
        shutil.copyfileobj(source, target)
    if hashlib.new(algorithm, destination.read_bytes()).hexdigest() != checksum:
        raise RuntimeError("Build tool checksum did not match its publisher's metadata.")


def extract(archive, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zipped:
        for item in zipped.infolist():
            base = os.path.abspath(destination)
            target = os.path.abspath(destination / item.filename)
            if os.path.commonpath([base, target]) != base:
                raise RuntimeError("Unexpected archive path.")
        zipped.extractall(destination)


def environment():
    cache = short_root() / ".cache/android-tools"
    jdk = next((cache / "java").glob("jdk-*"))
    sdk = cache / "sdk"
    return {
        **os.environ,
        "JAVA_HOME": str(jdk),
        "ANDROID_HOME": str(sdk),
        "ANDROID_SDK_ROOT": str(sdk),
        "ANDROID_USER_HOME": str(cache / "android-user"),
        # A short physical cache outside OneDrive avoids Java's SUBST probing,
        # Ninja's path limit, and sync locks during Gradle's atomic moves.
        "GRADLE_USER_HOME": str(Path.home() / "AppData/Local/Temp/yggdras-gradle"),
        "YGGDRAS_NATIVE_CACHE": str(short_root() / ".cache/cxx"),
        "YGGDRAS_ANDROID_SIGNING": str(SIGNING / "signing.properties"),
        "CMAKE_BUILD_PARALLEL_LEVEL": "2",
        "EXPO_NO_TELEMETRY": "1",
        "CI": "1",
        "PATH": str(jdk / "bin")
        + os.pathsep
        + str(sdk / "platform-tools")
        + os.pathsep
        + os.environ.get("PATH", ""),
    }


def setup():
    CACHE.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(ROOT).free < 6 * 1024**3:
        raise RuntimeError(
            "At least 6 GB of free disk space is required for the Android build tools."
        )
    if not list((CACHE / "java").glob("jdk-*/bin/java.exe")):
        url = "https://aka.ms/download-jdk/microsoft-jdk-17-windows-x64.zip"
        with urllib.request.urlopen(url + ".sha256sum.txt", timeout=40) as response:
            checksum = response.read().decode().split()[0]
        print("Downloading publisher-verified Java 17.", flush=True)
        download(url, CACHE / "java.zip", checksum)
        extract(CACHE / "java.zip", CACHE / "java")
    cache = short_root() / ".cache/android-tools"
    sdk = cache / "sdk"
    manager = sdk / "cmdline-tools/latest/bin/sdkmanager.bat"
    if not manager.exists():
        print("Downloading Android command-line tools.", flush=True)
        with urllib.request.urlopen(
            "https://dl.google.com/android/repository/repository2-3.xml", timeout=40
        ) as response:
            root = ET.fromstring(response.read())
        package = next(
            p
            for p in root
            if p.tag.endswith("remotePackage") and p.attrib.get("path") == "cmdline-tools;latest"
        )
        archives = package.find("archives")
        archive = next(a for a in archives if a.findtext("host-os") == "windows")
        complete = archive.find("complete")
        checksum = complete.find("checksum")
        filename = complete.findtext("url")
        download(
            "https://dl.google.com/android/repository/" + filename,
            CACHE / "android.zip",
            checksum.text,
            checksum.attrib.get("type", "sha1"),
        )
        extract(CACHE / "android.zip", cache / "unpacked")
        (sdk / "cmdline-tools").mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            cache / "unpacked/cmdline-tools", sdk / "cmdline-tools/latest", dirs_exist_ok=True
        )
    env = environment()
    packages = [
        "platform-tools",
        "platforms;android-36",
        "build-tools;36.0.0",
        "ndk;27.1.12297006",
        "cmake;3.22.1",
    ]
    # The 2026 Android CLI compatibility wrapper uses slash-separated IDs.
    # A package file also avoids cmd.exe interpreting semicolons as separators.
    modern = "Android CLI will be used instead" in manager.read_text()
    package_file = cache / "packages.txt"
    package_file.write_text("\n".join(p.replace(";", "/") if modern else p for p in packages))
    # License acceptance is confined to this project's SDK installation.
    with (CACHE / "sdk-install.log").open("w") as log:
        subprocess.run(
            [str(manager), "--licenses", "--sdk_root=" + str(sdk)],
            input="y\n" * 100,
            text=True,
            stdout=log,
            stderr=log,
            env=env,
            check=True,
        )
        print("Installing Android SDK and native build tools.", flush=True)
        subprocess.run(
            [str(manager), "--sdk_root=" + str(sdk), "--package_file=" + str(package_file)],
            stdout=log,
            stderr=log,
            env=env,
            check=True,
        )
    required = [
        sdk / "platform-tools/adb.exe",
        sdk / "platforms/android-36/android.jar",
        sdk / "build-tools/36.0.0/aapt2.exe",
        sdk / "ndk/27.1.12297006/source.properties",
        sdk / "cmake/3.22.1/bin/cmake.exe",
    ]
    if any(not path.is_file() for path in required):
        raise RuntimeError("Android SDK setup is incomplete; inspect the project-local SDK log.")
    print("Project-local Android build tools are ready.", flush=True)


def run(arguments):
    env = environment()
    root = short_root()
    if arguments[0] == "adb":
        command = [str(root / ".cache/android-tools/sdk/platform-tools/adb.exe"), *arguments[1:]]
    elif arguments[0] == "build":
        proxy_init = CACHE / "network.gradle"
        proxy_init.write_text("""
def configured = System.getenv('HTTPS_PROXY') ?: System.getenv('https_proxy')
if (configured) {
    def address = new URI(configured)
    ['http', 'https'].each { protocol ->
        System.setProperty(protocol + '.proxyHost', address.host)
        System.setProperty(protocol + '.proxyPort', String.valueOf(address.port > 0 ? address.port : 80))
    }
    System.setProperty('http.nonProxyHosts', 'localhost|127.*|[::1]')
}
gradle.beforeProject { project ->
    ['com.android.application', 'com.android.library'].each { plugin ->
        project.plugins.withId(plugin) {
            def android = project.extensions.findByName('android')
            android.externalNativeBuild.cmake.buildStagingDirectory = new File(System.getenv('YGGDRAS_NATIVE_CACHE'), project.name)
            android.defaultConfig.externalNativeBuild.cmake.arguments.add('-DCMAKE_OBJECT_PATH_MAX=240')
        }
    }
}
""")
        command = [
            str(ROOT / "android/gradlew.bat"),
            "assembleRelease",
            "--no-daemon",
            "--max-workers=2",
            "-I",
            str(root / ".cache/android-tools/network.gradle"),
            "-PreactNativeArchitectures=arm64-v8a",
        ]
    elif arguments[0] == "expo":
        command = ["cmd.exe", "/c", "npx.cmd", "expo", *arguments[1:]]
    else:
        raise RuntimeError("Unknown build operation.")
    return subprocess.call(
        command, cwd=ROOT / "android" if arguments[0] == "build" else root, env=env
    )


if __name__ == "__main__":
    try:
        if len(sys.argv) == 1 or sys.argv[1] == "setup":
            setup()
        elif sys.argv[1] == "android-key":
            android_key()
        else:
            raise SystemExit(run(sys.argv[1:]))
    except Exception as error:
        print("Android tooling stopped: " + type(error).__name__)
        raise SystemExit(1) from None
