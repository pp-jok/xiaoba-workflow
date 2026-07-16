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


class LearningBatchEvidenceNormalizationTests(unittest.TestCase):
    def test_workflow_reaches_evidence_normalization_after_collection(self):
        with temp_project() as root:
            task_dir = prepare_batch_collection_complete(root, ["sample-001"])

            state = read_text(task_dir / "state.yaml")
            self.assertIn("current_stage: evidence_normalization", state)
            self.assertIn("next_stage: analysis", state)

    def test_single_run_normalizes_one_sample_with_shared_evidence_structure(self):
        with temp_project() as root:
            task_dir = prepare_batch_collection_complete(root, ["sample-001", "sample-003"])

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            evidence_path = task_dir / "evidence/samples/sample-001/evidence.yaml"
            evidence = read_json(evidence_path)
            progress = read_json(task_dir / "analysis/batch-evidence-normalization-progress.json")
            for key in ("sample_id", "normalization", "source", "facts", "basic_structure", "coverage", "missing", "warnings", "source_refs"):
                self.assertIn(key, evidence)
            self.assertEqual(evidence["sample_id"], "sample-001")
            self.assertEqual(evidence["source"]["original_url"], "https://example.com/user/1/notes/001")
            self.assertEqual(progress["samples"][0]["normalization_status"], "partially_normalized")
            self.assertEqual(progress["samples"][1]["normalization_status"], "pending")
            self.assertIn("current_stage: evidence_normalization", read_text(task_dir / "state.yaml"))

    def test_multiple_runs_finish_and_create_batch_index(self):
        with temp_project() as root:
            task_dir = prepare_batch_collection_complete(root, ["sample-001", "sample-003"])

            first = run_cli("run", str(task_dir), cwd=root)
            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            index = read_json(task_dir / "evidence/batch-evidence-index.json")
            self.assertEqual(index["selected_sample_ids"], ["sample-001", "sample-003"])
            self.assertEqual(index["analyzable_samples"], [])
            self.assertEqual(index["partially_analyzable_samples"], ["sample-001", "sample-003"])
            self.assertEqual(index["skipped_samples"], [])
            self.assertEqual(index["failed_samples"], [])
            self.assertEqual(index["evidence_paths"]["sample-001"], "evidence/samples/sample-001/evidence.yaml")
            self.assertTrue(index["warnings"])
            self.assertIn("current_stage: analysis", read_text(task_dir / "state.yaml"))
            self.assertFalse((task_dir / "analysis/analysis.yaml").exists())

    def test_collection_failed_sample_is_skipped_without_evidence(self):
        with temp_project() as root:
            task_dir = prepare_batch_collection_with_failure(root)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            progress = read_json(task_dir / "analysis/batch-evidence-normalization-progress.json")
            statuses = {item["sample_id"]: item["normalization_status"] for item in progress["samples"]}
            self.assertEqual(statuses["sample-001"], "skipped")
            self.assertEqual(statuses["sample-002"], "pending")
            self.assertFalse((task_dir / "evidence/samples/sample-001/evidence.yaml").exists())

    def test_partial_success_enters_analysis_and_all_unavailable_blocks(self):
        with temp_project() as root:
            task_dir = prepare_batch_collection_with_failure(root)
            first = run_cli("run", str(task_dir), cwd=root)
            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("current_stage: analysis", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            task_dir = prepare_all_collection_failed(root)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: blocked", state)
            self.assertIn("current_stage: evidence_normalization", state)
            self.assertIn("no normalized batch evidence", state)

    def test_sample_id_url_and_progress_file_inconsistency_block(self):
        with temp_project() as root:
            task_dir = prepare_batch_collection_complete(root, ["sample-001"])
            note_path = task_dir / "raw/lingzao/samples/sample-001/note-detail.json"
            note = read_json(note_path)
            note["sample_id"] = "sample-other"
            write_json(note_path, note)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("raw sample_id mismatch", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            task_dir = prepare_batch_collection_complete(root, ["sample-001"])
            note_path = task_dir / "raw/lingzao/samples/sample-001/note-detail.json"
            note = read_json(note_path)
            note["source"]["original_url"] = "https://example.com/other"
            write_json(note_path, note)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("raw source URL mismatch", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            task_dir = prepare_batch_collection_complete(root, ["sample-001"])
            progress = read_json(task_dir / "analysis/batch-evidence-progress.json")
            progress["selected_sample_ids"] = ["sample-other"]
            write_json(task_dir / "analysis/batch-evidence-progress.json", progress)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("collection progress selected_sample_ids mismatch", read_text(task_dir / "state.yaml"))

    def test_existing_evidence_is_reused_and_interruption_resumes_next_pending(self):
        with temp_project() as root:
            task_dir = prepare_batch_collection_complete(root, ["sample-001", "sample-003"])
            run_cli("run", str(task_dir), cwd=root)
            evidence_before = read_text(task_dir / "evidence/samples/sample-001/evidence.yaml")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(read_text(task_dir / "evidence/samples/sample-001/evidence.yaml"), evidence_before)
            self.assertTrue((task_dir / "evidence/samples/sample-003/evidence.yaml").exists())

    def test_invalid_existing_evidence_blocks(self):
        with temp_project() as root:
            task_dir = prepare_batch_collection_complete(root, ["sample-001"])
            evidence_dir = task_dir / "evidence/samples/sample-001"
            evidence_dir.mkdir(parents=True)
            write_json(evidence_dir / "evidence.yaml", {"sample_id": "sample-001"})

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("normalization is required", read_text(task_dir / "state.yaml"))


def prepare_batch_collection_complete(root, sample_ids):
    task_dir = prepare_selected_batch(root, sample_ids)
    for _ in sample_ids:
        result = run_cli("run", str(task_dir), cwd=root)
        if result.returncode != 0:
            raise AssertionError(result.stderr)
    return task_dir


def prepare_batch_collection_with_failure(root):
    task_dir = prepare_selected_batch(root, ["sample-001", "sample-002"])
    selected_path = task_dir / "analysis/selected-samples.json"
    selected = read_json(selected_path)
    selected["selected_samples"][0]["title"] = "MOCK_FAIL failed collection"
    write_json(selected_path, selected)
    run_cli("run", str(task_dir), cwd=root)
    run_cli("run", str(task_dir), cwd=root)
    return task_dir


def prepare_all_collection_failed(root):
    task_dir = prepare_selected_batch(root, ["sample-001"])
    selected_path = task_dir / "analysis/selected-samples.json"
    selected = read_json(selected_path)
    selected["selected_samples"][0]["title"] = "MOCK_FAIL failed collection"
    write_json(selected_path, selected)
    run_cli("run", str(task_dir), cwd=root)
    set_running_stage(task_dir, "evidence_normalization", "analysis")
    return task_dir


def prepare_selected_batch(root, sample_ids):
    task_dir = create_task(root, "learning_batch", "https://example.com/user/1")
    run_cli("run", str(task_dir), cwd=root)
    run_cli("run", str(task_dir), cwd=root)
    result = run_cli("select-samples", str(task_dir), "--ids", *sample_ids, cwd=root)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return task_dir


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
        elif line.startswith("  ") and ("type:" in line or "reason:" in line):
            continue
        else:
            lines.append(line)
    state_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
