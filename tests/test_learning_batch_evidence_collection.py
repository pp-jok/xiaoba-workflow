import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args, cwd):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "xiaoba_workflow", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
    )


class LearningBatchEvidenceCollectionTests(unittest.TestCase):
    def test_first_run_initializes_progress_and_processes_one_sample(self):
        with temp_project() as root:
            task_dir = prepare_evidence_collection_task(root, ["sample-001", "sample-003"])

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            progress = read_json(task_dir / "analysis/batch-evidence-progress.json")
            self.assertEqual(progress["selected_sample_ids"], ["sample-001", "sample-003"])
            self.assertEqual(progress["samples"][0]["status"], "succeeded")
            self.assertEqual(progress["samples"][0]["attempts"], 1)
            self.assertEqual(progress["samples"][1]["status"], "pending")
            self.assertEqual(progress["counts"], {"pending": 1, "running": 0, "succeeded": 1, "failed": 0})
            self.assertIn("current_stage: evidence_collection", read_text(task_dir / "state.yaml"))

    def test_each_sample_writes_independent_raw_directory_with_selected_fields(self):
        with temp_project() as root:
            task_dir = prepare_evidence_collection_task(root, ["sample-001", "sample-003"])

            run_cli("run", str(task_dir), cwd=root)

            note = read_json(task_dir / "raw/lingzao/samples/sample-001/note-detail.json")
            invocation = read_json(task_dir / "raw/lingzao/samples/sample-001/invocation.json")
            selected = read_json(task_dir / "analysis/selected-samples.json")["selected_samples"][0]
            self.assertEqual(note["sample_id"], selected["sample_id"])
            self.assertEqual(note["source"]["original_url"], selected["url"])
            self.assertEqual(note["content"]["title"], selected["title"])
            self.assertEqual(note["published_at"], selected["published_at"])
            self.assertEqual(note["metrics"], selected["metrics"])
            self.assertEqual(invocation["sample_id"], "sample-001")
            self.assertFalse((task_dir / "raw/lingzao/note-detail.json").exists())

    def test_multiple_runs_process_in_selected_order_and_then_advance_to_evidence_normalization(self):
        with temp_project() as root:
            task_dir = prepare_evidence_collection_task(root, ["sample-003", "sample-001"])

            first = run_cli("run", str(task_dir), cwd=root)
            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            progress = read_json(task_dir / "analysis/batch-evidence-progress.json")
            self.assertEqual([item["sample_id"] for item in progress["samples"]], ["sample-001", "sample-003"])
            self.assertEqual(progress["counts"], {"pending": 0, "running": 0, "succeeded": 2, "failed": 0})
            self.assertIn("current_stage: evidence_normalization", read_text(task_dir / "state.yaml"))
            self.assertFalse((task_dir / "analysis/analysis.yaml").exists())

    def test_succeeded_samples_are_not_overwritten_on_resume(self):
        with temp_project() as root:
            task_dir = prepare_evidence_collection_task(root, ["sample-001", "sample-003"])
            run_cli("run", str(task_dir), cwd=root)
            note_before = read_text(task_dir / "raw/lingzao/samples/sample-001/note-detail.json")

            run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(read_text(task_dir / "raw/lingzao/samples/sample-001/note-detail.json"), note_before)

    def test_single_sample_failure_does_not_stop_pending_samples_and_partial_success_advances(self):
        with temp_project() as root:
            task_dir = prepare_evidence_collection_task(root, ["sample-001", "sample-002"])
            mark_selected_title(task_dir, "sample-001", "MOCK_FAIL broken sample")

            first = run_cli("run", str(task_dir), cwd=root)
            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            progress = read_json(task_dir / "analysis/batch-evidence-progress.json")
            self.assertEqual(progress["samples"][0]["status"], "failed")
            self.assertEqual(progress["samples"][1]["status"], "succeeded")
            self.assertEqual(progress["counts"], {"pending": 0, "running": 0, "succeeded": 1, "failed": 1})
            self.assertFalse((task_dir / "raw/lingzao/samples/sample-001/note-detail.json").exists())
            self.assertTrue((task_dir / "raw/lingzao/samples/sample-002/note-detail.json").exists())
            self.assertIn("current_stage: evidence_normalization", read_text(task_dir / "state.yaml"))

    def test_all_failed_blocks_and_keeps_evidence_collection(self):
        with temp_project() as root:
            task_dir = prepare_evidence_collection_task(root, ["sample-001", "sample-002"])
            mark_selected_title(task_dir, "sample-001", "MOCK_FAIL first")
            mark_selected_title(task_dir, "sample-002", "MOCK_FAIL second")

            first = run_cli("run", str(task_dir), cwd=root)
            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 1)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: blocked", state)
            self.assertIn("current_stage: evidence_collection", state)
            self.assertIn("all selected samples failed", state)

    def test_resume_from_pending_sample_after_interruption(self):
        with temp_project() as root:
            task_dir = prepare_evidence_collection_task(root, ["sample-001", "sample-003"])
            run_cli("run", str(task_dir), cwd=root)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((task_dir / "raw/lingzao/samples/sample-003/invocation.json").exists())
            self.assertIn("current_stage: evidence_normalization", read_text(task_dir / "state.yaml"))

    def test_progress_raw_inconsistency_and_incomplete_raw_are_rejected(self):
        with temp_project() as root:
            task_dir = prepare_evidence_collection_task(root, ["sample-001", "sample-003"])
            run_cli("run", str(task_dir), cwd=root)
            (task_dir / "raw/lingzao/samples/sample-001/invocation.json").unlink()

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("succeeded sample raw output is incomplete", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            task_dir = prepare_evidence_collection_task(root, ["sample-001", "sample-003"])
            raw_dir = task_dir / "raw/lingzao/samples/sample-001"
            raw_dir.mkdir(parents=True)
            write_json(raw_dir / "note-detail.json", {"partial": True})

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("pending sample has incomplete raw output", read_text(task_dir / "state.yaml"))

    def test_existing_complete_successful_batch_can_advance_safely(self):
        with temp_project() as root:
            task_dir = prepare_evidence_collection_task(root, ["sample-001"])
            first = run_cli("run", str(task_dir), cwd=root)
            self.assertEqual(first.returncode, 0, first.stderr)
            set_running_stage(task_dir, "evidence_collection", "evidence_normalization")

            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("current_stage: evidence_normalization", read_text(task_dir / "state.yaml"))

    def test_does_not_generate_standard_evidence_or_hot_learning_outputs(self):
        with temp_project() as root:
            task_dir = prepare_evidence_collection_task(root, ["sample-001"])

            run_cli("run", str(task_dir), cwd=root)

            self.assertFalse((task_dir / "evidence/evidence.yaml").exists())
            self.assertFalse((task_dir / "raw/hot-learning/analysis.md").exists())
            self.assertFalse((task_dir / "analysis/analysis.yaml").exists())
            self.assertFalse((task_dir / "content/generated-post.md").exists())


def prepare_evidence_collection_task(root, sample_ids):
    task_dir = create_task(root, "learning_batch", "https://example.com/user/1")
    run_cli("run", str(task_dir), cwd=root)
    run_cli("run", str(task_dir), cwd=root)
    result = run_cli("select-samples", str(task_dir), "--ids", *sample_ids, cwd=root)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return task_dir


def mark_selected_title(task_dir, sample_id, title):
    path = task_dir / "analysis/selected-samples.json"
    payload = read_json(path)
    for sample in payload["selected_samples"]:
        if sample["sample_id"] == sample_id:
            sample["title"] = title
    write_json(path, payload)


def temp_project():
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    shutil.copy(PROJECT_ROOT / "workflow.yaml", root / "workflow.yaml")
    return TempProject(temp, root)


class TempProject:
    def __init__(self, temp, root):
        self.temp = temp
        self.root = root

    def __enter__(self):
        return self.root

    def __exit__(self, exc_type, exc, tb):
        self.temp.cleanup()


def create_task(root, task_type, source_url=None):
    args = ["create-task", "--type", task_type]
    if source_url:
        args.extend(["--source-url", source_url])
    result = run_cli(*args, cwd=root)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    prefix = "Created task: "
    for line in result.stdout.splitlines():
        if line.startswith(prefix):
            return root / line[len(prefix) :]
    raise AssertionError(result.stdout)


def read_text(path):
    return path.read_text(encoding="utf-8")


def read_json(path):
    return json.loads(read_text(path))


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def set_running_stage(task_dir, current_stage, next_stage):
    state_path = task_dir / "state.yaml"
    lines = []
    for line in read_text(state_path).splitlines():
        if line.startswith("status:"):
            lines.append("status: running")
        elif line.startswith("current_stage:"):
            lines.append("current_stage: " + current_stage)
        elif line.startswith("next_stage:"):
            lines.append("next_stage: " + next_stage)
        elif line.startswith("waiting_for:"):
            lines.append("waiting_for: null")
        else:
            lines.append(line)
    state_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
