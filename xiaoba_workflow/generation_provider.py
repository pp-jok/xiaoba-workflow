import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from . import config as local_config


CONTRACT_VERSION = "1.0"


class GenerationProviderError(Exception):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def provider_config(root: Path) -> Dict[str, object]:
    settings = local_config.provider_settings(root, "generation")
    provider = os.environ.get("XIAOBA_GENERATION_PROVIDER") or settings.get("mode") or "mock"
    if provider not in ("mock", "codex", "external"):
        raise GenerationProviderError("unsupported generation provider: " + str(provider))
    command = settings.get("command")
    if os.environ.get("XIAOBA_GENERATION_COMMAND"):
        try:
            command = json.loads(os.environ["XIAOBA_GENERATION_COMMAND"])
        except json.JSONDecodeError as error:
            raise GenerationProviderError("XIAOBA_GENERATION_COMMAND must be a JSON array: " + str(error))
    if command is not None and (not isinstance(command, list) or not all(isinstance(item, str) for item in command)):
        raise GenerationProviderError("generation command must be a list of strings")
    timeout = os.environ.get("XIAOBA_GENERATION_TIMEOUT") or settings.get("timeout_seconds") or 300
    try:
        timeout_seconds = float(timeout)
    except (TypeError, ValueError):
        raise GenerationProviderError("generation timeout must be numeric")
    return {"provider": provider, "command": command, "timeout_seconds": timeout_seconds}


def doctor(root: Path) -> List[str]:
    config = provider_config(root)
    provider = str(config["provider"])
    messages = ["provider: " + provider, "contract_version: " + CONTRACT_VERSION]
    if provider == "mock":
        messages.append("operations: generate_topics, generate_content")
        messages.append("ready: true")
        return messages
    if provider == "codex":
        messages.append("ready: manual")
        messages.append("note: Codex manual mode writes requests and waits for user/Codex completion.")
        return messages
    if not config.get("command"):
        raise GenerationProviderError("XIAOBA_GENERATION_COMMAND is required for external generation provider")
    messages.append("command: configured")
    messages.append("ready: contract")
    return messages


def external_generate_topics(root: Path, task: Dict[str, str], context: Dict[str, object], output_dir: Path, count: int = 5) -> Dict[str, object]:
    request = {
        "contract_version": CONTRACT_VERSION,
        "operation": "generate_topics",
        "task_id": task["task_id"],
        "generation_context": context,
        "brief": context.get("brief") or {},
        "count": count,
        "output_dir": str(output_dir.resolve()),
    }
    return run_external(root, request, "topic-candidates.yaml")


def external_generate_content(
    root: Path,
    task: Dict[str, str],
    generation_context_ref: Path,
    selected_topic_ref: Path,
    output_dir: Path,
    revision_number: int,
    previous_content_ref: Optional[Path],
    feedback_ref: Optional[Path],
) -> Dict[str, object]:
    request = {
        "contract_version": CONTRACT_VERSION,
        "operation": "generate_content",
        "task_id": task["task_id"],
        "generation_context_ref": str(generation_context_ref.resolve()),
        "selected_topic_ref": str(selected_topic_ref.resolve()),
        "revision_number": revision_number,
        "previous_content_ref": str(previous_content_ref.resolve()) if previous_content_ref else None,
        "feedback_ref": str(feedback_ref.resolve()) if feedback_ref else None,
        "output_dir": str(output_dir.resolve()),
    }
    return run_external(root, request, "content-package.yaml")


def run_external(root: Path, request: Dict[str, object], expected_file: str) -> Dict[str, object]:
    config = provider_config(root)
    if config["provider"] != "external":
        raise GenerationProviderError("external generation provider is not configured")
    command = list(config.get("command") or [])
    if not command:
        raise GenerationProviderError("generation command is required")
    output_dir = Path(str(request["output_dir"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    request_path = output_dir / "request.json"
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    completed = subprocess.run(
        command + ["--input", str(request_path), "--output", str(output_dir)],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
        timeout=float(config["timeout_seconds"]),
        cwd=str(root),
    )
    if completed.returncode != 0:
        raise GenerationProviderError("external generation provider failed: " + redact(completed.stderr.strip() or completed.stdout.strip()))
    manifest_path = output_dir / "runner-manifest.json"
    payload_path = output_dir / expected_file
    if not manifest_path.is_file() or not payload_path.is_file():
        raise GenerationProviderError("external generation provider output is incomplete")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("contract_version") != CONTRACT_VERSION or manifest.get("operation") != request["operation"]:
        raise GenerationProviderError("external generation manifest mismatch")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise GenerationProviderError("external generation output must be an object")
    payload.setdefault("runner_manifest", "runner-manifest.json")
    return payload


def redact(text: str) -> str:
    result = text
    for key, value in os.environ.items():
        lowered = key.lower()
        if value and ("secret" in lowered or "token" in lowered or "password" in lowered or "key" in lowered):
            result = result.replace(value, "<redacted>")
    return result
