#!/opt/hermes/.venv/bin/python
from __future__ import annotations

import sys
from pathlib import Path

import yaml


RENDER_SKILL_DIRS = (
    "/opt/render-tools/skills-local",
    "/opt/render-tools/skills-upstream",
)

RENDER_MCP_URL = "https://mcp.render.com/mcp"
RENDER_MCP_AUTH = "Bearer ${RENDER_MCP_API_KEY}"

SELWA_LAW_MCP_URL = "http://selwa-law-mcp:8000/mcp"

OPENAI_API_URL = "https://api.openai.com/v1"


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[render-tools] cannot read {path}: {exc}", file=sys.stderr)
        return {}

    if not raw.strip():
        return {}

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        print(
            f"[render-tools] {path} is not valid YAML ({exc}); refusing to patch",
            file=sys.stderr,
        )
        return {}

    return data if isinstance(data, dict) else {}


def ensure_render_mcp(config: dict) -> bool:
    mcp_servers = config.setdefault("mcp_servers", {})

    if not isinstance(mcp_servers, dict):
        print("[render-tools] mcp_servers is not a mapping", file=sys.stderr)
        return False

    if "render" in mcp_servers:
        return False

    mcp_servers["render"] = {
        "url": RENDER_MCP_URL,
        "headers": {
            "Authorization": RENDER_MCP_AUTH,
        },
    }

    return True


def ensure_selwa_law_mcp(config: dict) -> bool:
    mcp_servers = config.setdefault("mcp_servers", {})

    if not isinstance(mcp_servers, dict):
        print("[render-tools] mcp_servers is not a mapping", file=sys.stderr)
        return False

    desired = {
        "url": SELWA_LAW_MCP_URL,
        "headers": {
            "mcp-protocol-version": "2025-06-18",
        },
        "tools": {
            "include": [
                "system_status",
                "list_matters",
            ],
        },
    }

    if mcp_servers.get("selwa_law") == desired:
        return False

    mcp_servers["selwa_law"] = desired
    return True


def ensure_openai_direct_provider(config: dict) -> bool:
    providers = config.setdefault("providers", {})

    if not isinstance(providers, dict):
        print("[render-tools] providers is not a mapping", file=sys.stderr)
        return False

    desired = {
        "api": OPENAI_API_URL,
        "key_env": "OPENAI_API_KEY",
        "transport": "codex_responses",
        "default_model": "gpt-5.4",
        "models": [
            "gpt-5.4",
        ],
    }

    if providers.get("openai-direct") == desired:
        return False

    providers["openai-direct"] = desired
    return True


def ensure_main_model(config: dict) -> bool:
    model = config.get("model")

    if not isinstance(model, dict):
        model = {}
        config["model"] = model

    changed = False

    if model.get("provider") != "custom:openai-direct":
        model["provider"] = "custom:openai-direct"
        changed = True

    if model.get("default") != "gpt-5.4":
        model["default"] = "gpt-5.4"
        changed = True

    # Remove stale settings from our earlier attempts.
    # The named provider above now owns the endpoint and transport.
    for stale_key in ("base_url", "api_mode"):
        if stale_key in model:
            model.pop(stale_key)
            changed = True

    return changed


def ensure_external_skill_dirs(config: dict) -> list[str]:
    skills = config.setdefault("skills", {})

    if not isinstance(skills, dict):
        print("[render-tools] skills is not a mapping", file=sys.stderr)
        return []

    existing = skills.get("external_dirs")

    if existing is None:
        skills["external_dirs"] = list(RENDER_SKILL_DIRS)
        return list(RENDER_SKILL_DIRS)

    if not isinstance(existing, list):
        print(
            "[render-tools] skills.external_dirs is not a list",
            file=sys.stderr,
        )
        return []

    added = []

    for path in RENDER_SKILL_DIRS:
        if path not in existing:
            existing.append(path)
            added.append(path)

    return added


def save_config(path: Path, config: dict) -> None:
    text = yaml.safe_dump(
        config,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )

    tmp = path.with_suffix(path.suffix + ".render-tools.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "usage: patch-config.py <path/to/config.yaml>",
            file=sys.stderr,
        )
        return 2

    path = Path(sys.argv[1])
    path.parent.mkdir(parents=True, exist_ok=True)

    config = load_config(path)

    changed_render = ensure_render_mcp(config)
    changed_selwa = ensure_selwa_law_mcp(config)
    changed_provider = ensure_openai_direct_provider(config)
    changed_model = ensure_main_model(config)
    added_dirs = ensure_external_skill_dirs(config)

    if (
        changed_render
        or changed_selwa
        or changed_provider
        or changed_model
        or added_dirs
    ):
        save_config(path, config)

        parts = []

        if changed_render:
            parts.append("mcp_servers.render")

        if changed_selwa:
            parts.append("mcp_servers.selwa_law")

        if changed_provider:
            parts.append("providers.openai-direct")

        if changed_model:
            parts.append("model = custom:openai-direct/gpt-5.4")

        for dir_path in added_dirs:
            parts.append(f"skills.external_dirs += {dir_path}")

        print(
            f"[render-tools] patched {path}: {', '.join(parts)}"
        )
    else:
        print(
            f"[render-tools] {path} already has required configuration; "
            "nothing to do"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
