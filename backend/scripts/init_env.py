"""Create or extend .env for local Docker Compose use.

Adds missing keys only (existing values, e.g. an LLM API key, are never
changed). Generated secrets are random and for local development only.

Usage: python scripts/init_env.py [path]
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

DEFAULTS = {
    "APP_ENV": lambda: "development",
    "POSTGRES_PASSWORD": lambda: secrets.token_urlsafe(24),
    "MINIO_ROOT_USER": lambda: "docintel",
    "MINIO_ROOT_PASSWORD": lambda: secrets.token_urlsafe(24),
    "JWT_SECRET": lambda: secrets.token_urlsafe(48),
    "METRICS_TOKEN": lambda: secrets.token_urlsafe(24),
    "REGISTRATION_MODE": lambda: "open",
}

# With an LLM key: Mistral extraction + embeddings. Without: fully local (offline) mode.
HOSTED_AI = {
    "EXTRACTION_PROVIDER": "hosted",
    "EMBEDDING_PROVIDER": "hosted",
    "EMBEDDING_MODEL": "mistral-embed",
    "EMBEDDING_BATCH_SIZE": "64",
    "AI_EXTERNAL_TRANSMISSION_ENABLED": "true",
}
LOCAL_AI = {"EXTRACTION_PROVIDER": "local", "EMBEDDING_PROVIDER": "local", "AI_EXTERNAL_TRANSMISSION_ENABLED": "false"}


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else ".env")
    lines = path.read_text().splitlines() if path.exists() else []
    values: dict[str, str] = {}
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            values[k.strip()] = v.split("#", 1)[0].strip()
    has_llm_key = bool(values.get("LLM_API_KEY") or values.get("MISTRAL_API_KEY"))
    wanted = {k: f() for k, f in DEFAULTS.items()} | (HOSTED_AI if has_llm_key else LOCAL_AI)
    # Fill keys that are missing or empty (e.g. after `cp .env.example .env`); never change set values.
    to_set = {k: v for k, v in wanted.items() if not values.get(k)}
    if not to_set:
        print(f"{path}: nothing to add")
        return
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in to_set:
            out.append(f"{key}={to_set.pop(key)}")
        else:
            out.append(line)
    if to_set:
        out.append("# --- added by scripts/init_env.py (local development values) ---")
        out.extend(f"{k}={v}" for k, v in to_set.items())
    path.write_text("\n".join(out) + "\n")
    path.chmod(0o600)
    print(f"{path}: set {', '.join(sorted(set(wanted) - {k for k in wanted if values.get(k)}))}")


if __name__ == "__main__":
    main()
