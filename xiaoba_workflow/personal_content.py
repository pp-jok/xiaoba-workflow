import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from . import config as local_config
from . import locks


WORKSPACE_REF = "mock://personal-content/default"
OPERATION = "create_or_match_candidate_mechanism"
REQUEST_FILE = "mechanism-intake-request.json"
RESPONSE_FILE = "mechanism-intake-response.json"
RESULT_FILE = "mechanism-intake-result.json"
BATCH_REQUEST_FILE = "batch-mechanism-intake-request.json"
BATCH_RESPONSE_FILE = "batch-mechanism-intake-response.json"
BATCH_RESULT_FILE = "batch-mechanism-intake-result.json"
BATCH_SUMMARY_FILE = "batch-learning-summary.yaml"
BATCH_OPERATION = "batch_create_or_match_candidate_mechanisms"


class PersonalContentError(Exception):
    pass


def doctor(root: Path = None) -> List[str]:
    config = provider_config(root)
    provider = str(config["provider"])
    messages = ["provider: " + provider]
    if provider == "unavailable":
        raise PersonalContentError("Personal Content is not configured")
    if provider == "mock":
        messages.append("workspace_ref: " + WORKSPACE_REF)
        messages.append("operations: mock mechanism_intake, mock generation_context")
        return messages

    command = list(config["command"])
    executable = shutil.which(command[0]) if command else None
    if executable is None:
        raise PersonalContentError("Personal Content command is not executable: " + (command[0] if command else ""))
    workspace = str(config["workspace"])
    messages.append("command: configured")
    messages.append("executable: " + executable)
    messages.append("workspace: configured")
    messages.append("workspace_path: " + workspace)

    completed = subprocess.run(command + ["--help"], check=False, capture_output=True, text=True, shell=False, timeout=10)
    if completed.returncode != 0:
        raise PersonalContentError("Personal Content --help failed: " + (completed.stderr.strip() or completed.stdout.strip()))
    help_text = completed.stdout + "\n" + completed.stderr
    required = [
        "import-mechanism",
        "show-generation-context",
        "propose-rule-from-mechanism",
        "create-rule-decision",
        "resolve-decision",
    ]
    missing = [item for item in required if item not in help_text]
    if missing:
        raise PersonalContentError("Personal Content command missing operations: " + ", ".join(missing))
    messages.append("operations: " + ", ".join(required))
    return messages


def run_mock_mechanism_intake(
    root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    analysis: Dict[str, object],
) -> None:
    config = provider_config(root)
    if config["provider"] == "unavailable" and task.get("execution_mode") == "demo":
        config = {"provider": "mock", "command": None, "workspace": None}
    if config["provider"] == "real":
        run_real_mechanism_intake(root, task_dir, task, state, analysis, config)
        return
    if config["provider"] == "unavailable":
        raise PersonalContentError("Personal Content is not configured")

    prompt_path = root / "prompts" / "personal-content-governance.md"
    if not prompt_path.is_file():
        raise PersonalContentError("Missing prompt: prompts/personal-content-governance.md")

    raw_dir = task_dir / "raw" / "personal-content"
    raw_dir.mkdir(parents=True, exist_ok=True)
    request_path, response_path, result_path = artifact_paths(task_dir)
    existing = [path.exists() for path in (request_path, response_path, result_path)]
    if all(existing):
        validate_existing_artifacts(request_path, response_path, result_path)
        return
    if any(existing):
        raise PersonalContentError("Incomplete mechanism intake artifacts exist")

    request = build_mechanism_intake_request(task, state, analysis, prompt_path)
    response = build_mock_response(request)
    result = build_result(response)

    write_json_atomic(request_path, request)
    write_json_atomic(response_path, response)
    write_json_atomic(result_path, result)

    ensure_has_successful_result(response["results"])


def provider_config(root: Path = None) -> Dict[str, object]:
    settings = local_config.provider_settings(root, "personal_content") if root is not None else {}
    provider = os.environ.get("XIAOBA_PERSONAL_CONTENT_PROVIDER") or str(settings.get("mode") or "mock")
    if provider == "demo":
        provider = "mock"
    if provider not in ("mock", "real", "unavailable"):
        raise PersonalContentError("unsupported Personal Content provider: " + provider)
    command = None
    if settings.get("command"):
        command = settings.get("command")
    if command == "[]":
        command = []
    if os.environ.get("XIAOBA_PERSONAL_CONTENT_COMMAND"):
        try:
            command = json.loads(os.environ["XIAOBA_PERSONAL_CONTENT_COMMAND"])
        except json.JSONDecodeError as error:
            raise PersonalContentError("XIAOBA_PERSONAL_CONTENT_COMMAND must be a JSON array: " + str(error))
    if command is not None and (not isinstance(command, list) or not all(isinstance(item, str) for item in command)):
        raise PersonalContentError("Personal Content command must be a list of strings")
    workspace = os.environ.get("XIAOBA_PERSONAL_CONTENT_WORKSPACE") or settings.get("workspace")
    if provider == "real" and not workspace:
        raise PersonalContentError("XIAOBA_PERSONAL_CONTENT_WORKSPACE is required for real Personal Content provider")
    if provider == "real" and not command:
        raise PersonalContentError("XIAOBA_PERSONAL_CONTENT_COMMAND is required for real Personal Content provider")
    return {"provider": provider, "command": command, "workspace": workspace}


def run_real_mechanism_intake(
    root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    analysis: Dict[str, object],
    config: Dict[str, object],
) -> None:
    prompt_path = root / "prompts" / "personal-content-governance.md"
    if not prompt_path.is_file():
        raise PersonalContentError("Missing prompt: prompts/personal-content-governance.md")

    raw_dir = task_dir / "raw" / "personal-content"
    raw_dir.mkdir(parents=True, exist_ok=True)
    request_path, response_path, result_path = artifact_paths(task_dir)
    existing = [path.exists() for path in (request_path, response_path, result_path)]
    if all(existing):
        validate_existing_artifacts(request_path, response_path, result_path)
        return
    if any(existing):
        raise PersonalContentError("Incomplete mechanism intake artifacts exist")

    request = build_mechanism_intake_request(task, state, analysis, prompt_path)
    request["adapter"] = "real_personal_content"
    request["mock"] = False
    request["workspace_ref"] = str(config["workspace"])
    for mechanism in request["mechanisms"]:
        mechanism["account_workspace_reference"] = str(config["workspace"])

    response = run_personal_content_imports(task_dir, request, config)
    result = build_result(response)
    wrote = []
    try:
        write_json_atomic(request_path, request)
        wrote.append(request_path)
        write_json_atomic(response_path, response)
        wrote.append(response_path)
        write_json_atomic(result_path, result)
        wrote.append(result_path)
        validate_existing_artifacts(request_path, response_path, result_path)
    except Exception as error:
        for path in wrote:
            if path.exists():
                path.unlink()
        raise PersonalContentError("Failed to write real mechanism intake artifacts: " + str(error))


def run_personal_content_imports(
    task_dir: Path,
    request: Dict[str, object],
    config: Dict[str, object],
) -> Dict[str, object]:
    temp_dir = task_dir / ".tmp" / ("personal-content-" + datetime.now().strftime("%Y%m%d%H%M%S%f"))
    temp_dir.mkdir(parents=True, exist_ok=True)
    results = []
    try:
        for mechanism in request["mechanisms"]:
            payload = build_personal_content_mechanism_payload(mechanism)
            payload_path = temp_dir / (str(mechanism.get("mechanism_id")) + ".json")
            write_json_atomic(payload_path, payload)
            results.append(run_personal_content_import_command(mechanism, payload_path, config))
    finally:
        if temp_dir.exists():
            for path in sorted(temp_dir.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            temp_dir.rmdir()

    response = {
        "adapter": "real_personal_content",
        "mock": False,
        "workspace_ref": request["workspace_ref"],
        "operation": request["operation"],
        "task_id": request["task_id"],
        "sample_id": request["sample_id"],
        "executed_at": now_iso(),
        "results": results,
    }
    ensure_has_successful_result(results)
    return response


def build_personal_content_mechanism_payload(mechanism: Dict[str, object]) -> Dict[str, object]:
    observed = [str(item.get("text") or item) for item in mechanism.get("observed_facts", []) if item]
    inferences = [str(item.get("text") or item) for item in mechanism.get("inferences", []) if item]
    limitations = [str(item) for item in mechanism.get("limitations", []) if item]
    source_id = "%s:%s" % (mechanism.get("task_id"), mechanism.get("mechanism_id"))
    return {
        "id": str(mechanism.get("mechanism_id") or ""),
        "name": mechanism.get("name"),
        "description": mechanism.get("description"),
        "status": "candidate",
        "confidence_level": mechanism.get("confidence") or "low",
        "source_refs": [{"source_type": "external_analysis", "source_id": source_id}],
        "evidence_summary": {
            "observed_facts": observed,
            "inferences": inferences,
            "user_stated_preferences": [],
            "missing_information": [],
            "limitations": limitations,
            "source_coverage": {"analysis": "present"},
        },
        "problem": mechanism.get("problem") or "",
        "solution": mechanism.get("solution") or mechanism.get("description") or "",
        "pattern": mechanism.get("pattern") or [mechanism.get("description")],
        "applicable_scope": mechanism.get("applicable_scope") or [],
        "limitations": limitations,
        "created_by": "xiaoba_workflow",
    }


def run_personal_content_import_command(
    mechanism: Dict[str, object],
    payload_path: Path,
    config: Dict[str, object],
) -> Dict[str, object]:
    command = list(config["command"]) + ["import-mechanism", "--workspace", str(config["workspace"]), "--file", str(payload_path)]
    completed = subprocess.run(command, check=False, capture_output=True, text=True, shell=False)
    if completed.returncode != 0:
        duplicate = adapt_duplicate_import_failure(mechanism, completed.stdout, completed.stderr, str(config["workspace"]))
        if duplicate is not None:
            duplicate["warnings"] = ["Personal Content import matched an existing candidate"]
            return duplicate
        return {
            "source_mechanism_id": mechanism.get("mechanism_id"),
            "status": "failed",
            "external_object_type": "content_mechanism",
            "external_object_id": None,
            "external_version": None,
            "external_object": {"type": "content_mechanism", "id": None, "version": None},
            "workspace_ref": str(config["workspace"]),
            "reason": completed.stderr.strip() or completed.stdout.strip() or "Personal Content command failed",
            "warnings": ["Personal Content import command exited with %s" % completed.returncode],
        }
    try:
        output = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        return {
            "source_mechanism_id": mechanism.get("mechanism_id"),
            "status": "failed",
            "external_object_type": "content_mechanism",
            "external_object_id": None,
            "external_version": None,
            "external_object": {"type": "content_mechanism", "id": None, "version": None},
            "workspace_ref": str(config["workspace"]),
            "reason": "Personal Content output is not JSON: " + str(error),
            "warnings": [],
        }
    return adapt_personal_content_import_result(mechanism, output, str(config["workspace"]))


def adapt_duplicate_import_failure(
    mechanism: Dict[str, object],
    stdout: str,
    stderr: str,
    workspace_ref: str,
) -> Dict[str, object]:
    output = parse_json_output(stdout) or parse_json_output(stderr)
    if not isinstance(output, dict):
        return None
    reason = str(output.get("error") or "")
    if "同名候选内容机制已存在" not in reason:
        return None
    existing = find_existing_content_mechanism(Path(workspace_ref), str(mechanism.get("name") or ""))
    object_id = existing.get("id")
    version = existing.get("version") if isinstance(existing.get("version"), int) else 1
    external_object = {"type": "content_mechanism", "id": object_id, "version": version}
    return {
        "source_mechanism_id": mechanism.get("mechanism_id"),
        "status": "matched_existing",
        "external_object_type": external_object["type"],
        "external_object_id": external_object["id"],
        "external_version": external_object["version"],
        "external_object": external_object,
        "workspace_ref": workspace_ref,
        "reason": reason,
        "warnings": [],
    }


def parse_json_output(value: str) -> Dict[str, object]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def find_existing_content_mechanism(workspace: Path, name: str) -> Dict[str, object]:
    mechanisms_dir = workspace / "content-mechanisms"
    if not mechanisms_dir.is_dir():
        return {"id": None, "version": None}
    for path in sorted(mechanisms_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("name") == name:
            return {"id": data.get("id"), "version": data.get("version")}
    return {"id": None, "version": None}


def adapt_personal_content_import_result(
    mechanism: Dict[str, object],
    output: Dict[str, object],
    workspace_ref: str,
) -> Dict[str, object]:
    result = output.get("result") if isinstance(output, dict) else None
    if not output.get("ok") or not isinstance(result, dict):
        status = "rejected" if isinstance(output, dict) else "failed"
        reason = str(output.get("error") if isinstance(output, dict) else "invalid Personal Content output")
        object_id = None
    else:
        status_category = result.get("status_category")
        if status_category == "created":
            status = "imported"
        elif status_category == "limited_created":
            status = "limited"
        elif status_category in ("not_enough_evidence", "invalid_input"):
            status = "rejected"
        else:
            status = "failed"
        reason = result.get("user_summary") or status_category or ""
        object_id = result.get("mechanism_id") if status in ("imported", "limited", "matched_existing") else None
    external_object = {"type": "content_mechanism", "id": object_id, "version": 1 if object_id else None}
    return {
        "source_mechanism_id": mechanism.get("mechanism_id"),
        "status": status,
        "external_object_type": external_object["type"],
        "external_object_id": external_object["id"],
        "external_version": external_object["version"],
        "external_object": external_object,
        "workspace_ref": workspace_ref,
        "reason": str(reason),
        "warnings": [],
    }


def run_mock_batch_mechanism_intake(
    root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    cross: Dict[str, object],
) -> None:
    config = provider_config(root)
    if config["provider"] == "unavailable":
        raise PersonalContentError("Personal Content is not configured")
    if config["provider"] == "real":
        raise PersonalContentError("real batch Personal Content intake is not implemented")

    prompt_path = root / "prompts" / "personal-content-governance.md"
    if not prompt_path.is_file():
        raise PersonalContentError("Missing prompt: prompts/personal-content-governance.md")

    raw_dir = task_dir / "raw" / "personal-content"
    raw_dir.mkdir(parents=True, exist_ok=True)
    request_path, response_path, result_path, summary_path = batch_artifact_paths(task_dir)
    existing = [path.exists() for path in (request_path, response_path, result_path, summary_path)]
    if all(existing):
        validate_existing_batch_artifacts(request_path, response_path, result_path, summary_path, cross, task)
        return
    if any(existing):
        raise PersonalContentError("Incomplete batch mechanism intake artifacts exist")

    if not cross.get("mechanism_candidates"):
        raise PersonalContentError("no mechanism candidates to import")

    request = build_batch_mechanism_intake_request(task, state, cross, prompt_path)
    response = build_batch_mock_response(request)
    result = build_batch_result(response, cross)
    summary = build_batch_learning_summary(cross, result)
    validate_batch_artifacts(request, response, result, summary, cross, task)

    wrote = []
    try:
        write_json_atomic(request_path, request)
        wrote.append(request_path)
        write_json_atomic(response_path, response)
        wrote.append(response_path)
        write_json_atomic(result_path, result)
        wrote.append(result_path)
        write_json_atomic(summary_path, summary)
        wrote.append(summary_path)
        validate_existing_batch_artifacts(request_path, response_path, result_path, summary_path, cross, task)
    except Exception as error:
        for path in wrote:
            if path.exists():
                path.unlink()
        raise PersonalContentError("Failed to write batch mechanism intake artifacts: " + str(error))


def artifact_paths(task_dir: Path) -> Tuple[Path, Path, Path]:
    return (
        task_dir / "raw" / "personal-content" / REQUEST_FILE,
        task_dir / "raw" / "personal-content" / RESPONSE_FILE,
        task_dir / "analysis" / RESULT_FILE,
    )


def batch_artifact_paths(task_dir: Path) -> Tuple[Path, Path, Path, Path]:
    return (
        task_dir / "raw" / "personal-content" / BATCH_REQUEST_FILE,
        task_dir / "raw" / "personal-content" / BATCH_RESPONSE_FILE,
        task_dir / "analysis" / BATCH_RESULT_FILE,
        task_dir / "analysis" / BATCH_SUMMARY_FILE,
    )


def build_mechanism_intake_request(
    task: Dict[str, str],
    state: Dict[str, object],
    analysis: Dict[str, object],
    prompt_path: Path,
) -> Dict[str, object]:
    sample_id = str(analysis.get("sample_id", ""))
    mechanisms = []
    for mechanism in analysis.get("mechanisms", []):
        mechanisms.append(
            {
                "task_id": task["task_id"],
                "sample_id": sample_id,
                "mechanism_id": mechanism.get("id"),
                "name": mechanism.get("name"),
                "description": mechanism.get("description"),
                "problem": mechanism.get("problem"),
                "solution": mechanism.get("solution"),
                "observed_facts": mechanism.get("observed_facts", []),
                "inferences": mechanism.get("inferences", []),
                "applicable_scope": mechanism.get("applicable_scope", []),
                "limitations": mechanism.get("limitations", []),
                "confidence": mechanism.get("confidence"),
                "source_references": mechanism.get("source_refs", []),
                "account_workspace_reference": WORKSPACE_REF,
                "operation": OPERATION,
            }
        )

    return {
        "adapter": "mock_personal_content",
        "mock": True,
        "task_id": task["task_id"],
        "stage": state.get("current_stage"),
        "operation": OPERATION,
        "workspace_ref": WORKSPACE_REF,
        "prompt_path": relative_prompt_path(prompt_path),
        "sample_id": sample_id,
        "mechanisms": mechanisms,
        "created_at": now_iso(),
    }


def build_mock_response(request: Dict[str, object]) -> Dict[str, object]:
    results = []
    for mechanism in request["mechanisms"]:
        status, reason, warnings = decide_status(mechanism)
        external_object = external_object_for(mechanism, status)
        results.append(
            {
                "source_mechanism_id": mechanism.get("mechanism_id"),
                "status": status,
                "external_object_type": external_object["type"],
                "external_object_id": external_object["id"],
                "external_version": external_object["version"],
                "external_object": external_object,
                "workspace_ref": request["workspace_ref"],
                "reason": reason,
                "warnings": warnings,
            }
        )

    return {
        "adapter": "mock_personal_content",
        "mock": True,
        "workspace_ref": request["workspace_ref"],
        "operation": request["operation"],
        "task_id": request["task_id"],
        "sample_id": request["sample_id"],
        "executed_at": now_iso(),
        "results": results,
    }


def build_batch_mechanism_intake_request(
    task: Dict[str, str],
    state: Dict[str, object],
    cross: Dict[str, object],
    prompt_path: Path,
) -> Dict[str, object]:
    candidates = []
    for candidate in cross.get("mechanism_candidates") or []:
        candidates.append(
            {
                "task_id": task["task_id"],
                "aggregation_id": cross.get("aggregation_id"),
                "candidate_id": candidate.get("candidate_id"),
                "name": candidate.get("name"),
                "description": candidate.get("description"),
                "member_mechanisms": candidate.get("member_mechanisms", []),
                "supporting_samples": candidate.get("supporting_samples", []),
                "support_count": candidate.get("support_count"),
                "observed_facts": candidate.get("observed_facts", []),
                "inferences": candidate.get("inferences", []),
                "counter_evidence": candidate.get("counter_evidence", []),
                "differences": candidate.get("differences", []),
                "applicable_scope": candidate.get("applicable_scope", []),
                "limitations": candidate.get("limitations", []),
                "alternative_explanations": candidate.get("alternative_explanations", []),
                "confidence": candidate.get("confidence"),
                "source_references": candidate.get("member_mechanisms", []),
                "merge_recommendation": candidate.get("merge_recommendation"),
                "account_workspace_reference": WORKSPACE_REF,
                "operation": OPERATION,
            }
        )
    return {
        "adapter": "mock_personal_content",
        "mock": True,
        "task_id": task["task_id"],
        "stage": state.get("current_stage"),
        "aggregation_id": cross.get("aggregation_id"),
        "workspace_ref": WORKSPACE_REF,
        "operation": BATCH_OPERATION,
        "prompt_path": relative_prompt_path(prompt_path),
        "candidates": candidates,
        "unmatched_observations": cross.get("unmatched_mechanisms", []),
        "rule_suggestions": cross.get("rule_suggestions", []),
        "asset_suggestions": cross.get("asset_suggestions", []),
        "content_opportunities": cross.get("content_opportunities", []),
        "created_at": now_iso(),
    }


def build_batch_mock_response(request: Dict[str, object]) -> Dict[str, object]:
    results = []
    for candidate in request["candidates"]:
        status, reason, warnings = decide_status(candidate)
        external_object = external_object_for_batch(candidate, status)
        results.append(
            {
                "source_candidate_id": candidate.get("candidate_id"),
                "status": status,
                "external_object_type": external_object["type"],
                "external_object_id": external_object["id"],
                "external_version": external_object["version"],
                "external_object": external_object,
                "workspace_ref": request["workspace_ref"],
                "reason": reason,
                "warnings": warnings,
                "retained_counter_evidence": candidate.get("counter_evidence", []),
                "retained_differences": candidate.get("differences", []),
            }
        )
    return {
        "adapter": "mock_personal_content",
        "mock": True,
        "task_id": request["task_id"],
        "aggregation_id": request["aggregation_id"],
        "workspace_ref": request["workspace_ref"],
        "operation": request["operation"],
        "executed_at": now_iso(),
        "results": results,
    }


def decide_status(mechanism: Dict[str, object]) -> Tuple[str, str, List[str]]:
    name = str(mechanism.get("name") or "")
    confidence = str(mechanism.get("confidence") or "")
    observed = mechanism.get("observed_facts") or []
    if "MOCK_FAIL" in name:
        return "failed", "Mock failure requested by mechanism name.", ["No external object was saved."]
    if "MATCH_EXISTING" in name or "Existing" in name:
        return "matched_existing", "Matched an existing candidate mechanism in the mock workspace.", []
    if "REJECT" in name or not observed:
        return "rejected", "Mechanism is too broad or lacks usable observed facts.", ["Rejected by deterministic mock rule."]
    if confidence == "low":
        return "limited", "Saved as a limited candidate because confidence is low.", ["Needs more samples before formal use."]
    return "imported", "Imported as a new candidate mechanism.", []


def external_object_for(mechanism: Dict[str, object], status: str) -> Dict[str, object]:
    object_type = "content_mechanism"
    source_id = str(mechanism.get("mechanism_id") or "unknown")
    safe_id = source_id.replace("_", "-")
    if status == "failed":
        return {"type": object_type, "id": None, "version": None}
    if status == "rejected":
        return {"type": object_type, "id": None, "version": None}
    if status == "matched_existing":
        return {"type": object_type, "id": "mock-existing-" + safe_id, "version": 3}
    if status == "limited":
        return {"type": object_type, "id": "mock-limited-" + safe_id, "version": 1}
    return {"type": object_type, "id": "mock-" + safe_id, "version": 1}


def external_object_for_batch(candidate: Dict[str, object], status: str) -> Dict[str, object]:
    object_type = "content_mechanism"
    source_id = str(candidate.get("candidate_id") or "unknown").replace("_", "-")
    if status in ("failed", "rejected"):
        return {"type": object_type, "id": None, "version": None}
    if status == "matched_existing":
        return {"type": object_type, "id": "mock-existing-" + source_id, "version": 3}
    if status == "limited":
        return {"type": object_type, "id": "mock-limited-" + source_id, "version": 1}
    return {"type": object_type, "id": "mock-" + source_id, "version": 1}


def build_result(response: Dict[str, object]) -> Dict[str, object]:
    results = []
    for item in response["results"]:
        results.append(
            {
                "source_mechanism_id": item["source_mechanism_id"],
                "status": item["status"],
                "external_object": item["external_object"],
                "reason": item["reason"],
                "warnings": item["warnings"],
            }
        )
    return {
        "workspace_ref": response["workspace_ref"],
        "operation": response["operation"],
        "results": results,
    }


def build_batch_result(response: Dict[str, object], cross: Dict[str, object]) -> Dict[str, object]:
    results = []
    for item in response["results"]:
        results.append(
            {
                "source_candidate_id": item["source_candidate_id"],
                "status": item["status"],
                "external_object": item["external_object"],
                "reason": item["reason"],
                "warnings": item["warnings"],
            }
        )
    return {
        "task_id": response["task_id"],
        "aggregation_id": response["aggregation_id"],
        "workspace_ref": response["workspace_ref"],
        "results": results,
        "unmatched_observations": cross.get("unmatched_mechanisms", []),
        "counts": count_statuses(results),
        "warnings": collect_result_warnings(results),
    }


def build_batch_learning_summary(cross: Dict[str, object], result: Dict[str, object]) -> Dict[str, object]:
    grouped = {status: [] for status in ("imported", "matched_existing", "limited", "rejected", "failed")}
    for item in result["results"]:
        grouped[item["status"]].append(item["source_candidate_id"])
    governance_reasons = []
    if cross.get("rule_suggestions"):
        governance_reasons.append("rule suggestions are pending review")
    if cross.get("asset_suggestions"):
        governance_reasons.append("asset suggestions are pending review")
    if grouped["limited"] or grouped["rejected"] or grouped["failed"]:
        governance_reasons.append("some candidates need follow-up")
    return {
        "task_id": cross.get("task_id"),
        "aggregation_id": cross.get("aggregation_id"),
        "sample_ids": cross.get("sample_ids", []),
        "sample_count": len(cross.get("sample_ids", [])),
        "cross_sample_summary": {
            "candidate_count": len(cross.get("mechanism_candidates", [])),
            "unmatched_count": len(cross.get("unmatched_mechanisms", [])),
            "warnings": (cross.get("normalization") or {}).get("warnings", []),
        },
        "mechanism_intake_summary": grouped,
        "governance": {
            "recommended": bool(governance_reasons),
            "reasons": governance_reasons,
            "pending_rule_suggestions": cross.get("rule_suggestions", []),
            "pending_asset_suggestions": cross.get("asset_suggestions", []),
        },
        "content_opportunities": cross.get("content_opportunities", []),
        "open_questions": cross.get("questions", []),
        "next_recommended_actions": ["review limited/rejected candidates"] if governance_reasons else [],
    }


def validate_existing_artifacts(request_path: Path, response_path: Path, result_path: Path) -> None:
    request = read_json(request_path)
    response = read_json(response_path)
    result = read_json(result_path)
    if request.get("operation") != OPERATION:
        raise PersonalContentError("Invalid existing mechanism intake request")
    if response.get("operation") != OPERATION or not isinstance(response.get("results"), list):
        raise PersonalContentError("Invalid existing mechanism intake response")
    workspace_ref = request.get("workspace_ref")
    if response.get("workspace_ref") != workspace_ref:
        raise PersonalContentError("Invalid existing mechanism intake workspace")
    if result.get("workspace_ref") != workspace_ref or not isinstance(result.get("results"), list):
        raise PersonalContentError("Invalid existing mechanism intake result")
    ensure_has_successful_result(response["results"])


def validate_existing_batch_artifacts(
    request_path: Path,
    response_path: Path,
    result_path: Path,
    summary_path: Path,
    cross: Dict[str, object],
    task: Dict[str, str],
) -> None:
    request = read_json(request_path)
    response = read_json(response_path)
    result = read_json(result_path)
    summary = read_json(summary_path)
    validate_batch_artifacts(request, response, result, summary, cross, task)


def validate_batch_artifacts(
    request: Dict[str, object],
    response: Dict[str, object],
    result: Dict[str, object],
    summary: Dict[str, object],
    cross: Dict[str, object],
    task: Dict[str, str],
) -> None:
    forbidden = {"rule_card", "content_asset", "generated_post", "generated_content", "approved", "formal_mechanism"}
    for payload_name, payload in (("request", request), ("response", response), ("result", result), ("summary", summary)):
        for key in forbidden:
            if key in payload:
                raise PersonalContentError("forbidden batch mechanism intake field in %s: %s" % (payload_name, key))
    if request.get("task_id") != task["task_id"] or response.get("task_id") != task["task_id"] or result.get("task_id") != task["task_id"]:
        raise PersonalContentError("batch mechanism intake task_id mismatch")
    if request.get("aggregation_id") != cross.get("aggregation_id") or response.get("aggregation_id") != cross.get("aggregation_id") or result.get("aggregation_id") != cross.get("aggregation_id"):
        raise PersonalContentError("batch mechanism intake aggregation_id mismatch")
    if request.get("operation") != BATCH_OPERATION or response.get("operation") != BATCH_OPERATION:
        raise PersonalContentError("invalid batch mechanism intake operation")
    cross_ids = [item.get("candidate_id") for item in cross.get("mechanism_candidates", [])]
    request_ids = [item.get("candidate_id") for item in request.get("candidates", [])]
    response_ids = [item.get("source_candidate_id") for item in response.get("results", [])]
    result_ids = [item.get("source_candidate_id") for item in result.get("results", [])]
    if not cross_ids:
        raise PersonalContentError("no mechanism candidates to import")
    if request_ids != cross_ids:
        raise PersonalContentError("request candidates mismatch")
    if sorted(response_ids) != sorted(cross_ids) or len(response_ids) != len(set(response_ids)):
        raise PersonalContentError("response candidates mismatch")
    if sorted(result_ids) != sorted(cross_ids) or len(result_ids) != len(set(result_ids)):
        raise PersonalContentError("result candidates mismatch")
    unmatched_ids = {item.get("mechanism_id") for item in cross.get("unmatched_mechanisms", [])}
    if unmatched_ids.intersection(request_ids):
        raise PersonalContentError("unmatched mechanisms must not be imported as candidates")
    for candidate, source in zip(request.get("candidates", []), cross.get("mechanism_candidates", [])):
        validate_request_candidate(candidate, source)
    for item in response.get("results", []):
        if item.get("status") not in ("imported", "matched_existing", "limited", "rejected", "failed"):
            raise PersonalContentError("invalid batch mechanism intake status")
        if item.get("status") in ("imported", "matched_existing", "limited") and not item.get("external_object_id"):
            raise PersonalContentError("successful batch mechanism intake result requires external object ID")
        if "retained_counter_evidence" not in item or "retained_differences" not in item:
            raise PersonalContentError("batch response must retain counter evidence and differences")
    expected_counts = count_statuses(result.get("results", []))
    if result.get("counts") != expected_counts:
        raise PersonalContentError("batch mechanism intake counts mismatch")
    ensure_has_successful_batch_result(response.get("results", []))
    validate_batch_summary(summary, cross, result)


def validate_request_candidate(candidate: Dict[str, object], source: Dict[str, object]) -> None:
    fields = (
        "candidate_id",
        "name",
        "description",
        "member_mechanisms",
        "supporting_samples",
        "support_count",
        "observed_facts",
        "inferences",
        "counter_evidence",
        "differences",
        "applicable_scope",
        "limitations",
        "alternative_explanations",
        "confidence",
        "merge_recommendation",
    )
    for field in fields:
        if candidate.get(field) != source.get(field):
            raise PersonalContentError("request candidate field mismatch: " + field)
    if candidate.get("operation") != OPERATION:
        raise PersonalContentError("invalid candidate operation")


def validate_batch_summary(summary: Dict[str, object], cross: Dict[str, object], result: Dict[str, object]) -> None:
    if summary.get("task_id") != cross.get("task_id") or summary.get("aggregation_id") != cross.get("aggregation_id"):
        raise PersonalContentError("batch learning summary id mismatch")
    if summary.get("sample_ids") != cross.get("sample_ids") or summary.get("sample_count") != len(cross.get("sample_ids", [])):
        raise PersonalContentError("batch learning summary sample count mismatch")
    cross_summary = summary.get("cross_sample_summary") or {}
    if cross_summary.get("candidate_count") != len(cross.get("mechanism_candidates", [])):
        raise PersonalContentError("batch learning summary candidate count mismatch")
    if cross_summary.get("unmatched_count") != len(cross.get("unmatched_mechanisms", [])):
        raise PersonalContentError("batch learning summary unmatched count mismatch")
    expected_grouped = {status: [] for status in ("imported", "matched_existing", "limited", "rejected", "failed")}
    for item in result.get("results", []):
        expected_grouped[item["status"]].append(item["source_candidate_id"])
    if summary.get("mechanism_intake_summary") != expected_grouped:
        raise PersonalContentError("batch learning summary mechanism counts mismatch")
    governance = summary.get("governance")
    if not isinstance(governance, dict) or "recommended" not in governance:
        raise PersonalContentError("batch learning summary governance is required")


def ensure_has_successful_result(results: Iterable[Dict[str, object]]) -> None:
    items = list(results)
    if not items:
        raise PersonalContentError("no mechanism intake results")
    if not any(item.get("status") in ("imported", "matched_existing", "limited") for item in items):
        if all(item.get("status") == "failed" for item in items):
            raise PersonalContentError("all mechanism intake results failed")
        raise PersonalContentError("no successful mechanism intake result")


def ensure_has_successful_batch_result(results: Iterable[Dict[str, object]]) -> None:
    items = list(results)
    if not items:
        raise PersonalContentError("no batch mechanism intake results")
    if not any(item.get("status") in ("imported", "matched_existing", "limited") for item in items):
        if all(item.get("status") == "failed" for item in items):
            raise PersonalContentError("all batch mechanism intake results failed")
        raise PersonalContentError("no successful batch mechanism intake result")


def count_statuses(results: Iterable[Dict[str, object]]) -> Dict[str, int]:
    counts = {"imported": 0, "matched_existing": 0, "limited": 0, "rejected": 0, "failed": 0}
    for item in results:
        status = item.get("status")
        if status not in counts:
            raise PersonalContentError("invalid status for counts: " + str(status))
        counts[status] += 1
    return counts


def collect_result_warnings(results: Iterable[Dict[str, object]]) -> List[str]:
    warnings = []
    for item in results:
        for warning in item.get("warnings", []):
            warnings.append(str(warning))
    return warnings


def read_json(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, payload: Dict[str, object]) -> None:
    with locks.file_lock(path):
        temp_file = path.with_name("." + path.name + ".tmp")
        temp_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp_file.replace(path)


def relative_prompt_path(prompt_path: Path) -> str:
    return "prompts/" + prompt_path.name


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
