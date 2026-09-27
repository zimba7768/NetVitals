"""Commit and push a NetPulse change, with the footguns removed.

Driven by push-update.bat. Written in Python rather than batch so it can be
tested, and because the two mistakes this exists to prevent were both created
by clever one-liners:

* The commit message was written into the repository, so ``git add -A`` staged
  it before it could be deleted — twice.
* PowerShell's ``Set-Content -Encoding utf8`` writes a byte-order mark, which
  ended up as an invisible character at the start of the commit subject.

Both are avoided here by writing the message to a temporary file outside the
working tree, encoded without a BOM.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TRAILERS = [
    "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>",
]


def run(args: list[str], capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=ROOT, text=True,
                          capture_output=capture)


def app_version() -> str:
    """The version the app reports, which the git tag has to match."""
    text = (ROOT / "netpulse" / "config.py").read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else ""


def build_message(subject: str, body: str = "") -> str:
    """Subject, optional body, then the trailers as one contiguous block."""
    parts = [subject.strip()]
    if body.strip():
        parts.append(body.strip())
    parts.append("\n".join(TRAILERS))
    return "\n\n".join(parts) + "\n"


def write_message(message: str) -> Path:
    """Write the message somewhere git will never be asked to track it."""
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="netpulse-commit-",
        encoding="utf-8", newline="\n", delete=False)
    with handle:
        handle.write(message)            # utf-8, and no BOM: see the docstring
    return Path(handle.name)


def changed_files() -> list[str]:
    result = run(["git", "status", "--porcelain"], capture=True)
    return [line for line in result.stdout.splitlines() if line.strip()]


def tests_pass() -> bool:
    print("Running the test suite first...\n")
    result = run([sys.executable, "-m", "unittest", "discover", "-s", "tests"])
    return result.returncode == 0


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-m", "--message", default="",
                        help="commit subject; prompted for when omitted")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would happen, change nothing")
    args = parser.parse_args()

    changes = changed_files()
    if not changes:
        print("Nothing to commit — the working tree is clean.")
        return 0

    print(f"{len(changes)} change(s):\n")
    for line in changes:
        print("   " + line)
    print()

    if not args.skip_tests and not args.dry_run and not tests_pass():
        print("\nTests failed. Nothing has been committed.")
        return 1

    subject = args.message or ask("Commit message: ")
    if not subject:
        print("No message given — stopping.")
        return 1

    message = build_message(subject)
    path = write_message(message)
    version = app_version()

    if args.dry_run:
        print("--- commit message " + "-" * 40)
        print(message, end="")
        print("-" * 59)
        print(f"message file: {path}  (outside the repository)")
        print(f"would tag:    v{version}")
        os.unlink(path)
        return 0

    try:
        if run(["git", "add", "-A"]).returncode:
            return 1
        if run(["git", "commit", "-F", str(path)]).returncode:
            return 1
    finally:
        # Outside the tree, so this is tidiness rather than correctness.
        try:
            os.unlink(path)
        except OSError:
            pass

    if run(["git", "push"]).returncode:
        print("\nThe commit was made but the push failed.")
        return 1

    if version:
        tag = f"v{version}"
        existing = run(["git", "tag", "-l", tag], capture=True).stdout.strip()
        if existing:
            print(f"\nTag {tag} already exists — not re-tagging.")
        elif ask(f"\nTag this commit as {tag} and release? [y/N] ").lower() in ("y", "yes"):
            if run(["git", "tag", tag]).returncode == 0:
                run(["git", "push", "origin", tag])
                print(f"\n{tag} pushed. The release workflow builds the exe now.")
        else:
            print(f"\nNot tagged. Run 'git tag {tag} && git push origin {tag}' "
                  "when you are ready.")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
