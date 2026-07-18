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


class LearningBatchAnalysisNormalizationTests(unittest.TestCase):
    def test_single_run_normalizes_one_sample(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_complete(root, ["sample-001", "sample-003"])

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            progress = read_json(task_dir / "analysis/batch-analysis-normalization-progress.json")
            self.assertEqual(progress["sample_ids"], ["sample-001", "sample-003"])
            self.assertEqual(progress["samples"][0]["normalization_status"], "normalized")
            self.assertEqual(progress["samples"][1]["normalization_status"], "pending")
            self.assertEqual(progress["counts"], {"pending": 1, "normalized": 1, "partially_normalized": 0, "failed": 0, "skipped": 0})
            self.assertTrue((task_dir / "analysis/samples/sample-001/analysis.yaml").is_file())
            self.assertFalse((task_dir / "analysis/samples/sample-003/analysis.yaml").exists())
            self.assertIn("current_stage: analysis_normalization", read_text(task_dir / "state.yaml"))

    def test_analysis_package_uses_shared_structure_and_sample_refs(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_complete(root, ["sample-001"])

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            analysis = read_json(task_dir / "analysis/samples/sample-001/analysis.yaml")
            for key in ("sample_id", "normalization", "mechanisms", "transfer", "rule_suggestions", "asset_suggestions", "content_opportunities", "questions"):
                self.assertIn(key, analysis)
            self.assertEqual(analysis["sample_id"], "sample-001")
            first = analysis["mechanisms"][0]
            self.assertEqual(first["observed_facts"][0]["evidence_ref"], "evidence.yaml#facts.title")
            self.assertEqual(first["inferences"][0]["raw_analysis_ref"]["file"], "raw/hot-learning/samples/sample-001/analysis.md")
            self.assertFalse((task_dir / "analysis/analysis.yaml").exists())

    def test_partial_raw_analysis_normalizes_and_preserves_limitations(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_complete(root, ["sample-001"])
            raw_path = task_dir / "raw/hot-learning/samples/sample-001/analysis.md"
            markdown = read_text(raw_path).split("### 机制 2", 1)[0]
            markdown += "\n## 缺失信息与限制\n- 缺失 comments\n- 缺失 transcript\n"
            write_text(raw_path, markdown)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            analysis = read_json(task_dir / "analysis/samples/sample-001/analysis.yaml")
            self.assertEqual(analysis["normalization"]["status"], "partially_normalized")
            self.assertIn("缺失 comments", analysis["questions"])

    def test_raw_failed_sample_is_skipped_and_partial_success_advances(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_complete(root, ["sample-001", "sample-003"])
            progress = read_json(task_dir / "analysis/batch-analysis-progress.json")
            progress["samples"][0]["analysis_status"] = "failed"
            progress["samples"][0]["error"] = "mock upstream failure"
            progress["samples"][1]["analysis_status"] = "succeeded"
            progress["counts"] = {"pending": 0, "succeeded": 1, "failed": 1, "skipped": 0}
            write_json(task_dir / "analysis/batch-analysis-progress.json", progress)
            shutil.rmtree(task_dir / "raw/hot-learning/samples/sample-001")

            first = run_cli("run", str(task_dir), cwd=root)
            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            norm_progress = read_json(task_dir / "analysis/batch-analysis-normalization-progress.json")
            statuses = {item["sample_id"]: item["normalization_status"] for item in norm_progress["samples"]}
            self.assertEqual(statuses["sample-001"], "skipped")
            self.assertEqual(statuses["sample-003"], "normalized")
            self.assertIn("current_stage: cross_sample_aggregation", read_text(task_dir / "state.yaml"))

    def test_single_sample_normalization_failure_does_not_stop_pending(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_complete(root, ["sample-001", "sample-003"])
            write_text(task_dir / "raw/hot-learning/samples/sample-001/analysis.md", "# Empty\n\nNo mechanisms.\n")

            first = run_cli("run", str(task_dir), cwd=root)
            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            progress = read_json(task_dir / "analysis/batch-analysis-normalization-progress.json")
            self.assertEqual(progress["samples"][0]["normalization_status"], "failed")
            self.assertEqual(progress["samples"][1]["normalization_status"], "normalized")
            self.assertIn("current_stage: cross_sample_aggregation", read_text(task_dir / "state.yaml"))

    def test_all_unavailable_blocks(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_complete(root, ["sample-001"])
            write_text(task_dir / "raw/hot-learning/samples/sample-001/analysis.md", "# Empty\n\nNo mechanisms.\n")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: blocked", state)
            self.assertIn("current_stage: analysis_normalization", state)
            self.assertIn("no normalized batch analysis", state)

    def test_inconsistency_blocks(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_complete(root, ["sample-001"])
            evidence = read_json(task_dir / "evidence/samples/sample-001/evidence.yaml")
            evidence["sample_id"] = "sample-other"
            write_json(task_dir / "evidence/samples/sample-001/evidence.yaml", evidence)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("evidence sample_id mismatch", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            task_dir = prepare_batch_analysis_complete(root, ["sample-001"])
            index = read_json(task_dir / "evidence/batch-evidence-index.json")
            index["evidence_paths"]["sample-001"] = "evidence/samples/sample-other/evidence.yaml"
            write_json(task_dir / "evidence/batch-evidence-index.json", index)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("analysis progress evidence_path mismatch", read_text(task_dir / "state.yaml"))

    def test_existing_analysis_reused_and_resume_creates_batch_index(self):
        with temp_project() as root:
            task_dir = prepare_batch_analysis_complete(root, ["sample-001", "sample-003"])
            run_cli("run", str(task_dir), cwd=root)
            first_analysis = read_text(task_dir / "analysis/samples/sample-001/analysis.yaml")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(read_text(task_dir / "analysis/samples/sample-001/analysis.yaml"), first_analysis)
            index = read_json(task_dir / "analysis/batch-analysis-index.json")
            self.assertEqual(index["selected_sample_ids"], ["sample-001", "sample-003"])
            self.assertEqual(index["partially_normalized_analyses"], [])
            self.assertEqual(index["analysis_paths"]["sample-001"], "analysis/samples/sample-001/analysis.yaml")
            self.assertIn("current_stage: cross_sample_aggregation", read_text(task_dir / "state.yaml"))

    def test_no_cross_sample_outputs_and_single_learning_still_works(self):
        with temp_project() as root:
            batch_dir = prepare_batch_analysis_complete(root, ["sample-001"])

            result = run_cli("run", str(batch_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((batch_dir / "analysis/cross-sample-aggregation.json").exists())
            self.assertFalse((batch_dir / "raw/personal-content/mechanism-intake-request.json").exists())

            learning_dir = create_task(root, "learning", "https://example.com/note/1")
            for _ in range(5):
                learning_result = run_cli("run", str(learning_dir), cwd=root)
                self.assertEqual(learning_result.returncode, 0, learning_result.stderr)
            self.assertTrue((learning_dir / "analysis/analysis.yaml").is_file())
            self.assertIn("current_stage: mechanism_intake", read_text(learning_dir / "state.yaml"))


def prepare_batch_analysis_complete(root, sample_ids):
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
