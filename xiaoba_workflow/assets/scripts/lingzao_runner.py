#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


CONTRACT_VERSION = "1.0"
OPERATIONS = (
    "collect_note",
    "collect_profile",
    "collect_posted_notes",
    "collect_comments",
    "collect_transcript",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Xiaoba Lingzao runner contract bridge.")
    parser.add_argument("--capabilities", action="store_true")
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--output")
    args = parser.parse_args()

    if args.capabilities or args.doctor:
        print(json.dumps(capabilities(), ensure_ascii=False, indent=2))
        return 0

    if not args.input or not args.output:
        print("--input and --output are required", file=sys.stderr)
        return 2

    try:
        request = read_json(Path(args.input))
        validate_request(request, Path(args.output))
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        started_at = now_iso()
        payload = call_lingzao(request)
        result = adapt_payload(request, payload)
        completed_at = now_iso()
        manifest = {
            "contract_version": CONTRACT_VERSION,
            "runner": "xiaoba-lingzao-runner",
            "operation": request["operation"],
            "started_at": started_at,
            "completed_at": completed_at,
            "status": "succeeded",
            "warnings": result.get("warnings") or [],
            "source_files": [],
        }
        write_json(output_dir / "result.json", result)
        write_json(output_dir / "runner-manifest.json", manifest)
        return 0
    except RunnerError as error:
        print(str(error), file=sys.stderr)
        return error.exit_code


class RunnerError(Exception):
    def __init__(self, message: str, exit_code: int = 1):
        self.exit_code = exit_code
        super().__init__(message)


def capabilities() -> Dict[str, Any]:
    client = resolve_client_path()
    config_path = Path.home() / ".lingzao" / "config.json"
    return {
        "contract_version": CONTRACT_VERSION,
        "runner": "xiaoba-lingzao-runner",
        "operations": list(OPERATIONS),
        "optional_cost_operations": ["collect_comments", "collect_transcript"],
        "unsupported_outputs": ["video_file"],
        "requires_auth": True,
        "required_env": ["LINGZAO_CLIENT_PATH or LINGZAO_SKILL_ROOT"],
        "login_state": "configured" if config_path.is_file() or os.environ.get("LINGZAO_API_KEY") else "missing_api_key",
        "dependencies": {
            "python": True,
            "lingzao_client": bool(client and client.is_file()),
        },
    }


def resolve_client_path() -> Path:
    explicit = os.environ.get("LINGZAO_CLIENT_PATH")
    if explicit:
        return Path(explicit).expanduser()
    skill_root = os.environ.get("LINGZAO_SKILL_ROOT")
    if skill_root:
        return Path(skill_root).expanduser() / "scripts" / "lingzao_client.py"
    return Path("")


def validate_request(request: Dict[str, Any], output_arg: Path) -> None:
    if request.get("contract_version") != CONTRACT_VERSION:
        raise RunnerError("unsupported contract_version", 2)
    if request.get("operation") not in OPERATIONS:
        raise RunnerError("unsupported operation", 2)
    source = request.get("source")
    if not isinstance(source, str) or not (source.startswith("http://") or source.startswith("https://")):
        raise RunnerError("source must be an absolute http(s) URL", 2)
    output_dir = request.get("output_dir")
    if not isinstance(output_dir, str) or not Path(output_dir).is_absolute():
        raise RunnerError("output_dir must be absolute", 2)
    if Path(output_dir).resolve() != output_arg.resolve():
        raise RunnerError("--output must match request.output_dir", 2)


def call_lingzao(request: Dict[str, Any]) -> Dict[str, Any]:
    client = resolve_client_path()
    if not client.is_file():
        raise RunnerError("Lingzao client not found. Set LINGZAO_CLIENT_PATH or LINGZAO_SKILL_ROOT.", 2)
    operation = request["operation"]
    if operation == "collect_note":
        command = ["get-note-detail", "--platform", "xhs", "--url", request["source"], "--format", "json"]
        note_type = infer_xhs_note_type(request)
        if note_type:
            command.extend(["--xhs-note-type", note_type])
    elif operation == "collect_profile":
        command = ["get-user-info", "--platform", "xhs", "--url", request["source"], "--format", "json"]
    elif operation == "collect_posted_notes":
        command = ["get-user-posted-notes", "--platform", "xhs", "--url", request["source"], "--format", "json"]
    elif operation == "collect_comments":
        command = ["get-note-comments", "--platform", "xhs", "--url", request["source"], "--format", "json"]
    elif operation == "collect_transcript":
        command = ["extract-video-copy", "--platform", "xhs", "--url", request["source"], "--format", "json"]
    else:
        raise RunnerError("unsupported operation", 2)

    result = subprocess.run(
        [sys.executable, str(client), *command],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    if result.returncode != 0:
        raise RunnerError(redact(result.stderr.strip()) or "Lingzao client failed", result.returncode)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RunnerError("Lingzao client returned invalid JSON: %s" % error)
    if not isinstance(payload, dict):
        raise RunnerError("Lingzao client returned non-object JSON")
    return payload


def infer_xhs_note_type(request: Dict[str, Any]) -> str:
    options = request.get("options")
    if isinstance(options, dict):
        option_value = normalize_xhs_note_type(options.get("xhs_note_type") or options.get("note_type"))
        if option_value:
            return option_value
    parsed = urllib.parse.urlparse(str(request.get("source") or ""))
    query = urllib.parse.parse_qs(parsed.query)
    for key in ("type", "xhs_note_type", "note_type"):
        values = query.get(key) or []
        for value in values:
            note_type = normalize_xhs_note_type(value)
            if note_type:
                return note_type
    return ""


def normalize_xhs_note_type(value: Any) -> str:
    lowered = str(value or "").strip().lower()
    if lowered in ("video", "image"):
        return lowered
    return ""


def adapt_payload(request: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    operation = request["operation"]
    source = request["source"]
    if operation == "collect_note":
        note = first_dict(data, "note", "item", "detail") or data
        return {
            "operation": operation,
            "source": source,
            "note": {
                "id": value(note, "id", "note_id"),
                "url": value(note, "url", "note_url") or source,
                "title": value(note, "title"),
                "body": value(note, "body", "content", "desc", "description"),
                "author": first_dict(note, "author", "user") or {},
                "published_at": value(note, "published_at", "publish_time", "created_at"),
                "metrics": first_dict(note, "metrics", "stats") or {},
                "images": list_value(note, "images", "image_list"),
                "comments": first_dict(note, "comments") or {"status": "missing", "items": []},
                "transcript": first_dict(note, "transcript") or {"status": "missing", "text": None},
            },
            "warnings": warnings(payload),
        }
    if operation == "collect_profile":
        profile = first_dict(data, "profile", "user", "account") or data
        return {
            "operation": operation,
            "source": source,
            "profile": {
                "id": value(profile, "id", "user_id", "profile_id"),
                "url": value(profile, "url", "profile_url") or source,
                "name": value(profile, "name", "nickname"),
                "bio": value(profile, "bio", "description", "desc"),
                "metrics": first_dict(profile, "metrics", "stats") or {},
            },
            "warnings": warnings(payload),
        }
    if operation == "collect_posted_notes":
        notes = list_value(data, "notes", "items", "list")
        return {
            "operation": operation,
            "source": source,
            "notes": [
                {
                    "id": value(item, "id", "note_id"),
                    "url": value(item, "url", "note_url"),
                    "title": value(item, "title"),
                    "published_at": value(item, "published_at", "publish_time", "created_at"),
                    "metrics": first_dict(item, "metrics", "stats") or {},
                }
                for item in notes
                if isinstance(item, dict)
            ],
            "warnings": warnings(payload),
        }
    if operation == "collect_comments":
        comments = list_value(data, "comments", "items", "list")
        return {
            "operation": operation,
            "source": source,
            "comments": {"status": "available", "items": comments},
            "warnings": warnings(payload),
        }
    transcript = first_dict(data, "transcript", "copy", "video_copy")
    text = value(transcript, "text", "content") if transcript else value(data, "text", "content", "transcript")
    return {
        "operation": operation,
        "source": source,
        "transcript": {
            "status": "available" if text else "missing",
            "text": text,
        },
        "video_file": {"status": "unsupported"},
        "warnings": warnings(payload),
    }


def warnings(payload: Dict[str, Any]) -> List[Any]:
    value_ = payload.get("warnings")
    return value_ if isinstance(value_, list) else []


def first_dict(payload: Dict[str, Any], *keys: str) -> Dict[str, Any]:
    for key in keys:
        value_ = payload.get(key)
        if isinstance(value_, dict):
            return value_
    return {}


def value(payload: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def list_value(payload: Dict[str, Any], *keys: str) -> List[Any]:
    for key in keys:
        value_ = payload.get(key)
        if isinstance(value_, list):
            return value_
    return []


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RunnerError("request must be a JSON object", 2)
    return payload


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def redact(text: str) -> str:
    result = text
    for key, value_ in os.environ.items():
        lowered = key.lower()
        if value_ and ("secret" in lowered or "token" in lowered or "password" in lowered or "key" in lowered):
            result = result.replace(value_, "<redacted>")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
