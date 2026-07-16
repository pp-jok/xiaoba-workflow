import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple


PROFILE_FILE = "profile.json"
POSTED_NOTES_FILE = "posted-notes.json"
INVOCATION_FILE = "invocation.json"
CANDIDATES_FILE = "sample-candidates.json"
SELECTED_FILE = "selected-samples.json"
PROGRESS_FILE = "batch-evidence-progress.json"


class BatchError(Exception):
    pass


def run_mock_benchmark_screening(task_dir: Path, task: Dict[str, str], state: Dict[str, object], source_url: str) -> None:
    raw_dir = task_dir / "raw" / "lingzao"
    analysis_dir = task_dir / "analysis"
    raw_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    profile_path, posted_path, invocation_path, candidates_path = screening_paths(task_dir)

    exists = [path.exists() for path in (profile_path, posted_path, invocation_path, candidates_path)]
    if all(exists):
        validate_candidates(read_json(candidates_path), candidates_path)
        return
    if any(exists):
        raise BatchError("Incomplete benchmark screening artifacts exist")

    captured_at = now_iso()
    profile = build_profile(task, source_url, captured_at)
    posted_notes = build_posted_notes(source_url, captured_at)
    invocation = {
        "adapter": "mock_lingzao",
        "mode": "mock",
        "provider": "mock",
        "task_id": task["task_id"],
        "task_type": task["task_type"],
        "stage": state.get("current_stage"),
        "sample_id": None,
        "operation": "collect_profile",
        "command": None,
        "started_at": captured_at,
        "completed_at": captured_at,
        "exit_code": 0,
        "raw_files": [
            "raw/lingzao/profile.json",
            "raw/lingzao/posted-notes.json",
            "raw/lingzao/invocation.json",
        ],
        "stdout_file": None,
        "stderr_file": None,
        "prompt_path": "prompts/lingzao-evidence-only.md",
        "source": source_url,
        "warnings": [],
        "source_url": source_url,
        "executed_at": captured_at,
        "outputs": [
            "raw/lingzao/profile.json",
            "raw/lingzao/posted-notes.json",
            "analysis/sample-candidates.json",
        ],
    }
    candidates = build_candidates(task, posted_notes, captured_at)

    write_json_atomic(profile_path, profile)
    write_json_atomic(posted_path, posted_notes)
    write_json_atomic(invocation_path, invocation)
    write_json_atomic(candidates_path, candidates)


def select_samples(task_dir: Path, task: Dict[str, str], state: Dict[str, object], sample_ids: Iterable[str]) -> Dict[str, object]:
    ids = list(sample_ids)
    if not ids:
        raise BatchError("at least one sample id is required")
    if len(ids) != len(set(ids)):
        raise BatchError("duplicate sample id")
    if task.get("task_type") != "learning_batch":
        raise BatchError("select-samples only supports learning_batch tasks")
    if state.get("status") != "waiting_for_user" or state.get("current_stage") != "sample_selection":
        raise BatchError("task is not waiting for sample_selection")

    selected_path = task_dir / "analysis" / SELECTED_FILE
    if selected_path.exists():
        raise BatchError("selected-samples.json already exists")

    candidates_path = task_dir / "analysis" / CANDIDATES_FILE
    candidates_payload = read_json(candidates_path)
    validate_candidates(candidates_payload, candidates_path)
    candidates = candidates_payload["candidates"]
    known = {candidate["sample_id"] for candidate in candidates}
    for sample_id in ids:
        if sample_id not in known:
            raise BatchError("unknown sample id: " + sample_id)

    selected_set = set(ids)
    selected = []
    for candidate in candidates:
        if candidate["sample_id"] in selected_set:
            copied = dict(candidate)
            copied["is_selected"] = True
            selected.append(copied)

    payload = {
        "task_id": task["task_id"],
        "selected_at": now_iso(),
        "candidates_file": "analysis/sample-candidates.json",
        "selected_sample_ids": [item["sample_id"] for item in selected],
        "selected_samples": selected,
    }
    write_json_atomic(selected_path, payload)
    return payload


def run_mock_batch_evidence_collection(
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    collector: Optional[Callable[[Dict[str, object]], None]] = None,
) -> str:
    selected_path = task_dir / "analysis" / SELECTED_FILE
    if not selected_path.is_file():
        raise BatchError("selected-samples.json is required")
    selected_payload = read_json(selected_path)
    selected_samples = selected_payload.get("selected_samples")
    if not isinstance(selected_samples, list) or not selected_samples:
        raise BatchError("selected_samples are required")

    progress_path = task_dir / "analysis" / PROGRESS_FILE
    if progress_path.exists():
        progress = read_json(progress_path)
        validate_progress(progress, task, selected_samples)
    else:
        progress = initial_progress(task, selected_samples)
        write_json_atomic(progress_path, progress)

    validate_progress_raw_consistency(task_dir, progress)
    if is_batch_finished(progress):
        ensure_batch_can_finish(progress)
        return "complete"

    sample_state = next_pending_sample(progress)
    sample = find_selected_sample(selected_samples, sample_state["sample_id"])
    sample_state["status"] = "running"
    sample_state["attempts"] = int(sample_state.get("attempts") or 0) + 1
    sample_state["updated_at"] = now_iso()
    update_counts(progress)
    write_json_atomic(progress_path, progress)

    try:
        if collector is None:
            write_mock_sample_raw(task_dir, task, state, sample)
        else:
            collector(sample)
        sample_state["status"] = "succeeded"
        sample_state["error"] = None
    except Exception as error:
        sample_state["status"] = "failed"
        sample_state["error"] = str(error)
    sample_state["updated_at"] = now_iso()
    update_counts(progress)
    write_json_atomic(progress_path, progress)

    if is_batch_finished(progress):
        ensure_batch_can_finish(progress)
        return "complete"
    return "in_progress"


def screening_paths(task_dir: Path) -> Tuple[Path, Path, Path, Path]:
    return (
        task_dir / "raw" / "lingzao" / PROFILE_FILE,
        task_dir / "raw" / "lingzao" / POSTED_NOTES_FILE,
        task_dir / "raw" / "lingzao" / INVOCATION_FILE,
        task_dir / "analysis" / CANDIDATES_FILE,
    )


def initial_progress(task: Dict[str, str], selected_samples: List[Dict[str, object]]) -> Dict[str, object]:
    samples = []
    for sample in selected_samples:
        sample_id = str(sample["sample_id"])
        samples.append(
            {
                "sample_id": sample_id,
                "status": "pending",
                "attempts": 0,
                "raw_dir": "raw/lingzao/samples/" + sample_id,
                "error": None,
                "updated_at": "",
            }
        )
    progress = {
        "task_id": task["task_id"],
        "selected_sample_ids": [sample["sample_id"] for sample in selected_samples],
        "samples": samples,
        "counts": {"pending": 0, "running": 0, "succeeded": 0, "failed": 0},
    }
    update_counts(progress)
    return progress


def validate_progress(progress: Dict[str, object], task: Dict[str, str], selected_samples: List[Dict[str, object]]) -> None:
    selected_ids = [sample["sample_id"] for sample in selected_samples]
    if progress.get("task_id") != task["task_id"]:
        raise BatchError("batch progress task_id mismatch")
    if progress.get("selected_sample_ids") != selected_ids:
        raise BatchError("batch progress selected_sample_ids mismatch")
    samples = progress.get("samples")
    if not isinstance(samples, list) or len(samples) != len(selected_ids):
        raise BatchError("batch progress samples mismatch")
    progress_ids = [item.get("sample_id") for item in samples if isinstance(item, dict)]
    if progress_ids != selected_ids:
        raise BatchError("batch progress sample order mismatch")
    for item in samples:
        if item.get("status") not in ("pending", "running", "succeeded", "failed"):
            raise BatchError("invalid batch sample status: " + str(item.get("status")))
    expected_counts = count_statuses(samples)
    if progress.get("counts") != expected_counts:
        raise BatchError("batch progress counts mismatch")


def validate_progress_raw_consistency(task_dir: Path, progress: Dict[str, object]) -> None:
    for item in progress["samples"]:
        raw_dir = task_dir / str(item["raw_dir"])
        note_path = raw_dir / "note-detail.json"
        invocation_path = raw_dir / "invocation.json"
        has_note = note_path.exists()
        has_invocation = invocation_path.exists()
        status = item["status"]
        if status == "succeeded" and not (has_note and has_invocation):
            raise BatchError("succeeded sample raw output is incomplete: " + str(item["sample_id"]))
        if status == "pending" and (has_note or has_invocation):
            if has_note and has_invocation:
                raise BatchError("pending sample has existing raw output: " + str(item["sample_id"]))
            raise BatchError("pending sample has incomplete raw output: " + str(item["sample_id"]))
        if status == "running":
            raise BatchError("batch progress contains running sample: " + str(item["sample_id"]))


def write_mock_sample_raw(
    task_dir: Path,
    task: Dict[str, str],
    state: Dict[str, object],
    sample: Dict[str, object],
) -> None:
    sample_id = str(sample["sample_id"])
    title = str(sample.get("title") or "")
    url = str(sample.get("url") or "")
    if "MOCK_FAIL" in title or "MOCK_FAIL" in url:
        raise BatchError("Mock Lingzao sample failure requested: " + sample_id)

    raw_dir = task_dir / "raw" / "lingzao" / "samples" / sample_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    note_path = raw_dir / "note-detail.json"
    invocation_path = raw_dir / "invocation.json"
    if note_path.exists() or invocation_path.exists():
        raise BatchError("sample raw output already exists: " + sample_id)

    captured_at = now_iso()
    note_detail = {
        "sample_id": sample_id,
        "source": {
            "source_type": "xhs_note",
            "original_url": url,
            "canonical_url": None,
        },
        "content": {
            "title": title,
            "body": "Mock batch note body for " + sample_id + ".",
            "tags": ["mock", "batch"],
            "images": [{"url": url + "/image-1", "alt": "mock image"}],
        },
        "author": {
            "id": "mock-batch-author",
            "name": "Mock Benchmark Account",
        },
        "published_at": sample.get("published_at") or "",
        "captured_at": captured_at,
        "metrics": sample.get("metrics") or {},
        "comments": {"status": "missing", "items": []},
        "transcript": {"status": "missing", "text": ""},
    }
    invocation = {
        "adapter": "mock_lingzao",
        "mode": "mock",
        "provider": "mock",
        "task_id": task["task_id"],
        "task_type": task["task_type"],
        "stage": state.get("current_stage"),
        "sample_id": sample_id,
        "operation": "collect_note",
        "command": None,
        "started_at": captured_at,
        "completed_at": captured_at,
        "exit_code": 0,
        "raw_files": [
            "raw/lingzao/samples/%s/note-detail.json" % sample_id,
            "raw/lingzao/samples/%s/invocation.json" % sample_id,
        ],
        "stdout_file": None,
        "stderr_file": None,
        "prompt_path": "prompts/lingzao-evidence-only.md",
        "source": url,
        "warnings": [],
        "source_url": url,
        "executed_at": captured_at,
        "outputs": [
            "raw/lingzao/samples/%s/note-detail.json" % sample_id,
            "raw/lingzao/samples/%s/invocation.json" % sample_id,
        ],
    }
    write_json_atomic(note_path, note_detail)
    write_json_atomic(invocation_path, invocation)


def is_batch_finished(progress: Dict[str, object]) -> bool:
    return progress["counts"]["pending"] == 0 and progress["counts"]["running"] == 0


def ensure_batch_can_finish(progress: Dict[str, object]) -> None:
    if progress["counts"]["succeeded"] < 1:
        raise BatchError("all selected samples failed")


def next_pending_sample(progress: Dict[str, object]) -> Dict[str, object]:
    for item in progress["samples"]:
        if item["status"] == "pending":
            return item
    raise BatchError("no pending samples")


def find_selected_sample(selected_samples: List[Dict[str, object]], sample_id: object) -> Dict[str, object]:
    for sample in selected_samples:
        if sample.get("sample_id") == sample_id:
            return sample
    raise BatchError("selected sample not found: " + str(sample_id))


def update_counts(progress: Dict[str, object]) -> None:
    progress["counts"] = count_statuses(progress["samples"])


def count_statuses(samples: List[Dict[str, object]]) -> Dict[str, int]:
    counts = {"pending": 0, "running": 0, "succeeded": 0, "failed": 0}
    for item in samples:
        counts[str(item["status"])] += 1
    return counts


def build_profile(task: Dict[str, str], source_url: str, captured_at: str) -> Dict[str, object]:
    return {
        "task_id": task["task_id"],
        "source_url": source_url,
        "profile_id": "mock-profile-" + task["task_id"],
        "nickname": "Mock Benchmark Account",
        "captured_at": captured_at,
        "metrics": {
            "followers": 120000,
            "notes": 128,
        },
    }


def build_posted_notes(source_url: str, captured_at: str) -> Dict[str, object]:
    notes = []
    for index in range(1, 7):
        notes.append(
            {
                "note_id": "note-%03d" % index,
                "title": "Mock benchmark note %03d" % index,
                "url": source_url.rstrip("/") + "/notes/%03d" % index,
                "published_at": "2026-07-%02dT09:00:00+08:00" % (index + 1),
                "metrics": {
                    "likes": 1000 - index * 53,
                    "saves": 360 - index * 17,
                    "comments": 90 - index * 5,
                    "shares": 40 - index,
                },
                "captured_at": captured_at,
            }
        )
    return {
        "source_url": source_url,
        "captured_at": captured_at,
        "notes": notes,
    }


def build_candidates(task: Dict[str, str], posted_notes: Dict[str, object], captured_at: str) -> Dict[str, object]:
    candidates = []
    for index, note in enumerate(posted_notes["notes"][:5], start=1):
        candidates.append(
            {
                "sample_id": "sample-%03d" % index,
                "title": note["title"],
                "url": note["url"],
                "published_at": note["published_at"],
                "metrics": note["metrics"],
                "selection_reason": "Mock ranking by recent engagement metrics.",
                "is_selected": False,
                "source_ref": "raw/lingzao/posted-notes.json#notes.%d" % (index - 1),
            }
        )
    return {
        "task_id": task["task_id"],
        "created_at": captured_at,
        "source_files": ["raw/lingzao/profile.json", "raw/lingzao/posted-notes.json"],
        "candidates": candidates,
    }


def validate_candidates(payload: Dict[str, object], candidates_path: Path) -> None:
    if not candidates_path.is_file():
        raise BatchError("sample-candidates.json does not exist")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) < 5:
        raise BatchError("sample-candidates.json must contain at least 5 candidates")
    seen = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise BatchError("candidate must be an object")
        sample_id = candidate.get("sample_id")
        if not sample_id:
            raise BatchError("candidate.sample_id is required")
        if sample_id in seen:
            raise BatchError("duplicate candidate sample_id: " + str(sample_id))
        seen.add(sample_id)
        for key in ("title", "url", "published_at", "metrics", "selection_reason", "is_selected"):
            if key not in candidate:
                raise BatchError("candidate.%s is required" % key)


def read_json(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, payload: Dict[str, object]) -> None:
    temp_file = path.with_name("." + path.name + ".tmp")
    temp_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_file.replace(path)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
