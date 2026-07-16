import subprocess
import sys
import tempfile
import unittest
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "xiaoba_workflow", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(cwd or PROJECT_ROOT),
        env={"PYTHONPATH": str(PROJECT_ROOT)},
    )


class CliTests(unittest.TestCase):
    def test_help_command_lists_validate_project(self):
        result = run_cli("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("validate-project", result.stdout)

    def test_validate_project_succeeds_when_required_files_exist(self):
        result = run_cli("validate-project")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Project baseline is valid", result.stdout)

    def test_create_learning_task_writes_task_and_state_files(self):
        with temp_project() as tmp:
            result = run_cli(
                "create-task",
                "--type",
                "learning",
                "--source-url",
                "https://example.com/note/1",
                cwd=tmp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            task_dir = created_task_dir(result.stdout, tmp)
            task_yaml = (task_dir / "task.yaml").read_text()
            state_yaml = (task_dir / "state.yaml").read_text()

            self.assertIn("task_type: learning", task_yaml)
            self.assertIn("source_type: xhs_note", task_yaml)
            self.assertIn("value: https://example.com/note/1", task_yaml)
            self.assertIn("auto_generate: false", task_yaml)
            self.assertIn("status: running", state_yaml)
            self.assertIn("current_stage: task_intake", state_yaml)
            self.assertIn("current_step: transition", state_yaml)
            self.assertIn("next_stage: evidence_collection", state_yaml)

    def test_create_learning_batch_task(self):
        with temp_project() as tmp:
            result = run_cli(
                "create-task",
                "--type",
                "learning_batch",
                "--source-url",
                "https://example.com/user/1",
                cwd=tmp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            task_yaml = (created_task_dir(result.stdout, tmp) / "task.yaml").read_text()

            self.assertIn("task_type: learning_batch", task_yaml)
            self.assertIn("value: https://example.com/user/1", task_yaml)

    def test_create_generation_task_without_source_url(self):
        with temp_project() as tmp:
            result = run_cli("create-task", "--type", "generation", cwd=tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            task_yaml = (created_task_dir(result.stdout, tmp) / "task.yaml").read_text()

            self.assertIn("task_type: generation", task_yaml)
            self.assertIn("sources: []", task_yaml)
            self.assertIn("auto_generate: false", task_yaml)

    def test_create_task_rejects_invalid_task_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_cli("create-task", "--type", "invalid", cwd=tmp)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid choice", result.stderr)

    def test_create_learning_requires_source_url(self):
        with temp_project() as tmp:
            result = run_cli("create-task", "--type", "learning", cwd=tmp)

            self.assertEqual(result.returncode, 2)
            self.assertIn("--source-url is required for learning tasks", result.stderr)

    def test_created_task_directory_structure_is_complete(self):
        with temp_project() as tmp:
            result = run_cli(
                "create-task",
                "--type",
                "learning",
                "--source-url",
                "https://example.com/note/1",
                cwd=tmp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            task_dir = created_task_dir(result.stdout, tmp)
            expected_paths = [
                "task.yaml",
                "state.yaml",
                "feedback.md",
                "run-log.md",
                "raw/lingzao",
                "raw/hot-learning",
                "raw/personal-content",
                "evidence",
                "analysis",
                "governance",
                "content",
            ]
            for path in expected_paths:
                self.assertTrue((task_dir / path).exists(), path)

    def test_create_task_does_not_overwrite_existing_task(self):
        with temp_project() as tmp:
            first = run_cli(
                "create-task",
                "--type",
                "learning",
                "--source-url",
                "https://example.com/note/1",
                cwd=tmp,
            )
            second = run_cli(
                "create-task",
                "--type",
                "learning",
                "--source-url",
                "https://example.com/note/1",
                cwd=tmp,
            )

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            first_dir = created_task_dir(first.stdout, tmp)
            second_dir = created_task_dir(second.stdout, tmp)
            self.assertNotEqual(first_dir, second_dir)
            self.assertTrue(first_dir.exists())
            self.assertTrue(second_dir.exists())

    def test_task_status_reads_core_state(self):
        with temp_project() as tmp:
            create_result = run_cli(
                "create-task",
                "--type",
                "learning",
                "--source-url",
                "https://example.com/note/1",
                cwd=tmp,
            )
            task_dir = created_task_dir(create_result.stdout, tmp)

            result = run_cli("task-status", str(task_dir), cwd=tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("task_id:", result.stdout)
            self.assertIn("task_type: learning", result.stdout)
            self.assertIn("status: running", result.stdout)
            self.assertIn("current_stage: task_intake", result.stdout)

    def test_task_status_reports_missing_task_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_cli("task-status", "tasks/missing-task", cwd=tmp)

            self.assertEqual(result.returncode, 1)
            self.assertIn("Task directory not found", result.stderr)


def created_task_dir(stdout, root):
    prefix = "Created task: "
    for line in stdout.splitlines():
        if line.startswith(prefix):
            return Path(root) / line[len(prefix) :]
    raise AssertionError("create-task output did not include task path: " + stdout)


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
        return str(self.root)

    def __exit__(self, exc_type, exc, tb):
        self.temp.cleanup()
