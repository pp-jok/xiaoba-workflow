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


class LearningBatchAnalysisTests(unittest.TestCase):
    def test_workflow_analysis_advances_to_analysis_normalization(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_task(root, ["sample-001"])

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("current_stage: analysis_normalization", read_text(task_dir / "state.yaml"))
            self.assertIn("next_stage: cross_sample_aggregation", read_text(task_dir / "state.yaml"))

    def test_single_run_initializes_progress_and_processes_one_sample(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_task(root, ["sample-001", "sample-003"])

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            progress = read_json(task_dir / "analysis/batch-analysis-progress.json")
            self.assertEqual(progress["sample_ids"], ["sample-001", "sample-003"])
            self.assertEqual(progress["samples"][0]["analysis_status"], "succeeded")
            self.assertEqual(progress["samples"][1]["analysis_status"], "pending")
            self.assertEqual(progress["counts"], {"pending": 1, "succeeded": 1, "failed": 0, "skipped": 0})
            self.assertIn("current_stage: analysis", read_text(task_dir / "state.yaml"))

    def test_raw_analysis_directory_and_invocation_are_per_sample(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_task(root, ["sample-001"])

            run_cli("run", str(task_dir), cwd=root)

            analysis_md = read_text(task_dir / "raw/hot-learning/samples/sample-001/analysis.md")
            invocation = read_json(task_dir / "raw/hot-learning/samples/sample-001/invocation.json")
            self.assertIn("Sample ID: sample-001", analysis_md)
            self.assertIn("Evidence reference: evidence.yaml#facts.title", analysis_md)
            self.assertIn("Missing comments", analysis_md)
            self.assertEqual(invocation["adapter"], "mock_hot_learning")
            self.assertTrue(invocation["mock"])
            self.assertEqual(invocation["sample_id"], "sample-001")
            self.assertEqual(invocation["evidence_path"], "evidence/samples/sample-001/evidence.yaml")
            self.assertEqual(invocation["evidence_normalization_status"], "partially_normalized")
            self.assertFalse((task_dir / "raw/hot-learning/analysis.md").exists())

    def test_multiple_runs_complete_in_index_order(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_task(root, ["sample-001", "sample-003"])

            first = run_cli("run", str(task_dir), cwd=root)
            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            progress = read_json(task_dir / "analysis/batch-analysis-progress.json")
            self.assertEqual([item["sample_id"] for item in progress["samples"]], ["sample-001", "sample-003"])
            self.assertEqual(progress["counts"], {"pending": 0, "succeeded": 2, "failed": 0, "skipped": 0})
            self.assertIn("current_stage: analysis_normalization", read_text(task_dir / "state.yaml"))

    def test_single_sample_failure_does_not_block_pending_and_partial_success_advances(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_task(root, ["sample-001", "sample-003"])
            evidence_path = task_dir / "evidence/samples/sample-001/evidence.yaml"
            evidence = read_json(evidence_path)
            evidence["facts"]["title"] = "MOCK_HOT_FAIL analysis failure"
            write_json(evidence_path, evidence)

            first = run_cli("run", str(task_dir), cwd=root)
            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            progress = read_json(task_dir / "analysis/batch-analysis-progress.json")
            self.assertEqual(progress["samples"][0]["analysis_status"], "failed")
            self.assertEqual(progress["samples"][1]["analysis_status"], "succeeded")
            self.assertIn("current_stage: analysis_normalization", read_text(task_dir / "state.yaml"))
            self.assertFalse((task_dir / "raw/hot-learning/samples/sample-001/analysis.md").exists())

    def test_all_failed_or_skipped_blocks(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_task(root, ["sample-001"])
            evidence_path = task_dir / "evidence/samples/sample-001/evidence.yaml"
            evidence = read_json(evidence_path)
            evidence["facts"]["title"] = "MOCK_HOT_FAIL analysis failure"
            write_json(evidence_path, evidence)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("status: blocked", read_text(task_dir / "state.yaml"))
            self.assertIn("all batch analyses failed or skipped", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            task_dir = prepare_batch_analysis_task(root, ["sample-001"])
            index = read_json(task_dir / "evidence/batch-evidence-index.json")
            index["partially_analyzable_samples"] = []
            index["skipped_samples"] = ["sample-001"]
            index["evidence_paths"] = {}
            write_json(task_dir / "evidence/batch-evidence-index.json", index)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("all batch analyses failed or skipped", read_text(task_dir / "state.yaml"))

    def test_evidence_or_index_inconsistency_blocks(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_task(root, ["sample-001"])
            evidence = read_json(task_dir / "evidence/samples/sample-001/evidence.yaml")
            evidence["sample_id"] = "sample-other"
            write_json(task_dir / "evidence/samples/sample-001/evidence.yaml", evidence)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("evidence sample_id mismatch", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            task_dir = prepare_batch_analysis_task(root, ["sample-001"])
            index = read_json(task_dir / "evidence/batch-evidence-index.json")
            index["evidence_urls"] = {"sample-001": "https://example.com/other"}
            write_json(task_dir / "evidence/batch-evidence-index.json", index)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("index source URL mismatch", read_text(task_dir / "state.yaml"))

    def test_existing_success_raw_is_reused_and_incomplete_raw_blocks(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_task(root, ["sample-001", "sample-003"])
            run_cli("run", str(task_dir), cwd=root)
            analysis_before = read_text(task_dir / "raw/hot-learning/samples/sample-001/analysis.md")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(read_text(task_dir / "raw/hot-learning/samples/sample-001/analysis.md"), analysis_before)

        with temp_project() as root:
            task_dir = prepare_batch_analysis_task(root, ["sample-001"])
            raw_dir = task_dir / "raw/hot-learning/samples/sample-001"
            raw_dir.mkdir(parents=True)
            write_text(raw_dir / "analysis.md", "partial")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("Incomplete raw hot-learning output exists", read_text(task_dir / "state.yaml"))

    def test_no_standard_analysis_or_cross_sample_outputs_are_generated(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_task(root, ["sample-001"])

            run_cli("run", str(task_dir), cwd=root)

            self.assertFalse((task_dir / "analysis/analysis.yaml").exists())
            self.assertFalse((task_dir / "analysis/samples/sample-001/analysis.yaml").exists())
            self.assertFalse((task_dir / "analysis/cross-sample-aggregation.json").exists())
            self.assertFalse((task_dir / "content/generated-post.md").exists())


def prepare_batch_analysis_task(root, sample_ids):
    task_dir = create_task(root, "learning_batch", "https://example.com/user/1")
    run_cli("run", str(task_dir), cwd=root)
    run_cli("run", str(task_dir), cwd=root)
    result = run_cli("select-samples", str(task_dir), "--ids", *sample_ids, cwd=root)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    for _ in sample_ids:
        result = run_cli("run", str(task_dir), cwd=root)
        if result.returncode != 0:
            raise AssertionError(result.stderr)
    for _ in sample_ids:
        result = run_cli("run", str(task_dir), cwd=root)
        if result.returncode != 0:
            raise AssertionError(result.stderr)
    return task_dir


def temp_project():
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    shutil.copy(PROJECT_ROOT / "workflow.yaml", root / "workflow.yaml")
    shutil.copytree(PROJECT_ROOT / "prompts", root / "prompts")
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


def write_text(path, value):
    path.write_text(value, encoding="utf-8")


def read_json(path):
    return json.loads(read_text(path))


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
