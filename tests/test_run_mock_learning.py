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


class MockLearningRunTests(unittest.TestCase):
    def test_run_executes_task_intake_only_once(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning", "https://example.com/note/1")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("已完成：获取内容", result.stdout)
            self.assertNotIn("task_intake", result.stdout)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("current_stage: evidence_collection", state)
            self.assertFalse((task_dir / "raw/lingzao/note-detail.json").exists())

    def test_run_executes_evidence_collection_and_writes_raw_lingzao_files(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning", "https://example.com/note/1")
            run_cli("run", str(task_dir), cwd=root)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("已完成：获取内容", result.stdout)
            self.assertNotIn("evidence_collection", result.stdout)
            note_detail = json.loads(read_text(task_dir / "raw/lingzao/note-detail.json"))
            invocation = json.loads(read_text(task_dir / "raw/lingzao/invocation.json"))
            state = read_text(task_dir / "state.yaml")

            self.assertEqual(note_detail["source"]["original_url"], "https://example.com/note/1")
            self.assertEqual(invocation["adapter"], "mock_lingzao")
            self.assertEqual(invocation["mode"], "mock")
            self.assertEqual(invocation["task_id"], task_dir.name)
            self.assertIn("current_stage: evidence_normalization", state)

    def test_mock_adapter_does_not_write_downstream_outputs(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning", "https://example.com/note/1")
            run_cli("run", str(task_dir), cwd=root)
            run_cli("run", str(task_dir), cwd=root)

            self.assertFalse((task_dir / "evidence/evidence.yaml").exists())
            self.assertEqual([], list((task_dir / "analysis").iterdir()))
            self.assertEqual([], list((task_dir / "governance").iterdir()))
            self.assertEqual([], list((task_dir / "content").iterdir()))

    def test_generation_task_intake_runs_once(self):
        with temp_project() as root:
            task_dir = create_task(root, "generation")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("current_stage: context_assembly", read_text(task_dir / "state.yaml"))

    def test_waiting_blocked_and_completed_tasks_cannot_run(self):
        with temp_project() as root:
            waiting = create_task(root, "learning_batch", "https://example.com/user/1")
            run_cli("run", str(waiting), cwd=root)
            run_cli("run", str(waiting), cwd=root)
            waiting_result = run_cli("run", str(waiting), cwd=root)
            self.assertEqual(waiting_result.returncode, 1)
            self.assertIn("waiting_for_user", waiting_result.stderr)

            blocked = create_task(root, "learning", "https://example.com/note/1")
            run_cli("block", str(blocked), "--reason", "test", cwd=root)
            blocked_result = run_cli("run", str(blocked), cwd=root)
            self.assertEqual(blocked_result.returncode, 1)
            self.assertIn("blocked", blocked_result.stderr)

            completed = create_task(root, "learning", "https://example.com/note/1")
            for _ in range(7):
                run_cli("advance", str(completed), cwd=root)
            completed_result = run_cli("run", str(completed), cwd=root)
            self.assertEqual(completed_result.returncode, 1)
            self.assertIn("completed", completed_result.stderr)

    def test_unknown_stage_cannot_run(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning", "https://example.com/note/1")
            replace_line(task_dir / "state.yaml", "current_stage:", "current_stage: made_up_stage")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("Invalid current_stage", result.stderr)

    def test_mock_adapter_failure_blocks_without_advancing_stage(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning", "mock-fail://note")
            run_cli("run", str(task_dir), cwd=root)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: blocked", state)
            self.assertIn("current_stage: evidence_collection", state)
            self.assertIn("type: stage_failure", state)
            self.assertIn("Mock Lingzao failure requested", state)

    def test_repeated_evidence_collection_run_keeps_existing_raw_output(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning", "https://example.com/note/1")
            run_cli("run", str(task_dir), cwd=root)
            run_cli("run", str(task_dir), cwd=root)
            note_file = task_dir / "raw/lingzao/note-detail.json"
            original = read_text(note_file)

            replace_line(task_dir / "state.yaml", "current_stage:", "current_stage: evidence_collection")
            replace_line(task_dir / "state.yaml", "next_stage:", "next_stage: evidence_normalization")
            replace_line(task_dir / "state.yaml", "status:", "status: running")
            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(read_text(note_file), original)


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


def replace_line(path, prefix, replacement):
    lines = read_text(path).splitlines()
    updated = [replacement if line.startswith(prefix) else line for line in lines]
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")
