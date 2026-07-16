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


class MockHotLearningTests(unittest.TestCase):
    def test_analysis_stage_writes_raw_hot_learning_files_and_advances(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((task_dir / "raw/hot-learning/analysis.md").is_file())
            self.assertTrue((task_dir / "raw/hot-learning/invocation.json").is_file())
            self.assertIn("current_stage: analysis_normalization", read_text(task_dir / "state.yaml"))

    def test_analysis_markdown_contains_facts_inferences_and_evidence_refs(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            run_cli("run", str(task_dir), cwd=root)

            markdown = read_text(task_dir / "raw/hot-learning/analysis.md")

            self.assertIn("## Observable Facts", markdown)
            self.assertIn("## Inferences", markdown)
            self.assertIn("## Content Mechanisms", markdown)
            self.assertIn("Evidence reference: evidence.yaml#facts.title", markdown)
            self.assertIn("Confidence: medium", markdown)

    def test_invocation_json_records_context(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            run_cli("run", str(task_dir), cwd=root)

            invocation = read_json(task_dir / "raw/hot-learning/invocation.json")

            self.assertEqual(invocation["adapter"], "mock_hot_learning")
            self.assertTrue(invocation["mock"])
            self.assertEqual(invocation["task_id"], task_dir.name)
            self.assertEqual(invocation["stage"], "analysis")
            self.assertEqual(invocation["evidence_path"], "evidence/evidence.yaml")
            self.assertTrue(invocation["evidence_sample_id"].startswith("sample-"))
            self.assertEqual(invocation["prompt_path"], "prompts/hot-learning-analysis-only.md")
            self.assertIn("analyze evidence", invocation["allowed_actions"])
            self.assertIn("create formal rules", invocation["forbidden_actions"])
            self.assertEqual(invocation["outputs"], ["raw/hot-learning/analysis.md"])

    def test_partial_evidence_limitations_are_included_in_markdown(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            run_cli("run", str(task_dir), cwd=root)

            markdown = read_text(task_dir / "raw/hot-learning/analysis.md")

            self.assertIn("Missing comments", markdown)
            self.assertIn("Missing transcript", markdown)
            self.assertIn("Cannot judge real video shots without local video.", markdown)

    def test_missing_evidence_blocks_and_keeps_analysis_stage(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            (task_dir / "evidence/evidence.yaml").unlink()

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: blocked", state)
            self.assertIn("current_stage: analysis", state)
            self.assertIn("evidence.yaml", state)

    def test_invalid_evidence_blocks(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            write_json(task_dir / "evidence/evidence.yaml", {"sample_id": "x", "mechanisms": []})

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("forbidden evidence field", read_text(task_dir / "state.yaml"))
            self.assertIn("current_stage: analysis", read_text(task_dir / "state.yaml"))

    def test_normalization_failed_evidence_blocks(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            evidence_path = task_dir / "evidence/evidence.yaml"
            evidence = read_json(evidence_path)
            evidence["normalization"]["status"] = "normalization_failed"
            write_json(evidence_path, evidence)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("normalization_failed", read_text(task_dir / "state.yaml"))

    def test_adapter_does_not_modify_evidence_or_downstream_outputs(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            evidence_before = read_text(task_dir / "evidence/evidence.yaml")

            run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(read_text(task_dir / "evidence/evidence.yaml"), evidence_before)
            self.assertFalse((task_dir / "analysis/analysis.yaml").exists())
            self.assertEqual([], list((task_dir / "governance").iterdir()))
            self.assertEqual([], list((task_dir / "content").iterdir()))

    def test_mock_failure_blocks_without_complete_outputs(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            evidence_path = task_dir / "evidence/evidence.yaml"
            evidence = read_json(evidence_path)
            evidence["source"]["original_url"] = "mock-hot-fail://note"
            write_json(evidence_path, evidence)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: blocked", state)
            self.assertIn("current_stage: analysis", state)
            self.assertIn("Mock Hot Learning failure requested", state)
            self.assertFalse((task_dir / "raw/hot-learning/analysis.md").exists())
            self.assertFalse((task_dir / "raw/hot-learning/invocation.json").exists())

    def test_write_failure_does_not_leave_complete_success_outputs(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            os.mkdir(task_dir / "raw/hot-learning/.analysis.md.tmp")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertFalse((task_dir / "raw/hot-learning/analysis.md").exists())
            self.assertFalse((task_dir / "raw/hot-learning/invocation.json").exists())
            self.assertIn("current_stage: analysis", read_text(task_dir / "state.yaml"))

    def test_repeated_analysis_run_reuses_existing_raw_outputs(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            first = run_cli("run", str(task_dir), cwd=root)
            analysis_path = task_dir / "raw/hot-learning/analysis.md"
            invocation_path = task_dir / "raw/hot-learning/invocation.json"
            analysis_before = read_text(analysis_path)
            invocation_before = read_text(invocation_path)

            replace_line(task_dir / "state.yaml", "current_stage:", "current_stage: analysis")
            replace_line(task_dir / "state.yaml", "next_stage:", "next_stage: analysis_normalization")
            replace_line(task_dir / "state.yaml", "status:", "status: running")
            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(read_text(analysis_path), analysis_before)
            self.assertEqual(read_text(invocation_path), invocation_before)

    def test_once_run_does_not_continue_into_analysis_normalization(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)

            run_cli("run", str(task_dir), cwd=root)

            status = run_cli("task-status", str(task_dir), cwd=root)
            self.assertIn("current_stage: analysis_normalization", status.stdout)
            self.assertFalse((task_dir / "analysis/analysis.yaml").exists())

    def test_generation_needs_brief_and_learning_batch_completes(self):
        with temp_project() as root:
            generation = create_task(root, "generation")
            batch = create_task(root, "learning_batch", "https://example.com/user/1")

            generation_intake = run_cli("run", str(generation), cwd=root)
            generation_context = run_cli("run", str(generation), cwd=root)
            run_cli("run", str(batch), cwd=root)
            run_cli("run", str(batch), cwd=root)
            run_cli("select-samples", str(batch), "--ids", "sample-001", "sample-003", cwd=root)
            for _ in range(10):
                run_cli("run", str(batch), cwd=root)
            batch_status = run_cli("task-status", str(batch), cwd=root)
            completed_run = run_cli("run", str(batch), cwd=root)

            self.assertEqual(generation_intake.returncode, 0, generation_intake.stderr)
            self.assertEqual(generation_context.returncode, 1)
            self.assertIn("generation brief required", generation_context.stderr)
            self.assertIn("status: completed", batch_status.stdout)
            self.assertIn("current_stage: completed", batch_status.stdout)
            self.assertEqual(completed_run.returncode, 1)
            self.assertIn("Task is completed and cannot run", completed_run.stderr)


def prepare_analysis_task(root):
    task_dir = create_task(root, "learning", "https://example.com/note/1")
    run_cli("run", str(task_dir), cwd=root)
    run_cli("run", str(task_dir), cwd=root)
    run_cli("run", str(task_dir), cwd=root)
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


def read_json(path):
    return json.loads(read_text(path))


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def replace_line(path, prefix, replacement):
    lines = read_text(path).splitlines()
    updated = [replacement if line.startswith(prefix) else line for line in lines]
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")
