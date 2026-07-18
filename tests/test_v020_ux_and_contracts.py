import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args, cwd=None, env_extra=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "xiaoba_workflow", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(cwd or PROJECT_ROOT),
        env=env,
    )


class V020UxAndContractsTests(unittest.TestCase):
    def test_hot_learning_runner_capabilities_and_mock_single_analysis(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            evidence_path = root / "evidence.yaml"
            output_dir = root / "out"
            evidence = {
                "sample_id": "sample-001",
                "normalization": {"status": "partially_normalized", "warnings": ["缺少评论"]},
                "source": {"original_url": "https://example.com/note/1", "author": "作者"},
                "facts": {
                    "title": "自媒体人快速用上 Codex 的 3 个场景",
                    "body": "拆视频、剪视频和做排版。",
                    "metrics": {"likes": 2418, "saves": 3444, "comments": 58, "shares": 710},
                },
                "coverage": {"comments": "available", "transcript": "available", "video_file": "unsupported"},
                "missing": ["video_file"],
                "warnings": [],
            }
            evidence_path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
            request = {
                "contract_version": "1.0",
                "operation": "analyze_single",
                "task_id": "task-runner",
                "input_refs": {"evidence": str(evidence_path.resolve())},
                "prompt": {"path": str((PROJECT_ROOT / "prompts/hot-learning-analysis-only.md").resolve()), "version": "test"},
                "language": "zh-CN",
                "output_dir": str(output_dir.resolve()),
            }
            request_path = root / "request.json"
            request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")

            caps = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "scripts/hot_learning_runner.py"), "--capabilities"],
                check=False,
                capture_output=True,
                text=True,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "scripts/hot_learning_runner.py"),
                    "--input",
                    str(request_path),
                    "--output",
                    str(output_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(caps.returncode, 0, caps.stderr)
            capabilities = json.loads(caps.stdout)
            self.assertEqual(capabilities["contract_version"], "1.0")
            self.assertIn("analyze_single", capabilities["operations"])
            self.assertIn("analyze_cross_sample", capabilities["operations"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output_dir / "analysis.md").is_file())
            self.assertTrue((output_dir / "runner-manifest.json").is_file())
            manifest = json.loads((output_dir / "runner-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["operation"], "analyze_single")
            self.assertEqual(manifest["provider"], "mock")
            self.assertIn("Evidence reference: evidence.yaml#facts.title", (output_dir / "analysis.md").read_text(encoding="utf-8"))

    def test_doctor_all_and_task_status_user_view(self):
        result = run_cli("doctor", "--all")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Xiaoba 核心工作流", result.stdout)
        self.assertIn("Lingzao", result.stdout)
        self.assertIn("Hot Learning", result.stdout)
        self.assertIn("自动发布", result.stdout)

        with temp_project() as root:
            created = run_cli("create-task", "--type", "learning", "--source-url", "https://example.com/note/1", cwd=root)
            task_dir = created_task_dir(created.stdout, root)
            status = run_cli("task-status", str(task_dir), cwd=root)
            technical = run_cli("task-status", str(task_dir), "--technical", cwd=root)

            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("任务：学习单条小红书笔记", status.stdout)
            self.assertIn("整体进度：0 /", status.stdout)
            self.assertIn("下一步建议：", status.stdout)
            self.assertEqual(technical.returncode, 0, technical.stderr)
            self.assertIn("task_type: learning", technical.stdout)
            self.assertIn("current_stage: task_intake", technical.stdout)

    def test_run_until_gate_completes_mock_learning_and_stops_at_generation_brief_gate(self):
        with temp_project() as root:
            learning = create_task(root, "learning", "https://example.com/note/1")

            completed = run_cli("run-until-gate", str(learning), cwd=root)

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("使用能力：Lingzao", completed.stdout)
            self.assertIn("使用能力：Hot Learning", completed.stdout)
            self.assertIn("使用能力：Personal Content", completed.stdout)
            self.assertIn("status: completed", (learning / "state.yaml").read_text(encoding="utf-8"))

            generation = create_task(root, "generation")
            waiting = run_cli("run-until-gate", str(generation), cwd=root)

            self.assertEqual(waiting.returncode, 0, waiting.stderr)
            state = (generation / "state.yaml").read_text(encoding="utf-8")
            self.assertIn("status: waiting_for_user", state)
            self.assertIn("generation_brief", state)
            self.assertIn("下一步建议：", waiting.stdout)

    def test_start_command_lists_guided_entry_points(self):
        result = run_cli("start")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("你想做什么？", result.stdout)
        self.assertIn("学习一条小红书笔记", result.stdout)
        self.assertIn("复盘一篇已发布内容", result.stdout)

    def test_lingzao_runner_v020_capabilities_include_comments_and_transcript(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts/lingzao_runner.py"), "--capabilities"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        capabilities = json.loads(result.stdout)
        self.assertEqual(capabilities["contract_version"], "1.0")
        self.assertIn("collect_comments", capabilities["operations"])
        self.assertIn("collect_transcript", capabilities["operations"])
        self.assertIn("video_file", capabilities["unsupported_outputs"])

    def test_request_changes_creates_feedback_candidate_without_auto_activation(self):
        with temp_project() as root:
            generation = create_task(root, "generation", brief="写一条 Codex 使用心得")
            run_cli("run", str(generation), cwd=root)
            run_cli("run", str(generation), cwd=root)
            run_cli("run", str(generation), cwd=root)
            run_cli("select-topic", str(generation), "--id", "topic-001", cwd=root)
            run_cli("run", str(generation), cwd=root)

            review = run_cli(
                "review-content",
                str(generation),
                "--decision",
                "request_changes",
                "--feedback",
                "请减少营销感，增加真实经历限制。",
                cwd=root,
            )

            self.assertEqual(review.returncode, 0, review.stderr)
            candidates = json.loads((generation / "feedback/governance-candidates.yaml").read_text(encoding="utf-8"))
            self.assertEqual(candidates["task_id"], generation.name)
            self.assertEqual(candidates["candidates"][0]["status"], "candidate")
            self.assertFalse(candidates["auto_activated"])
            self.assertIn("marketing_intensity", candidates["candidates"][0]["categories"])
            self.assertFalse((generation / "feedback/active-rules.json").exists())

            confirmed = run_cli(
                "confirm-feedback-rule",
                str(generation),
                "--candidate-id",
                "feedback-rule-001",
                "--decision",
                "confirm",
                cwd=root,
            )

            self.assertEqual(confirmed.returncode, 0, confirmed.stderr)
            result = json.loads((generation / "feedback/feedback-rule-001-confirmation.json").read_text(encoding="utf-8"))
            self.assertEqual(result["decision"], "confirm")
            self.assertFalse(result["auto_activated"])

    def test_post_publish_review_task_generates_suggestions_without_rule_state_changes(self):
        with temp_project() as root:
            task = create_task(root, "post_publish_review", "https://example.com/published/1")

            intake = run_cli("run", str(task), cwd=root)
            review = run_cli("run", str(task), cwd=root)

            self.assertEqual(intake.returncode, 0, intake.stderr)
            self.assertEqual(review.returncode, 0, review.stderr)
            payload = json.loads((task / "analysis/post-publish-review.yaml").read_text(encoding="utf-8"))
            self.assertEqual(payload["task_id"], task.name)
            self.assertEqual(payload["source"]["published_url"], "https://example.com/published/1")
            self.assertFalse(payload["auto_changed_rule_status"])
            self.assertFalse(payload["published"])
            self.assertIn("status: completed", (task / "state.yaml").read_text(encoding="utf-8"))

    def test_generation_topic_generation_can_use_external_fake_provider_contract(self):
        with temp_project() as root:
            runner = root / "fake_generation_provider.py"
            runner.write_text(
                textwrap.dedent(
                    """
                    import json
                    import sys
                    from pathlib import Path

                    args = sys.argv[1:]
                    request = json.loads(Path(args[args.index("--input") + 1]).read_text(encoding="utf-8"))
                    output = Path(args[args.index("--output") + 1])
                    output.mkdir(parents=True, exist_ok=True)
                    candidates = []
                    for index in range(1, 6):
                        candidates.append({
                            "topic_id": "topic-%03d" % index,
                            "title_direction": "外部 Provider 选题 %d" % index,
                            "core_point": "遵循 GenerationContext，不自动发布。",
                            "target_audience": None,
                            "content_goal": None,
                            "mechanism_refs": [],
                            "rule_refs": [],
                            "asset_refs": [],
                            "learning_source_refs": [],
                            "fit_reason": "external fake contract",
                            "originality_requirements": ["不得复制来源内容"],
                            "risks": [],
                            "limitations": [],
                            "selected": False,
                        })
                    (output / "topic-candidates.yaml").write_text(json.dumps({
                        "task_id": request["task_id"],
                        "context_path": "content/generation-context.yaml",
                        "candidates": candidates
                    }, ensure_ascii=False), encoding="utf-8")
                    (output / "runner-manifest.json").write_text(json.dumps({
                        "contract_version": "1.0",
                        "operation": "generate_topics",
                        "status": "succeeded"
                    }, ensure_ascii=False), encoding="utf-8")
                    """
                ),
                encoding="utf-8",
            )
            generation = create_task(root, "generation", brief="生成外部 provider 选题")
            env = {
                "XIAOBA_GENERATION_PROVIDER": "external",
                "XIAOBA_GENERATION_COMMAND": json.dumps([sys.executable, str(runner)]),
            }

            self.assertEqual(run_cli("run", str(generation), cwd=root, env_extra=env).returncode, 0)
            self.assertEqual(run_cli("run", str(generation), cwd=root, env_extra=env).returncode, 0)
            topic = run_cli("run", str(generation), cwd=root, env_extra=env)

            self.assertEqual(topic.returncode, 0, topic.stderr)
            candidates = json.loads((generation / "content/topic-candidates.json").read_text(encoding="utf-8"))
            response = json.loads((generation / "raw/personal-content/topic-generation-response.json").read_text(encoding="utf-8"))
            self.assertEqual(candidates["candidates"][0]["title_direction"], "外部 Provider 选题 1")
            self.assertEqual(response["adapter"], "external_generation_provider")
            self.assertFalse(response["published"])
            self.assertIn("current_stage: topic_selection", (generation / "state.yaml").read_text(encoding="utf-8"))

    def test_lingzao_real_video_cost_gate_confirm_collects_comments_transcript_and_evidence(self):
        with temp_project() as root:
            runner = write_fake_lingzao_cost_runner(root)
            task = create_task(root, "learning", "https://example.com/explore/video-1?type=video")
            env = {
                "XIAOBA_LINGZAO_PROVIDER": "real",
                "XIAOBA_LINGZAO_COMMAND": json.dumps([sys.executable, str(runner)]),
                "XIAOBA_LINGZAO_TIMEOUT": "5",
            }

            self.assertEqual(run_cli("run", str(task), cwd=root, env_extra=env).returncode, 0)
            collect = run_cli("run", str(task), cwd=root, env_extra=env)

            self.assertEqual(collect.returncode, 0, collect.stderr)
            state = (task / "state.yaml").read_text(encoding="utf-8")
            self.assertIn("status: waiting_for_user", state)
            self.assertIn("external_cost_confirmation", state)
            self.assertIn("collect_comments", state)
            self.assertIn("collect_transcript", state)
            self.assertEqual(run_cli("advance", str(task), cwd=root, env_extra=env).returncode, 1)
            self.assertEqual(run_cli("resume", str(task), cwd=root, env_extra=env).returncode, 1)

            confirmed = run_cli("confirm-external-cost", str(task), "--decision", "confirm", cwd=root, env_extra=env)
            self.assertEqual(confirmed.returncode, 0, confirmed.stderr)
            enriched = run_cli("run", str(task), cwd=root, env_extra=env)
            self.assertEqual(enriched.returncode, 0, enriched.stderr)

            note = json.loads((task / "raw/lingzao/note-detail.json").read_text(encoding="utf-8"))
            index = json.loads((task / "raw/lingzao/invocations/index.json").read_text(encoding="utf-8"))
            self.assertEqual(note["comments"]["status"], "available")
            self.assertEqual(note["transcript"]["status"], "available")
            self.assertEqual(note["coverage"]["video_file"], "unsupported")
            self.assertEqual([item["operation"] for item in index["invocations"]], ["collect_note", "collect_comments", "collect_transcript"])
            self.assertTrue((task / "raw/lingzao/invocations/note-detail.json").is_file())
            self.assertTrue((task / "raw/lingzao/invocations/comments.json").is_file())
            self.assertTrue((task / "raw/lingzao/invocations/transcript.json").is_file())

            normalized = run_cli("run", str(task), cwd=root, env_extra=env)
            self.assertEqual(normalized.returncode, 0, normalized.stderr)
            evidence = json.loads((task / "evidence/evidence.yaml").read_text(encoding="utf-8"))
            self.assertEqual(evidence["coverage"]["comments"], "available")
            self.assertEqual(evidence["coverage"]["transcript"], "available")
            self.assertEqual(evidence["coverage"]["video_file"], "unsupported")

    def test_lingzao_real_video_cost_gate_skip_marks_optional_evidence_skipped(self):
        with temp_project() as root:
            runner = write_fake_lingzao_cost_runner(root)
            task = create_task(root, "learning", "https://example.com/explore/video-2?type=video")
            env = {
                "XIAOBA_LINGZAO_PROVIDER": "real",
                "XIAOBA_LINGZAO_COMMAND": json.dumps([sys.executable, str(runner)]),
            }

            run_cli("run", str(task), cwd=root, env_extra=env)
            run_cli("run", str(task), cwd=root, env_extra=env)
            skipped = run_cli("confirm-external-cost", str(task), "--decision", "skip", cwd=root, env_extra=env)
            advanced = run_cli("run", str(task), cwd=root, env_extra=env)

            self.assertEqual(skipped.returncode, 0, skipped.stderr)
            self.assertEqual(advanced.returncode, 0, advanced.stderr)
            note = json.loads((task / "raw/lingzao/note-detail.json").read_text(encoding="utf-8"))
            self.assertEqual(note["comments"]["status"], "skipped")
            self.assertEqual(note["transcript"]["status"], "skipped")
            self.assertIn("current_stage: evidence_normalization", (task / "state.yaml").read_text(encoding="utf-8"))

    def test_lingzao_always_policy_still_requires_confirmation_without_auto_paid_opt_in(self):
        with temp_project() as root:
            runner = write_fake_lingzao_cost_runner(root)
            (root / "xiaoba.local.yaml").write_text(
                "learning:\n  collect_comments: always\n  collect_transcript: always\n",
                encoding="utf-8",
            )
            task = create_task(root, "learning", "https://example.com/explore/video-3?type=video")
            env = {
                "XIAOBA_LINGZAO_PROVIDER": "real",
                "XIAOBA_LINGZAO_COMMAND": json.dumps([sys.executable, str(runner)]),
            }

            self.assertEqual(run_cli("run", str(task), cwd=root, env_extra=env).returncode, 0)
            pending = run_cli("run", str(task), cwd=root, env_extra=env)

            self.assertEqual(pending.returncode, 0, pending.stderr)
            state = (task / "state.yaml").read_text(encoding="utf-8")
            self.assertIn("status: waiting_for_user", state)
            self.assertIn("external_cost_confirmation", state)
            self.assertFalse((task / "raw/lingzao/invocations/comments.json").exists())

    def test_lingzao_never_policy_marks_optional_outputs_skipped_without_cost_gate(self):
        with temp_project() as root:
            runner = write_fake_lingzao_cost_runner(root)
            (root / "xiaoba.local.yaml").write_text(
                "learning:\n  collect_comments: never\n  collect_transcript: never\n",
                encoding="utf-8",
            )
            task = create_task(root, "learning", "https://example.com/explore/video-4?type=video")
            env = {
                "XIAOBA_LINGZAO_PROVIDER": "real",
                "XIAOBA_LINGZAO_COMMAND": json.dumps([sys.executable, str(runner)]),
            }

            self.assertEqual(run_cli("run", str(task), cwd=root, env_extra=env).returncode, 0)
            advanced = run_cli("run", str(task), cwd=root, env_extra=env)

            self.assertEqual(advanced.returncode, 0, advanced.stderr)
            note = json.loads((task / "raw/lingzao/note-detail.json").read_text(encoding="utf-8"))
            self.assertEqual(note["comments"]["status"], "skipped")
            self.assertEqual(note["transcript"]["status"], "skipped")
            self.assertIn("current_stage: evidence_normalization", (task / "state.yaml").read_text(encoding="utf-8"))

    def test_lingzao_required_transcript_failure_blocks_evidence_collection(self):
        with temp_project() as root:
            runner = write_fake_lingzao_cost_runner(root)
            (root / "xiaoba.local.yaml").write_text(
                "learning:\n  transcript_required: true\n",
                encoding="utf-8",
            )
            task = create_task(root, "learning", "https://example.com/explore/fail-transcript?type=video")
            env = {
                "XIAOBA_LINGZAO_PROVIDER": "real",
                "XIAOBA_LINGZAO_COMMAND": json.dumps([sys.executable, str(runner)]),
            }

            self.assertEqual(run_cli("run", str(task), cwd=root, env_extra=env).returncode, 0)
            self.assertEqual(run_cli("run", str(task), cwd=root, env_extra=env).returncode, 0)
            self.assertEqual(run_cli("confirm-external-cost", str(task), "--decision", "confirm", cwd=root, env_extra=env).returncode, 0)
            blocked = run_cli("run", str(task), cwd=root, env_extra=env)

            self.assertEqual(blocked.returncode, 1)
            state = (task / "state.yaml").read_text(encoding="utf-8")
            self.assertIn("status: blocked", state)
            self.assertIn("current_stage: evidence_collection", state)
            self.assertIn("transcript is required", state)
            note = json.loads((task / "raw/lingzao/note-detail.json").read_text(encoding="utf-8"))
            self.assertEqual(note["transcript"]["status"], "failed")

    def test_external_generation_content_revision_one_and_two_then_approve(self):
        with temp_project() as root:
            runner = write_fake_generation_content_runner(root)
            generation = create_task(root, "generation", brief="生成完整外部正文")
            env = {
                "XIAOBA_GENERATION_PROVIDER": "external",
                "XIAOBA_GENERATION_COMMAND": json.dumps([sys.executable, str(runner)]),
                "XIAOBA_GENERATION_TIMEOUT": "5",
            }

            self.assertEqual(run_cli("run", str(generation), cwd=root, env_extra=env).returncode, 0)
            self.assertEqual(run_cli("run", str(generation), cwd=root, env_extra=env).returncode, 0)
            self.assertEqual(run_cli("run", str(generation), cwd=root, env_extra=env).returncode, 0)
            self.assertEqual(run_cli("select-topic", str(generation), "--id", "topic-001", cwd=root, env_extra=env).returncode, 0)
            first = run_cli("run", str(generation), cwd=root, env_extra=env)
            self.assertEqual(first.returncode, 0, first.stderr)
            first_package = json.loads((generation / "content/content-package.yaml").read_text(encoding="utf-8"))
            self.assertEqual(first_package["revision_number"], 1)
            self.assertTrue((generation / "content/external/revision-001/runner-manifest.json").is_file())

            change = run_cli(
                "review-content",
                str(generation),
                "--decision",
                "request_changes",
                "--feedback",
                "请降低营销感",
                cwd=root,
                env_extra=env,
            )
            self.assertEqual(change.returncode, 0, change.stderr)
            second = run_cli("run", str(generation), cwd=root, env_extra=env)
            self.assertEqual(second.returncode, 0, second.stderr)
            second_package = json.loads((generation / "content/content-package.yaml").read_text(encoding="utf-8"))
            calls = json.loads((root / "fake-generation-content-calls.json").read_text(encoding="utf-8"))

            self.assertEqual(second_package["revision_number"], 2)
            self.assertEqual(calls[-1]["operation"], "generate_content")
            self.assertEqual(calls[-1]["revision_number"], 2)
            self.assertTrue(calls[-1]["previous_content_ref"].endswith("content/revisions/revision-001/content-package.yaml"))
            self.assertTrue(calls[-1]["feedback_ref"].endswith("content/revisions/revision-001/review-decision.json"))
            self.assertTrue((generation / "content/external/revision-002/runner-manifest.json").is_file())
            self.assertFalse((generation / "published").exists())

            approved = run_cli("review-content", str(generation), "--decision", "approve", cwd=root, env_extra=env)
            self.assertEqual(approved.returncode, 0, approved.stderr)
            self.assertIn("status: completed", (generation / "state.yaml").read_text(encoding="utf-8"))


def temp_project():
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    for item in ("workflow.yaml", "templates", "prompts"):
        source = PROJECT_ROOT / item
        target = root / item
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy(source, target)
    (root / "tasks").mkdir()
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
        raise AssertionError(result.stderr)
    return created_task_dir(result.stdout, root)


def created_task_dir(stdout, root):
    prefix = "Created task: "
    for line in stdout.splitlines():
        if line.startswith(prefix):
            return Path(root) / line[len(prefix):]
    raise AssertionError("create-task output did not include task path: " + stdout)


def write_fake_lingzao_cost_runner(root: Path) -> Path:
    runner = root / "fake_lingzao_cost_runner.py"
    runner.write_text(
        textwrap.dedent(
            """
            import json
            import sys
            from datetime import datetime
            from pathlib import Path

            args = sys.argv[1:]
            if "--capabilities" in args:
                print(json.dumps({
                    "contract_version": "1.0",
                    "operations": ["collect_note", "collect_profile", "collect_posted_notes", "collect_comments", "collect_transcript"],
                    "unsupported_outputs": ["video_file"],
                    "dependencies": {},
                    "requires_auth": False
                }))
                raise SystemExit(0)
            request = json.loads(Path(args[args.index("--input") + 1]).read_text(encoding="utf-8"))
            out = Path(args[args.index("--output") + 1])
            out.mkdir(parents=True, exist_ok=True)
            now = datetime.now().astimezone().isoformat(timespec="seconds")
            op = request["operation"]
            source = request["source"]
            result = {"operation": op, "source": source, "warnings": []}
            if op == "collect_note":
                result["note"] = {
                    "id": "video-note-1",
                    "url": source,
                    "title": "视频笔记标题",
                    "body": "视频笔记正文",
                    "author": {"id": "author-1", "name": "作者"},
                    "published_at": "2026-05-18T14:53:08+00:00",
                    "metrics": {"likes": 2418, "saves": 3444, "comments": 58, "shares": 710},
                    "images": [],
                    "comments": {"status": "missing", "items": []},
                    "transcript": {"status": "missing", "text": None}
                }
            elif op == "collect_comments":
                result["comments"] = {"status": "available", "items": [{"text": "怎么安装呀"}]}
            elif op == "collect_transcript":
                if "fail-transcript" in source:
                    print("transcript failed without secret", file=sys.stderr)
                    raise SystemExit(2)
                result["transcript"] = {"status": "available", "text": "这是一段真实 runner 返回的逐字稿。"}
                result["video_file"] = {"status": "unsupported"}
            else:
                result["notes"] = []
            (out / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            (out / "runner-manifest.json").write_text(json.dumps({
                "contract_version": "1.0",
                "operation": op,
                "started_at": now,
                "completed_at": now,
                "status": "succeeded",
                "warnings": [],
                "source_files": []
            }, ensure_ascii=False), encoding="utf-8")
            """
        ),
        encoding="utf-8",
    )
    return runner


def write_fake_generation_content_runner(root: Path) -> Path:
    runner = root / "fake_generation_content_runner.py"
    runner.write_text(
        textwrap.dedent(
            """
            import json
            import sys
            from pathlib import Path

            args = sys.argv[1:]
            if "--capabilities" in args:
                print(json.dumps({"contract_version": "1.0", "operations": ["generate_topics", "generate_content"]}))
                raise SystemExit(0)
            request_path = Path(args[args.index("--input") + 1])
            request = json.loads(request_path.read_text(encoding="utf-8"))
            out = Path(args[args.index("--output") + 1])
            out.mkdir(parents=True, exist_ok=True)
            calls_path = Path(__file__).with_name("fake-generation-content-calls.json")
            calls = json.loads(calls_path.read_text(encoding="utf-8")) if calls_path.exists() else []
            calls.append(request)
            calls_path.write_text(json.dumps(calls, ensure_ascii=False), encoding="utf-8")
            if request["operation"] == "generate_topics":
                candidates = []
                for index in range(1, 6):
                    candidates.append({
                        "topic_id": "topic-%03d" % index,
                        "title_direction": "外部正文链路选题 %d" % index,
                        "core_point": "使用外部 provider 生成选题。",
                        "target_audience": None,
                        "content_goal": None,
                        "mechanism_refs": [],
                        "rule_refs": [],
                        "asset_refs": [],
                        "learning_source_refs": [],
                        "fit_reason": "external fake contract",
                        "originality_requirements": ["不得复制来源内容"],
                        "risks": [],
                        "limitations": [],
                        "selected": False,
                    })
                payload = {"task_id": request["task_id"], "context_path": "content/generation-context.yaml", "candidates": candidates}
                output_name = "topic-candidates.yaml"
            else:
                revision = request["revision_number"]
                payload = {
                    "task_id": request["task_id"],
                    "content_id": "content-" + request["task_id"].replace("task-", ""),
                    "status": "draft",
                    "revision_number": revision,
                    "previous_content_ref": request.get("previous_content_ref"),
                    "feedback_ref": request.get("feedback_ref"),
                    "platform": "xiaohongshu",
                    "selected_topic_id": "topic-001",
                    "title_options": ["外部正文 revision-%03d" % revision],
                    "recommended_title": "外部正文 revision-%03d" % revision,
                    "body": {
                        "hook": "外部 provider 生成的待审核开头。",
                        "sections": [
                            {"heading": "问题", "content": "不编造个人经历。"},
                            {"heading": "方法", "content": "保留 traceability。"}
                        ],
                        "closing": "待人工审核。",
                        "cta": "确认后再发布。"
                    },
                    "hashtags": ["小红书内容"],
                    "visual_plan": [],
                    "traceability": {"mechanism_refs": [], "rule_refs": [], "asset_refs": [], "learning_source_refs": []},
                    "originality": {"requirements": ["不得复制来源内容"], "notes": []},
                    "assumptions": ["需要人工确认。"],
                    "risks": [],
                    "limitations": ["真实模型未在线验证。"],
                    "review_questions": ["是否通过？"]
                }
                output_name = "content-package.yaml"
            (out / output_name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            (out / "runner-manifest.json").write_text(json.dumps({
                "contract_version": "1.0",
                "operation": request["operation"],
                "status": "succeeded"
            }, ensure_ascii=False), encoding="utf-8")
            """
        ),
        encoding="utf-8",
    )
    return runner
