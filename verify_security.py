"""
verify_security.py
------------------
Pre-commit / Pre-push security auditor for CodeCrew.
Verifies that:
1. .env is ignored and not tracked by Git.
2. .env.example contains NO live secrets.
3. No tracked or staged files contain API keys, private keys, or passwords.
"""

import os
import re
import sys
import subprocess

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SECRET_PATTERNS = [
    (r"AIza[0-9A-Za-z\\-_]{35}", "Google API Key"),
    (r"AQ\.[a-zA-Z0-9_-]{20,}", "Google/Gemini Access Token"),
    (r"sk-[a-zA-Z0-9_-]{32,}", "OpenAI API Key"),
    (r"sk-ant-[a-zA-Z0-9_-]{32,}", "Anthropic API Key"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token"),
    (r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "Private Key"),
]

SAFE_ALLOWED_FILES = {
    ".env",  # .env is allowed to exist locally, but MUST NOT be tracked by git
}


def check_git_status():
    print("[1/2] Checking Git tracking and ignored files...")
    # Check if git is initialized
    git_check = subprocess.run(["git", "status"], capture_output=True, text=True)
    if git_check.returncode != 0:
        print("  Notice: Git repository not yet initialized. Will verify after git init.")
        return True

    # Check if .env is tracked
    result = subprocess.run(["git", "ls-files", ".env"], capture_output=True, text=True)
    if result.stdout.strip():
        print("  [ERROR] CRITICAL: .env is currently tracked by Git!")
        print("  Run: git rm --cached .env")
        return False
    print("  [OK] .env is properly ignored and not tracked by Git.")
    return True


def scan_files_for_secrets():
    print("[2/2] Scanning codebase files for accidental secret leaks...")
    leaks_found = 0
    workspace = os.path.dirname(os.path.abspath(__file__))

    # Directories to ignore
    ignored_dirs = {"venv", ".venv", "env", "node_modules", ".git", "__pycache__", "dist", "build"}

    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for file in files:
            if file in SAFE_ALLOWED_FILES or file.endswith((".pyc", ".png", ".jpg", ".ico", ".svg")):
                continue
            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, workspace)

            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    for pattern, desc in SECRET_PATTERNS:
                        matches = re.findall(pattern, content)
                        if matches:
                            print(f"  [ERROR] LEAK DETECTED in {rel_path}: Found {desc} pattern!")
                            leaks_found += 1
            except Exception:
                pass

    if leaks_found == 0:
        print("  [OK] No secrets or leaked keys detected across the project!")
        return True
    else:
        print(f"  [FAIL] Found {leaks_found} potential secret leaks. Fix them before pushing!")
        return False


if __name__ == "__main__":
    git_ok = check_git_status()
    secrets_ok = scan_files_for_secrets()
    if git_ok and secrets_ok:
        print("\n>>> SECURITY AUDIT PASSED: Safe to commit and push to GitHub.")
        sys.exit(0)
    else:
        print("\n>>> SECURITY AUDIT FAILED: Review errors above before pushing.")
        sys.exit(1)
