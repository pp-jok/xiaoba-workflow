import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class GenerationError(Exception):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = path.with_name("." + path.name + ".tmp")
    temp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_file.replace(path)


def run_content_generation(task_dir: Path, task: Dict[str, str], workspace_ref: str) -> Dict[str, object]:
    context = read_json(task_dir / "content" / "generation-context.yaml")
    candidates = read_json(task_dir / "content" / "topic-candidates.json")
    selected = read_json(task_dir / "content" / "selected-topic.json")
    selected_topic = validate_selected_topic(task, context, candidates, selected)

    request_path = task_dir / "raw" / "personal-content" / "content-generation-request.json"
    response_path = task_dir / "raw" / "personal-content" / "content-generation-response.json"
    package_path = task_dir / "content" / "content-package.yaml"
    artifacts = (request_path, response_path, package_path)
    existing_count = sum(1 for path in artifacts if path.exists())
    if existing_count not in (0, 3):
        raise GenerationError("Incomplete content generation artifacts")
    revision_number = next_revision_number(task_dir)

    if existing_count == 3:
        package = read_json(package_path)
        validate_content_package(package, task, context, selected_topic)
        ensure_revision_package(task_dir, revision_number, package_path)
        return package

    revision = load_latest_change_request(task_dir)
    if revision is not None:
        revision["number"] = revision_number
    request = build_content_generation_request(task, context, selected_topic, workspace_ref, revision)
    response = build_content_generation_response(task, context, selected_topic, request)
    package = build_content_package(task, context, selected_topic, response)
    validate_content_package(package, task, context, selected_topic)

    write_json_atomic(request_path, request)
    write_json_atomic(response_path, response)
    write_json_atomic(package_path, package)
    write_json_atomic(revision_dir(task_dir, revision_number) / "content-package.yaml", package)
    update_revision_index(task_dir, revision_number)
    return package


def validate_selected_topic(
    task: Dict[str, str],
    context: Dict[str, object],
    candidates: Dict[str, object],
    selected: Dict[str, object],
) -> Dict[str, object]:
    if selected.get("task_id") != task["task_id"]:
        raise GenerationError("selected topic task_id mismatch")
    topic_id = selected.get("selected_topic_id")
    if not topic_id:
        raise GenerationError("selected topic id is required")
    candidate = None
    for item in candidates.get("candidates", []):
        if item.get("topic_id") == topic_id:
            candidate = item
            break
    if candidate is None:
        raise GenerationError("selected topic is not in candidates")
    if selected.get("topic") != candidate:
        raise GenerationError("selected topic snapshot mismatch")
    validate_topic_refs(candidate, context)
    return candidate


def validate_topic_refs(topic: Dict[str, object], context: Dict[str, object]) -> None:
    checks = (
        ("mechanism_refs", context.get("mechanism_refs") or []),
        ("rule_refs", context.get("rule_refs") or []),
        ("asset_refs", context.get("asset_refs") or []),
        ("learning_source_refs", context.get("learning_sources") or []),
    )
    for key, allowed in checks:
        for ref in topic.get(key, []):
            if ref not in allowed:
                raise GenerationError("selected topic references unknown " + key)


def build_content_generation_request(
    task: Dict[str, str],
    context: Dict[str, object],
    topic: Dict[str, object],
    workspace_ref: str,
    revision: Optional[Dict[str, object]],
) -> Dict[str, object]:
    payload = {
        "task_id": task["task_id"],
        "operation": "generate_reviewable_content_package",
        "workspace_ref": workspace_ref,
        "brief": context.get("brief") or {},
        "selected_topic": topic,
        "generation_context_refs": {
            "mechanism_refs": topic.get("mechanism_refs", []),
            "rule_refs": topic.get("rule_refs", []),
            "asset_refs": topic.get("asset_refs", []),
            "learning_sources": topic.get("learning_source_refs", []),
        },
        "allowed_actions": [
            "generate draft from selected topic",
            "use existing GenerationContext references",
            "label assumptions limitations and sources",
            "output reviewable content",
        ],
        "forbidden_actions": [
            "auto publish",
            "modify formal mechanisms",
            "modify formal rules",
            "modify formal assets",
            "auto approve content",
            "auto complete task",
            "invent unavailable product facts data or user experiences",
        ],
        "created_at": now_iso(),
    }
    if revision is not None:
        payload["revision"] = revision
    return payload


def build_content_generation_response(
    task: Dict[str, str],
    context: Dict[str, object],
    topic: Dict[str, object],
    request: Dict[str, object],
) -> Dict[str, object]:
    brief = context.get("brief") or {}
    topic_title = str(topic.get("title_direction", "生成选题"))
    revision = request.get("revision") or {}
    feedback_note = ""
    if revision.get("feedback"):
        feedback_note = " 已根据上一轮反馈调整：" + str(revision["feedback"])
    return {
        "task_id": task["task_id"],
        "selected_topic_id": topic["topic_id"],
        "draft_title_options": [
            topic_title,
            "把一个想法做成可执行内容的 3 个步骤",
            "给独立开发者的内容表达检查清单",
        ],
        "opening_hook": "这个选题适合用一个具体问题开场，再交代解决路径。" + feedback_note,
        "section_structure": [
            {"heading": "问题", "content": "先描述 brief 中的创作需求，不补造个人经历或业务数字。"},
            {"heading": "方法", "content": "结合已选题的 core_point，拆成可审核的表达步骤。"},
            {"heading": "提醒", "content": "说明哪些内容需要人工确认，避免把假设写成事实。"},
        ],
        "closing_cta": "如果这个方向可用，人工审核后再决定是否进入发布准备。",
        "hashtags": ["小红书内容", "独立开发者", "内容创作"],
        "visual_suggestions": [
            {
                "slot": 1,
                "purpose": "cover",
                "description": "用静态文字封面呈现核心问题，不生成图片文件。",
                "asset_refs": topic.get("asset_refs", []),
            }
        ],
        "mechanism_refs_used": topic.get("mechanism_refs", []),
        "rule_refs_used": topic.get("rule_refs", []),
        "asset_refs_used": topic.get("asset_refs", []),
        "learning_source_refs_used": topic.get("learning_source_refs", []),
        "originality_notes": list(topic.get("originality_requirements", [])),
        "assumptions": ["草稿中的表达对象和场景需要人工确认。"],
        "risks": list(topic.get("risks", [])),
        "limitations": list(topic.get("limitations", [])),
        "review_questions": ["是否允许使用这个标题方向？", "正文中的示例表达是否符合账号口吻？"],
        "generated_at": now_iso(),
    }


def build_content_package(
    task: Dict[str, str],
    context: Dict[str, object],
    topic: Dict[str, object],
    response: Dict[str, object],
) -> Dict[str, object]:
    titles = response["draft_title_options"]
    return {
        "task_id": task["task_id"],
        "content_id": "content-" + task["task_id"].replace("task-", ""),
        "status": "draft",
        "platform": (context.get("brief") or {}).get("platform", "xiaohongshu"),
        "selected_topic_id": topic["topic_id"],
        "title_options": titles,
        "recommended_title": titles[0],
        "body": {
            "hook": response["opening_hook"],
            "sections": response["section_structure"],
            "closing": "以上内容是待人工审核草稿，不代表发布版本。",
            "cta": response["closing_cta"],
        },
        "hashtags": response["hashtags"],
        "visual_plan": response["visual_suggestions"],
        "traceability": {
            "mechanism_refs": compact_refs(response["mechanism_refs_used"]),
            "rule_refs": compact_refs(response["rule_refs_used"]),
            "asset_refs": compact_refs(response["asset_refs_used"]),
            "learning_source_refs": response["learning_source_refs_used"],
        },
        "originality": {
            "requirements": list(topic.get("originality_requirements", [])),
            "notes": response["originality_notes"],
        },
        "assumptions": response["assumptions"],
        "risks": response["risks"],
        "limitations": response["limitations"],
        "review_questions": response["review_questions"],
    }


def validate_content_package(
    package: Dict[str, object],
    task: Dict[str, str],
    context: Dict[str, object],
    selected_topic: Dict[str, object],
) -> None:
    if package.get("task_id") != task["task_id"]:
        raise GenerationError("content package task_id mismatch")
    if package.get("selected_topic_id") != selected_topic.get("topic_id"):
        raise GenerationError("content package selected_topic_id mismatch")
    if package.get("status") != "draft":
        raise GenerationError("content package status must be draft")
    if not package.get("platform"):
        raise GenerationError("content package platform is required")
    titles = package.get("title_options")
    if not isinstance(titles, list) or not titles:
        raise GenerationError("content package requires title options")
    if package.get("recommended_title") not in titles:
        raise GenerationError("recommended title must come from title options")
    body = package.get("body")
    if not isinstance(body, dict) or not body.get("hook") or not body.get("closing"):
        raise GenerationError("content package body is incomplete")
    sections = body.get("sections")
    if not isinstance(sections, list) or len(sections) < 2:
        raise GenerationError("content package requires at least two sections")
    traceability = package.get("traceability")
    if not isinstance(traceability, dict):
        raise GenerationError("content package traceability is required")
    validate_traceability(traceability, context)
    for key in ("assumptions", "risks", "limitations", "review_questions"):
        if key not in package or not isinstance(package.get(key), list):
            raise GenerationError("content package %s must be a list" % key)
    reject_forbidden_content_package_fields(package)


def validate_traceability(traceability: Dict[str, object], context: Dict[str, object]) -> None:
    checks = (
        ("mechanism_refs", compact_refs(context.get("mechanism_refs") or [])),
        ("rule_refs", compact_refs(context.get("rule_refs") or [])),
        ("asset_refs", compact_refs(context.get("asset_refs") or [])),
        ("learning_source_refs", context.get("learning_sources") or []),
    )
    for key, allowed in checks:
        refs = traceability.get(key)
        if not isinstance(refs, list):
            raise GenerationError("traceability %s must be a list" % key)
        for ref in refs:
            if ref not in allowed:
                raise GenerationError("content package references unknown " + key)


def compact_refs(refs: object) -> List[object]:
    compacted: List[object] = []
    if not isinstance(refs, list):
        return compacted
    for ref in refs:
        if not isinstance(ref, dict):
            compacted.append(ref)
            continue
        item: Dict[str, object] = {}
        for key in (
            "source_task_id",
            "ref",
            "rule_id",
            "rule_version",
            "mechanism_id",
            "asset_id",
            "asset_version",
            "external_object",
            "summary",
        ):
            if key in ref:
                item[key] = ref[key]
        compacted.append(item)
    return compacted


def reject_forbidden_content_package_fields(value: object) -> None:
    forbidden_keys = {
        "auto_publish",
        "access_token",
        "platform_credentials",
        "upload_result",
        "published",
        "approved",
        "validated",
        "formal_mechanism_state",
        "RuleCard",
        "ContentAsset",
        "status_before_generation",
        "lifecycle_status",
    }
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in forbidden_keys:
                raise GenerationError("forbidden content package field: " + key)
            if key == "status" and nested in ("approved", "validated", "published"):
                raise GenerationError("forbidden content package field: " + str(nested))
            reject_forbidden_content_package_fields(nested)
    elif isinstance(value, list):
        for item in value:
            reject_forbidden_content_package_fields(item)


def review_content(task_dir: Path, task: Dict[str, str], state: Dict[str, object], decision: str, feedback: Optional[str]) -> Dict[str, object]:
    if task.get("task_type") != "generation":
        raise GenerationError("review-content only supports generation tasks")
    if state.get("status") != "waiting_for_user" or state.get("current_stage") != "review":
        raise GenerationError("task is not waiting for content review")
    if decision not in ("approve", "request_changes", "reject"):
        raise GenerationError("unsupported review decision: " + decision)
    package_path = task_dir / "content" / "content-package.yaml"
    if not package_path.is_file():
        raise GenerationError("content package is missing")
    package = read_json(package_path)
    if decision == "request_changes" and (not feedback or not feedback.strip()):
        raise GenerationError("feedback is required for request_changes")
    if decision in ("approve", "reject") and (task_dir / "content" / "review-decision.json").exists():
        raise GenerationError("review decision already exists")

    revision_number = current_revision_number(task_dir)
    payload = {
        "task_id": task["task_id"],
        "content_id": package.get("content_id"),
        "decision": decision,
        "feedback": feedback.strip() if feedback and feedback.strip() else None,
        "revision_number": revision_number,
        "reviewed_at": now_iso(),
    }
    if decision == "request_changes":
        rev_dir = revision_dir(task_dir, revision_number)
        if not (rev_dir / "content-package.yaml").is_file():
            shutil.copy2(package_path, rev_dir / "content-package.yaml")
        write_json_atomic(rev_dir / "review-decision.json", payload)
        record_revision_decision(task_dir, revision_number, "content/revisions/revision-%03d/review-decision.json" % revision_number)
        clear_current_content_artifacts(task_dir)
    else:
        write_json_atomic(task_dir / "content" / "review-decision.json", payload)
    return payload


def revision_dir(task_dir: Path, number: int) -> Path:
    return task_dir / "content" / "revisions" / ("revision-%03d" % number)


def revision_index_path(task_dir: Path) -> Path:
    return task_dir / "content" / "content-revisions.json"


def read_revision_index(task_dir: Path) -> Dict[str, object]:
    path = revision_index_path(task_dir)
    if not path.exists():
        return {"current_revision": 0, "revisions": []}
    return read_json(path)


def update_revision_index(task_dir: Path, number: int) -> None:
    index = read_revision_index(task_dir)
    revisions = index.setdefault("revisions", [])
    if not any(item.get("number") == number for item in revisions):
        revisions.append(
            {
                "number": number,
                "content_path": "content/revisions/revision-%03d/content-package.yaml" % number,
                "decision_path": None,
            }
        )
    index["current_revision"] = number
    write_json_atomic(revision_index_path(task_dir), index)


def record_revision_decision(task_dir: Path, number: int, decision_path: str) -> None:
    index = read_revision_index(task_dir)
    for item in index.get("revisions", []):
        if item.get("number") == number:
            item["decision_path"] = decision_path
            break
    write_json_atomic(revision_index_path(task_dir), index)


def current_revision_number(task_dir: Path) -> int:
    return int(read_revision_index(task_dir).get("current_revision") or 1)


def next_revision_number(task_dir: Path) -> int:
    index = read_revision_index(task_dir)
    current = int(index.get("current_revision") or 0)
    latest_decision = latest_request_changes(task_dir)
    if latest_decision is not None and current > 0:
        return current + 1
    return max(current, 1)


def latest_request_changes(task_dir: Path) -> Optional[Dict[str, object]]:
    index = read_revision_index(task_dir)
    for item in reversed(index.get("revisions", [])):
        decision_path = item.get("decision_path")
        if decision_path:
            decision = read_json(task_dir / str(decision_path))
            if decision.get("decision") == "request_changes":
                return decision
    return None


def load_latest_change_request(task_dir: Path) -> Optional[Dict[str, object]]:
    decision = latest_request_changes(task_dir)
    if decision is None:
        return None
    return {
        "previous_content_ref": "content/revisions/revision-%03d/content-package.yaml" % int(decision["revision_number"]),
        "feedback": decision.get("feedback"),
    }


def ensure_revision_package(task_dir: Path, number: int, package_path: Path) -> None:
    rev_package = revision_dir(task_dir, number) / "content-package.yaml"
    if not rev_package.is_file():
        rev_package.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(package_path, rev_package)
        update_revision_index(task_dir, number)


def clear_current_content_artifacts(task_dir: Path) -> None:
    for path in (
        task_dir / "raw" / "personal-content" / "content-generation-request.json",
        task_dir / "raw" / "personal-content" / "content-generation-response.json",
        task_dir / "content" / "content-package.yaml",
    ):
        if path.exists():
            path.unlink()
