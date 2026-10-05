"""Scan tracked files for credentials. Exit 1 on findings. Prints locations, never the values."""

import re
import shutil
import subprocess  # noqa: S404 - fixed git invocation
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "Slack token": re.compile(r"\bxox[abpors]-[A-Za-z0-9-]{10,}\b"),
    "Anthropic API key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    "OpenAI API key": re.compile(r"\bsk-(?!ant-)(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "assigned secret": re.compile(
        r"(?i)\b(password|passwd|secret|api_key|client_secret|master_key|signing_key)\s*[=:]\s*"
        r"['\"]?(?!\{|\$|<|os\.environ|settings\.|none|null|true|false|\"\")[A-Za-z0-9+/_\-]{20,}={0,2}['\"]?"
    ),
    "connection string with password": re.compile(r"postgres(?:ql)?://[^:/\s]+:(?!\{)[^@\s{]{8,}@"),
}
SKIP = {"package-lock.json", "requirements.lock"}


def tracked_files(root: Path):
    try:
        git = shutil.which("git")
        if not git:
            raise OSError("git not found")
        out = subprocess.run(  # noqa: S603 - fixed git command, argument list, no shell
            [git, "-c", f"safe.directory={root.as_posix()}", "ls-files"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return [root / line for line in out.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        return [p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]


def scan(files):
    findings = []
    for path in files:
        if (
            path.name in SKIP
            or path.suffix in {".png", ".jpg", ".zip", ".ico"}
            or not path.exists()
        ):
            continue
        if path.name == ".env" or path.name.startswith(".env.") and path.name != ".env.example":
            findings.append((str(path), 0, "environment file is tracked"))
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for name, pattern in PATTERNS.items():
                if pattern.search(line) and "secret-scan: allow" not in line:
                    findings.append(
                        (
                            str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
                            number,
                            name,
                        )
                    )
    return findings


def main():
    findings = scan(tracked_files(ROOT))
    for path, line, name in findings:
        print(f"{path}:{line}: possible {name}")
    print(f"{len(findings)} finding(s)")
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
