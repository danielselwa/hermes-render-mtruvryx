#!/opt/hermes/.venv/bin/python
"""Idempotent patcher for Hermes' config.yaml on Render.

Adds:
  1. Render's MCP server.
  2. Selwa Law's private MCP server.
  3. Render's bundled external skill directories.

The patcher is INSERT-only. Existing user configuration is preserved.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


# Render skill directories, in precedence order.
RENDER_SKILL_DIRS = (
    "/opt/render-tools/skills-local",
    "/opt/render-tools/skills-upstream",
)

# Render MCP.
RENDER_MCP_URL = "https://mcp.render.com/mcp"
RENDER_MCP_AUTH = "Bearer ${RENDER_MCP_API_KEY}"

# Selwa Law MCP.
# Both services are in Render's Virginia region, so this uses
# Render's private network rather than the public internet.
SELWA_LAW_MCP_URL = "http://selwa-law-mcp:8000/mcp"


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
        sys.exit(0)

    return data if isinstance(data, dict) else {}


def _render_entry() -> dict:
    return {
        "url": RENDER_MCP_URL,
        "headers": {
            "Authorization": RENDER_MCP_AUTH,
        },
    }


def _selwa_law_entry() -> dict:
    return {
        "url": SELWA_LAW_MCP_URL,
        "tools": {
            "include": [
                "system_status",
                "list_matters",
            ],
        },
    }


def ensure_render_mcp(config: dict) -> bool:
    """Insert mcp_servers.render if missing."""
    mcp_servers = config.get("mcp_servers")

    if mcp_servers is None:
        config["mcp_servers"] = {
            "render": _render_entry(),
        }
        return True

    if not isinstance(mcp_servers, dict):
        print(
            "[render-tools] mcp_servers is not a mapping; skipping Render MCP",
            file=sys.stderr,
        )
        return False

    if "render" in mcp_servers:
        return False

    mcp_servers["render"] = _render_entry()
    return True


def ensure_selwa_law_mcp(config: dict) -> bool:
    """Insert mcp_servers.selwa_law if missing."""
    mcp_servers = config.get("mcp_servers")

    if mcp_servers is None:
        config["mcp_servers"] = {
            "selwa_law": _selwa_law_entry(),
        }
        return True

    if not isinstance(mcp_servers, dict):
        print(
            "[render-tools] mcp_servers is not a mapping; skipping Selwa Law MCP",
            file=sys.stderr,
        )
        return False

    if "selwa_law" in mcp_servers:
        return False

    mcp_servers["selwa_law"] = _selwa_law_entry()
    return True


def ensure_external_skill_dirs(config: dict) -> list[str]:
    """Append Render skill directories if missing."""
    skills = config.setdefault("skills", {})

    if not isinstance(skills, dict):
        print(
            "[render-tools] skills is not a mapping; skipping external_dirs",
            file=sys.stderr,
        )
        return []

    existing = skills.get("external_dirs")

    if existing is None:
        skills["external_dirs"] = list(RENDER_SKILL_DIRS)
        return list(RENDER_SKILL_DIRS)

    if not isinstance(existing, list):
        print(
            "[render-tools] skills.external_dirs is not a list; skipping",
            file=sys.stderr,
        )
        return []

    added: list[str] = []

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

    changed_render_mcp = ensure_render_mcp(config)
    changed_selwa_mcp = ensure_selwa_law_mcp(config)
    added_dirs = ensure_external_skill_dirs(config)

    if changed_render_mcp or changed_selwa_mcp or added_dirs:
        save_config(path, config)

        parts = []

        if changed_render_mcp:
            parts.append("mcp_servers.render")

        if changed_selwa_mcp:
            parts.append("mcp_servers.selwa_law")

        for dir_path in added_dirs:
            parts.append(f"skills.external_dirs += {dir_path}")

        print(
            f"[render-tools] patched {path}: {', '.join(parts)}"
        )
    else:
        print(
            f"[render-tools] {path} already contains Render MCP, "
            "Selwa Law MCP, and skill dirs; nothing to do"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
