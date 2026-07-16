import argparse
import json
import shutil
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from . import analysis as analysis_module
from . import batch as batch_module
from . import generation as generation_module
from . import learning_summary as learning_summary_module
from . import lingzao as lingzao_module
from . import personal_content as personal_content_module


REQUIRED_DIRECTORIES = (
    "templates",
    "prompts",
    "tasks",
    "tests",
)

REQUIRED_FILES = (
    "workflow.yaml",
    "templates/task.yaml",
    "templates/state.yaml",
    "templates/evidence.yaml",
    "templates/analysis.yaml",
    "templates/learning-summary.yaml",
    "prompts/lingzao-evidence-only.md",
    "prompts/hot-learning-analysis-only.md",
    "prompts/hot-learning-cross-sample.md",
    "prompts/personal-content-governance.md",
    "prompts/personal-content-generation.md",
)

TASK_TYPES = ("learning", "learning_batch", "generation")

NEXT_STAGE_BY_TYPE = {
    "learning": "evidence_collection",
    "learning_batch": "benchmark_screening",
    "generation": "context_assembly",
}

GOAL_BY_TYPE = {
    "learning": "持续学习并沉淀，不生成帖子",
    "learning_batch": "批量学习并沉淀，不生成帖子",
    "generation": "按需生成内容，等待用户审阅",
}

TASK_SUBDIRECTORIES = (
    "raw/lingzao",
    "raw/hot-learning",
    "raw/personal-content",
    "evidence",
    "analysis",
    "governance",
    "content",
)

MANUAL_ADVANCE_PROHIBITED = {
    ("generation", "context_assembly"): "Stage context_assembly must be executed with run; it cannot be advanced manually.",
    ("generation", "topic_selection"): "Stage topic_selection requires select-topic; it cannot be advanced manually.",
    ("generation", "review"): "Stage review requires review-content; it cannot be advanced manually.",
    ("learning_batch", "sample_selection"): "Stage sample_selection requires select-samples; it cannot be advanced manually.",
}


def validate_project(root: Path) -> List[str]:
    missing = []

    for directory in REQUIRED_DIRECTORIES:
        if not (root / directory).is_dir():
            missing.append(directory + "/")

    for file_path in REQUIRED_FILES:
        if not (root / file_path).is_file():
            missing.append(file_path)

    return missing


def doctor(root: Path, skill: str = "lingzao") -> List[str]:
    if skill != "lingzao":
        raise WorkflowError("unsupported doctor skill: " + skill)
    try:
        return lingzao_module.doctor(root)
    except lingzao_module.LingzaoError as error:
        raise WorkflowError(str(error))


def create_task(root: Path, task_type: str, source_url: Optional[str], brief: Optional[str] = None) -> Path:
    if task_type not in TASK_TYPES:
        raise ValueError("unsupported task type: " + task_type)
    if task_type in ("learning", "learning_batch") and not source_url:
        raise ValueError("--source-url is required for %s tasks" % task_type)

    tasks_root = root / "tasks"
    tasks_root.mkdir(exist_ok=True)

    task_id = generate_task_id(tasks_root, task_type)
    final_dir = tasks_root / task_id
    temp_dir = tasks_root / (".tmp-" + task_id)

    try:
        temp_dir.mkdir()
        for subdirectory in TASK_SUBDIRECTORIES:
            (temp_dir / subdirectory).mkdir(parents=True)

        workflow = get_task_workflow(load_workflows(root / "workflow.yaml"), task_type)
        created_at = now_iso()
        write_text(temp_dir / "task.yaml", render_task_yaml(task_id, task_type, source_url, created_at))
        state = initial_state(task_id, task_type, workflow, created_at)
        write_text(temp_dir / "state.yaml", render_state_yaml(state))
        write_text(temp_dir / "feedback.md", "")
        write_text(temp_dir / "run-log.md", "# Run Log\n\n")
        if task_type == "generation" and brief:
            write_generation_brief(temp_dir, task_id, brief, created_at)

        temp_dir.rename(final_dir)
        return final_dir
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(str(temp_dir))
        raise


def generate_task_id(tasks_root: Path, task_type: str) -> str:
    suffix = task_type.replace("_", "-")
    for _ in range(100):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        task_id = "task-%s-%s" % (stamp, suffix)
        if not (tasks_root / task_id).exists() and not (tasks_root / (".tmp-" + task_id)).exists():
            return task_id
    raise RuntimeError("could not allocate a unique task id")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def write_text_atomic(path: Path, content: str) -> None:
    temp_file = path.with_name("." + path.name + ".tmp")
    temp_file.write_text(content, encoding="utf-8")
    temp_file.replace(path)


def write_json_atomic(path: Path, payload: Dict[str, object]) -> None:
    temp_file = path.with_name("." + path.name + ".tmp")
    temp_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_file.replace(path)


def write_generation_brief(task_dir: Path, task_id: str, brief: str, created_at: Optional[str] = None) -> None:
    if not brief or not brief.strip():
        raise WorkflowError("generation brief is required")
    payload = {
        "task_id": task_id,
        "request": brief.strip(),
        "platform": "xiaohongshu",
        "target_audience": None,
        "content_goal": None,
        "constraints": [],
        "forbidden": [],
        "created_at": created_at or now_iso(),
    }
    write_json_atomic(task_dir / "content" / "generation-brief.json", payload)


def render_task_yaml(task_id: str, task_type: str, source_url: Optional[str], created_at: str) -> str:
    if source_url:
        sources = "\nsources:\n  - type: url\n    value: %s\n" % yaml_scalar(source_url)
        source_type = "xhs_note"
    else:
        sources = "\nsources: []\n"
        source_type = ""

    return (
        "task_id: {task_id}\n"
        "task_type: {task_type}\n\n"
        "source_type: {source_type}\n"
        "{sources}\n"
        "goal: {goal}\n\n"
        "requested_outputs: []\n\n"
        "generation_policy:\n"
        "  auto_generate: false\n\n"
        "created_at: {created_at}\n"
    ).format(
        task_id=task_id,
        task_type=task_type,
        source_type=source_type,
        sources=sources,
        goal=GOAL_BY_TYPE[task_type],
        created_at=created_at,
    )


def initial_state(task_id: str, task_type: str, workflow: Dict[str, object], created_at: str) -> Dict[str, object]:
    initial_stage = str(workflow["initial_stage"])
    stages = workflow["stages"]
    next_stage = stages[initial_stage].get("next")
    return {
        "task_id": task_id,
        "task_type": task_type,
        "status": "running",
        "current_stage": initial_stage,
        "current_step": "transition",
        "completed_stages": [],
        "waiting_for": None,
        "next_stage": next_stage,
        "last_updated_at": created_at,
    }


def render_state_yaml(state: Dict[str, object]) -> str:
    completed_stages = state.get("completed_stages") or []
    if completed_stages:
        completed = "completed_stages:\n" + "".join("  - %s\n" % stage for stage in completed_stages)
    else:
        completed = "completed_stages: []\n"

    waiting_for = state.get("waiting_for")
    if isinstance(waiting_for, dict):
        waiting = "waiting_for:\n"
        for key, value in waiting_for.items():
            waiting += "  %s: %s\n" % (key, value)
    else:
        waiting = "waiting_for: null\n"

    next_stage = state.get("next_stage")
    if next_stage is None or next_stage == "":
        next_line = "next_stage: null"
    else:
        next_line = "next_stage: %s" % next_stage

    return (
        "task_id: {task_id}\n"
        "task_type: {task_type}\n\n"
        "status: {status}\n"
        "current_stage: {current_stage}\n"
        "current_step: {current_step}\n\n"
        "{completed}\n"
        "{waiting}"
        "{next_line}\n\n"
        "last_updated_at: {last_updated_at}\n"
    ).format(
        task_id=state["task_id"],
        task_type=state["task_type"],
        status=state["status"],
        current_stage=state["current_stage"],
        current_step=state["current_step"],
        completed=completed,
        waiting=waiting,
        next_line=next_line,
        last_updated_at=state["last_updated_at"],
    )


def yaml_scalar(value: str) -> str:
    return value


def read_top_level_scalars(path: Path) -> Dict[str, str]:
    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line or raw_line.startswith(" ") or raw_line.startswith("-"):
            continue
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def read_first_source_url(path: Path) -> Optional[str]:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("value:"):
            return line.split(":", 1)[1].strip().strip('"')
    return None


def load_workflows(path: Path) -> Dict[str, Dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError("Missing workflow.yaml: " + str(path))

    workflows = {}
    current_type = None
    current_stage = None
    in_workflows = False
    in_stages = False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        if indent == 0:
            in_workflows = line == "workflows:"
            in_stages = False
            current_type = None
            current_stage = None
            continue

        if not in_workflows:
            continue

        if indent == 2 and line.endswith(":"):
            current_type = line[:-1]
            workflows[current_type] = {"stages": {}}
            in_stages = False
            current_stage = None
            continue

        if current_type is None:
            continue

        if indent == 4 and line == "stages:":
            in_stages = True
            continue

        if indent == 4 and ":" in line and not in_stages:
            key, value = split_yaml_pair(line)
            workflows[current_type][key] = parse_yaml_scalar(value)
            continue

        if indent == 6 and in_stages and line.endswith(":"):
            current_stage = line[:-1]
            workflows[current_type]["stages"][current_stage] = {}
            continue

        if indent == 8 and in_stages and current_stage and ":" in line:
            key, value = split_yaml_pair(line)
            workflows[current_type]["stages"][current_stage][key] = parse_yaml_scalar(value)

    return workflows


def split_yaml_pair(line: str) -> Tuple[str, str]:
    key, value = line.split(":", 1)
    return key.strip(), value.strip()


def parse_yaml_scalar(value: str):
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "null":
        return None
    return value.strip('"')


def get_task_workflow(workflows: Dict[str, Dict[str, object]], task_type: str) -> Dict[str, object]:
    if task_type not in workflows:
        raise WorkflowError("No workflow configured for task_type: " + task_type)
    return workflows[task_type]


def read_task_files(task_dir: Path) -> Tuple[Dict[str, str], Dict[str, object]]:
    if not task_dir.is_dir():
        raise FileNotFoundError("Task directory not found: " + str(task_dir))

    task_file = task_dir / "task.yaml"
    state_file = task_dir / "state.yaml"
    if not task_file.is_file():
        raise FileNotFoundError("Missing task.yaml: " + str(task_file))
    if not state_file.is_file():
        raise FileNotFoundError("Missing state.yaml: " + str(state_file))

    task = read_top_level_scalars(task_file)
    state = read_state_yaml(state_file)
    if task.get("task_type") != state.get("task_type"):
        raise WorkflowError("task type mismatch between task.yaml and state.yaml")
    if task.get("task_id") != state.get("task_id"):
        raise WorkflowError("task id mismatch between task.yaml and state.yaml")
    return task, state


def read_task_context(task_dir: Path) -> Tuple[Dict[str, str], Dict[str, object], Optional[str]]:
    task, state = read_task_files(task_dir)
    source_url = read_first_source_url(task_dir / "task.yaml")
    return task, state, source_url


def read_state_yaml(path: Path) -> Dict[str, object]:
    state = {
        "completed_stages": [],
        "waiting_for": None,
    }
    current_block = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line:
            continue

        if raw_line.startswith("  - ") and current_block == "completed_stages":
            state["completed_stages"].append(raw_line[4:].strip())
            continue

        if raw_line.startswith("  ") and current_block == "waiting_for":
            key, value = split_yaml_pair(raw_line.strip())
            if state["waiting_for"] is None:
                state["waiting_for"] = {}
            state["waiting_for"][key] = parse_yaml_scalar(value)
            continue

        current_block = None
        if ":" not in raw_line:
            continue
        key, value = split_yaml_pair(raw_line)
        if key == "completed_stages":
            current_block = key
            if value == "[]":
                state[key] = []
            continue
        if key == "waiting_for":
            current_block = key
            state[key] = None if value == "null" else {}
            continue
        state[key] = parse_yaml_scalar(value)

    return state


def write_state_atomic(task_dir: Path, state: Dict[str, object]) -> None:
    state_file = task_dir / "state.yaml"
    temp_file = task_dir / ".state.yaml.tmp"
    try:
        temp_file.write_text(render_state_yaml(state), encoding="utf-8")
        temp_file.replace(state_file)
    except Exception as error:
        if temp_file.is_file():
            temp_file.unlink()
        raise WorkflowError("Failed to write state.yaml: " + str(error))


class WorkflowError(Exception):
    pass


def advance_task(root: Path, task_dir: Path) -> Dict[str, object]:
    task, state = read_task_files(task_dir)
    workflow = get_task_workflow(load_workflows(root / "workflow.yaml"), task["task_type"])

    if state.get("status") == "completed":
        raise WorkflowError("Task is already completed")
    if state.get("status") == "blocked":
        raise WorkflowError("Task is blocked")
    if state.get("status") == "waiting_for_user":
        raise WorkflowError("Task is waiting_for_user and cannot advance")
    if state.get("status") != "running":
        raise WorkflowError("Task status cannot advance: " + str(state.get("status")))
    protected_message = manual_advance_prohibited_message(task, state)
    if protected_message:
        raise WorkflowError(protected_message)

    return move_to_next_stage(task_dir, workflow, state)


def manual_advance_prohibited_message(task: Dict[str, str], state: Dict[str, object]) -> Optional[str]:
    return MANUAL_ADVANCE_PROHIBITED.get((str(task.get("task_type")), str(state.get("current_stage"))))


def resume_task(root: Path, task_dir: Path) -> Dict[str, object]:
    task, state = read_task_files(task_dir)
    workflow = get_task_workflow(load_workflows(root / "workflow.yaml"), task["task_type"])

    if state.get("status") != "waiting_for_user":
        raise WorkflowError("Task is not waiting_for_user")

    stage = str(state.get("current_stage"))
    if task.get("task_type") == "learning_batch" and stage == "sample_selection":
        raise WorkflowError("sample_selection requires select-samples")
    if task.get("task_type") == "generation" and stage == "topic_selection":
        raise WorkflowError("topic_selection requires select-topic")
    if task.get("task_type") == "generation" and stage == "review":
        raise WorkflowError("review requires review-content")
    stage_config = get_stage_config(workflow, stage)
    if not stage_config.get("human_gate"):
        raise WorkflowError("Current stage is not a human gate: " + stage)

    return move_to_next_stage(task_dir, workflow, state)


def block_task(task_dir: Path, reason: str) -> Dict[str, object]:
    _task, state = read_task_files(task_dir)
    if state.get("status") == "completed":
        raise WorkflowError("Completed task cannot be blocked")
    state["status"] = "blocked"
    state["waiting_for"] = {"type": "blocked", "reason": reason}
    state["last_updated_at"] = now_iso()
    write_state_atomic(task_dir, state)
    return state


def block_stage_failure(task_dir: Path, state: Dict[str, object], reason: str) -> Dict[str, object]:
    state["status"] = "blocked"
    state["waiting_for"] = {"type": "stage_failure", "reason": reason}
    state["last_updated_at"] = now_iso()
    write_state_atomic(task_dir, state)
    return state


def unblock_task(task_dir: Path) -> Dict[str, object]:
    _task, state = read_task_files(task_dir)
    if state.get("status") != "blocked":
        raise WorkflowError("Task is not blocked")
    state["status"] = "running"
    state["waiting_for"] = None
    state["last_updated_at"] = now_iso()
    write_state_atomic(task_dir, state)
    return state


def select_samples(root: Path, task_dir: Path, sample_ids: Iterable[str]) -> Dict[str, object]:
    task, state = read_task_files(task_dir)
    workflow = get_task_workflow(load_workflows(root / "workflow.yaml"), task["task_type"])
    try:
        batch_module.select_samples(task_dir, task, state, sample_ids)
    except Exception as error:
        raise WorkflowError(str(error))
    return move_to_next_stage(task_dir, workflow, state)


def set_generation_brief(task_dir: Path, brief: str) -> Dict[str, object]:
    task, state = read_task_files(task_dir)
    if task.get("task_type") != "generation":
        raise WorkflowError("set-generation-brief only supports generation tasks")
    if not brief or not brief.strip():
        raise WorkflowError("generation brief is required")
    if state.get("current_stage") not in ("task_intake", "context_assembly"):
        raise WorkflowError("cannot modify brief after topic_generation")
    brief_path = task_dir / "content" / "generation-brief.json"
    if brief_path.exists():
        raise WorkflowError("generation brief already exists")
    write_generation_brief(task_dir, str(task["task_id"]), brief)
    if state.get("status") == "waiting_for_user":
        state["status"] = "running"
        state["waiting_for"] = None
        state["last_updated_at"] = now_iso()
        write_state_atomic(task_dir, state)
    return state


def attach_learning_source(root: Path, generation_task_dir: Path, source_task_dir: Path) -> Dict[str, object]:
    task, state = read_task_files(generation_task_dir)
    if task.get("task_type") != "generation":
        raise WorkflowError("attach-learning only supports generation tasks")
    if state.get("current_stage") not in ("task_intake", "context_assembly"):
        raise WorkflowError("cannot attach learning source after topic_generation")
    source_task, source_state = read_task_files(source_task_dir)
    if source_task.get("task_type") not in ("learning", "learning_batch"):
        raise WorkflowError("source task must be learning or learning_batch")
    if source_state.get("status") != "completed":
        raise WorkflowError("source task must be completed")
    source_type = str(source_task["task_type"])
    if source_type == "learning":
        summary_rel = "analysis/learning-summary.yaml"
        result_rel = "analysis/mechanism-intake-result.json"
    else:
        summary_rel = "analysis/batch-learning-summary.yaml"
        result_rel = "analysis/batch-mechanism-intake-result.json"
    summary_path = source_task_dir / summary_rel
    result_path = source_task_dir / result_rel
    if not summary_path.is_file():
        raise WorkflowError("source summary is missing: " + summary_rel)
    if not result_path.is_file():
        raise WorkflowError("source mechanism intake result is missing: " + result_rel)
    source_summary = read_json_file(summary_path)
    if source_summary.get("task_id") != source_task.get("task_id"):
        raise WorkflowError("source summary task_id mismatch")

    sources_path = generation_task_dir / "content" / "context-sources.json"
    if sources_path.exists():
        payload = read_json_file(sources_path)
        if payload.get("generation_task_id") != task["task_id"]:
            raise WorkflowError("context sources generation_task_id mismatch")
    else:
        payload = {"generation_task_id": task["task_id"], "sources": []}
    existing_ids = [item.get("source_task_id") for item in payload.get("sources", [])]
    if source_task["task_id"] in existing_ids:
        raise WorkflowError("learning source already attached")
    source_entry = {
        "source_task_id": source_task["task_id"],
        "source_task_type": source_type,
        "source_task_path": str(source_task_dir.relative_to(root)) if source_task_dir.is_relative_to(root) else str(source_task_dir),
        "summary_path": summary_rel,
        "mechanism_intake_result_path": result_rel,
        "attached_at": now_iso(),
    }
    payload.setdefault("sources", []).append(source_entry)
    write_json_atomic(sources_path, payload)
    return state


def select_topic(root: Path, task_dir: Path, topic_id: str) -> Dict[str, object]:
    task, state = read_task_files(task_dir)
    workflow = get_task_workflow(load_workflows(root / "workflow.yaml"), task["task_type"])
    if task.get("task_type") != "generation":
        raise WorkflowError("select-topic only supports generation tasks")
    if not topic_id or not topic_id.strip():
        raise WorkflowError("topic id is required")
    selected_path = task_dir / "content" / "selected-topic.json"
    if selected_path.exists():
        raise WorkflowError("topic already selected")
    if state.get("status") != "waiting_for_user" or state.get("current_stage") != "topic_selection":
        raise WorkflowError("task is not waiting for topic_selection")
    candidates_path = task_dir / "content" / "topic-candidates.json"
    if not candidates_path.is_file():
        raise WorkflowError("topic candidates are missing")
    context_path = task_dir / "content" / "generation-context.yaml"
    if not context_path.is_file():
        raise WorkflowError("generation context is missing")
    context = read_json_file(context_path)
    validate_generation_context(context, task)
    candidates = read_json_file(candidates_path)
    validate_topic_candidates(candidates, task, context)
    selected = None
    for item in candidates.get("candidates", []):
        if item.get("topic_id") == topic_id.strip():
            selected = item
            break
    if selected is None:
        raise WorkflowError("unknown topic id: " + topic_id)
    payload = {
        "task_id": task["task_id"],
        "selected_topic_id": topic_id.strip(),
        "topic": selected,
        "source_candidates_path": "content/topic-candidates.json",
        "selected_at": now_iso(),
    }
    write_json_atomic(selected_path, payload)
    return move_to_next_stage(task_dir, workflow, state)


def review_content(root: Path, task_dir: Path, decision: str, feedback: Optional[str] = None) -> Dict[str, object]:
    task, state = read_task_files(task_dir)
    workflow = get_task_workflow(load_workflows(root / "workflow.yaml"), task["task_type"])
    try:
        generation_module.review_content(task_dir, task, state, decision, feedback)
    except generation_module.GenerationError as error:
        raise WorkflowError(str(error))
    if decision == "request_changes":
        state["status"] = "running"
        state["current_stage"] = "content_generation"
        state["current_step"] = "transition"
        state["waiting_for"] = None
        state["next_stage"] = "review"
        state["last_updated_at"] = now_iso()
        write_state_atomic(task_dir, state)
        return state
    return move_to_next_stage(task_dir, workflow, state)


def get_stage_config(workflow: Dict[str, object], stage: str) -> Dict[str, object]:
    stages = workflow.get("stages", {})
    if stage not in stages:
        raise WorkflowError("Invalid current_stage: " + stage)
    return stages[stage]


def move_to_next_stage(task_dir: Path, workflow: Dict[str, object], state: Dict[str, object]) -> Dict[str, object]:
    current_stage = str(state.get("current_stage"))
    current_config = get_stage_config(workflow, current_stage)
    if current_config.get("terminal"):
        raise WorkflowError("Task is already completed")

    next_stage = current_config.get("next")
    if not next_stage:
        raise WorkflowError("No next stage configured for: " + current_stage)
    next_config = get_stage_config(workflow, str(next_stage))

    completed = list(state.get("completed_stages") or [])
    if current_stage not in completed:
        completed.append(current_stage)

    state["completed_stages"] = completed
    state["current_stage"] = next_stage
    state["current_step"] = "transition"
    state["last_updated_at"] = now_iso()

    if next_config.get("terminal"):
        state["status"] = "completed"
        state["waiting_for"] = None
        state["next_stage"] = None
    elif next_config.get("human_gate"):
        state["status"] = "waiting_for_user"
        if next_stage == "sample_selection":
            state["waiting_for"] = {"type": "sample_selection", "candidates_file": "analysis/sample-candidates.json"}
        elif next_stage == "topic_selection":
            state["waiting_for"] = {"type": "topic_selection", "candidates_file": "content/topic-candidates.json"}
        elif next_stage == "review":
            state["waiting_for"] = {"type": "content_review", "content_file": "content/content-package.yaml"}
        else:
            state["waiting_for"] = {"type": "stage_decision", "stage": next_stage}
        state["next_stage"] = next_config.get("next")
    else:
        state["status"] = "running"
        state["waiting_for"] = None
        state["next_stage"] = next_config.get("next")

    write_state_atomic(task_dir, state)
    return state


def run_task(root: Path, task_dir: Path) -> Dict[str, object]:
    task, state, source_url = read_task_context(task_dir)
    workflow = get_task_workflow(load_workflows(root / "workflow.yaml"), task["task_type"])

    status = state.get("status")
    if status == "waiting_for_user":
        raise WorkflowError("Task is waiting_for_user and cannot run")
    if status == "blocked":
        raise WorkflowError("Task is blocked and cannot run")
    if status == "completed":
        raise WorkflowError("Task is completed and cannot run")
    if status != "running":
        raise WorkflowError("Task status cannot run: " + str(status))

    stage = str(state.get("current_stage"))
    get_stage_config(workflow, stage)
    executor = get_stage_executor(str(task["task_type"]), stage)
    if executor is None:
        raise WorkflowError("No executor for %s:%s" % (task["task_type"], stage))

    updated = executor(root, task_dir, task, state, source_url, workflow)
    updated["_executed_stage"] = stage
    return updated


def get_stage_executor(task_type: str, stage: str):
    executors = {
        ("learning", "task_intake"): execute_learning_task_intake,
        ("learning", "evidence_collection"): execute_learning_evidence_collection,
        ("learning", "evidence_normalization"): execute_learning_evidence_normalization,
        ("learning", "analysis"): execute_learning_analysis,
        ("learning", "analysis_normalization"): execute_learning_analysis_normalization,
        ("learning", "mechanism_intake"): execute_learning_mechanism_intake,
        ("learning", "aggregation"): execute_learning_aggregation,
        ("learning_batch", "task_intake"): execute_learning_batch_task_intake,
        ("learning_batch", "benchmark_screening"): execute_learning_batch_benchmark_screening,
        ("learning_batch", "evidence_collection"): execute_learning_batch_evidence_collection,
        ("learning_batch", "evidence_normalization"): execute_learning_batch_evidence_normalization,
        ("learning_batch", "analysis"): execute_learning_batch_analysis,
        ("learning_batch", "analysis_normalization"): execute_learning_batch_analysis_normalization,
        ("learning_batch", "cross_sample_aggregation"): execute_learning_batch_cross_sample_aggregation,
        ("learning_batch", "mechanism_intake"): execute_learning_batch_mechanism_intake,
        ("generation", "task_intake"): execute_generation_task_intake,
        ("generation", "context_assembly"): execute_generation_context_assembly,
        ("generation", "topic_generation"): execute_generation_topic_generation,
        ("generation", "content_generation"): execute_generation_content_generation,
    }
    return executors.get((task_type, stage))


def execute_generation_task_intake(
    _root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    _source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    if task.get("task_type") != "generation":
        raise WorkflowError("generation task_intake requires generation task")
    task_text = (task_dir / "task.yaml").read_text(encoding="utf-8")
    if "auto_generate: true" in task_text or "auto_publish: true" in task_text:
        raise WorkflowError("generation task cannot enable automatic generation or publishing")
    return move_to_next_stage(task_dir, workflow, state)


def execute_generation_context_assembly(
    root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    _source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    try:
        result = run_generation_context_assembly(root, task_dir, task, state)
    except Exception as error:
        if str(error) == "generation brief required":
            state["status"] = "waiting_for_user"
            state["waiting_for"] = {
                "type": "generation_brief",
                "reason": "Generation brief is required",
            }
            state["last_updated_at"] = now_iso()
            write_state_atomic(task_dir, state)
        else:
            block_stage_failure(task_dir, state, str(error))
        raise WorkflowError(str(error))
    if result == "complete":
        return move_to_next_stage(task_dir, workflow, state)
    return state


def execute_generation_topic_generation(
    _root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    _source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    try:
        run_generation_topic_generation(task_dir, task)
    except Exception as error:
        block_stage_failure(task_dir, state, str(error))
        raise WorkflowError(str(error))
    return move_to_next_stage(task_dir, workflow, state)


def execute_generation_content_generation(
    _root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    _source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    try:
        context = read_json_file(task_dir / "content" / "generation-context.yaml")
        validate_generation_context(context, task)
        candidates = read_json_file(task_dir / "content" / "topic-candidates.json")
        validate_topic_candidates(candidates, task, context)
        generation_module.run_content_generation(task_dir, task, personal_content_module.WORKSPACE_REF)
    except Exception as error:
        block_stage_failure(task_dir, state, str(error))
        raise WorkflowError(str(error))
    return move_to_next_stage(task_dir, workflow, state)


def execute_learning_task_intake(
    _root: Path,
    task_dir: Path,
    _task: Dict[str, str],
    state: Dict[str, object],
    source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    if not source_url:
        raise WorkflowError("learning task requires a source URL")
    return move_to_next_stage(task_dir, workflow, state)


def execute_learning_batch_task_intake(
    _root: Path,
    task_dir: Path,
    _task: Dict[str, str],
    state: Dict[str, object],
    source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    if not source_url:
        raise WorkflowError("learning_batch task requires a source URL")
    return move_to_next_stage(task_dir, workflow, state)


def execute_learning_batch_benchmark_screening(
    root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    try:
        if not source_url:
            raise WorkflowError("learning_batch benchmark_screening requires a source URL")
        provider = lingzao_module.provider_config(root)["provider"]
        if provider == "mock":
            batch_module.run_mock_benchmark_screening(task_dir, task, state, source_url)
        else:
            lingzao_module.collect_profile(root, task_dir, task, state, source_url)
            profile_path, posted_path, invocation_path, candidates_path = batch_module.screening_paths(task_dir)
            exists = [path.exists() for path in (profile_path, posted_path, invocation_path, candidates_path)]
            if all(exists):
                batch_module.validate_candidates(read_json_file(candidates_path), candidates_path)
            elif any(exists[:3]) and not candidates_path.exists():
                posted_notes = read_json_file(posted_path)
                candidates = batch_module.build_candidates(task, posted_notes, now_iso())
                write_json_atomic(candidates_path, candidates)
            else:
                raise WorkflowError("incomplete_output: benchmark screening artifacts are incomplete")
    except Exception as error:
        block_stage_failure(task_dir, state, str(error))
        raise WorkflowError(str(error))
    return move_to_next_stage(task_dir, workflow, state)


def execute_learning_batch_evidence_collection(
    root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    _source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    try:
        provider = lingzao_module.provider_config(root)["provider"]
        collector = None
        if provider == "real":
            collector = lambda sample: lingzao_module.collect_note(
                root,
                task_dir,
                task,
                state,
                str(sample.get("url") or ""),
                str(sample.get("sample_id")),
                task_dir / "raw" / "lingzao" / "samples" / str(sample.get("sample_id")),
            )
        result = batch_module.run_mock_batch_evidence_collection(task_dir, task, state, collector=collector)
    except Exception as error:
        block_stage_failure(task_dir, state, str(error))
        raise WorkflowError(str(error))
    if result == "complete":
        return move_to_next_stage(task_dir, workflow, state)
    return state


def execute_learning_batch_evidence_normalization(
    _root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    _source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    try:
        result = run_learning_batch_evidence_normalization(task_dir, task)
    except Exception as error:
        block_stage_failure(task_dir, state, str(error))
        raise WorkflowError(str(error))
    if result == "complete":
        return move_to_next_stage(task_dir, workflow, state)
    return state


def execute_learning_batch_analysis(
    root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    _source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    try:
        result = run_learning_batch_analysis(root, task_dir, task, state)
    except Exception as error:
        block_stage_failure(task_dir, state, str(error))
        raise WorkflowError(str(error))
    if result == "complete":
        return move_to_next_stage(task_dir, workflow, state)
    return state


def execute_learning_batch_analysis_normalization(
    _root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    _source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    try:
        result = run_learning_batch_analysis_normalization(task_dir, task)
    except Exception as error:
        block_stage_failure(task_dir, state, str(error))
        raise WorkflowError(str(error))
    if result == "complete":
        return move_to_next_stage(task_dir, workflow, state)
    return state


def execute_learning_batch_cross_sample_aggregation(
    root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    _source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    try:
        run_learning_batch_cross_sample_aggregation(root, task_dir, task, state)
    except Exception as error:
        block_stage_failure(task_dir, state, str(error))
        raise WorkflowError(str(error))
    return move_to_next_stage(task_dir, workflow, state)


def execute_learning_batch_mechanism_intake(
    root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    _source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    try:
        context = load_cross_sample_context(task_dir, task)
        cross_path = task_dir / "analysis" / "cross-sample-analysis.yaml"
        cross = read_json_file(cross_path)
        validate_cross_sample_analysis(cross, cross_path, context, task)
        personal_content_module.run_mock_batch_mechanism_intake(root, task_dir, task, state, cross)
    except Exception as error:
        block_stage_failure(task_dir, state, str(error))
        raise WorkflowError(str(error))
    return move_to_next_stage(task_dir, workflow, state)


def execute_learning_evidence_collection(
    root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    try:
        if not source_url:
            raise WorkflowError("learning evidence_collection requires a source URL")
        lingzao_module.collect_note(root, task_dir, task, state, source_url)
    except Exception as error:
        block_stage_failure(task_dir, state, str(error))
        raise WorkflowError(str(error))
    return move_to_next_stage(task_dir, workflow, state)


def execute_learning_evidence_normalization(
    _root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    _source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    try:
        evidence_path = task_dir / "evidence" / "evidence.yaml"
        if evidence_path.exists():
            evidence = read_json_file(evidence_path)
        else:
            evidence = normalize_lingzao_evidence(task_dir, task)
            if evidence["normalization"]["status"] == "normalization_failed":
                raise WorkflowError("normalization_failed: " + "; ".join(evidence["warnings"]))
            write_json_atomic(evidence_path, evidence)

        validate_evidence(evidence, evidence_path)
    except Exception as error:
        block_stage_failure(task_dir, state, str(error))
        raise WorkflowError(str(error))

    return move_to_next_stage(task_dir, workflow, state)


def execute_learning_analysis(
    root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    _source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    try:
        evidence_path = task_dir / "evidence" / "evidence.yaml"
        if not evidence_path.is_file():
            raise WorkflowError("Missing evidence.yaml: " + str(evidence_path))
        evidence = read_json_file(evidence_path)
        validate_evidence(evidence, evidence_path)
        ensure_evidence_is_analyzable(evidence)
        write_mock_hot_learning_raw(root, task_dir, task, state, evidence)
    except Exception as error:
        block_stage_failure(task_dir, state, str(error))
        raise WorkflowError(str(error))

    return move_to_next_stage(task_dir, workflow, state)


def execute_learning_analysis_normalization(
    _root: Path,
    task_dir: Path,
    _task: Dict[str, str],
    state: Dict[str, object],
    _source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    try:
        evidence_path = task_dir / "evidence" / "evidence.yaml"
        analysis_path = task_dir / "analysis" / "analysis.yaml"
        evidence = read_json_file(evidence_path)
        validate_evidence(evidence, evidence_path)

        if analysis_path.exists():
            analysis = read_json_file(analysis_path)
        else:
            analysis = analysis_module.normalize_hot_learning_analysis(task_dir, evidence)
            if analysis["normalization"]["status"] == "normalization_failed":
                raise WorkflowError("normalization_failed: " + "; ".join(analysis["normalization"]["warnings"]))
            write_json_atomic(analysis_path, analysis)

        analysis_module.validate_analysis(analysis, analysis_path, evidence)
    except Exception as error:
        block_stage_failure(task_dir, state, str(error))
        raise WorkflowError(str(error))

    return move_to_next_stage(task_dir, workflow, state)


def execute_learning_mechanism_intake(
    root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    _source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    try:
        evidence_path = task_dir / "evidence" / "evidence.yaml"
        analysis_path = task_dir / "analysis" / "analysis.yaml"
        if not analysis_path.is_file():
            raise WorkflowError("Missing analysis.yaml: " + str(analysis_path))

        evidence = read_json_file(evidence_path)
        validate_evidence(evidence, evidence_path)
        analysis = read_json_file(analysis_path)
        analysis_module.validate_analysis(analysis, analysis_path, evidence)
        personal_content_module.run_mock_mechanism_intake(root, task_dir, task, state, analysis)
    except Exception as error:
        block_stage_failure(task_dir, state, str(error))
        raise WorkflowError(str(error))

    return move_to_next_stage(task_dir, workflow, state)


def execute_learning_aggregation(
    _root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    _source_url: Optional[str],
    workflow: Dict[str, object],
) -> Dict[str, object]:
    try:
        evidence_path = task_dir / "evidence" / "evidence.yaml"
        analysis_path = task_dir / "analysis" / "analysis.yaml"
        intake_path = task_dir / "analysis" / "mechanism-intake-result.json"
        summary_path = task_dir / "analysis" / "learning-summary.yaml"

        evidence = read_json_file(evidence_path)
        validate_evidence(evidence, evidence_path)
        analysis = read_json_file(analysis_path)
        analysis_module.validate_analysis(analysis, analysis_path, evidence)
        intake_result = read_json_file(intake_path)
        learning_summary_module.validate_intake_result(intake_result, task)

        if summary_path.exists():
            summary = read_json_file(summary_path)
        else:
            summary = learning_summary_module.build_learning_summary(task, evidence, analysis, intake_result)
            learning_summary_module.write_json_atomic(summary_path, summary)

        learning_summary_module.validate_learning_summary(summary, summary_path, task, evidence, analysis, intake_result)
    except Exception as error:
        block_stage_failure(task_dir, state, str(error))
        raise WorkflowError(str(error))

    return move_to_next_stage(task_dir, workflow, state)


BATCH_EVIDENCE_NORMALIZATION_PROGRESS = "batch-evidence-normalization-progress.json"


def run_learning_batch_evidence_normalization(task_dir: Path, task: Dict[str, str]) -> str:
    selected_path = task_dir / "analysis" / "selected-samples.json"
    collection_path = task_dir / "analysis" / "batch-evidence-progress.json"
    progress_path = task_dir / "analysis" / BATCH_EVIDENCE_NORMALIZATION_PROGRESS

    selected = read_json_file(selected_path)
    collection_progress = read_json_file(collection_path)
    selected_samples = selected.get("selected_samples")
    if not isinstance(selected_samples, list) or not selected_samples:
        raise WorkflowError("selected_samples are required")
    validate_batch_collection_progress(collection_progress, task, selected_samples)

    if progress_path.exists():
        progress = read_json_file(progress_path)
        validate_batch_normalization_progress(progress, task, selected_samples, collection_progress)
    else:
        progress = initial_batch_normalization_progress(task, selected_samples, collection_progress)
        write_json_atomic(progress_path, progress)

    validate_batch_evidence_consistency(task_dir, selected_samples, collection_progress, progress)
    if batch_normalization_finished(progress):
        ensure_batch_normalization_has_evidence(progress)
        write_batch_evidence_index(task_dir, task, progress)
        return "complete"

    sample_state = next_pending_normalization_sample(progress)
    collection_state = collection_sample_state(collection_progress, sample_state["sample_id"])
    selected_sample = selected_sample_by_id(selected_samples, sample_state["sample_id"])
    if collection_state["status"] == "failed":
        sample_state["normalization_status"] = "skipped"
        sample_state["error"] = collection_state.get("error")
        sample_state["updated_at"] = now_iso()
        update_batch_normalization_counts(progress)
        write_json_atomic(progress_path, progress)
    else:
        normalize_one_batch_sample(task_dir, task, sample_state, selected_sample)
        update_batch_normalization_counts(progress)
        write_json_atomic(progress_path, progress)

    if batch_normalization_finished(progress):
        ensure_batch_normalization_has_evidence(progress)
        write_batch_evidence_index(task_dir, task, progress)
        return "complete"
    return "in_progress"


def initial_batch_normalization_progress(
    task: Dict[str, str],
    selected_samples: List[Dict[str, object]],
    collection_progress: Dict[str, object],
) -> Dict[str, object]:
    samples = []
    for sample in selected_samples:
        sample_id = sample["sample_id"]
        collection = collection_sample_state(collection_progress, sample_id)
        samples.append(
            {
                "sample_id": sample_id,
                "collection_status": collection["status"],
                "normalization_status": "pending",
                "evidence_path": None,
                "error": None,
                "updated_at": "",
            }
        )
    progress = {
        "task_id": task["task_id"],
        "selected_sample_ids": [sample["sample_id"] for sample in selected_samples],
        "samples": samples,
        "counts": {"pending": 0, "normalized": 0, "partially_normalized": 0, "failed": 0, "skipped": 0},
    }
    update_batch_normalization_counts(progress)
    return progress


def validate_batch_collection_progress(
    collection_progress: Dict[str, object],
    task: Dict[str, str],
    selected_samples: List[Dict[str, object]],
) -> None:
    selected_ids = [sample["sample_id"] for sample in selected_samples]
    if collection_progress.get("task_id") != task["task_id"]:
        raise WorkflowError("collection progress task_id mismatch")
    if collection_progress.get("selected_sample_ids") != selected_ids:
        raise WorkflowError("collection progress selected_sample_ids mismatch")
    samples = collection_progress.get("samples")
    if not isinstance(samples, list):
        raise WorkflowError("collection progress samples are required")
    if [item.get("sample_id") for item in samples] != selected_ids:
        raise WorkflowError("collection progress sample order mismatch")
    if any(item.get("status") in ("pending", "running") for item in samples):
        raise WorkflowError("collection progress is not complete")


def validate_batch_normalization_progress(
    progress: Dict[str, object],
    task: Dict[str, str],
    selected_samples: List[Dict[str, object]],
    collection_progress: Dict[str, object],
) -> None:
    selected_ids = [sample["sample_id"] for sample in selected_samples]
    if progress.get("task_id") != task["task_id"]:
        raise WorkflowError("normalization progress task_id mismatch")
    if progress.get("selected_sample_ids") != selected_ids:
        raise WorkflowError("normalization progress selected_sample_ids mismatch")
    samples = progress.get("samples")
    if not isinstance(samples, list) or [item.get("sample_id") for item in samples] != selected_ids:
        raise WorkflowError("normalization progress sample order mismatch")
    for item in samples:
        if item.get("collection_status") != collection_sample_state(collection_progress, item.get("sample_id")).get("status"):
            raise WorkflowError("normalization progress collection_status mismatch")
        if item.get("normalization_status") not in ("pending", "normalized", "partially_normalized", "failed", "skipped"):
            raise WorkflowError("invalid normalization status: " + str(item.get("normalization_status")))
    expected = count_batch_normalization_statuses(samples)
    if progress.get("counts") != expected:
        raise WorkflowError("normalization progress counts mismatch")


def validate_batch_evidence_consistency(
    task_dir: Path,
    selected_samples: List[Dict[str, object]],
    collection_progress: Dict[str, object],
    progress: Dict[str, object],
) -> None:
    for sample_state in progress["samples"]:
        sample_id = sample_state["sample_id"]
        selected = selected_sample_by_id(selected_samples, sample_id)
        collection = collection_sample_state(collection_progress, sample_id)
        evidence_path = task_dir / "evidence" / "samples" / sample_id / "evidence.yaml"
        if collection["status"] == "failed" and evidence_path.exists():
            raise WorkflowError("collection failed sample has evidence: " + str(sample_id))
        if collection["status"] == "succeeded":
            validate_batch_raw_matches_selection(task_dir, sample_id, selected)
        status = sample_state["normalization_status"]
        if status in ("normalized", "partially_normalized"):
            validate_existing_batch_evidence(evidence_path, sample_id, selected)
        elif status == "pending" and evidence_path.exists():
            validate_existing_batch_evidence(evidence_path, sample_id, selected)


def validate_batch_raw_matches_selection(task_dir: Path, sample_id: str, selected: Dict[str, object]) -> None:
    note_path = task_dir / "raw" / "lingzao" / "samples" / sample_id / "note-detail.json"
    invocation_path = task_dir / "raw" / "lingzao" / "samples" / sample_id / "invocation.json"
    if not note_path.is_file() or not invocation_path.is_file():
        raise WorkflowError("collection raw output is incomplete: " + sample_id)
    note = read_json_file(note_path)
    if note.get("sample_id") != sample_id:
        raise WorkflowError("raw sample_id mismatch: " + sample_id)
    source = note.get("source") or {}
    if source.get("original_url") != selected.get("url"):
        raise WorkflowError("raw source URL mismatch: " + sample_id)


def validate_existing_batch_evidence(evidence_path: Path, sample_id: str, selected: Dict[str, object]) -> Dict[str, object]:
    evidence = read_json_file(evidence_path)
    validate_evidence(evidence, evidence_path)
    if evidence.get("sample_id") != sample_id:
        raise WorkflowError("evidence sample_id mismatch: " + sample_id)
    source = evidence.get("source") or {}
    if source.get("original_url") != selected.get("url"):
        raise WorkflowError("evidence source URL mismatch: " + sample_id)
    return evidence


def normalize_one_batch_sample(
    task_dir: Path,
    task: Dict[str, str],
    sample_state: Dict[str, object],
    selected: Dict[str, object],
) -> None:
    sample_id = str(sample_state["sample_id"])
    evidence_path = task_dir / "evidence" / "samples" / sample_id / "evidence.yaml"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    if evidence_path.exists():
        evidence = validate_existing_batch_evidence(evidence_path, sample_id, selected)
    else:
        note_path = task_dir / "raw" / "lingzao" / "samples" / sample_id / "note-detail.json"
        invocation_path = task_dir / "raw" / "lingzao" / "samples" / sample_id / "invocation.json"
        evidence = normalize_lingzao_evidence_from_files(task, note_path, invocation_path, sample_id)
        if evidence["normalization"]["status"] == "normalization_failed":
            sample_state["normalization_status"] = "failed"
            sample_state["error"] = "; ".join(evidence["normalization"].get("warnings") or [])
            sample_state["updated_at"] = now_iso()
            return
        write_json_atomic(evidence_path, evidence)
        validate_evidence(evidence, evidence_path)

    sample_state["normalization_status"] = evidence["normalization"]["status"]
    sample_state["evidence_path"] = "evidence/samples/%s/evidence.yaml" % sample_id
    sample_state["error"] = None
    sample_state["updated_at"] = now_iso()


def batch_normalization_finished(progress: Dict[str, object]) -> bool:
    return progress["counts"]["pending"] == 0


def ensure_batch_normalization_has_evidence(progress: Dict[str, object]) -> None:
    if progress["counts"]["normalized"] + progress["counts"]["partially_normalized"] < 1:
        raise WorkflowError("no normalized batch evidence")


def write_batch_evidence_index(task_dir: Path, task: Dict[str, str], progress: Dict[str, object]) -> None:
    index_path = task_dir / "evidence" / "batch-evidence-index.json"
    analyzable = []
    partially = []
    skipped = []
    failed = []
    evidence_paths = {}
    warnings = []
    for item in progress["samples"]:
        sample_id = item["sample_id"]
        status = item["normalization_status"]
        if status == "normalized":
            analyzable.append(sample_id)
        elif status == "partially_normalized":
            partially.append(sample_id)
        elif status == "skipped":
            skipped.append(sample_id)
        elif status == "failed":
            failed.append(sample_id)
        if item.get("evidence_path"):
            evidence_paths[sample_id] = item["evidence_path"]
            evidence = read_json_file(task_dir / str(item["evidence_path"]))
            warnings.extend(evidence.get("warnings") or [])
        elif item.get("error"):
            warnings.append(str(item["error"]))
    payload = {
        "task_id": task["task_id"],
        "selected_sample_ids": progress["selected_sample_ids"],
        "analyzable_samples": analyzable,
        "partially_analyzable_samples": partially,
        "skipped_samples": skipped,
        "failed_samples": failed,
        "evidence_paths": evidence_paths,
        "warnings": warnings,
    }
    write_json_atomic(index_path, payload)


def next_pending_normalization_sample(progress: Dict[str, object]) -> Dict[str, object]:
    for item in progress["samples"]:
        if item["normalization_status"] == "pending":
            return item
    raise WorkflowError("no pending normalization samples")


def collection_sample_state(collection_progress: Dict[str, object], sample_id: object) -> Dict[str, object]:
    for item in collection_progress.get("samples") or []:
        if item.get("sample_id") == sample_id:
            return item
    raise WorkflowError("collection sample not found: " + str(sample_id))


def selected_sample_by_id(selected_samples: List[Dict[str, object]], sample_id: object) -> Dict[str, object]:
    for item in selected_samples:
        if item.get("sample_id") == sample_id:
            return item
    raise WorkflowError("selected sample not found: " + str(sample_id))


def update_batch_normalization_counts(progress: Dict[str, object]) -> None:
    progress["counts"] = count_batch_normalization_statuses(progress["samples"])


def count_batch_normalization_statuses(samples: List[Dict[str, object]]) -> Dict[str, int]:
    counts = {"pending": 0, "normalized": 0, "partially_normalized": 0, "failed": 0, "skipped": 0}
    for item in samples:
        counts[str(item["normalization_status"])] += 1
    return counts


BATCH_ANALYSIS_PROGRESS = "batch-analysis-progress.json"
BATCH_ANALYSIS_NORMALIZATION_PROGRESS = "batch-analysis-normalization-progress.json"


def run_learning_batch_analysis(root: Path, task_dir: Path, task: Dict[str, str], state: Dict[str, object]) -> str:
    prompt_path = root / "prompts" / "hot-learning-analysis-only.md"
    if not prompt_path.is_file():
        raise WorkflowError("Missing prompt: prompts/hot-learning-analysis-only.md")
    index_path = task_dir / "evidence" / "batch-evidence-index.json"
    index = read_json_file(index_path)
    progress_path = task_dir / "analysis" / BATCH_ANALYSIS_PROGRESS

    if progress_path.exists():
        progress = read_json_file(progress_path)
        validate_batch_analysis_progress(progress, task, task_dir, index)
    else:
        progress = initial_batch_analysis_progress(task, index)
        write_json_atomic(progress_path, progress)

    validate_batch_analysis_inputs(task_dir, progress, index)
    validate_batch_analysis_raw_consistency(task_dir, progress)
    if batch_analysis_finished(progress):
        ensure_batch_analysis_has_success(progress)
        return "complete"

    sample_state = next_pending_analysis_sample(progress)
    if sample_state["evidence_status"] == "skipped":
        sample_state["analysis_status"] = "skipped"
        sample_state["error"] = "Evidence is not analyzable"
        sample_state["updated_at"] = now_iso()
        update_batch_analysis_counts(progress)
        write_json_atomic(progress_path, progress)
    else:
        analyze_one_batch_sample(task_dir, task, state, sample_state, index)
        update_batch_analysis_counts(progress)
        write_json_atomic(progress_path, progress)

    if batch_analysis_finished(progress):
        ensure_batch_analysis_has_success(progress)
        return "complete"
    return "in_progress"


def initial_batch_analysis_progress(task: Dict[str, str], index: Dict[str, object]) -> Dict[str, object]:
    sample_ids = batch_analysis_sample_ids(index)
    samples = []
    for sample_id in sample_ids:
        evidence_path = (index.get("evidence_paths") or {}).get(sample_id, "")
        evidence_status = "skipped" if not evidence_path else evidence_status_for_index(index, sample_id)
        samples.append(
            {
                "sample_id": sample_id,
                "evidence_status": evidence_status,
                "analysis_status": "pending",
                "evidence_path": evidence_path,
                "raw_analysis_dir": "raw/hot-learning/samples/" + sample_id,
                "error": None,
                "updated_at": "",
            }
        )
    progress = {
        "task_id": task["task_id"],
        "sample_ids": sample_ids,
        "samples": samples,
        "counts": {"pending": 0, "succeeded": 0, "failed": 0, "skipped": 0},
    }
    update_batch_analysis_counts(progress)
    return progress


def batch_analysis_sample_ids(index: Dict[str, object]) -> List[str]:
    ids = []
    for key in ("analyzable_samples", "partially_analyzable_samples", "skipped_samples", "failed_samples"):
        for sample_id in index.get(key) or []:
            if sample_id not in ids:
                ids.append(sample_id)
    return ids


def evidence_status_for_index(index: Dict[str, object], sample_id: str) -> str:
    if sample_id in (index.get("analyzable_samples") or []):
        return "normalized"
    if sample_id in (index.get("partially_analyzable_samples") or []):
        return "partially_normalized"
    return "skipped"


def validate_batch_analysis_progress(progress: Dict[str, object], task: Dict[str, str], task_dir: Path, index: Dict[str, object]) -> None:
    expected_ids = batch_analysis_sample_ids(index)
    if progress.get("task_id") != task["task_id"]:
        raise WorkflowError("batch analysis progress task_id mismatch")
    if progress.get("sample_ids") != expected_ids:
        raise WorkflowError("batch analysis progress sample_ids mismatch")
    samples = progress.get("samples")
    if not isinstance(samples, list) or [item.get("sample_id") for item in samples] != expected_ids:
        raise WorkflowError("batch analysis progress sample order mismatch")
    for item in samples:
        if item.get("analysis_status") not in ("pending", "succeeded", "failed", "skipped"):
            raise WorkflowError("invalid batch analysis status: " + str(item.get("analysis_status")))
        if item.get("evidence_status") != evidence_status_for_index(index, item.get("sample_id")):
            raise WorkflowError("batch analysis evidence_status mismatch")
        evidence_path = item.get("evidence_path")
        if evidence_path:
            validate_batch_analysis_evidence(task_dir, item, index)
    expected_counts = count_batch_analysis_statuses(samples)
    if progress.get("counts") != expected_counts:
        raise WorkflowError("batch analysis counts mismatch")


def validate_batch_analysis_inputs(task_dir: Path, progress: Dict[str, object], index: Dict[str, object]) -> None:
    for item in progress["samples"]:
        if item.get("evidence_path"):
            validate_batch_analysis_evidence(task_dir, item, index)


def validate_batch_analysis_evidence(task_dir: Path, sample_state: Dict[str, object], index: Dict[str, object]) -> Dict[str, object]:
    sample_id = str(sample_state["sample_id"])
    evidence_path = task_dir / str(sample_state["evidence_path"])
    evidence = read_json_file(evidence_path)
    validate_evidence(evidence, evidence_path)
    ensure_evidence_is_analyzable(evidence)
    if evidence.get("sample_id") != sample_id:
        raise WorkflowError("evidence sample_id mismatch: " + sample_id)
    source = evidence.get("source") or {}
    indexed_urls = index.get("evidence_urls") or {}
    if sample_id in indexed_urls and indexed_urls[sample_id] != source.get("original_url"):
        raise WorkflowError("index source URL mismatch: " + sample_id)
    return evidence


def validate_batch_analysis_raw_consistency(task_dir: Path, progress: Dict[str, object]) -> None:
    for item in progress["samples"]:
        raw_dir = task_dir / str(item["raw_analysis_dir"])
        analysis_path = raw_dir / "analysis.md"
        invocation_path = raw_dir / "invocation.json"
        has_analysis = analysis_path.exists()
        has_invocation = invocation_path.exists()
        if item["analysis_status"] == "succeeded" and not (has_analysis and has_invocation):
            raise WorkflowError("succeeded analysis raw output is incomplete: " + str(item["sample_id"]))
        if item["analysis_status"] == "pending" and (has_analysis or has_invocation):
            raise WorkflowError("Incomplete raw hot-learning output exists")


def analyze_one_batch_sample(
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    sample_state: Dict[str, object],
    index: Dict[str, object],
) -> None:
    sample_id = str(sample_state["sample_id"])
    try:
        evidence = validate_batch_analysis_evidence(task_dir, sample_state, index)
        write_mock_hot_learning_raw_to_dir(
            raw_dir=task_dir / str(sample_state["raw_analysis_dir"]),
            task=task,
            state=state,
            evidence=evidence,
            evidence_path=str(sample_state["evidence_path"]),
            output_path=str(sample_state["raw_analysis_dir"]) + "/analysis.md",
        )
        sample_state["analysis_status"] = "succeeded"
        sample_state["error"] = None
    except Exception as error:
        sample_state["analysis_status"] = "failed"
        sample_state["error"] = str(error)
    sample_state["updated_at"] = now_iso()


def batch_analysis_finished(progress: Dict[str, object]) -> bool:
    return progress["counts"]["pending"] == 0


def ensure_batch_analysis_has_success(progress: Dict[str, object]) -> None:
    if progress["counts"]["succeeded"] < 1:
        raise WorkflowError("all batch analyses failed or skipped")


def next_pending_analysis_sample(progress: Dict[str, object]) -> Dict[str, object]:
    for item in progress["samples"]:
        if item["analysis_status"] == "pending":
            return item
    raise WorkflowError("no pending batch analysis samples")


def update_batch_analysis_counts(progress: Dict[str, object]) -> None:
    progress["counts"] = count_batch_analysis_statuses(progress["samples"])


def count_batch_analysis_statuses(samples: List[Dict[str, object]]) -> Dict[str, int]:
    counts = {"pending": 0, "succeeded": 0, "failed": 0, "skipped": 0}
    for item in samples:
        counts[str(item["analysis_status"])] += 1
    return counts


def run_learning_batch_analysis_normalization(task_dir: Path, task: Dict[str, str]) -> str:
    evidence_index_path = task_dir / "evidence" / "batch-evidence-index.json"
    raw_progress_path = task_dir / "analysis" / BATCH_ANALYSIS_PROGRESS
    progress_path = task_dir / "analysis" / BATCH_ANALYSIS_NORMALIZATION_PROGRESS

    evidence_index = read_json_file(evidence_index_path)
    raw_progress = read_json_file(raw_progress_path)
    validate_batch_analysis_progress(raw_progress, task, task_dir, evidence_index)

    if progress_path.exists():
        progress = read_json_file(progress_path)
        validate_batch_analysis_normalization_progress(progress, task, task_dir, raw_progress, evidence_index)
    else:
        progress = initial_batch_analysis_normalization_progress(task, raw_progress)
        write_json_atomic(progress_path, progress)

    validate_batch_analysis_normalization_inputs(task_dir, progress, raw_progress, evidence_index)
    if batch_analysis_normalization_finished(progress):
        ensure_batch_analysis_normalization_has_analysis(progress)
        write_batch_analysis_index(task_dir, task, progress)
        return "complete"

    sample_state = next_pending_analysis_normalization_sample(progress)
    normalize_one_batch_analysis_sample(task_dir, sample_state, raw_progress, evidence_index)
    update_batch_analysis_normalization_counts(progress)
    write_json_atomic(progress_path, progress)

    if batch_analysis_normalization_finished(progress):
        ensure_batch_analysis_normalization_has_analysis(progress)
        write_batch_analysis_index(task_dir, task, progress)
        return "complete"
    return "in_progress"


def initial_batch_analysis_normalization_progress(task: Dict[str, str], raw_progress: Dict[str, object]) -> Dict[str, object]:
    sample_ids = list(raw_progress.get("sample_ids") or [])
    samples = []
    for raw_item in raw_progress.get("samples") or []:
        sample_id = str(raw_item.get("sample_id"))
        raw_status = str(raw_item.get("analysis_status"))
        analysis_path = "analysis/samples/%s/analysis.yaml" % sample_id if raw_status == "succeeded" else None
        samples.append(
            {
                "sample_id": sample_id,
                "raw_analysis_status": raw_status,
                "normalization_status": "pending",
                "raw_analysis_dir": raw_item.get("raw_analysis_dir"),
                "raw_analysis_path": str(raw_item.get("raw_analysis_dir")) + "/analysis.md" if raw_item.get("raw_analysis_dir") else "",
                "evidence_path": raw_item.get("evidence_path"),
                "analysis_path": analysis_path,
                "error": None,
                "updated_at": "",
            }
        )
    progress = {
        "task_id": task["task_id"],
        "sample_ids": sample_ids,
        "samples": samples,
        "counts": {"pending": 0, "normalized": 0, "partially_normalized": 0, "failed": 0, "skipped": 0},
    }
    update_batch_analysis_normalization_counts(progress)
    return progress


def validate_batch_analysis_normalization_progress(
    progress: Dict[str, object],
    task: Dict[str, str],
    task_dir: Path,
    raw_progress: Dict[str, object],
    evidence_index: Dict[str, object],
) -> None:
    expected_ids = list(raw_progress.get("sample_ids") or [])
    if progress.get("task_id") != task["task_id"]:
        raise WorkflowError("batch analysis normalization progress task_id mismatch")
    if progress.get("sample_ids") != expected_ids:
        raise WorkflowError("batch analysis normalization progress sample_ids mismatch")
    samples = progress.get("samples")
    if not isinstance(samples, list) or [item.get("sample_id") for item in samples] != expected_ids:
        raise WorkflowError("batch analysis normalization progress sample order mismatch")
    for item in samples:
        sample_id = str(item.get("sample_id"))
        raw_item = raw_analysis_sample_state(raw_progress, sample_id)
        if item.get("raw_analysis_status") != raw_item.get("analysis_status"):
            raise WorkflowError("raw analysis status mismatch: " + sample_id)
        if item.get("raw_analysis_dir") != raw_item.get("raw_analysis_dir"):
            raise WorkflowError("raw analysis dir mismatch: " + sample_id)
        if item.get("evidence_path") != raw_item.get("evidence_path"):
            raise WorkflowError("analysis progress evidence_path mismatch: " + sample_id)
        status = item.get("normalization_status")
        if status not in ("pending", "normalized", "partially_normalized", "failed", "skipped"):
            raise WorkflowError("invalid batch analysis normalization status: " + str(status))
        if status in ("normalized", "partially_normalized"):
            validate_existing_batch_analysis_package(task_dir, item, evidence_index)
    expected_counts = count_batch_analysis_normalization_statuses(samples)
    if progress.get("counts") != expected_counts:
        raise WorkflowError("batch analysis normalization counts mismatch")


def validate_batch_analysis_normalization_inputs(
    task_dir: Path,
    progress: Dict[str, object],
    raw_progress: Dict[str, object],
    evidence_index: Dict[str, object],
) -> None:
    selected_ids = evidence_index.get("selected_sample_ids")
    if selected_ids != raw_progress.get("sample_ids"):
        raise WorkflowError("selected samples and analysis progress mismatch")
    validate_batch_analysis_raw_consistency(task_dir, raw_progress)
    for item in progress["samples"]:
        raw_item = raw_analysis_sample_state(raw_progress, item["sample_id"])
        if item.get("raw_analysis_status") != raw_item.get("analysis_status"):
            raise WorkflowError("raw analysis status mismatch: " + str(item["sample_id"]))
        if raw_item.get("analysis_status") == "succeeded":
            validate_batch_analysis_normalization_source(task_dir, item, raw_item, evidence_index)


def validate_batch_analysis_normalization_source(
    task_dir: Path,
    sample_state: Dict[str, object],
    raw_item: Dict[str, object],
    evidence_index: Dict[str, object],
) -> Dict[str, object]:
    sample_id = str(sample_state["sample_id"])
    if sample_state.get("evidence_path") != raw_item.get("evidence_path"):
        raise WorkflowError("analysis progress evidence_path mismatch: " + sample_id)
    expected_evidence_path = (evidence_index.get("evidence_paths") or {}).get(sample_id)
    if expected_evidence_path != sample_state.get("evidence_path"):
        raise WorkflowError("analysis progress evidence_path mismatch: " + sample_id)

    evidence_path = task_dir / str(sample_state["evidence_path"])
    evidence = read_json_file(evidence_path)
    validate_evidence(evidence, evidence_path)
    if evidence.get("sample_id") != sample_id:
        raise WorkflowError("evidence sample_id mismatch: " + sample_id)

    raw_dir = task_dir / str(sample_state["raw_analysis_dir"])
    analysis_md = raw_dir / "analysis.md"
    invocation_path = raw_dir / "invocation.json"
    if not analysis_md.is_file() or not invocation_path.is_file():
        raise WorkflowError("raw analysis output is incomplete: " + sample_id)
    invocation = read_json_file(invocation_path)
    if invocation.get("sample_id") != sample_id:
        raise WorkflowError("raw analysis sample_id mismatch: " + sample_id)
    if invocation.get("evidence_path") != sample_state.get("evidence_path"):
        raise WorkflowError("raw analysis evidence_path mismatch: " + sample_id)
    return evidence


def normalize_one_batch_analysis_sample(
    task_dir: Path,
    sample_state: Dict[str, object],
    raw_progress: Dict[str, object],
    evidence_index: Dict[str, object],
) -> None:
    sample_id = str(sample_state["sample_id"])
    raw_item = raw_analysis_sample_state(raw_progress, sample_id)
    raw_status = raw_item.get("analysis_status")
    if raw_status in ("failed", "skipped"):
        sample_state["normalization_status"] = "skipped"
        sample_state["error"] = raw_item.get("error") or "raw analysis was " + str(raw_status)
        sample_state["updated_at"] = now_iso()
        return

    try:
        evidence = validate_batch_analysis_normalization_source(task_dir, sample_state, raw_item, evidence_index)
        analysis_path = task_dir / str(sample_state["analysis_path"])
        analysis_path.parent.mkdir(parents=True, exist_ok=True)
        raw_analysis_ref_file = str(sample_state["raw_analysis_path"])

        if analysis_path.exists():
            analysis = read_json_file(analysis_path)
        else:
            analysis = analysis_module.normalize_hot_learning_analysis_from_files(
                markdown_path=task_dir / str(sample_state["raw_analysis_path"]),
                invocation_path=task_dir / str(sample_state["raw_analysis_dir"]) / "invocation.json",
                evidence=evidence,
                raw_analysis_ref_file=raw_analysis_ref_file,
            )
            if analysis["normalization"]["status"] == "normalization_failed":
                sample_state["normalization_status"] = "failed"
                sample_state["error"] = "; ".join(analysis["normalization"].get("warnings") or [])
                sample_state["updated_at"] = now_iso()
                return
            write_json_atomic(analysis_path, analysis)

        analysis_module.validate_analysis(analysis, analysis_path, evidence, expected_raw_analysis_file=raw_analysis_ref_file)
        status = (analysis.get("normalization") or {}).get("status")
        sample_state["normalization_status"] = status
        sample_state["error"] = None
    except Exception as error:
        sample_state["normalization_status"] = "failed"
        sample_state["error"] = str(error)
    sample_state["updated_at"] = now_iso()


def validate_existing_batch_analysis_package(
    task_dir: Path,
    sample_state: Dict[str, object],
    evidence_index: Dict[str, object],
) -> Dict[str, object]:
    evidence = validate_batch_analysis_normalization_source(
        task_dir,
        sample_state,
        {
            "sample_id": sample_state["sample_id"],
            "analysis_status": sample_state["raw_analysis_status"],
            "raw_analysis_dir": sample_state["raw_analysis_dir"],
            "evidence_path": sample_state["evidence_path"],
        },
        evidence_index,
    )
    analysis_path = task_dir / str(sample_state["analysis_path"])
    analysis = read_json_file(analysis_path)
    analysis_module.validate_analysis(
        analysis,
        analysis_path,
        evidence,
        expected_raw_analysis_file=str(sample_state["raw_analysis_path"]),
    )
    return analysis


def raw_analysis_sample_state(raw_progress: Dict[str, object], sample_id: object) -> Dict[str, object]:
    for item in raw_progress.get("samples") or []:
        if item.get("sample_id") == sample_id:
            return item
    raise WorkflowError("raw analysis sample not found: " + str(sample_id))


def batch_analysis_normalization_finished(progress: Dict[str, object]) -> bool:
    return progress["counts"]["pending"] == 0


def ensure_batch_analysis_normalization_has_analysis(progress: Dict[str, object]) -> None:
    if progress["counts"]["normalized"] + progress["counts"]["partially_normalized"] < 1:
        errors = [str(item.get("error")) for item in progress["samples"] if item.get("error")]
        detail = ": " + "; ".join(errors) if errors else ""
        raise WorkflowError("no normalized batch analysis" + detail)


def next_pending_analysis_normalization_sample(progress: Dict[str, object]) -> Dict[str, object]:
    for item in progress["samples"]:
        if item["normalization_status"] == "pending":
            return item
    raise WorkflowError("no pending batch analysis normalization samples")


def update_batch_analysis_normalization_counts(progress: Dict[str, object]) -> None:
    progress["counts"] = count_batch_analysis_normalization_statuses(progress["samples"])


def count_batch_analysis_normalization_statuses(samples: List[Dict[str, object]]) -> Dict[str, int]:
    counts = {"pending": 0, "normalized": 0, "partially_normalized": 0, "failed": 0, "skipped": 0}
    for item in samples:
        counts[str(item["normalization_status"])] += 1
    return counts


def write_batch_analysis_index(task_dir: Path, task: Dict[str, str], progress: Dict[str, object]) -> None:
    index_path = task_dir / "analysis" / "batch-analysis-index.json"
    normalized = []
    partially = []
    skipped = []
    failed = []
    analysis_paths = {}
    warnings = []
    for item in progress["samples"]:
        sample_id = item["sample_id"]
        status = item["normalization_status"]
        if status == "normalized":
            normalized.append(sample_id)
        elif status == "partially_normalized":
            partially.append(sample_id)
        elif status == "skipped":
            skipped.append(sample_id)
        elif status == "failed":
            failed.append(sample_id)

        if status in ("normalized", "partially_normalized"):
            analysis_paths[sample_id] = item["analysis_path"]
            analysis = read_json_file(task_dir / str(item["analysis_path"]))
            warnings.extend((analysis.get("normalization") or {}).get("warnings") or [])
        elif item.get("error"):
            warnings.append(str(item["error"]))

    payload = {
        "task_id": task["task_id"],
        "selected_sample_ids": progress["sample_ids"],
        "normalized_analyses": normalized,
        "partially_normalized_analyses": partially,
        "skipped_samples": skipped,
        "failed_samples": failed,
        "analysis_paths": analysis_paths,
        "warnings": warnings,
    }
    write_json_atomic(index_path, payload)


def run_learning_batch_cross_sample_aggregation(
    root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
) -> None:
    prompt_path = root / "prompts" / "hot-learning-cross-sample.md"
    if not prompt_path.is_file():
        raise WorkflowError("Missing prompt: prompts/hot-learning-cross-sample.md")

    raw_markdown_path = task_dir / "raw" / "hot-learning" / "cross-sample-analysis.md"
    invocation_path = task_dir / "raw" / "hot-learning" / "cross-sample-invocation.json"
    cross_path = task_dir / "analysis" / "cross-sample-analysis.yaml"
    artifacts = (raw_markdown_path, invocation_path, cross_path)
    existing_count = sum(1 for path in artifacts if path.exists())
    if existing_count not in (0, 3):
        raise WorkflowError("Incomplete cross-sample aggregation artifacts")

    context = load_cross_sample_context(task_dir, task)
    if len(context["sample_ids"]) < 2:
        raise WorkflowError("cross_sample_aggregation requires at least 2 available samples")

    if existing_count == 3:
        cross = read_json_file(cross_path)
        validate_cross_sample_analysis(cross, cross_path, context, task)
        return

    cross = build_cross_sample_analysis(task, context)
    markdown = render_cross_sample_markdown(cross, context)
    invocation = {
        "adapter": "mock_hot_learning_cross_sample",
        "mock": True,
        "task_id": task.get("task_id", ""),
        "task_type": task.get("task_type", ""),
        "stage": state.get("current_stage", ""),
        "sample_ids": context["sample_ids"],
        "analysis_index_path": "analysis/batch-analysis-index.json",
        "prompt_path": "prompts/hot-learning-cross-sample.md",
        "executed_at": now_iso(),
        "outputs": [
            "raw/hot-learning/cross-sample-analysis.md",
            "analysis/cross-sample-analysis.yaml",
        ],
        "allowed_actions": [
            "compare standardized analysis packages",
            "identify candidate repeated mechanisms",
            "write raw markdown cross-sample analysis",
            "write candidate-only cross-sample analysis package",
        ],
        "forbidden_actions": [
            "create formal mechanisms",
            "create rule cards",
            "create content assets",
            "approve governance decisions",
            "generate posts",
            "modify sample analysis packages",
            "modify evidence packages",
            "call Personal Content",
        ],
    }
    validate_cross_sample_analysis(cross, cross_path, context, task, require_file=False)

    wrote = []
    try:
        write_text_atomic(raw_markdown_path, markdown)
        wrote.append(raw_markdown_path)
        write_json_atomic(invocation_path, invocation)
        wrote.append(invocation_path)
        write_json_atomic(cross_path, cross)
        wrote.append(cross_path)
        validate_cross_sample_analysis(cross, cross_path, context, task)
    except Exception as error:
        for path in wrote:
            if path.exists():
                path.unlink()
        raise WorkflowError("Failed to write cross-sample aggregation output: " + str(error))


def load_cross_sample_context(task_dir: Path, task: Dict[str, str]) -> Dict[str, object]:
    analysis_index_path = task_dir / "analysis" / "batch-analysis-index.json"
    evidence_index_path = task_dir / "evidence" / "batch-evidence-index.json"
    analysis_index = read_json_file(analysis_index_path)
    evidence_index = read_json_file(evidence_index_path)
    if analysis_index.get("task_id") != task["task_id"]:
        raise WorkflowError("batch analysis index task_id mismatch")
    if evidence_index.get("task_id") != task["task_id"]:
        raise WorkflowError("batch evidence index task_id mismatch")
    sample_ids = list(analysis_index.get("normalized_analyses") or []) + list(analysis_index.get("partially_normalized_analyses") or [])
    sample_ids = dedupe_preserving_order(sample_ids)
    analyses = {}
    evidence = {}
    for sample_id in sample_ids:
        analysis_rel = (analysis_index.get("analysis_paths") or {}).get(sample_id)
        evidence_rel = (evidence_index.get("evidence_paths") or {}).get(sample_id)
        if not analysis_rel:
            raise WorkflowError("missing analysis path for sample: " + sample_id)
        if not evidence_rel:
            raise WorkflowError("missing evidence path for sample: " + sample_id)
        analysis_path = task_dir / str(analysis_rel)
        evidence_path = task_dir / str(evidence_rel)
        sample_analysis = read_json_file(analysis_path)
        sample_evidence = read_json_file(evidence_path)
        validate_evidence(sample_evidence, evidence_path)
        if sample_evidence.get("sample_id") != sample_id:
            raise WorkflowError("evidence sample_id mismatch: " + sample_id)
        expected_raw = "raw/hot-learning/samples/%s/analysis.md" % sample_id
        analysis_module.validate_analysis(sample_analysis, analysis_path, sample_evidence, expected_raw_analysis_file=expected_raw)
        if sample_analysis.get("sample_id") != sample_id:
            raise WorkflowError("analysis sample_id mismatch: " + sample_id)
        analyses[sample_id] = sample_analysis
        evidence[sample_id] = sample_evidence
    return {
        "analysis_index": analysis_index,
        "evidence_index": evidence_index,
        "sample_ids": sample_ids,
        "analyses": analyses,
        "evidence": evidence,
    }


def dedupe_preserving_order(values: Iterable[str]) -> List[str]:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def build_cross_sample_analysis(task: Dict[str, str], context: Dict[str, object]) -> Dict[str, object]:
    groups: Dict[str, List[Tuple[str, int, Dict[str, object]]]] = {}
    for sample_id in context["sample_ids"]:
        for index, mechanism in enumerate((context["analyses"][sample_id].get("mechanisms") or [])):
            key = mechanism_group_key(mechanism)
            groups.setdefault(key, []).append((sample_id, index, mechanism))

    candidates = []
    unmatched = []
    warnings = []
    for group_items in groups.values():
        support_samples = dedupe_preserving_order(item[0] for item in group_items)
        if len(support_samples) >= 2:
            candidates.append(build_cross_sample_candidate(len(candidates) + 1, group_items, context))
        else:
            sample_id, index, mechanism = group_items[0]
            unmatched.append(
                {
                    "sample_id": sample_id,
                    "mechanism_id": str(mechanism.get("id", "")),
                    "analysis_ref": mechanism_analysis_ref(sample_id, index),
                    "reason": "No deterministic match in another sample",
                }
            )

    if not candidates:
        warnings.append("No repeated mechanism candidate found with deterministic grouping")

    return {
        "task_id": task["task_id"],
        "aggregation_id": "cross-" + task["task_id"],
        "sample_ids": context["sample_ids"],
        "normalization": {"status": "normalized" if candidates else "partially_normalized", "warnings": warnings},
        "mechanism_candidates": candidates,
        "unmatched_mechanisms": unmatched,
        "cross_sample_patterns": build_cross_sample_patterns(candidates),
        "rule_suggestions": aggregate_unique_list(context, "rule_suggestions"),
        "asset_suggestions": aggregate_unique_list(context, "asset_suggestions"),
        "content_opportunities": aggregate_unique_list(context, "content_opportunities"),
        "questions": aggregate_unique_list(context, "questions"),
    }


def mechanism_group_key(mechanism: Dict[str, object]) -> str:
    name = str(mechanism.get("name") or "").lower()
    cleaned = "".join(char for char in name if char.isalnum())
    if cleaned:
        return cleaned
    description = str(mechanism.get("description") or "").lower()
    return "".join(char for char in description if char.isalnum())[:48]


def build_cross_sample_candidate(
    candidate_index: int,
    group_items: List[Tuple[str, int, Dict[str, object]]],
    context: Dict[str, object],
) -> Dict[str, object]:
    first_mechanism = group_items[0][2]
    supporting_samples = dedupe_preserving_order(item[0] for item in group_items)
    member_mechanisms = []
    observed_facts = []
    inferences = []
    counter_evidence = []
    differences = []
    limitations = []
    alternatives = []
    descriptions = []

    for sample_id, mechanism_index, mechanism in group_items:
        analysis_ref = mechanism_analysis_ref(sample_id, mechanism_index)
        member_mechanisms.append(
            {
                "sample_id": sample_id,
                "mechanism_id": str(mechanism.get("id", "")),
                "analysis_ref": analysis_ref,
            }
        )
        descriptions.append(str(mechanism.get("description") or ""))
        for fact in mechanism.get("observed_facts") or []:
            observed_facts.append(
                {
                    "sample_id": sample_id,
                    "text": str(fact.get("text") or ""),
                    "evidence_ref": str(fact.get("evidence_ref") or ""),
                    "analysis_ref": analysis_ref,
                }
            )
        for inference in mechanism.get("inferences") or []:
            inferences.append(
                {
                    "sample_id": sample_id,
                    "text": str(inference.get("text") or ""),
                    "analysis_ref": analysis_ref,
                    "raw_analysis_ref": inference.get("raw_analysis_ref") or {},
                }
            )
        for alternative in mechanism.get("alternative_explanations") or []:
            alternative_text = str(alternative)
            alternatives.append(alternative_text)
            if "CONFLICT" in alternative_text or "conflict" in alternative_text.lower():
                counter_evidence.append(
                    {
                        "sample_id": sample_id,
                        "text": alternative_text,
                        "analysis_ref": analysis_ref,
                    }
                )
        evidence = context["evidence"][sample_id]
        if (evidence.get("normalization") or {}).get("status") == "partially_normalized":
            limitations.append({"sample_id": sample_id, "text": "Evidence is partially normalized"})

    unique_descriptions = dedupe_preserving_order(descriptions)
    if len(unique_descriptions) > 1:
        for description in unique_descriptions:
            differences.append({"text": description})
    else:
        differences.append({"text": "No major description difference detected by deterministic mock comparison"})

    confidence, basis = cross_sample_confidence(supporting_samples, context, counter_evidence)
    return {
        "candidate_id": "cross-mechanism-%03d" % candidate_index,
        "name": str(first_mechanism.get("name") or ""),
        "description": "Candidate repeated mechanism observed across samples: " + str(first_mechanism.get("description") or ""),
        "member_mechanisms": member_mechanisms,
        "supporting_samples": supporting_samples,
        "support_count": len(supporting_samples),
        "observed_facts": observed_facts,
        "inferences": inferences,
        "counter_evidence": counter_evidence,
        "differences": differences,
        "applicable_scope": dedupe_preserving_order(flatten_mechanism_list(group_items, "applicable_scope")),
        "limitations": limitations,
        "alternative_explanations": dedupe_preserving_order(alternatives),
        "confidence": confidence,
        "confidence_basis": basis,
        "merge_recommendation": "candidate",
    }


def cross_sample_confidence(
    supporting_samples: List[str],
    context: Dict[str, object],
    counter_evidence: List[Dict[str, object]],
) -> Tuple[str, List[str]]:
    basis = ["support_count=%d" % len(supporting_samples)]
    has_partial = False
    for sample_id in supporting_samples:
        analysis_status = ((context["analyses"][sample_id].get("normalization") or {}).get("status"))
        evidence_status = ((context["evidence"][sample_id].get("normalization") or {}).get("status"))
        if analysis_status == "partially_normalized" or evidence_status == "partially_normalized":
            has_partial = True
    if has_partial:
        basis.append("partial evidence or analysis limits confidence")
    if counter_evidence:
        basis.append("counter evidence prevents high confidence")
    if len(supporting_samples) >= 3 and not has_partial and not counter_evidence:
        return "high", basis
    if len(supporting_samples) >= 2 and not counter_evidence and not has_partial:
        return "medium", basis
    return "low", basis


def flatten_mechanism_list(group_items: List[Tuple[str, int, Dict[str, object]]], field: str) -> List[str]:
    values = []
    for _sample_id, _index, mechanism in group_items:
        for item in mechanism.get(field) or []:
            values.append(str(item))
    return values


def build_cross_sample_patterns(candidates: List[Dict[str, object]]) -> List[Dict[str, object]]:
    return [
        {
            "candidate_id": candidate["candidate_id"],
            "name": candidate["name"],
            "supporting_samples": candidate["supporting_samples"],
            "status": "candidate",
        }
        for candidate in candidates
    ]


def aggregate_unique_list(context: Dict[str, object], field: str) -> List[str]:
    values = []
    for sample_id in context["sample_ids"]:
        for item in context["analyses"][sample_id].get(field) or []:
            text = str(item)
            if text not in values:
                values.append(text)
    return values


def mechanism_analysis_ref(sample_id: str, mechanism_index: int) -> str:
    return "%s:analysis.yaml#mechanisms[%d]" % (sample_id, mechanism_index)


def render_cross_sample_markdown(cross: Dict[str, object], context: Dict[str, object]) -> str:
    lines = [
        "# Mock Hot Learning Cross-Sample Raw Analysis",
        "",
        "## Input Samples",
    ]
    for sample_id in cross["sample_ids"]:
        lines.append("- %s: analysis.yaml and evidence.yaml" % sample_id)
    lines.extend(["", "## Per Sample Mechanism Summary"])
    for sample_id in cross["sample_ids"]:
        analysis = context["analyses"][sample_id]
        for index, mechanism in enumerate(analysis.get("mechanisms") or []):
            lines.append("- %s: analysis.yaml#mechanisms[%d] %s" % (sample_id, index, mechanism.get("name", "")))
    lines.extend(["", "## Repeated Mechanism Candidates"])
    for candidate in cross["mechanism_candidates"]:
        lines.append("### %s: %s" % (candidate["candidate_id"], candidate["name"]))
        lines.append("- Support: " + ", ".join(candidate["supporting_samples"]))
        lines.append("- Confidence: " + candidate["confidence"])
        for member in candidate["member_mechanisms"]:
            lines.append("- Member: %s" % member["analysis_ref"])
        for fact in candidate["observed_facts"][:2]:
            lines.append("- Supporting evidence: %s: %s" % (fact["sample_id"], fact["evidence_ref"]))
        for sample_id in candidate["supporting_samples"]:
            lines.append("- Metric reference: %s: evidence.yaml#facts.metrics.likes" % sample_id)
        for counter in candidate["counter_evidence"]:
            lines.append("- Counter evidence: %s: %s" % (counter["sample_id"], counter["text"]))
        for difference in candidate["differences"]:
            lines.append("- Difference: " + str(difference.get("text", "")))
        lines.append("- Merge recommendation: candidate only, not formal.")
    lines.extend(["", "## Unmatched Mechanisms"])
    for item in cross["unmatched_mechanisms"]:
        lines.append("- %s because %s" % (item["analysis_ref"], item["reason"]))
    lines.extend(["", "## Rule Direction Suggestions"])
    for item in cross["rule_suggestions"]:
        lines.append("- " + str(item))
    lines.extend(["", "## Asset Direction Suggestions"])
    for item in cross["asset_suggestions"]:
        lines.append("- " + str(item))
    lines.extend(["", "## Content Opportunities"])
    for item in cross["content_opportunities"]:
        lines.append("- " + str(item))
    lines.extend(["", "## Missing Information And Questions"])
    for item in cross["questions"]:
        lines.append("- " + str(item))
    if not cross["questions"]:
        lines.append("- More real samples are needed before formal mechanism merge.")
    return "\n".join(lines) + "\n"


def validate_cross_sample_analysis(
    cross: Dict[str, object],
    cross_path: Path,
    context: Dict[str, object],
    task: Dict[str, str],
    require_file: bool = True,
) -> None:
    forbidden = {
        "approved",
        "validated",
        "testing",
        "rule_card",
        "content_asset",
        "generated_post",
        "generated_content",
        "formal_mechanism",
    }
    for key in forbidden:
        if key in cross:
            raise WorkflowError("forbidden cross-sample field: " + key)
    if require_file and not cross_path.is_file():
        raise WorkflowError("cross-sample-analysis.yaml does not exist")
    if cross.get("task_id") != task["task_id"]:
        raise WorkflowError("cross-sample task_id mismatch")
    if cross.get("sample_ids") != context["sample_ids"]:
        raise WorkflowError("cross-sample sample_ids mismatch")
    if len(cross.get("sample_ids") or []) < 2:
        raise WorkflowError("cross-sample requires at least 2 samples")
    normalization = cross.get("normalization")
    if not isinstance(normalization, dict) or normalization.get("status") not in ("normalized", "partially_normalized"):
        raise WorkflowError("invalid cross-sample normalization.status")
    candidates = cross.get("mechanism_candidates")
    if not isinstance(candidates, list):
        raise WorkflowError("mechanism_candidates must be a list")
    for candidate in candidates:
        validate_cross_sample_candidate(candidate, context)
    for item in cross.get("unmatched_mechanisms") or []:
        if not valid_mechanism_ref(item.get("sample_id"), item.get("mechanism_id"), item.get("analysis_ref"), context):
            raise WorkflowError("invalid unmatched mechanism")
    for field in ("cross_sample_patterns", "rule_suggestions", "asset_suggestions", "content_opportunities", "questions"):
        if not isinstance(cross.get(field), list):
            raise WorkflowError(field + " must be a list")


def validate_cross_sample_candidate(candidate: Dict[str, object], context: Dict[str, object]) -> None:
    member_mechanisms = candidate.get("member_mechanisms")
    if not isinstance(member_mechanisms, list) or len(member_mechanisms) < 2:
        raise WorkflowError("candidate must include at least 2 member mechanisms")
    member_samples = []
    for member in member_mechanisms:
        sample_id = member.get("sample_id")
        member_samples.append(sample_id)
        if not valid_mechanism_ref(sample_id, member.get("mechanism_id"), member.get("analysis_ref"), context):
            raise WorkflowError("invalid member mechanism")
    if len(set(member_samples)) < 2:
        raise WorkflowError("candidate must include at least 2 distinct samples")
    supporting_samples = candidate.get("supporting_samples")
    if not isinstance(supporting_samples, list):
        raise WorkflowError("supporting_samples must be a list")
    if candidate.get("support_count") != len(supporting_samples):
        raise WorkflowError("support_count mismatch")
    if set(supporting_samples) != set(member_samples):
        raise WorkflowError("supporting_samples mismatch")
    if candidate.get("confidence") not in ("low", "medium", "high"):
        raise WorkflowError("invalid cross-sample confidence")
    if candidate.get("confidence") == "high" and candidate.get("counter_evidence"):
        raise WorkflowError("counter evidence cannot have high confidence")
    if "counter_evidence" not in candidate or "differences" not in candidate:
        raise WorkflowError("candidate must include counter_evidence and differences")
    if candidate.get("merge_recommendation") != "candidate":
        raise WorkflowError("merge_recommendation must remain candidate")
    for fact in candidate.get("observed_facts") or []:
        sample_id = fact.get("sample_id")
        if sample_id not in context["sample_ids"]:
            raise WorkflowError("observed fact must reference a sample")
        evidence_ref = str(fact.get("evidence_ref") or "")
        if not evidence_ref or not analysis_module.evidence_ref_exists(evidence_ref, context["evidence"][sample_id]):
            raise WorkflowError("invalid observed fact evidence_ref")
    if not candidate.get("observed_facts"):
        raise WorkflowError("candidate observed_facts are required")
    for inference in candidate.get("inferences") or []:
        sample_id = inference.get("sample_id")
        if sample_id not in context["sample_ids"] or not inference.get("analysis_ref"):
            raise WorkflowError("inference must reference a sample analysis")


def valid_mechanism_ref(
    sample_id: object,
    mechanism_id: object,
    analysis_ref: object,
    context: Dict[str, object],
) -> bool:
    if sample_id not in context["sample_ids"]:
        return False
    mechanisms = context["analyses"][sample_id].get("mechanisms") or []
    for index, mechanism in enumerate(mechanisms):
        if mechanism.get("id") == mechanism_id and analysis_ref == mechanism_analysis_ref(str(sample_id), index):
            return True
    return False


def run_generation_context_assembly(
    root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
) -> str:
    brief_path = task_dir / "content" / "generation-brief.json"
    if not brief_path.is_file():
        raise WorkflowError("generation brief required")
    request_path = task_dir / "raw" / "personal-content" / "generation-context-request.json"
    response_path = task_dir / "raw" / "personal-content" / "generation-context-response.json"
    context_path = task_dir / "content" / "generation-context.yaml"
    artifacts = (request_path, response_path, context_path)
    existing_count = sum(1 for path in artifacts if path.exists())
    if existing_count not in (0, 3):
        raise WorkflowError("Incomplete generation context artifacts")

    brief = read_json_file(brief_path)
    sources = load_generation_context_sources(root, task_dir, task)
    if existing_count == 3:
        context = read_json_file(context_path)
        validate_generation_context(context, task, sources)
        return "complete"

    request = build_generation_context_request(task, state, brief, sources)
    response = build_generation_context_response(request, sources)
    context = build_generation_context(task, brief, response, sources)
    validate_generation_context(context, task, sources)
    write_json_atomic(request_path, request)
    write_json_atomic(response_path, response)
    write_json_atomic(context_path, context)
    return "complete"


def load_generation_context_sources(root: Path, task_dir: Path, task: Dict[str, str]) -> List[Dict[str, object]]:
    sources_path = task_dir / "content" / "context-sources.json"
    if not sources_path.exists():
        return []
    payload = read_json_file(sources_path)
    if payload.get("generation_task_id") != task["task_id"]:
        raise WorkflowError("context sources generation_task_id mismatch")
    loaded = []
    for item in payload.get("sources", []):
        source_task_dir = root / str(item.get("source_task_path", ""))
        source_task, source_state = read_task_files(source_task_dir)
        if source_task.get("task_type") not in ("learning", "learning_batch"):
            raise WorkflowError("source task must be learning or learning_batch")
        if source_state.get("status") != "completed":
            raise WorkflowError("source task must be completed")
        summary_rel = str(item.get("summary_path"))
        result_rel = str(item.get("mechanism_intake_result_path"))
        summary_path = source_task_dir / summary_rel
        result_path = source_task_dir / result_rel
        if not summary_path.is_file():
            raise WorkflowError("source summary is missing: " + summary_rel)
        if not result_path.is_file():
            raise WorkflowError("source mechanism intake result is missing: " + result_rel)
        summary = read_json_file(summary_path)
        result = read_json_file(result_path)
        loaded.append(
            {
                "source_task_id": source_task["task_id"],
                "source_task_type": source_task["task_type"],
                "source_task_path": item.get("source_task_path"),
                "summary_path": summary_rel,
                "mechanism_intake_result_path": result_rel,
                "summary": summary,
                "intake_result": result,
            }
        )
    return loaded


def build_generation_context_request(
    task: Dict[str, str],
    state: Dict[str, object],
    brief: Dict[str, object],
    sources: List[Dict[str, object]],
) -> Dict[str, object]:
    return {
        "adapter": "mock_personal_content",
        "mock": True,
        "task_id": task["task_id"],
        "stage": state.get("current_stage"),
        "operation": "assemble_generation_context",
        "workspace_ref": personal_content_module.WORKSPACE_REF,
        "brief": brief,
        "learning_sources": [
            {
                "source_task_id": item["source_task_id"],
                "source_task_type": item["source_task_type"],
                "summary_path": item["summary_path"],
                "mechanism_intake_result_path": item["mechanism_intake_result_path"],
            }
            for item in sources
        ],
        "allowed_actions": [
            "read generation brief",
            "read explicitly attached learning summaries",
            "return references and constraints for generation",
        ],
        "forbidden_actions": [
            "modify formal mechanisms",
            "create formal rules",
            "create formal assets",
            "generate post body",
            "auto publish",
            "auto select topic",
        ],
        "created_at": now_iso(),
    }


def build_generation_context_response(request: Dict[str, object], sources: List[Dict[str, object]]) -> Dict[str, object]:
    mechanism_refs = []
    rule_refs = []
    asset_refs = []
    opportunities = []
    questions = []
    for source in sources:
        intake = source.get("intake_result") or {}
        for result in intake.get("results", []):
            external = result.get("external_object") or {}
            if external.get("id"):
                mechanism_refs.append(
                    {
                        "source_task_id": source["source_task_id"],
                        "external_object": external,
                        "status": result.get("status"),
                    }
                )
        summary = source.get("summary") or {}
        governance = summary.get("governance") or {}
        for item in governance.get("pending_rule_suggestions", []):
            rule_refs.append({"source_task_id": source["source_task_id"], "ref": str(item)})
        for item in governance.get("pending_asset_suggestions", []):
            asset_refs.append({"source_task_id": source["source_task_id"], "ref": str(item)})
        opportunities.extend(summary.get("content_opportunities", []))
        questions.extend(summary.get("open_questions", []))
    return {
        "adapter": "mock_personal_content",
        "mock": True,
        "task_id": request["task_id"],
        "operation": request["operation"],
        "workspace_ref": request["workspace_ref"],
        "account_profile_summary": "Mock account context assembled from explicit learning sources.",
        "active_mechanism_references": mechanism_refs,
        "candidate_mechanism_references": mechanism_refs,
        "relevant_rules": rule_refs,
        "relevant_assets": asset_refs,
        "prior_content_warnings": [],
        "originality_constraints": ["Do not copy source titles or wording directly."],
        "content_opportunities": opportunities,
        "open_questions": questions,
        "learning_source_references": request["learning_sources"],
        "executed_at": now_iso(),
    }


def build_generation_context(
    task: Dict[str, str],
    brief: Dict[str, object],
    response: Dict[str, object],
    sources: List[Dict[str, object]],
) -> Dict[str, object]:
    warnings = list(response.get("prior_content_warnings", []))
    if not sources:
        warnings.append("No learning sources attached; context is limited.")
    return {
        "task_id": task["task_id"],
        "normalization": {
            "status": "normalized",
            "warnings": warnings,
        },
        "brief": {
            "request": brief.get("request", ""),
            "platform": brief.get("platform", "xiaohongshu"),
            "target_audience": brief.get("target_audience"),
            "content_goal": brief.get("content_goal"),
            "constraints": brief.get("constraints", []),
            "forbidden": brief.get("forbidden", []),
        },
        "account_context": {
            "profile_summary": response.get("account_profile_summary", ""),
            "workspace_ref": response.get("workspace_ref", ""),
        },
        "mechanism_refs": response.get("candidate_mechanism_references", []),
        "rule_refs": response.get("relevant_rules", []),
        "asset_refs": response.get("relevant_assets", []),
        "learning_sources": [
            {
                "source_task_id": item["source_task_id"],
                "source_task_type": item["source_task_type"],
                "summary_path": item["summary_path"],
                "mechanism_intake_result_path": item["mechanism_intake_result_path"],
            }
            for item in sources
        ],
        "content_opportunities": response.get("content_opportunities", []),
        "open_questions": response.get("open_questions", []),
        "warnings": warnings,
        "originality_requirements": response.get("originality_constraints", []),
    }


def validate_generation_context(context: Dict[str, object], task: Dict[str, str], sources: Optional[List[Dict[str, object]]] = None) -> None:
    if context.get("task_id") != task["task_id"]:
        raise WorkflowError("generation context task_id mismatch")
    normalization = context.get("normalization")
    if not isinstance(normalization, dict) or normalization.get("status") not in ("normalized", "partially_normalized"):
        raise WorkflowError("generation context normalization status is invalid")
    brief = context.get("brief")
    if not isinstance(brief, dict) or not brief.get("request"):
        raise WorkflowError("generation context brief is required")
    if not brief.get("platform"):
        raise WorkflowError("generation context platform is required")
    if sources is not None and len(context.get("learning_sources", [])) != len(sources):
        raise WorkflowError("generation context learning source mismatch")
    if sources is not None:
        explicit_ids = {item["source_task_id"] for item in sources}
        for source in context.get("learning_sources", []):
            if source.get("source_task_id") not in explicit_ids:
                raise WorkflowError("generation context contains implicit learning source")
            if source.get("source_task_type") not in ("learning", "learning_batch"):
                raise WorkflowError("generation context source task type is invalid")
    for key in ("mechanism_refs", "rule_refs", "asset_refs"):
        value = context.get(key, [])
        if not isinstance(value, list):
            raise WorkflowError("generation context %s must be a list" % key)
        for ref in value:
            if not isinstance(ref, dict):
                raise WorkflowError("generation context %s must contain references only" % key)
            for forbidden_key in ("description", "observed_facts", "inferences", "generated_content", "body", "content"):
                if forbidden_key in ref:
                    raise WorkflowError("generation context embeds full object content")
    text = json.dumps(context, ensure_ascii=False)
    for forbidden in (
        "generated_post",
        "post_body",
        "auto_publish",
        "formal_mechanism_state",
        "modify_personal_content",
        "selected_topic_id",
    ):
        if forbidden in text:
            raise WorkflowError("forbidden generation context content: " + forbidden)


def run_generation_topic_generation(task_dir: Path, task: Dict[str, str]) -> None:
    context_path = task_dir / "content" / "generation-context.yaml"
    response_path = task_dir / "raw" / "personal-content" / "topic-generation-response.json"
    candidates_path = task_dir / "content" / "topic-candidates.json"
    artifacts = (response_path, candidates_path)
    existing_count = sum(1 for path in artifacts if path.exists())
    if existing_count not in (0, 2):
        raise WorkflowError("Incomplete topic generation artifacts")
    context = read_json_file(context_path)
    validate_generation_context(context, task)
    if existing_count == 2:
        validate_topic_candidates(read_json_file(candidates_path), task, context)
        return
    topics = build_topic_candidates(task, context)
    response = {
        "adapter": "mock_personal_content",
        "mock": True,
        "task_id": task["task_id"],
        "operation": "generate_topic_candidates",
        "workspace_ref": personal_content_module.WORKSPACE_REF,
        "executed_at": now_iso(),
        "candidates": topics["candidates"],
    }
    validate_topic_candidates(topics, task, context)
    write_json_atomic(response_path, response)
    write_json_atomic(candidates_path, topics)


def build_topic_candidates(task: Dict[str, str], context: Dict[str, object]) -> Dict[str, object]:
    brief = context.get("brief") or {}
    mechanism_refs = context.get("mechanism_refs") or []
    rule_refs = context.get("rule_refs") or []
    asset_refs = context.get("asset_refs") or []
    learning_sources = context.get("learning_sources") or []
    opportunities = context.get("content_opportunities") or []
    request = brief.get("request", "")
    candidates = []
    for index in range(1, 6):
        candidates.append(
            {
                "topic_id": "topic-%03d" % index,
                "title_direction": "%s - 选题方向 %d" % (request, index),
                "core_point": "基于 GenerationContext 的 brief 和显式学习引用提炼原创角度。",
                "target_audience": brief.get("target_audience"),
                "content_goal": brief.get("content_goal"),
                "mechanism_refs": mechanism_refs[:3],
                "rule_refs": rule_refs[:3],
                "asset_refs": asset_refs[:3],
                "learning_source_refs": learning_sources,
                "fit_reason": "Uses explicit GenerationContext references rather than copying source content.",
                "originality_requirements": context.get("originality_requirements", []),
                "risks": context.get("warnings", []),
                "limitations": context.get("open_questions", []),
                "selected": False,
            }
        )
    return {"task_id": task["task_id"], "context_path": "content/generation-context.yaml", "candidates": candidates}


def validate_topic_candidates(payload: Dict[str, object], task: Dict[str, str], context: Dict[str, object]) -> None:
    if payload.get("task_id") != task["task_id"]:
        raise WorkflowError("topic candidates task_id mismatch")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) < 5:
        raise WorkflowError("at least 5 topic candidates are required")
    seen_ids = set()
    allowed_mechanisms = context.get("mechanism_refs") or []
    allowed_rules = context.get("rule_refs") or []
    allowed_assets = context.get("asset_refs") or []
    allowed_sources = context.get("learning_sources") or []
    for item in candidates:
        topic_id = item.get("topic_id")
        if not topic_id:
            raise WorkflowError("topic_id is required")
        if topic_id in seen_ids:
            raise WorkflowError("topic_id must be unique")
        seen_ids.add(topic_id)
        if not item.get("title_direction") or not item.get("core_point"):
            raise WorkflowError("topic candidate title_direction and core_point are required")
        if item.get("selected") is not False:
            raise WorkflowError("topic candidates must default to selected false")
        if not isinstance(item.get("originality_requirements"), list) or not item.get("originality_requirements"):
            raise WorkflowError("topic candidate originality requirements are required")
        for ref in item.get("mechanism_refs", []):
            if ref not in allowed_mechanisms:
                raise WorkflowError("topic candidate references unknown mechanism")
        for ref in item.get("rule_refs", []):
            if ref not in allowed_rules:
                raise WorkflowError("topic candidate references unknown rule")
        for ref in item.get("asset_refs", []):
            if ref not in allowed_assets:
                raise WorkflowError("topic candidate references unknown asset")
        for ref in item.get("learning_source_refs", []):
            if ref not in allowed_sources:
                raise WorkflowError("topic candidate references unknown learning source")
        text = json.dumps(item, ensure_ascii=False)
        for forbidden in ("generated_post", "post_body", "generated_content", "auto_publish", "formal_mechanism_state"):
            if forbidden in text:
                raise WorkflowError("topic candidate must not include generated content or formal writes")


def write_mock_lingzao_raw(
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    source_url: Optional[str],
) -> None:
    if not source_url:
        raise WorkflowError("learning evidence_collection requires a source URL")
    if source_url.startswith("mock-fail://"):
        raise WorkflowError("Mock Lingzao failure requested")

    raw_dir = task_dir / "raw" / "lingzao"
    raw_dir.mkdir(parents=True, exist_ok=True)
    note_path = raw_dir / "note-detail.json"
    invocation_path = raw_dir / "invocation.json"

    if note_path.exists() and invocation_path.exists():
        return

    captured_at = now_iso()
    note_detail = {
        "source": {
            "source_type": "xhs_note",
            "original_url": source_url,
            "canonical_url": source_url,
        },
        "author": {
            "name": "Mock Author",
            "id": "mock-author-001",
        },
        "content": {
            "title": "Mock note title",
            "body": "Mock note body for downstream evidence normalization.",
            "tags": ["mock", "learning"],
            "images": [
                {"url": "https://example.com/mock-image-1.jpg", "alt": "mock image"}
            ],
        },
        "published_at": "2026-07-15T00:00:00+08:00",
        "captured_at": captured_at,
        "metrics": {
            "likes": 128,
            "saves": 64,
            "comments": 12,
            "shares": 8,
        },
        "comments": {
            "status": "missing",
            "items": [],
        },
        "transcript": {
            "status": "missing",
            "text": "",
        },
    }
    invocation = {
        "adapter": "mock_lingzao",
        "mode": "mock",
        "task_id": task.get("task_id", ""),
        "task_type": task.get("task_type", ""),
        "stage": state.get("current_stage", ""),
        "source_url": source_url,
        "executed_at": captured_at,
    }

    write_json_atomic(note_path, note_detail)
    write_json_atomic(invocation_path, invocation)


def read_json_file(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_lingzao_evidence(task_dir: Path, task: Dict[str, str]) -> Dict[str, object]:
    note_path = task_dir / "raw" / "lingzao" / "note-detail.json"
    invocation_path = task_dir / "raw" / "lingzao" / "invocation.json"
    sample_id = "sample-" + task.get("task_id", "unknown")
    return normalize_lingzao_evidence_from_files(task, note_path, invocation_path, sample_id)


def normalize_lingzao_evidence_from_files(
    task: Dict[str, str],
    note_path: Path,
    invocation_path: Path,
    sample_id: str,
) -> Dict[str, object]:
    if not note_path.is_file():
        return failed_evidence(task, ["normalization_failed: missing " + str(note_path)], sample_id)
    if not invocation_path.is_file():
        return failed_evidence(task, ["normalization_failed: missing " + str(invocation_path)], sample_id)

    note = read_json_file(note_path)
    invocation = read_json_file(invocation_path)
    if not note:
        return failed_evidence(task, ["normalization_failed: raw note detail is empty"], sample_id)

    source = note.get("source") or {}
    content = note.get("content") or {}
    author = note.get("author") or {}
    comments = note.get("comments") or {}
    transcript = note.get("transcript") or {}
    metrics = note.get("metrics") or {}

    original_url = source.get("original_url")
    title = content.get("title")
    body = content.get("body")
    warnings = []
    missing = []

    if not original_url:
        warnings.append("normalization_failed: source.original_url is required")
    if not title:
        warnings.append("normalization_failed: content.title is required")
    if not body:
        warnings.append("normalization_failed: content.body is required")
    if warnings:
        return failed_evidence(task, warnings, sample_id)

    metric_values = {}
    for metric in ("likes", "saves", "comments", "shares"):
        value = metrics.get(metric)
        metric_values[metric] = value if isinstance(value, int) else None
        if metric_values[metric] is None:
            missing.append("metrics." + metric)

    comments_status = comments.get("status") or "missing"
    transcript_status = transcript.get("status") or "missing"
    transcript_text = transcript.get("text") if transcript_status == "available" else None
    if comments_status != "available":
        missing.append("comments")
    if transcript_status != "available":
        missing.append("transcript")
    missing.append("local_video")

    status = "partially_normalized" if missing else "normalized"
    normalization_warnings = ["Missing " + item for item in missing]

    evidence = {
        "sample_id": sample_id,
        "normalization": {
            "status": status,
            "warnings": normalization_warnings,
        },
        "source": {
            "source_type": source.get("source_type") or "xhs_note",
            "original_url": original_url,
            "canonical_url": source.get("canonical_url"),
            "author": author.get("name") or "",
            "author_id": author.get("id"),
            "published_at": note.get("published_at") or "",
            "captured_at": note.get("captured_at") or invocation.get("executed_at") or "",
        },
        "facts": {
            "title": title,
            "body": body,
            "tags": content.get("tags") or [],
            "cover": {},
            "images": content.get("images") or [],
            "transcript": transcript_text,
            "metrics": metric_values,
            "comments": comments.get("items") or [],
        },
        "basic_structure": {
            "content_type": "xhs_note",
            "sections": [],
            "visible_cta": [],
        },
        "coverage": {
            "note_detail": "available",
            "comments": comments_status,
            "transcript": transcript_status,
            "local_video": "missing",
        },
        "missing": missing,
        "warnings": normalization_warnings,
        "source_refs": build_evidence_source_refs(metric_values),
    }
    return evidence


def failed_evidence(task: Dict[str, str], warnings: List[str], sample_id: Optional[str] = None) -> Dict[str, object]:
    return {
        "sample_id": sample_id or "sample-" + task.get("task_id", "unknown"),
        "normalization": {
            "status": "normalization_failed",
            "warnings": warnings,
        },
        "source": {
            "source_type": "xhs_note",
            "original_url": "",
            "canonical_url": None,
            "author": "",
            "author_id": None,
            "published_at": "",
            "captured_at": "",
        },
        "facts": {
            "title": "",
            "body": "",
            "tags": [],
            "cover": {},
            "images": [],
            "transcript": None,
            "metrics": {"likes": None, "saves": None, "comments": None, "shares": None},
            "comments": [],
        },
        "basic_structure": {"content_type": "", "sections": [], "visible_cta": []},
        "coverage": {
            "note_detail": "missing",
            "comments": "missing",
            "transcript": "missing",
            "local_video": "missing",
        },
        "missing": ["note_detail"],
        "warnings": warnings,
        "source_refs": [],
    }


def build_evidence_source_refs(metrics: Dict[str, object]) -> List[Dict[str, str]]:
    refs = [
        ref("facts.title", "$.content.title"),
        ref("facts.body", "$.content.body"),
        ref("source.author", "$.author.name"),
        ref("source.author_id", "$.author.id"),
        ref("source.published_at", "$.published_at"),
        ref("facts.images", "$.content.images"),
        ref("coverage.comments", "$.comments.status"),
        ref("coverage.transcript", "$.transcript.status"),
    ]
    for metric in ("likes", "saves", "comments", "shares"):
        refs.append(ref("facts.metrics." + metric, "$.metrics." + metric))
    return refs


def ref(target: str, source_path: str) -> Dict[str, str]:
    return {
        "target": target,
        "raw_file": "raw/lingzao/note-detail.json",
        "source_path": source_path,
    }


def validate_evidence(evidence: Dict[str, object], evidence_path: Path) -> None:
    forbidden = {
        "mechanisms",
        "rule_suggestions",
        "asset_suggestions",
        "approved",
        "testing",
        "validated",
        "generated_content",
        "formal_post",
        "post_draft",
    }
    for key in forbidden:
        if key in evidence:
            raise WorkflowError("forbidden evidence field: " + key)

    if not evidence_path.is_file():
        raise WorkflowError("evidence.yaml does not exist")
    if not evidence.get("sample_id"):
        raise WorkflowError("sample_id is required")

    normalization = evidence.get("normalization")
    if not isinstance(normalization, dict):
        raise WorkflowError("normalization is required")
    status = normalization.get("status")
    if status not in ("normalized", "partially_normalized", "normalization_failed"):
        raise WorkflowError("invalid normalization.status: " + str(status))
    if status == "normalization_failed":
        raise WorkflowError("normalization_failed cannot advance")

    source = evidence.get("source")
    if not isinstance(source, dict) or not source.get("original_url"):
        raise WorkflowError("source.original_url is required")
    facts = evidence.get("facts")
    if not isinstance(facts, dict):
        raise WorkflowError("facts is required")
    coverage = evidence.get("coverage")
    if not isinstance(coverage, dict):
        raise WorkflowError("coverage is required")

    metrics = facts.get("metrics")
    if not isinstance(metrics, dict):
        raise WorkflowError("facts.metrics is required")
    for metric in ("likes", "saves", "comments", "shares"):
        value = metrics.get(metric)
        if value is not None and not isinstance(value, int):
            raise WorkflowError("metric must be integer or null: " + metric)

    refs = evidence.get("source_refs")
    if not isinstance(refs, list) or not refs:
        raise WorkflowError("source_refs are required")
    for item in refs:
        if not isinstance(item, dict):
            raise WorkflowError("source_refs must contain objects")
        if not item.get("target") or not item.get("raw_file") or not item.get("source_path"):
            raise WorkflowError("source_refs require target, raw_file, and source_path")
        if not str(item.get("raw_file")).startswith("raw/lingzao/"):
            raise WorkflowError("source_refs must reference raw/lingzao files")


def ensure_evidence_is_analyzable(evidence: Dict[str, object]) -> None:
    facts = evidence.get("facts") or {}
    title = facts.get("title")
    body = facts.get("body")
    if not title and not body:
        raise WorkflowError("Evidence must include facts.title or facts.body for analysis")


def write_mock_hot_learning_raw(
    root: Path,
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    evidence: Dict[str, object],
) -> None:
    source = evidence.get("source") or {}
    original_url = source.get("original_url", "")
    if str(original_url).startswith("mock-hot-fail://"):
        raise WorkflowError("Mock Hot Learning failure requested")

    prompt_path = root / "prompts" / "hot-learning-analysis-only.md"
    if not prompt_path.is_file():
        raise WorkflowError("Missing prompt: prompts/hot-learning-analysis-only.md")

    write_mock_hot_learning_raw_to_dir(
        raw_dir=task_dir / "raw" / "hot-learning",
        task=task,
        state=state,
        evidence=evidence,
        evidence_path="evidence/evidence.yaml",
        output_path="raw/hot-learning/analysis.md",
    )


def write_mock_hot_learning_raw_to_dir(
    raw_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    evidence: Dict[str, object],
    evidence_path: str,
    output_path: str,
) -> None:
    facts = evidence.get("facts") or {}
    title = str(facts.get("title") or "")
    if "MOCK_HOT_FAIL" in title:
        raise WorkflowError("Mock Hot Learning failure requested")

    raw_dir.mkdir(parents=True, exist_ok=True)
    analysis_path = raw_dir / "analysis.md"
    invocation_path = raw_dir / "invocation.json"

    if analysis_path.exists() and invocation_path.exists():
        return
    if analysis_path.exists() != invocation_path.exists():
        raise WorkflowError("Incomplete raw hot-learning output exists")

    markdown = render_mock_hot_learning_markdown(evidence)
    invocation = {
        "adapter": "mock_hot_learning",
        "mock": True,
        "task_id": task.get("task_id", ""),
        "task_type": task.get("task_type", ""),
        "stage": state.get("current_stage", ""),
        "sample_id": evidence.get("sample_id", ""),
        "evidence_path": evidence_path,
        "evidence_sample_id": evidence.get("sample_id", ""),
        "evidence_normalization_status": (evidence.get("normalization") or {}).get("status"),
        "prompt_path": "prompts/hot-learning-analysis-only.md",
        "executed_at": now_iso(),
        "outputs": [output_path],
        "allowed_actions": [
            "analyze evidence",
            "identify observable facts",
            "write raw markdown analysis",
        ],
        "forbidden_actions": [
            "create formal rules",
            "write analysis.yaml",
            "generate formal posts",
            "modify evidence.yaml",
            "modify Personal Content workspace",
            "cross-sample aggregation",
        ],
    }

    wrote_analysis = False
    wrote_invocation = False
    try:
        write_text_atomic(analysis_path, markdown)
        wrote_analysis = True
        write_json_atomic(invocation_path, invocation)
        wrote_invocation = True
    except Exception as error:
        if not wrote_invocation and invocation_path.exists():
            invocation_path.unlink()
        if wrote_analysis and analysis_path.exists():
            analysis_path.unlink()
        temp_analysis = raw_dir / ".analysis.md.tmp"
        temp_invocation = raw_dir / ".invocation.json.tmp"
        if temp_analysis.is_file():
            temp_analysis.unlink()
        if temp_invocation.is_file():
            temp_invocation.unlink()
        raise WorkflowError("Failed to write raw hot-learning output: " + str(error))


def render_mock_hot_learning_markdown(evidence: Dict[str, object]) -> str:
    sample_id = evidence.get("sample_id", "")
    facts = evidence.get("facts") or {}
    source = evidence.get("source") or {}
    normalization = evidence.get("normalization") or {}
    missing = evidence.get("missing") or []
    warnings = normalization.get("warnings") or evidence.get("warnings") or []

    title = facts.get("title") or ""
    body = facts.get("body") or ""
    author = source.get("author") or ""
    metrics = facts.get("metrics") or {}

    limitation_lines = []
    for item in missing:
        limitation_lines.append("- Missing " + str(item).replace("_", " "))
    if "local_video" in missing:
        limitation_lines.append("- Cannot judge real video shots without local video.")
    if not limitation_lines:
        limitation_lines.append("- No major limitations recorded in Evidence.")

    warning_lines = ["- " + str(item) for item in warnings] or ["- None"]

    return """# Mock Hot Learning Raw Analysis

Sample ID: {sample_id}
Source URL: {url}

## Observable Facts
- Title: {title}
  Evidence reference: evidence.yaml#facts.title
- Body summary: {body}
  Evidence reference: evidence.yaml#facts.body
- Author: {author}
  Evidence reference: evidence.yaml#source.author
- Metrics: likes={likes}, saves={saves}, comments={comments}, shares={shares}
  Evidence reference: evidence.yaml#facts.metrics

## Inferences
- The note likely relies on a clear promise in the title.
- The body supports the promise with compact explanatory detail.
- Current engagement metrics suggest the structure is worth studying, but causality is not proven.

## Content Mechanisms
### Mechanism 1: Specific Promise Title
- Description: The title packages the benefit into a direct promise.
- Evidence: evidence.yaml#facts.title
- Confidence: medium
- Alternative explanation: Performance may depend on creator trust or distribution timing.

### Mechanism 2: Compact Evidence Body
- Description: The body gives enough concrete context to support the promise without overloading the reader.
- Evidence: evidence.yaml#facts.body
- Confidence: medium
- Alternative explanation: The topic may already be high-demand regardless of structure.

### Mechanism 3: Low-Friction Visual Support
- Description: Images appear available as supporting assets, but the mock evidence does not prove visual sequencing.
- Evidence: evidence.yaml#facts.images
- Confidence: low
- Alternative explanation: Visual impact cannot be verified without richer image analysis.

## Learnable Parts
- Clear promise framing.
- Compact supporting body structure.
- Separating observable facts from transfer suggestions.

## Not Copyable Parts
- Do not copy title wording directly.
- Do not invent personal experience or results.
- Do not assume comments or transcript patterns when they are missing.

## Rule Direction Suggestions
- Candidate direction: require title promises to be supported by explicit body evidence.
- Candidate direction: mark missing comments/transcripts as analysis limitations.

## Content Asset Direction Suggestions
- Save reusable title-promise patterns as candidate assets after more samples.
- Save evidence-backed body outlines as candidate assets after validation.

## Content Opportunities
- Draft a topic around the same problem-solution pattern using original examples.
- Compare whether similar titles work across multiple samples.

## Missing Information And Limitations
{limitations}

## Evidence Warnings
{warnings}
""".format(
        sample_id=sample_id,
        url=source.get("original_url", ""),
        title=title,
        body=body,
        author=author,
        likes=metrics.get("likes"),
        saves=metrics.get("saves"),
        comments=metrics.get("comments"),
        shares=metrics.get("shares"),
        limitations="\n".join(limitation_lines),
        warnings="\n".join(warning_lines),
    )


def normalize_hot_learning_analysis(task_dir: Path, evidence: Dict[str, object]) -> Dict[str, object]:
    markdown_path = task_dir / "raw" / "hot-learning" / "analysis.md"
    invocation_path = task_dir / "raw" / "hot-learning" / "invocation.json"
    if not markdown_path.is_file():
        return failed_analysis(evidence, ["normalization_failed: missing raw/hot-learning/analysis.md"])
    if not invocation_path.is_file():
        return failed_analysis(evidence, ["normalization_failed: missing raw/hot-learning/invocation.json"])

    markdown = markdown_path.read_text(encoding="utf-8")
    validate_markdown_evidence_refs(markdown, evidence)
    sections = parse_markdown_sections(markdown)
    warnings = []
    mechanisms = parse_mechanisms(markdown, sections, warnings)

    if not mechanisms:
        return failed_analysis(evidence, ["normalization_failed: no valid mechanisms extracted"])

    status = "normalized"
    if len(mechanisms) < 3 or warnings:
        status = "partially_normalized"
        if len(mechanisms) < 3:
            warnings.append("Expected 3 mock mechanisms, extracted %s" % len(mechanisms))

    limitations = section_list(sections, "Missing Information And Limitations")
    questions = [item for item in limitations if "Missing" in item]

    return {
        "sample_id": evidence.get("sample_id", ""),
        "normalization": {"status": status, "warnings": warnings},
        "mechanisms": mechanisms,
        "transfer": {
            "learnable": section_list(sections, "Learnable Parts"),
            "not_copyable": section_list(sections, "Not Copyable Parts"),
            "account_fit": [],
            "originality_requirements": section_list(sections, "Not Copyable Parts"),
        },
        "rule_suggestions": section_list(sections, "Rule Direction Suggestions"),
        "asset_suggestions": section_list(sections, "Content Asset Direction Suggestions"),
        "content_opportunities": section_list(sections, "Content Opportunities"),
        "questions": questions,
    }


def validate_markdown_evidence_refs(markdown: str, evidence: Dict[str, object]) -> None:
    for token in markdown.replace("\n", " ").split():
        if token.startswith("evidence.yaml#"):
            cleaned = token.rstrip(".,;)")
            if not evidence_ref_exists(cleaned, evidence):
                raise WorkflowError("invalid evidence_ref: " + cleaned)


def failed_analysis(evidence: Dict[str, object], warnings: List[str]) -> Dict[str, object]:
    return {
        "sample_id": evidence.get("sample_id", ""),
        "normalization": {"status": "normalization_failed", "warnings": warnings},
        "mechanisms": [],
        "transfer": {"learnable": [], "not_copyable": [], "account_fit": [], "originality_requirements": []},
        "rule_suggestions": [],
        "asset_suggestions": [],
        "content_opportunities": [],
        "questions": [],
    }


def parse_markdown_sections(markdown: str) -> Dict[str, str]:
    sections = {}
    current = None
    lines = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(lines).strip()
            current = line[3:].strip()
            lines = []
        elif current:
            lines.append(line)
    if current:
        sections[current] = "\n".join(lines).strip()
    return sections


def section_list(sections: Dict[str, str], section: str) -> List[str]:
    values = []
    for line in sections.get(section, "").splitlines():
        text = line.strip()
        if text.startswith("- "):
            values.append(text[2:].strip())
    return values


def parse_mechanisms(markdown: str, sections: Dict[str, str], warnings: List[str]) -> List[Dict[str, object]]:
    mechanisms = []
    inference_text = first_list_item(sections.get("Inferences", ""))
    mechanism_section = sections.get("Content Mechanisms", "")
    chunks = mechanism_section.split("### Mechanism ")
    for chunk in chunks[1:]:
        mechanism = parse_mechanism_chunk(chunk, len(mechanisms) + 1, inference_text)
        if mechanism is None:
            warnings.append("Could not parse mechanism chunk")
            continue
        mechanisms.append(mechanism)
    return mechanisms


def parse_mechanism_chunk(chunk: str, index: int, inference_text: str) -> Optional[Dict[str, object]]:
    lines = [line.strip() for line in chunk.splitlines() if line.strip()]
    if not lines:
        return None
    heading = lines[0]
    if ":" in heading:
        name = heading.split(":", 1)[1].strip()
    else:
        name = heading.strip()

    description = value_after_prefix(lines, "- Description:")
    evidence_ref = value_after_prefix(lines, "- Evidence:")
    confidence = value_after_prefix(lines, "- Confidence:") or "medium"
    alternative = value_after_prefix(lines, "- Alternative explanation:")
    if not name or not description or not evidence_ref:
        return None

    observed_fragment = evidence_ref
    if evidence_ref == "evidence.yaml#facts.title":
        observed_text = "Title: Mock note title"
    elif evidence_ref == "evidence.yaml#facts.body":
        observed_text = "Body summary: Mock note body for downstream evidence normalization."
    else:
        observed_text = "Evidence cited from %s" % evidence_ref

    return {
        "id": "mechanism-%03d" % index,
        "name": name,
        "description": description,
        "problem": "",
        "solution": "",
        "observed_facts": [
            {
                "text": observed_text,
                "evidence_ref": evidence_ref,
                "source_fragment": observed_fragment,
            }
        ],
        "inferences": [
            {
                "text": inference_text or description,
                "raw_analysis_ref": {"file": "raw/hot-learning/analysis.md", "section": "Inferences"},
                "source_fragment": inference_text or description,
            }
        ],
        "pattern": [description],
        "applicable_scope": [],
        "missing_information": [],
        "limitations": [],
        "alternative_explanations": [alternative] if alternative else [],
        "confidence": confidence,
        "source_refs": ["raw/hot-learning/analysis.md#Content Mechanisms"],
    }


def value_after_prefix(lines: List[str], prefix: str) -> str:
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def first_list_item(section_text: str) -> str:
    for line in section_text.splitlines():
        text = line.strip()
        if text.startswith("- "):
            return text[2:].strip()
    return ""


def validate_analysis(analysis: Dict[str, object], analysis_path: Path, evidence: Dict[str, object]) -> None:
    forbidden = {
        "approved",
        "testing",
        "validated",
        "decision",
        "rule_card",
        "generated_post",
        "generated_content",
        "formal_post",
        "post_draft",
    }
    for key in forbidden:
        if key in analysis:
            raise WorkflowError("forbidden analysis field: " + key)
    if not analysis_path.is_file():
        raise WorkflowError("analysis.yaml does not exist")
    if analysis.get("sample_id") != evidence.get("sample_id"):
        raise WorkflowError("sample_id mismatch")
    normalization = analysis.get("normalization")
    if not isinstance(normalization, dict):
        raise WorkflowError("normalization is required")
    status = normalization.get("status")
    if status not in ("normalized", "partially_normalized", "normalization_failed"):
        raise WorkflowError("invalid analysis normalization.status: " + str(status))
    if status == "normalization_failed":
        raise WorkflowError("normalization_failed cannot advance")
    mechanisms = analysis.get("mechanisms")
    if not isinstance(mechanisms, list) or not mechanisms:
        raise WorkflowError("mechanisms must be a non-empty list")
    for mechanism in mechanisms:
        validate_mechanism(mechanism, evidence)
    if not isinstance(analysis.get("rule_suggestions"), list):
        raise WorkflowError("rule_suggestions must be a list")
    if not isinstance(analysis.get("asset_suggestions"), list):
        raise WorkflowError("asset_suggestions must be a list")


def validate_mechanism(mechanism: Dict[str, object], evidence: Dict[str, object]) -> None:
    if not mechanism.get("name"):
        raise WorkflowError("mechanism name is required")
    confidence = mechanism.get("confidence")
    if confidence not in ("low", "medium", "high"):
        raise WorkflowError("invalid confidence: " + str(confidence))
    observed = mechanism.get("observed_facts")
    if not isinstance(observed, list) or not observed:
        raise WorkflowError("mechanism must include an observed fact")
    for fact in observed:
        if not isinstance(fact, dict):
            raise WorkflowError("observed fact must be an object")
        text = str(fact.get("text", ""))
        if is_generic_observed_fact(text):
            raise WorkflowError("generic observed fact is not allowed: " + text)
        evidence_ref = fact.get("evidence_ref")
        if not evidence_ref or not evidence_ref_exists(str(evidence_ref), evidence):
            raise WorkflowError("invalid evidence_ref: " + str(evidence_ref))
    inferences = mechanism.get("inferences")
    if not isinstance(inferences, list):
        raise WorkflowError("inferences must be a list")
    for inference in inferences:
        if not isinstance(inference, dict):
            raise WorkflowError("inference must be an object")
        ref_data = inference.get("raw_analysis_ref")
        if not isinstance(ref_data, dict) or ref_data.get("file") != "raw/hot-learning/analysis.md":
            raise WorkflowError("inference must reference raw analysis markdown")


def is_generic_observed_fact(text: str) -> bool:
    return text.strip() in {"内容很好", "值得学习", "很有价值", "容易爆", "用户喜欢"}


def evidence_ref_exists(evidence_ref: str, evidence: Dict[str, object]) -> bool:
    prefix = "evidence.yaml#"
    if not evidence_ref.startswith(prefix):
        return False
    path = evidence_ref[len(prefix):].split(".")
    current = evidence
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def read_task_status(task_dir: Path) -> Dict[str, str]:
    task, state = read_task_files(task_dir)
    return {
        "task_id": task.get("task_id", ""),
        "task_type": task.get("task_type", ""),
        "status": state.get("status", ""),
        "current_stage": state.get("current_stage", ""),
        "current_step": state.get("current_step", ""),
        "next_stage": state.get("next_stage", ""),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xiaoba_workflow",
        description="Lightweight project baseline tools for the Xiaoba workflow.",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "validate-project",
        help="Check required baseline directories, templates, prompts, and workflow.yaml.",
    )
    create_parser = subparsers.add_parser(
        "create-task",
        help="Create a task directory with task.yaml, state.yaml, and working folders.",
    )
    create_parser.add_argument("--type", required=True, choices=TASK_TYPES, dest="task_type")
    create_parser.add_argument("--source-url")

    status_parser = subparsers.add_parser(
        "task-status",
        help="Read and display the core task and state fields.",
    )
    status_parser.add_argument("task_dir")

    advance_parser = subparsers.add_parser(
        "advance",
        help="Advance a task by one configured workflow stage without running stage business logic.",
    )
    advance_parser.add_argument("task_dir")

    resume_parser = subparsers.add_parser(
        "resume",
        help="Resume a task waiting at a configured human gate and move to its next stage.",
    )
    resume_parser.add_argument("task_dir")

    block_parser = subparsers.add_parser(
        "block",
        help="Mark a task blocked without changing its current stage.",
    )
    block_parser.add_argument("task_dir")
    block_parser.add_argument("--reason", required=True)

    unblock_parser = subparsers.add_parser(
        "unblock",
        help="Clear blocked status without advancing the task.",
    )
    unblock_parser.add_argument("task_dir")

    run_parser = subparsers.add_parser(
        "run",
        help="Execute the current stage once without running a full workflow.",
    )
    run_parser.add_argument("task_dir")
    return parser


def main(argv: Iterable[str] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate-project":
        root = Path.cwd()
        missing = validate_project(root)
        if missing:
            print("Project baseline is invalid. Missing:")
            for item in missing:
                print("- " + item)
            return 1
        print("Project baseline is valid.")
        return 0

    if args.command == "create-task":
        try:
            task_dir = create_task(Path.cwd(), args.task_type, args.source_url)
        except ValueError as error:
            parser.error(str(error))
        except (OSError, WorkflowError, FileNotFoundError) as error:
            print("Failed to create task: " + str(error))
            return 1

        print("Created task: " + str(task_dir.relative_to(Path.cwd())))
        return 0

    if args.command == "task-status":
        try:
            status = read_task_status(Path(args.task_dir))
        except (FileNotFoundError, WorkflowError) as error:
            print(str(error), file=sys.stderr)
            return 1

        for key in ("task_id", "task_type", "status", "current_stage", "current_step", "next_stage"):
            print("%s: %s" % (key, status[key]))
        return 0

    if args.command == "advance":
        return run_state_command(lambda: advance_task(Path.cwd(), Path(args.task_dir)), "Advanced task")

    if args.command == "resume":
        return run_state_command(lambda: resume_task(Path.cwd(), Path(args.task_dir)), "Resumed task")

    if args.command == "block":
        return run_state_command(lambda: block_task(Path(args.task_dir), args.reason), "Blocked task")

    if args.command == "unblock":
        return run_state_command(lambda: unblock_task(Path(args.task_dir)), "Unblocked task")

    if args.command == "run":
        return run_state_command(lambda: run_task(Path.cwd(), Path(args.task_dir)), "Ran stage")

    parser.print_help()
    return 0


def run_state_command(action, label: str) -> int:
    try:
        state = action()
    except (FileNotFoundError, WorkflowError) as error:
        print(str(error), file=sys.stderr)
        return 1
    reported_stage = state.get("_executed_stage", state["current_stage"])
    print("%s: %s" % (label, reported_stage))
    return 0
