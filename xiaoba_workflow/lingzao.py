import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit

from . import config as local_config
from . import locks


LOG_LIMIT = 64 * 1024
CONTRACT_VERSION = "1.0"
SUPPORTED_OPERATIONS = ("collect_note", "collect_profile", "collect_posted_notes")
OPTIONAL_OPERATIONS = ("collect_comments", "collect_transcript")
ALL_OPERATIONS = SUPPORTED_OPERATIONS + OPTIONAL_OPERATIONS


class LingzaoError(Exception):
    def __init__(self, kind: str, message: str):
        self.kind = kind
        super().__init__("%s: %s" % (kind, message))


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_json_atomic(path: Path, payload: Dict[str, object]) -> None:
    with locks.file_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = path.with_name("." + path.name + ".tmp")
        temp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp_file.replace(path)


def read_json(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def provider_config(root: Path) -> Dict[str, object]:
    config = read_workflow_lingzao_config(root / "workflow.yaml")
    local = local_config.provider_settings(root, "lingzao")
    provider = os.environ.get("XIAOBA_LINGZAO_PROVIDER") or str(local.get("mode") or config.get("provider") or "mock")
    command = config.get("command")
    if local.get("command"):
        command = local.get("command")
    if os.environ.get("XIAOBA_LINGZAO_COMMAND"):
        try:
            command = json.loads(os.environ["XIAOBA_LINGZAO_COMMAND"])
        except json.JSONDecodeError as error:
            raise LingzaoError("configuration_error", "XIAOBA_LINGZAO_COMMAND must be a JSON array: " + str(error))
    timeout = os.environ.get("XIAOBA_LINGZAO_TIMEOUT") or local.get("timeout_seconds") or config.get("timeout_seconds") or 300
    try:
        timeout_seconds = float(timeout)
    except (TypeError, ValueError):
        raise LingzaoError("configuration_error", "Lingzao timeout must be numeric")
    if provider not in ("mock", "real"):
        raise LingzaoError("configuration_error", "unsupported Lingzao provider: " + str(provider))
    if command is not None and (not isinstance(command, list) or not all(isinstance(item, str) for item in command)):
        raise LingzaoError("configuration_error", "Lingzao command must be a list of strings")
    return {
        "provider": provider,
        "command": command,
        "timeout_seconds": timeout_seconds,
        "workdir": local.get("workdir") or config.get("workdir"),
    }


def read_workflow_lingzao_config(path: Path) -> Dict[str, object]:
    if not path.is_file():
        return {"provider": "mock"}
    lines = path.read_text(encoding="utf-8").splitlines()
    config: Dict[str, object] = {}
    in_lingzao = False
    in_command = False
    command: List[str] = []
    for raw in lines:
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 2 and line == "lingzao:":
            in_lingzao = True
            in_command = False
            continue
        if in_lingzao and indent <= 2 and line != "lingzao:":
            break
        if not in_lingzao:
            continue
        if indent == 4 and line.startswith("provider:"):
            config["provider"] = line.split(":", 1)[1].strip().strip('"') or "mock"
        elif indent == 4 and line.startswith("timeout_seconds:"):
            config["timeout_seconds"] = line.split(":", 1)[1].strip().strip('"')
        elif indent == 4 and line.startswith("workdir:"):
            config["workdir"] = line.split(":", 1)[1].strip().strip('"')
        elif indent == 4 and line == "command:":
            in_command = True
        elif in_command and indent == 6 and line.startswith("- "):
            command.append(line[2:].strip().strip('"'))
    if command:
        config["command"] = command
    config.setdefault("provider", "mock")
    return config


def doctor(root: Path) -> List[str]:
    config = provider_config(root)
    messages = ["provider: " + str(config["provider"])]
    prompt = root / "prompts" / "lingzao-evidence-only.md"
    if not prompt.is_file():
        raise LingzaoError("configuration_error", "missing prompt: prompts/lingzao-evidence-only.md")
    messages.append("prompt: ok")
    if config["provider"] == "mock":
        return messages
    command = config.get("command")
    if not command:
        raise LingzaoError("configuration_error", "real command is required")
    executable = shutil.which(str(command[0])) if command else None
    if executable is None and not Path(str(command[0])).exists():
        raise LingzaoError("configuration_error", "real command executable not found")
    workdir = config.get("workdir")
    if workdir and not Path(str(workdir)).is_dir():
        raise LingzaoError("configuration_error", "Lingzao workdir does not exist")
    capabilities = read_capabilities(command, config, root)
    if str(capabilities.get("contract_version")) != CONTRACT_VERSION:
        raise LingzaoError("configuration_error", "unsupported Lingzao contract_version: " + str(capabilities.get("contract_version")))
    operations = capabilities.get("operations")
    if not isinstance(operations, list):
        raise LingzaoError("configuration_error", "Lingzao capabilities operations must be a list")
    for operation in SUPPORTED_OPERATIONS:
        if operation not in operations:
            raise LingzaoError("configuration_error", "unsupported Lingzao operation: " + operation)
    dependencies = capabilities.get("dependencies")
    if isinstance(dependencies, dict):
        for name, ok in dependencies.items():
            if ok is False:
                raise LingzaoError("configuration_error", "missing Lingzao dependency: " + str(name))
    login_state = str(capabilities.get("login_state") or "")
    if capabilities.get("requires_auth") is True and login_state.startswith("missing"):
        raise LingzaoError("configuration_error", "Lingzao auth not ready: " + login_state)
    messages.append("command: configured")
    messages.append("contract_version: " + CONTRACT_VERSION)
    messages.append("operations: " + ", ".join(str(item) for item in operations))
    optional = [operation for operation in OPTIONAL_OPERATIONS if operation in operations]
    if optional:
        messages.append("optional_operations: " + ", ".join(optional))
    if "unsupported_outputs" in capabilities:
        messages.append("unsupported_outputs: " + ", ".join(str(item) for item in capabilities.get("unsupported_outputs") or []))
    if "requires_auth" in capabilities:
        messages.append("requires_auth: " + str(capabilities.get("requires_auth")))
    if capabilities.get("login_state"):
        messages.append("login_state: " + str(capabilities.get("login_state")))
    messages.append("timeout_seconds: %s" % config["timeout_seconds"])
    return messages


def read_capabilities(command: List[str], config: Dict[str, object], root: Path) -> Dict[str, object]:
    try:
        result = subprocess.run(
            list(command) + ["--capabilities"],
            check=False,
            capture_output=True,
            text=True,
            timeout=float(config["timeout_seconds"]),
            cwd=str(config.get("workdir") or root),
            shell=False,
        )
    except subprocess.TimeoutExpired:
        raise LingzaoError("timeout", "Lingzao capabilities command timed out")
    if result.returncode != 0:
        raise LingzaoError("configuration_error", "Lingzao capabilities command failed: " + redact(result.stderr.strip()))
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise LingzaoError("configuration_error", "Lingzao capabilities output is not valid JSON: " + str(error))
    if not isinstance(payload, dict):
        raise LingzaoError("configuration_error", "Lingzao capabilities output must be a JSON object")
    return payload


def collect_note(root: Path, task_dir: Path, task: Dict[str, str], state: Dict[str, object], source_url: str, sample_id: Optional[str] = None, raw_dir: Optional[Path] = None) -> None:
    config = provider_config(root)
    target_dir = raw_dir or (task_dir / "raw" / "lingzao")
    if config["provider"] == "mock":
        write_mock_note(target_dir, task, state, source_url, sample_id)
    else:
        run_real(root, task_dir, target_dir, task, "collect_note", source_url, config, sample_id)


def collect_profile(root: Path, task_dir: Path, task: Dict[str, str], state: Dict[str, object], source_url: str) -> None:
    config = provider_config(root)
    target_dir = task_dir / "raw" / "lingzao"
    if config["provider"] == "mock":
        raise LingzaoError("configuration_error", "mock profile collection should use batch mock builder")
    run_real_profile_bundle(root, task_dir, target_dir, task, state, source_url, config)


def write_mock_note(target_dir: Path, task: Dict[str, str], state: Dict[str, object], source_url: str, sample_id: Optional[str]) -> None:
    if source_url.startswith("mock-fail://"):
        raise LingzaoError("execution_error", "Mock Lingzao failure requested")
    target_dir.mkdir(parents=True, exist_ok=True)
    note_path = target_dir / "note-detail.json"
    invocation_path = target_dir / "invocation.json"
    if note_path.exists() and invocation_path.exists():
        return
    if note_path.exists() or invocation_path.exists():
        raise LingzaoError("incomplete_output", "Lingzao raw output is incomplete")
    captured_at = now_iso()
    note_detail = {
        "sample_id": sample_id,
        "source": {"source_type": "xhs_note", "original_url": source_url, "canonical_url": source_url},
        "author": {"name": "Mock Author", "id": "mock-author-001"},
        "content": {
            "title": "Mock note title" if sample_id is None else "Mock batch note title",
            "body": "Mock note body for downstream evidence normalization.",
            "tags": ["mock", "learning"],
            "images": [{"url": "https://example.com/mock-image-1.jpg", "alt": "mock image"}],
        },
        "published_at": "2026-07-15T00:00:00+08:00",
        "captured_at": captured_at,
        "metrics": {"likes": 128, "saves": 64, "comments": None, "shares": None},
        "comments": {"status": "missing", "items": []},
        "transcript": {"status": "missing", "text": ""},
    }
    if sample_id is not None:
        note_detail["sample_id"] = sample_id
    invocation = manifest(
        provider="mock",
        task=task,
        state=state,
        operation="collect_note",
        source=source_url,
        sample_id=sample_id,
        started_at=captured_at,
        completed_at=captured_at,
        exit_code=0,
        raw_files=[relative_raw_file(target_dir, "note-detail.json"), relative_raw_file(target_dir, "invocation.json")],
        command=None,
        stdout_file=None,
        stderr_file=None,
        warnings=[],
    )
    invocation["adapter"] = "mock_lingzao"
    invocation["mode"] = "mock"
    invocation["task_type"] = task["task_type"]
    invocation["stage"] = state.get("current_stage")
    invocation["source_url"] = source_url
    invocation["executed_at"] = captured_at
    invocation["outputs"] = invocation["raw_files"]
    write_json_atomic(note_path, note_detail)
    write_json_atomic(invocation_path, invocation)


def relative_raw_file(target_dir: Path, name: str) -> str:
    parts = list(target_dir.parts)
    if "raw" in parts:
        raw_index = parts.index("raw")
        return str(Path(*parts[raw_index:]) / name)
    return name


def run_real(root: Path, task_dir: Path, target_dir: Path, task: Dict[str, str], operation: str, source_url: str, config: Dict[str, object], sample_id: Optional[str]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    expected = expected_files(operation)
    existing = [target_dir / name for name in expected + ["invocation.json"] if (target_dir / name).exists()]
    if existing:
        raise LingzaoError("incomplete_output", "refusing to overwrite existing Lingzao raw output")
    run_id = uuid.uuid4().hex[:12]
    temp_dir = task_dir / ".tmp" / ("lingzao-" + run_id)
    external_tmp = temp_dir / "external"
    external_tmp.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    result, args = run_runner_contract(root, target_dir, external_tmp, task, operation, source_url, config, sample_id)
    try:
        validate_external_paths(external_tmp)
        external_dir = target_dir / "external"
        if external_dir.exists():
            raise LingzaoError("incomplete_output", "external raw directory already exists")
        shutil.copytree(external_tmp, external_dir)
        contract = read_runner_contract(external_tmp, operation, source_url)
        adapted = adapt_external_contract(contract["result"], contract["manifest"], operation, source_url, sample_id)
    except LingzaoError:
        cleanup_temp(temp_dir)
        raise
    except json.JSONDecodeError as error:
        cleanup_temp(temp_dir)
        raise LingzaoError("invalid_output", "invalid Lingzao JSON: " + str(error))
    except Exception as error:
        cleanup_temp(temp_dir)
        raise LingzaoError("contract_adaptation_error", str(error))

    completed_at = now_iso()
    wrote = []
    for name, payload in adapted.items():
        write_json_atomic(target_dir / name, payload)
        wrote.append(relative_raw_file(target_dir, name))
    invocation = manifest(
        provider="real",
        task=task,
        state={"current_stage": operation},
        operation=operation,
        source=source_url,
        sample_id=sample_id,
        started_at=started_at,
        completed_at=completed_at,
        exit_code=result.returncode,
        raw_files=wrote + [relative_raw_file(target_dir, "invocation.json")],
        command=sanitize_command(args),
        stdout_file=relative_raw_file(target_dir, "execution-stdout.log"),
        stderr_file=relative_raw_file(target_dir, "execution-stderr.log"),
        warnings=[],
    )
    invocation["contract_version"] = CONTRACT_VERSION
    invocation["runner_manifest"] = relative_raw_file(target_dir, "external/runner-manifest.json")
    write_json_atomic(target_dir / "invocation.json", invocation)
    record_operation_invocation(target_dir, operation, "succeeded", invocation, wrote, [], None, None)
    cleanup_temp(temp_dir)


def collect_optional(root: Path, task_dir: Path, task: Dict[str, str], state: Dict[str, object], source_url: str, operations: List[str]) -> None:
    target_dir = task_dir / "raw" / "lingzao"
    note_path = target_dir / "note-detail.json"
    if not note_path.is_file():
        raise LingzaoError("incomplete_output", "note-detail.json is required before optional collection")
    note = read_json(note_path)
    config = provider_config(root)
    for operation in operations:
        if operation not in OPTIONAL_OPERATIONS:
            raise LingzaoError("configuration_error", "unsupported optional Lingzao operation: " + operation)
        existing = note.get("comments" if operation == "collect_comments" else "transcript") or {}
        if existing.get("status") in ("available", "skipped", "failed"):
            continue
        started_at = now_iso()
        try:
            adapted, invocation = run_real_operation(root, task_dir, target_dir, task, state, operation, source_url, config)
            if operation == "collect_comments":
                note["comments"] = adapted["comments.json"]
                output_refs = ["raw/lingzao/comments.json"]
            else:
                note["transcript"] = adapted["transcript.json"]
                output_refs = ["raw/lingzao/transcript.json"]
            record_operation_invocation(target_dir, operation, "succeeded", invocation, output_refs, [], None, None)
        except LingzaoError as error:
            status_payload = {"status": "failed", "items": [], "error": str(error)} if operation == "collect_comments" else {"status": "failed", "text": None, "error": str(error)}
            if operation == "collect_comments":
                note["comments"] = status_payload
            else:
                note["transcript"] = status_payload
            record_operation_invocation(
                target_dir,
                operation,
                "failed",
                {
                    "operation": operation,
                    "started_at": started_at,
                    "completed_at": now_iso(),
                    "warnings": [str(error)],
                },
                [],
                [str(error)],
                error.kind,
                None,
            )
    note.setdefault("coverage", {})["video_file"] = "unsupported"
    write_json_atomic(note_path, note)


def run_real_operation(
    root: Path,
    task_dir: Path,
    target_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    operation: str,
    source_url: str,
    config: Dict[str, object],
) -> tuple:
    run_id = uuid.uuid4().hex[:12]
    temp_dir = task_dir / ".tmp" / ("lingzao-" + operation + "-" + run_id)
    external_tmp = temp_dir / "external"
    external_tmp.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    result, args = run_runner_contract(root, target_dir, external_tmp, task, operation, source_url, config, None)
    try:
        validate_external_paths(external_tmp)
        external_dir = target_dir / "external" / operation
        if not external_dir.exists():
            shutil.copytree(external_tmp, external_dir)
        contract = read_runner_contract(external_tmp, operation, source_url)
        adapted = adapt_external_contract(contract["result"], contract["manifest"], operation, source_url, None)
    finally:
        cleanup_temp(temp_dir)
    completed_at = now_iso()
    for name, payload in adapted.items():
        write_json_atomic(target_dir / name, payload)
    invocation = manifest(
        provider="real",
        task=task,
        state=state,
        operation=operation,
        source=source_url,
        sample_id=None,
        started_at=started_at,
        completed_at=completed_at,
        exit_code=result.returncode,
        raw_files=[relative_raw_file(target_dir, name) for name in adapted] + [relative_raw_file(target_dir, "invocations/" + invocation_file_name(operation))],
        command=sanitize_command(args),
        stdout_file=relative_raw_file(target_dir, "execution-stdout.log"),
        stderr_file=relative_raw_file(target_dir, "execution-stderr.log"),
        warnings=[],
    )
    invocation["contract_version"] = CONTRACT_VERSION
    invocation["runner_manifest"] = relative_raw_file(target_dir, "external/" + operation + "/runner-manifest.json")
    write_json_atomic(target_dir / "invocations" / invocation_file_name(operation), invocation)
    return adapted, invocation


def record_skipped_optional(target_dir: Path, operations: List[str], reason: str, decision_ref: str) -> None:
    note_path = target_dir / "note-detail.json"
    note = read_json(note_path)
    for operation in operations:
        if operation == "collect_comments":
            note["comments"] = {"status": "skipped", "items": [], "reason": reason}
        elif operation == "collect_transcript":
            note["transcript"] = {"status": "skipped", "text": None, "reason": reason}
        record_operation_invocation(
            target_dir,
            operation,
            "skipped",
            {"operation": operation, "started_at": now_iso(), "completed_at": now_iso(), "warnings": []},
            [],
            [],
            None,
            decision_ref,
            skipped_reason=reason,
        )
    note.setdefault("coverage", {})["video_file"] = "unsupported"
    write_json_atomic(note_path, note)


def record_operation_invocation(
    target_dir: Path,
    operation: str,
    status: str,
    invocation: Dict[str, object],
    output_refs: List[str],
    warnings: List[str],
    failure_kind: Optional[str],
    cost_confirmation_ref: Optional[str],
    skipped_reason: Optional[str] = None,
) -> None:
    invocations_dir = target_dir / "invocations"
    invocations_dir.mkdir(parents=True, exist_ok=True)
    invocation_path = invocations_dir / invocation_file_name(operation)
    if not invocation_path.exists():
        write_json_atomic(invocation_path, invocation)
    index_path = invocations_dir / "index.json"
    if index_path.exists():
        index = read_json(index_path)
    else:
        index = {"contract_version": CONTRACT_VERSION, "invocations": []}
    entries = [item for item in index.get("invocations", []) if item.get("operation") != operation]
    entries.append(
        {
            "operation": operation,
            "status": status,
            "output_refs": output_refs,
            "started_at": invocation.get("started_at"),
            "completed_at": invocation.get("completed_at"),
            "warnings": warnings or invocation.get("warnings") or [],
            "skipped_reason": skipped_reason,
            "failure_kind": failure_kind,
            "cost_confirmation_ref": cost_confirmation_ref,
        }
    )
    order = {"collect_note": 0, "collect_comments": 1, "collect_transcript": 2}
    index["invocations"] = sorted(entries, key=lambda item: order.get(str(item.get("operation")), 99))
    write_json_atomic(index_path, index)


def invocation_file_name(operation: str) -> str:
    if operation == "collect_note":
        return "note-detail.json"
    if operation == "collect_comments":
        return "comments.json"
    if operation == "collect_transcript":
        return "transcript.json"
    return operation + ".json"


def run_real_profile_bundle(root: Path, task_dir: Path, target_dir: Path, task: Dict[str, str], state: Dict[str, object], source_url: str, config: Dict[str, object]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    existing = [target_dir / name for name in ["profile.json", "posted-notes.json", "invocation.json"] if (target_dir / name).exists()]
    if existing:
        raise LingzaoError("incomplete_output", "refusing to overwrite existing Lingzao raw output")
    run_id = uuid.uuid4().hex[:12]
    temp_dir = task_dir / ".tmp" / ("lingzao-" + run_id)
    profile_tmp = temp_dir / "external" / "collect_profile"
    posted_tmp = temp_dir / "external" / "collect_posted_notes"
    profile_tmp.mkdir(parents=True, exist_ok=True)
    posted_tmp.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    profile_result, profile_args = run_runner_contract(root, target_dir, profile_tmp, task, "collect_profile", source_url, config, None)
    posted_result, posted_args = run_runner_contract(root, target_dir, posted_tmp, task, "collect_posted_notes", source_url, config, None)
    try:
        validate_external_paths(temp_dir / "external")
        external_dir = target_dir / "external"
        if external_dir.exists():
            raise LingzaoError("incomplete_output", "external raw directory already exists")
        shutil.copytree(temp_dir / "external", external_dir)
        profile_contract = read_runner_contract(profile_tmp, "collect_profile", source_url)
        posted_contract = read_runner_contract(posted_tmp, "collect_posted_notes", source_url)
        adapted = {}
        adapted.update(adapt_external_contract(profile_contract["result"], profile_contract["manifest"], "collect_profile", source_url, None))
        adapted.update(adapt_external_contract(posted_contract["result"], posted_contract["manifest"], "collect_posted_notes", source_url, None))
    except LingzaoError:
        cleanup_temp(temp_dir)
        raise
    except json.JSONDecodeError as error:
        cleanup_temp(temp_dir)
        raise LingzaoError("invalid_output", "invalid Lingzao JSON: " + str(error))
    except Exception as error:
        cleanup_temp(temp_dir)
        raise LingzaoError("contract_adaptation_error", str(error))

    completed_at = now_iso()
    wrote = []
    for name, payload in adapted.items():
        write_json_atomic(target_dir / name, payload)
        wrote.append(relative_raw_file(target_dir, name))
    invocation = manifest(
        provider="real",
        task=task,
        state=state,
        operation="collect_profile",
        source=source_url,
        sample_id=None,
        started_at=started_at,
        completed_at=completed_at,
        exit_code=profile_result.returncode if profile_result.returncode != 0 else posted_result.returncode,
        raw_files=wrote + [relative_raw_file(target_dir, "invocation.json")],
        command=[sanitize_command(profile_args), sanitize_command(posted_args)],
        stdout_file=relative_raw_file(target_dir, "execution-stdout.log"),
        stderr_file=relative_raw_file(target_dir, "execution-stderr.log"),
        warnings=[],
    )
    invocation["contract_version"] = CONTRACT_VERSION
    invocation["runner_manifest"] = {
        "collect_profile": relative_raw_file(target_dir, "external/collect_profile/runner-manifest.json"),
        "collect_posted_notes": relative_raw_file(target_dir, "external/collect_posted_notes/runner-manifest.json"),
    }
    write_json_atomic(target_dir / "invocation.json", invocation)
    cleanup_temp(temp_dir)


def run_runner_contract(root: Path, target_dir: Path, external_tmp: Path, task: Dict[str, str], operation: str, source_url: str, config: Dict[str, object], sample_id: Optional[str]):
    command = list(config.get("command") or [])
    if not command:
        raise LingzaoError("configuration_error", "real command is required")
    if operation not in ALL_OPERATIONS:
        raise LingzaoError("configuration_error", "unsupported Lingzao operation: " + operation)
    if not is_valid_url(source_url):
        raise LingzaoError("configuration_error", "Lingzao source must be an absolute http(s) URL")
    prompt_path = root / "prompts" / "lingzao-evidence-only.md"
    request_path = external_tmp.parent / (operation + "-request.json")
    request = {
        "contract_version": CONTRACT_VERSION,
        "operation": operation,
        "task_id": task["task_id"],
        "sample_id": sample_id,
        "source": source_url,
        "output_dir": str(external_tmp.resolve()),
        "prompt_path": str(prompt_path.resolve()),
        "options": {
            "collect_comments": False,
            "collect_transcript": False,
        },
    }
    write_json_atomic(request_path, request)
    args = command + ["--input", str(request_path), "--output", str(external_tmp.resolve())]
    try:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=float(config["timeout_seconds"]),
            cwd=str(config.get("workdir") or root),
            shell=False,
        )
    except subprocess.TimeoutExpired as error:
        save_logs(target_dir, error.stdout or "", error.stderr or "")
        raise LingzaoError("timeout", "Lingzao command timed out")
    save_logs(target_dir, result.stdout, result.stderr)
    if result.returncode != 0:
        raise LingzaoError("nonzero_exit", "Lingzao command exited with %s" % result.returncode)
    return result, args


def expected_files(operation: str) -> List[str]:
    if operation == "collect_note":
        return ["note-detail.json"]
    if operation == "collect_profile":
        return ["profile.json", "posted-notes.json"]
    if operation == "collect_posted_notes":
        return ["posted-notes.json"]
    if operation == "collect_comments":
        return ["comments.json"]
    if operation == "collect_transcript":
        return ["transcript.json"]
    raise LingzaoError("configuration_error", "unsupported Lingzao operation: " + operation)


def read_runner_contract(external_dir: Path, operation: str, source_url: str) -> Dict[str, Dict[str, object]]:
    result_path = external_dir / "result.json"
    manifest_path = external_dir / "runner-manifest.json"
    if not result_path.is_file() or not manifest_path.is_file():
        raise LingzaoError("incomplete_output", "missing result.json or runner-manifest.json")
    result = read_json(result_path)
    manifest_data = read_json(manifest_path)
    if str(manifest_data.get("contract_version")) != CONTRACT_VERSION:
        raise LingzaoError("contract_adaptation_error", "contract_version mismatch")
    if result.get("operation") != operation or manifest_data.get("operation") != operation:
        raise LingzaoError("contract_adaptation_error", "operation mismatch")
    if result.get("source") != source_url:
        raise LingzaoError("contract_adaptation_error", "source mismatch")
    if manifest_data.get("status") != "succeeded":
        raise LingzaoError("contract_adaptation_error", "runner manifest status is not succeeded")
    return {"result": result, "manifest": manifest_data}


def adapt_external_contract(result: Dict[str, object], runner_manifest: Dict[str, object], operation: str, source_url: str, sample_id: Optional[str]) -> Dict[str, Dict[str, object]]:
    if operation == "collect_note":
        note = result.get("note")
        if not isinstance(note, dict):
            raise LingzaoError("contract_adaptation_error", "result.note is required")
        note_url = note.get("url") or source_url
        if not same_source_or_canonical(str(note_url), source_url):
            raise LingzaoError("contract_adaptation_error", "note.url source mismatch")
        internal = {
            "sample_id": sample_id,
            "source": {"source_type": "xhs_note", "original_url": source_url, "canonical_url": note_url},
            "author": normalize_author(note.get("author")),
            "content": {
                "title": note.get("title"),
                "body": note.get("body"),
                "tags": note.get("tags") or [],
                "images": note.get("images") or [],
            },
            "published_at": note.get("published_at"),
            "captured_at": runner_manifest.get("completed_at"),
            "metrics": normalize_metrics(note.get("metrics")),
            "comments": note.get("comments") or {"status": "missing", "items": []},
            "transcript": note.get("transcript") or {"status": "missing", "text": None},
        }
        return {"note-detail.json": internal}
    if operation == "collect_profile":
        profile = result.get("profile")
        if not isinstance(profile, dict):
            raise LingzaoError("contract_adaptation_error", "result.profile is required")
        return {"profile.json": {
            "source_url": source_url,
            "profile_id": profile.get("id"),
            "nickname": profile.get("name"),
            "bio": profile.get("bio"),
            "captured_at": runner_manifest.get("completed_at"),
            "metrics": normalize_metrics(profile.get("metrics")),
        }}
    if operation == "collect_posted_notes":
        notes = result.get("notes")
        if not isinstance(notes, list):
            raise LingzaoError("contract_adaptation_error", "result.notes are required")
        internal_notes = []
        for item in notes:
            if not isinstance(item, dict):
                raise LingzaoError("contract_adaptation_error", "posted note item must be an object")
            internal_notes.append({
                "note_id": item.get("id"),
                "title": item.get("title"),
                "url": item.get("url"),
                "published_at": item.get("published_at"),
                "metrics": normalize_metrics(item.get("metrics")),
                "captured_at": runner_manifest.get("completed_at"),
            })
        return {"posted-notes.json": {
            "source_url": source_url,
            "captured_at": runner_manifest.get("completed_at"),
            "notes": internal_notes,
        }}
    if operation == "collect_comments":
        comments = result.get("comments")
        if not isinstance(comments, dict):
            raise LingzaoError("contract_adaptation_error", "result.comments is required")
        return {"comments.json": comments}
    if operation == "collect_transcript":
        transcript = result.get("transcript")
        if not isinstance(transcript, dict):
            raise LingzaoError("contract_adaptation_error", "result.transcript is required")
        return {"transcript.json": transcript}
    raise LingzaoError("configuration_error", "unsupported Lingzao operation: " + operation)


def normalize_author(value: object) -> Dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {
        "id": value.get("id"),
        "name": value.get("name") or value.get("nickname"),
    }


def normalize_metrics(value: object) -> Dict[str, object]:
    if not isinstance(value, dict):
        return {}
    aliases = {
        "liked": "likes",
        "like": "likes",
        "collected": "saves",
        "collect": "saves",
        "commented": "comments",
        "comment": "comments",
        "shared": "shares",
        "share": "shares",
    }
    normalized: Dict[str, object] = {}
    for key, item in value.items():
        target = aliases.get(str(key), str(key))
        normalized[target] = item
    return normalized


def same_source_or_canonical(candidate: str, source_url: str) -> bool:
    if candidate == source_url:
        return True
    return strip_query_and_fragment(candidate) == strip_query_and_fragment(source_url)


def strip_query_and_fragment(value: str) -> str:
    parsed = urlsplit(value)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def is_valid_url(value: str) -> bool:
    return isinstance(value, str) and (value.startswith("https://") or value.startswith("http://"))


def validate_external_paths(external_dir: Path) -> None:
    manifest_path = external_dir / "manifest.json"
    if manifest_path.is_file():
        manifest_data = read_json(manifest_path)
        for item in manifest_data.get("files", []):
            candidate = (external_dir / str(item)).resolve()
            if not is_relative_to(candidate, external_dir.resolve()):
                raise LingzaoError("contract_adaptation_error", "external output path escapes output directory")
    for path in external_dir.rglob("*"):
        resolved = path.resolve()
        if not is_relative_to(resolved, external_dir.resolve()):
            raise LingzaoError("contract_adaptation_error", "external output path escapes output directory")


def is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def manifest(provider: str, task: Dict[str, str], state: Dict[str, object], operation: str, source: str, sample_id: Optional[str], started_at: str, completed_at: str, exit_code: int, raw_files: List[str], command: Optional[List[str]], stdout_file: Optional[str], stderr_file: Optional[str], warnings: List[str]) -> Dict[str, object]:
    return {
        "provider": provider,
        "adapter": "lingzao",
        "task_id": task["task_id"],
        "sample_id": sample_id,
        "operation": operation,
        "command": command,
        "started_at": started_at,
        "completed_at": completed_at,
        "exit_code": exit_code,
        "raw_files": raw_files,
        "stdout_file": stdout_file,
        "stderr_file": stderr_file,
        "prompt_path": "prompts/lingzao-evidence-only.md",
        "source": source,
        "warnings": warnings,
    }


def sanitize_command(args: List[str]) -> List[str]:
    sanitized = []
    skip_next = False
    for item in args:
        if skip_next:
            sanitized.append("<redacted>")
            skip_next = False
            continue
        lowered = item.lower()
        if "secret" in lowered or "token" in lowered or "password" in lowered:
            sanitized.append("<redacted>")
            if item.startswith("--"):
                skip_next = True
        else:
            sanitized.append(item)
    return sanitized


def save_logs(target_dir: Path, stdout: object, stderr: object) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    write_limited_log(target_dir / "execution-stdout.log", stdout)
    write_limited_log(target_dir / "execution-stderr.log", stderr)


def write_limited_log(path: Path, value: object) -> None:
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value or "")
    text = redact(text)
    if len(text.encode("utf-8")) > LOG_LIMIT:
        text = text.encode("utf-8")[:LOG_LIMIT].decode("utf-8", errors="ignore") + "\n[truncated]\n"
    path.write_text(text, encoding="utf-8")


def redact(text: str) -> str:
    for key, value in os.environ.items():
        lowered = key.lower()
        if value and ("secret" in lowered or "token" in lowered or "password" in lowered):
            text = text.replace(value, "<redacted>")
    return text


def cleanup_temp(temp_dir: Path) -> None:
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
