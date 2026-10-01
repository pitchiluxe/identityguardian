"""Download verified portable Java/Keycloak into ignored .local; no global install."""

import hashlib
import json
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".local" / "runtime"
KEYCLOAK_VERSION = "26.7.3"


def download(client, url, name, checksum, algorithm="sha256"):
    path = RUNTIME / name
    if not path.exists():
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with path.open("wb") as output:
                for chunk in response.iter_bytes():
                    output.write(chunk)
    actual = hashlib.new(algorithm, path.read_bytes()).hexdigest()
    if actual.lower() != checksum.lower():
        raise SystemExit(f"Checksum mismatch for {name}; do not execute it.")
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            if not (RUNTIME / item.filename).resolve().is_relative_to(RUNTIME.resolve()):
                raise SystemExit("Unsafe archive member")
        archive.extractall(RUNTIME)


def main():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        assets = client.get(
            "https://api.adoptium.net/v3/assets/latest/21/hotspot",
            params={"architecture": "x64", "image_type": "jdk", "os": "windows"},
        )
        assets.raise_for_status()
        package = assets.json()[0]["binary"]["package"]
        print("Downloading and verifying portable Java 21…", flush=True)
        download(client, package["link"], "java.zip", package["checksum"])
        base = f"https://github.com/keycloak/keycloak/releases/download/{KEYCLOAK_VERSION}/keycloak-{KEYCLOAK_VERSION}.zip"
        print("Downloading and verifying Keycloak distribution…", flush=True)
        # SHA-256 published in the official GitHub release asset metadata.
        download(
            client,
            base,
            "keycloak.zip",
            "27a6535553c3cdcd083872ba40629efafb3475e3b758e0c6f691395561dd0f1f",
        )
    java = next(RUNTIME.glob("jdk-*"))
    (RUNTIME / "versions.json").write_text(
        json.dumps({"java_home": str(java), "keycloak": KEYCLOAK_VERSION})
    )
    print("Portable runtime ready; no system installation changed.")


if __name__ == "__main__":
    main()
