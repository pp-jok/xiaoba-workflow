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


class StateMachineTests(unittest.TestCase):
    def test_learning_advances_from_task_intake(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning", "https://example.com/note/1")

            result = run_cli("advance", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: running", state)
            self.assertIn("current_stage: evidence_collection", state)
            self.assertIn("next_stage: evidence_normalization", state)
            self.assertIn("  - task_intake", state)

    def test_learning_reaches_completed_without_generation_stage(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning", "https://example.com/note/1")

            outputs = []
            for _ in range(8):
                result = run_cli("advance", str(task_dir), cwd=root)
                outputs.append(read_text(task_dir / "state.yaml"))
                if "status: completed" in outputs[-1]:
                    break

            self.assertEqual(result.returncode, 0, result.stderr)
            final_state = outputs[-1]
            self.assertIn("status: completed", final_state)
            self.assertIn("current_stage: completed", final_state)
            self.assertNotIn("generation", "\n".join(outputs))

    def test_learning_batch_pauses_at_sample_selection(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning_batch", "https://example.com/user/1")

            run_cli("advance", str(task_dir), cwd=root)
            result = run_cli("advance", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: waiting_for_user", state)
            self.assertIn("current_stage: sample_selection", state)
            self.assertIn("type: sample_selection", state)
            self.assertIn("candidates_file: analysis/sample-candidates.json", state)

    def test_generation_pauses_at_topic_selection_and_review(self):
        with temp_project() as root:
            task_dir = create_task(root, "generation")

            run_cli("advance", str(task_dir), cwd=root)
            result = run_cli("advance", str(task_dir), cwd=root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("context_assembly must be executed with run", result.stderr)
            self.assertIn("current_stage: context_assembly", read_text(task_dir / "state.yaml"))

            run_cli("run", str(task_dir), cwd=root)
            run_cli("set-generation-brief", str(task_dir), "--brief", "补充生成需求", cwd=root)
            run_cli("run", str(task_dir), cwd=root)
            result = run_cli("run", str(task_dir), cwd=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("current_stage: topic_selection", read_text(task_dir / "state.yaml"))
            self.assertIn("status: waiting_for_user", read_text(task_dir / "state.yaml"))

            resume = run_cli("resume", str(task_dir), cwd=root)
            self.assertEqual(resume.returncode, 1)
            self.assertIn("select-topic", resume.stderr)
            self.assertIn("current_stage: topic_selection", read_text(task_dir / "state.yaml"))

    def test_waiting_for_user_rejects_advance_and_sample_selection_rejects_resume(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning_batch", "https://example.com/user/1")
            run_cli("advance", str(task_dir), cwd=root)
            run_cli("advance", str(task_dir), cwd=root)

            blocked_advance = run_cli("advance", str(task_dir), cwd=root)
            self.assertEqual(blocked_advance.returncode, 1)
            self.assertIn("waiting_for_user", blocked_advance.stderr)

            resumed = run_cli("resume", str(task_dir), cwd=root)
            self.assertEqual(resumed.returncode, 1)
            self.assertIn("select-samples", resumed.stderr)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: waiting_for_user", state)
            self.assertIn("current_stage: sample_selection", state)

    def test_non_human_stage_cannot_resume(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning", "https://example.com/note/1")

            result = run_cli("resume", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("not waiting_for_user", result.stderr)

    def test_blocked_task_cannot_advance_and_unblock_keeps_stage(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning", "https://example.com/note/1")

            block = run_cli("block", str(task_dir), "--reason", "needs review", cwd=root)
            self.assertEqual(block.returncode, 0, block.stderr)
            blocked_state = read_text(task_dir / "state.yaml")
            self.assertIn("status: blocked", blocked_state)
            self.assertIn("reason: needs review", blocked_state)

            advance = run_cli("advance", str(task_dir), cwd=root)
            self.assertEqual(advance.returncode, 1)
            self.assertIn("blocked", advance.stderr)

            unblock = run_cli("unblock", str(task_dir), cwd=root)
            self.assertEqual(unblock.returncode, 0, unblock.stderr)
            unblocked_state = read_text(task_dir / "state.yaml")
            self.assertIn("status: running", unblocked_state)
            self.assertIn("current_stage: task_intake", unblocked_state)
            self.assertIn("waiting_for: null", unblocked_state)

    def test_completed_task_cannot_advance(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning", "https://example.com/note/1")
            for _ in range(7):
                run_cli("advance", str(task_dir), cwd=root)

            result = run_cli("advance", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("already completed", result.stderr)

    def test_invalid_current_stage_is_rejected(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning", "https://example.com/note/1")
            replace_line(task_dir / "state.yaml", "current_stage:", "current_stage: made_up_stage")

            result = run_cli("advance", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("Invalid current_stage", result.stderr)

    def test_task_type_must_match_workflow(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning", "https://example.com/note/1")
            replace_line(task_dir / "state.yaml", "task_type:", "task_type: generation")

            result = run_cli("advance", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("task type mismatch", result.stderr)

    def test_missing_task_or_state_file_returns_clear_error(self):
        with temp_project() as root:
            missing = run_cli("advance", "tasks/missing", cwd=root)
            self.assertEqual(missing.returncode, 1)
            self.assertIn("Task directory not found", missing.stderr)

            task_dir = create_task(root, "learning", "https://example.com/note/1")
            (task_dir / "state.yaml").unlink()
            missing_state = run_cli("advance", str(task_dir), cwd=root)
            self.assertEqual(missing_state.returncode, 1)
            self.assertIn("Missing state.yaml", missing_state.stderr)

    def test_failed_state_write_keeps_original_state_file(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning", "https://example.com/note/1")
            original = read_text(task_dir / "state.yaml")
            os.mkdir(task_dir / ".state.yaml.tmp")

            result = run_cli("advance", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("Failed to write state.yaml", result.stderr)
            self.assertEqual(read_text(task_dir / "state.yaml"), original)


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
