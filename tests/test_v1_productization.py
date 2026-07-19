import os
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from xiaoba_workflow import runtime
from xiaoba_workflow import workspace as workspace_module


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args, cwd=None, env_extra=None, input_text=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "xiaoba_workflow", *args],
        cwd=str(cwd or PROJECT_ROOT),
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


class V1ProductizationTests(unittest.TestCase):
    def test_workspace_resolves_cli_env_and_default_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            env_workspace = Path(tmp) / "env-workspace"
            cli_workspace = Path(tmp) / "cli-workspace"

            default = workspace_module.resolve_workspace(None, {}, home)
            from_env = workspace_module.resolve_workspace(None, {"XIAOBA_WORKSPACE": str(env_workspace)}, home)
            from_cli = workspace_module.resolve_workspace(str(cli_workspace), {"XIAOBA_WORKSPACE": str(env_workspace)}, home)

            self.assertEqual(default.base, (home / ".xiaoba-workflow").resolve())
            self.assertEqual(from_env.base, env_workspace.resolve())
            self.assertEqual(from_cli.base, cli_workspace.resolve())

    def test_bootstrap_creates_safe_workspace_without_secrets_or_skill_pollution(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = workspace_module.bootstrap_workspace(Path(tmp) / "workspace")

            self.assertTrue(workspace.config_path.is_file())
            self.assertTrue(workspace.tasks_dir.is_dir())
            self.assertTrue(workspace.logs_dir.is_dir())
            self.assertTrue(workspace.project_root.joinpath("workflow.yaml").is_file())
            self.assertTrue(workspace.project_root.joinpath("prompts/hot-learning-analysis-only.md").is_file())
            config_text = workspace.config_path.read_text(encoding="utf-8")
            self.assertIn("mode: unavailable", config_text)
            self.assertIn("mode: codex_manual", config_text)
            self.assertIn("collect_comments: never", config_text)
            self.assertNotIn("API_KEY", config_text)
            self.assertFalse((PROJECT_ROOT / "tasks/task-v1-pollution-check").exists())

    def test_default_cli_enters_start_and_bootstraps_workspace_from_non_repo_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "user-workspace"
            outside = Path(tmp) / "outside"
            outside.mkdir()

            result = run_cli(
                cwd=outside,
                env_extra={"XIAOBA_WORKSPACE": str(workspace)},
                input_text="6\n",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Xiaoba 已完成首次初始化。", result.stdout)
            self.assertIn("你想做什么？", result.stdout)
            self.assertTrue((workspace / "config/xiaoba.local.yaml").is_file())
            self.assertTrue((workspace / "tasks").is_dir())
            self.assertFalse((outside / "tasks").exists())

    def test_start_can_create_demo_learning_task_only_after_user_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "user-workspace"
            outside = Path(tmp) / "outside"
            outside.mkdir()

            result = run_cli(
                "start",
                "--workspace",
                str(workspace),
                cwd=outside,
                input_text="1\n1\nhttps://example.com/real-link\n3\n",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("当前未配置 Lingzao", result.stdout)
            self.assertIn("演示流程", result.stdout)
            task_dirs = list((workspace / "tasks").glob("task-*"))
            self.assertEqual(len(task_dirs), 1)
            task_text = task_dirs[0].joinpath("task.yaml").read_text(encoding="utf-8")
            self.assertIn("execution_mode: demo", task_text)
            self.assertTrue(task_dirs[0].joinpath("raw/lingzao/demo-mode.json").is_file())

    def test_list_tasks_and_show_result_use_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "user-workspace"
            outside = Path(tmp) / "outside"
            outside.mkdir()
            create = run_cli(
                "start",
                "--workspace",
                str(workspace),
                cwd=outside,
                input_text="1\n4\nhttps://example.com/published\n",
            )
            self.assertEqual(create.returncode, 0, create.stderr)

            listed = run_cli("list-tasks", "--workspace", str(workspace), cwd=outside)
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertIn("最近任务", listed.stdout)

            task_dir = next((workspace / "tasks").glob("task-*"))
            shown = run_cli("show-result", str(task_dir), "--workspace", str(workspace), cwd=outside)
            self.assertEqual(shown.returncode, 0, shown.stderr)
            self.assertIn("复盘完成。", shown.stdout)

    def test_ordinary_cli_create_task_uses_workspace_from_outside_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            outside = Path(tmp) / "outside"
            outside.mkdir()

            result = run_cli(
                "create-task",
                "--type",
                "learning",
                "--source-url",
                "https://example.com/note/ordinary-cli",
                cwd=outside,
                env_extra={"XIAOBA_WORKSPACE": str(workspace)},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(list((workspace / "tasks").glob("task-*"))), 1)
            self.assertFalse((outside / "tasks").exists())

    def test_codex_manual_hot_learning_blocks_until_manual_analysis_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            outside = Path(tmp) / "outside"
            outside.mkdir()

            start = run_cli(
                "start",
                "--workspace",
                str(workspace),
                cwd=outside,
                input_text="1\n1\nhttps://example.com/note/manual\n1\n手工标题\n手工正文\n5\n",
            )

            self.assertEqual(start.returncode, 0, start.stderr)
            task_dir = next((workspace / "tasks").glob("task-*"))
            state_text = task_dir.joinpath("state.yaml").read_text(encoding="utf-8")
            self.assertIn("status: blocked", state_text)
            self.assertIn("current_stage: analysis", state_text)
            self.assertIn("Hot Learning is configured as codex_manual", state_text)
            self.assertFalse(task_dir.joinpath("raw/hot-learning/analysis.md").exists())
            self.assertFalse(task_dir.joinpath("analysis/analysis.yaml").exists())

            evidence = json.loads(task_dir.joinpath("evidence/evidence.yaml").read_text(encoding="utf-8"))
            markdown_path = Path(tmp) / "manual-analysis.md"
            markdown_path.write_text(runtime.render_mock_hot_learning_markdown(evidence), encoding="utf-8")
            imported = run_cli(
                "import-hot-learning-analysis",
                str(task_dir),
                "--markdown",
                str(markdown_path),
                "--workspace",
                str(workspace),
                cwd=outside,
            )

            self.assertEqual(imported.returncode, 0, imported.stderr)
            self.assertIn("status: running", task_dir.joinpath("state.yaml").read_text(encoding="utf-8"))
            self.assertTrue(task_dir.joinpath("raw/hot-learning/analysis.md").is_file())


if __name__ == "__main__":
    unittest.main()
