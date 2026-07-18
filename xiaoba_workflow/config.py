from pathlib import Path
from typing import Dict


def load_local_config(root: Path) -> Dict[str, object]:
    path = root / "xiaoba.local.yaml"
    if not path.is_file():
        return {}
    return parse_simple_yaml(path.read_text(encoding="utf-8"))


def parse_simple_yaml(text: str) -> Dict[str, object]:
    root: Dict[str, object] = {}
    stack = [(0, root)]
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        while stack and indent <= stack[-1][0] and stack[-1][1] is not root:
            stack.pop()
        parent = stack[-1][1]
        if value == "":
            child: Dict[str, object] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = parse_scalar(value)
    return root


def parse_scalar(value: str):
    cleaned = value.strip().strip('"').strip("'")
    if cleaned == "true":
        return True
    if cleaned == "false":
        return False
    if cleaned == "null":
        return None
    try:
        return int(cleaned)
    except ValueError:
        return cleaned


def provider_settings(root: Path, provider_name: str) -> Dict[str, object]:
    providers = (load_local_config(root).get("providers") or {})
    if not isinstance(providers, dict):
        return {}
    settings = providers.get(provider_name) or {}
    return settings if isinstance(settings, dict) else {}
