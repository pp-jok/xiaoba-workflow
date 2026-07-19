import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args, cwd=None, input_text=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "xiaoba_workflow", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(cwd or PROJECT_ROOT),
        input=input_text,
        env=env,
    )


class UxLiteTests(unittest.TestCase):
    def test_start_first_screen_shows_only_four_user_entries_without_technical_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_cli("start", "--workspace", tmp)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Xiaoba 已完成首次初始化。", result.stdout)
        self.assertIn("你想做什么？", result.stdout)
        self.assertIn("1. 新建任务", result.stdout)
        self.assertIn("2. 继续未完成任务", result.stdout)
        self.assertIn("3. 查看最近结果", result.stdout)
        first_screen = result.stdout.split("请选择", 1)[0]
        self.assertNotIn("task type", first_screen)
        self.assertNotIn("provider", first_screen)
        self.assertNotIn("runner", first_screen)
        self.assertNotIn("YAML", first_screen)

    def test_start_learning_creates_task_runs_to_completed_and_prints_summary(self):
        with temp_project() as root:
            result = run_cli("start", "--workspace", str(root), cwd=root, input_text="1\n1\nhttps://example.com/note/1\n3\n")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("演示结果。", result.stdout)
            self.assertIn("本次得到：", result.stdout)
            self.assertIn("使用能力：", result.stdout)
            self.assertIn("Lingzao：获取公开内容", result.stdout)
            self.assertNotIn("current_stage", result.stdout)
            self.assertEqual(len(list((root / "tasks").glob("task-*"))), 1)

    def test_start_generation_without_personal_content_blocks_before_topics(self):
        with temp_project() as root:
            result = run_cli("start", "--workspace", str(root), cwd=root, input_text="1\n3\n生成一篇小红书帖子\n")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Personal Content is not configured", result.stdout)
            self.assertIn("任务暂停在：准备个人规则", result.stdout)
            self.assertNotIn("topic-001", result.stdout)
            self.assertNotIn("已生成", result.stdout)
            self.assertNotIn("current_stage", result.stdout)
            task = next((root / "tasks").glob("task-*"))
            state = (task / "state.yaml").read_text(encoding="utf-8")
            self.assertIn("status: blocked", state)
            self.assertIn("current_stage: context_assembly", state)
            self.assertFalse((task / "content/topic-candidates.json").exists())

    def test_start_generation_without_personal_content_cannot_approve_fake_content(self):
        with temp_project() as root:
            result = run_cli("start", "--workspace", str(root), cwd=root, input_text="1\n3\n生成一篇小红书帖子\n1\n1\n")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Personal Content is not configured", result.stdout)
            self.assertNotIn("已选择选题。", result.stdout)
            self.assertNotIn("正文已经生成。", result.stdout)
            self.assertNotIn("内容已完成审核。", result.stdout)
            self.assertNotIn("topic-001", result.stdout)
            task = next((root / "tasks").glob("task-*"))
            state = (task / "state.yaml").read_text(encoding="utf-8")
            self.assertIn("status: blocked", state)
            self.assertFalse((task / "content/review-decision.json").exists())

    def test_start_generation_without_personal_content_cannot_enter_revision_flow(self):
        with temp_project() as root:
            result = run_cli(
                "start",
                "--workspace",
                str(root),
                cwd=root,
                input_text="1\n3\n生成一篇小红书帖子\n1\n2\n请加强安装步骤\n1\n",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Personal Content is not configured", result.stdout)
            self.assertNotIn("请告诉我需要修改什么。", result.stdout)
            self.assertNotIn("内容已完成审核。", result.stdout)
            task = next((root / "tasks").glob("task-*"))
            self.assertFalse((task / "content/revisions/revision-001/content-package.yaml").exists())
            self.assertFalse((task / "content/revisions/revision-002/content-package.yaml").exists())
            state = (task / "state.yaml").read_text(encoding="utf-8")
            self.assertIn("status: blocked", state)

    def test_start_invalid_choice_reprompts_one_question_at_a_time(self):
        with temp_project() as root:
            result = run_cli("start", "--workspace", str(root), cwd=root, input_text="9\n1\n4\nhttps://example.com/published/1\n")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("请输入 1 到 6。", result.stdout)
            self.assertIn("复盘完成。", result.stdout)

    def test_task_status_default_hides_internal_stage_and_technical_shows_it(self):
        with temp_project() as root:
            task = create_task(root, "learning", "https://example.com/note/1")

            default = run_cli("task-status", str(task), cwd=root)
            technical = run_cli("task-status", str(task), "--technical", cwd=root)

            self.assertEqual(default.returncode, 0, default.stderr)
            self.assertIn("整体进度：", default.stdout)
            self.assertIn("1. 获取内容", default.stdout)
            self.assertNotIn("current_stage:", default.stdout)
            self.assertEqual(technical.returncode, 0, technical.stderr)
            self.assertIn("current_stage: task_intake", technical.stdout)

    def test_run_default_uses_user_stage_and_technical_keeps_internal_stage(self):
        with temp_project() as root:
            task = create_task(root, "learning", "https://example.com/note/1")

            default = run_cli("run", str(task), cwd=root)
            technical = run_cli("run", str(task), "--technical", cwd=root)

            self.assertEqual(default.returncode, 0, default.stderr)
            self.assertIn("已完成：获取内容", default.stdout)
            self.assertNotIn("task_intake", default.stdout)
            self.assertEqual(technical.returncode, 0, technical.stderr)
            self.assertIn("Ran stage: evidence_collection", technical.stdout)

    def test_setup_creates_conservative_local_config_without_secret_and_refuses_overwrite(self):
        with temp_project() as root:
            first = run_cli("setup", "--workspace", str(root), cwd=root, input_text="6\n")
            second = run_cli("setup", "--workspace", str(root), cwd=root, input_text="6\n")

            self.assertEqual(first.returncode, 0, first.stderr)
            config_path = root / "config/xiaoba.local.yaml"
            self.assertTrue(config_path.is_file())
            config_text = config_path.read_text(encoding="utf-8")
            self.assertIn("collect_comments: never", config_text)
            self.assertIn("collect_transcript: ask", config_text)
            self.assertIn("allow_auto_paid_calls: false", config_text)
            self.assertIn("mode: unavailable", config_text)
            self.assertNotIn("API_KEY", config_text)
            self.assertEqual(second.returncode, 0, second.stderr)


def temp_project():
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    for item in ("workflow.yaml", "templates", "prompts", "scripts", "xiaoba.local.example.yaml", ".gitignore"):
        source = PROJECT_ROOT / item
        target = root / item
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy(source, target)
    (root / "tasks").mkdir(exist_ok=True)
    return TempProject(temp, root)


class TempProject:
    def __init__(self, temp, root):
        self.temp = temp
        self.root = root

    def __enter__(self):
        return self.root

    def __exit__(self, exc_type, exc, tb):
        self.temp.cleanup()


def create_task(root, task_type, source_url=None, brief=None):
    args = ["create-task", "--type", task_type]
    if source_url:
        args.extend(["--source-url", source_url])
    if brief:
        args.extend(["--brief", brief])
    result = run_cli(*args, cwd=root)
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    prefix = "Created task: "
    for line in result.stdout.splitlines():
        if line.startswith(prefix):
            return root / line[len(prefix):]
    raise AssertionError("created task path not found: " + result.stdout)
