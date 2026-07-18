import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args, cwd, env_extra=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "xiaoba_workflow", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
    )


class GenerationFlowTests(unittest.TestCase):
    def test_generation_task_intake_advances_once(self):
        with temp_project() as root:
            task_dir = create_task(root, "generation", brief="为包子 IP 生成小红书选题")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("current_stage: context_assembly", state)
            self.assertFalse((task_dir / "content/generation-context.yaml").exists())

    def test_create_task_with_brief_and_set_brief_when_missing(self):
        with temp_project() as root:
            with_brief = create_task(root, "generation", brief="面向独立开发者的包子 IP 选题")
            brief = read_json(with_brief / "content/generation-brief.json")
            self.assertEqual(brief["request"], "面向独立开发者的包子 IP 选题")
            self.assertEqual(brief["platform"], "xiaohongshu")
            self.assertIsNone(brief["target_audience"])
            self.assertEqual(brief["forbidden"], [])

            missing = create_task(root, "generation")
            run_cli("run", str(missing), cwd=root)
            result = run_cli("run", str(missing), cwd=root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("status: waiting_for_user", read_text(missing / "state.yaml"))
            self.assertIn("generation_brief", read_text(missing / "state.yaml"))
            self.assertIn("Generation brief is required", read_text(missing / "state.yaml"))

            set_result = run_cli("set-generation-brief", str(missing), "--brief", "补充一个生成需求", cwd=root)
            self.assertEqual(set_result.returncode, 0, set_result.stderr)
            self.assertIn("status: running", read_text(missing / "state.yaml"))
            self.assertEqual(read_json(missing / "content/generation-brief.json")["request"], "补充一个生成需求")

    def test_generation_context_assembly_cannot_be_manually_advanced_before_waiting(self):
        with temp_project() as root:
            generation = create_task(root, "generation")
            intake = run_cli("run", str(generation), cwd=root)
            before = read_text(generation / "state.yaml")

            result = run_cli("advance", str(generation), cwd=root)

            self.assertEqual(intake.returncode, 0, intake.stderr)
            self.assertEqual(result.returncode, 1)
            self.assertIn("context_assembly must be executed with run", result.stderr)
            self.assertEqual(read_text(generation / "state.yaml"), before)
            self.assertFalse((generation / "content/topic-candidates.json").exists())
            self.assertFalse((generation / "content/generation-context.yaml").exists())

    def test_generation_brief_waiting_requires_set_brief_before_context_run(self):
        with temp_project() as root:
            generation = create_task(root, "generation")
            run_cli("run", str(generation), cwd=root)
            missing_brief = run_cli("run", str(generation), cwd=root)
            self.assertEqual(missing_brief.returncode, 1)
            self.assertIn("status: waiting_for_user", read_text(generation / "state.yaml"))
            self.assertIn("generation_brief", read_text(generation / "state.yaml"))

            advance = run_cli("advance", str(generation), cwd=root)
            resume = run_cli("resume", str(generation), cwd=root)
            self.assertEqual(advance.returncode, 1)
            self.assertIn("waiting_for_user", advance.stderr)
            self.assertEqual(resume.returncode, 1)
            self.assertIn("Current stage is not a human gate", resume.stderr)

            set_brief = run_cli("set-generation-brief", str(generation), "--brief", "补充一个生成需求", cwd=root)
            self.assertEqual(set_brief.returncode, 0, set_brief.stderr)
            self.assertIn("status: running", read_text(generation / "state.yaml"))

            context = run_cli("run", str(generation), cwd=root)
            self.assertEqual(context.returncode, 0, context.stderr)
            self.assertIn("current_stage: topic_generation", read_text(generation / "state.yaml"))
            self.assertTrue((generation / "content/generation-context.yaml").is_file())

    def test_generation_context_assembly_with_existing_brief_still_requires_run(self):
        with temp_project() as root:
            generation = create_task(root, "generation", brief="已有需求")
            intake = run_cli("run", str(generation), cwd=root)
            before = read_text(generation / "state.yaml")

            advance = run_cli("advance", str(generation), cwd=root)

            self.assertEqual(intake.returncode, 0, intake.stderr)
            self.assertEqual(advance.returncode, 1)
            self.assertIn("context_assembly must be executed with run", advance.stderr)
            self.assertEqual(read_text(generation / "state.yaml"), before)

            context = run_cli("run", str(generation), cwd=root)
            self.assertEqual(context.returncode, 0, context.stderr)
            self.assertIn("current_stage: topic_generation", read_text(generation / "state.yaml"))
            self.assertTrue((generation / "content/generation-context.yaml").is_file())

    def test_real_personal_content_generation_context_uses_only_active_rules(self):
        with temp_project() as root:
            generation = create_task(root, "generation", brief="围绕 Codex 自媒体提效生成选题")
            runner = write_fake_personal_content_generation_cli(root)
            env = {
                "XIAOBA_PERSONAL_CONTENT_PROVIDER": "real",
                "XIAOBA_PERSONAL_CONTENT_COMMAND": json.dumps([sys.executable, str(runner)]),
                "XIAOBA_PERSONAL_CONTENT_WORKSPACE": str(root / "pc-workspace"),
            }

            intake = run_cli("run", str(generation), cwd=root, env_extra=env)
            context_result = run_cli("run", str(generation), cwd=root, env_extra=env)
            topic_result = run_cli("run", str(generation), cwd=root, env_extra=env)

            self.assertEqual(intake.returncode, 0, intake.stderr)
            self.assertEqual(context_result.returncode, 0, context_result.stderr)
            self.assertEqual(topic_result.returncode, 0, topic_result.stderr)
            context = read_json(generation / "content/generation-context.yaml")
            request = read_json(generation / "raw/personal-content/generation-context-request.json")
            response = read_json(generation / "raw/personal-content/generation-context-response.json")
            candidates = read_json(generation / "content/topic-candidates.json")
            self.assertEqual(request["adapter"], "real_personal_content")
            self.assertEqual(response["operation"], "show_generation_context")
            self.assertEqual(context["account_context"]["profile_id"], "creator-main")
            self.assertEqual([item["rule_id"] for item in context["rule_refs"]], ["rule-approved-001"])
            self.assertEqual(context["rule_refs"][0]["status"], "approved")
            self.assertNotIn("rule-candidate-001", json.dumps(context))
            self.assertEqual(candidates["candidates"][0]["rule_refs"], context["rule_refs"])
            self.assertFalse((generation / "published").exists())
            self.assertFalse((generation / "content/generated-post.md").exists())

            calls = read_json(root / "fake-personal-content-generation-calls.json")
            self.assertEqual(calls[0]["command"], "show-generation-context")
            self.assertEqual(calls[0]["profile_id"], "creator-main")
            self.assertEqual(calls[0]["intent"], "围绕 Codex 自媒体提效生成选题")

    def test_content_generation_compacts_real_rule_refs_without_lifecycle_state(self):
        with temp_project() as root:
            generation = create_task(root, "generation", brief="围绕 Codex 自媒体提效生成选题")
            runner = write_fake_personal_content_generation_cli(root)
            env = {
                "XIAOBA_PERSONAL_CONTENT_PROVIDER": "real",
                "XIAOBA_PERSONAL_CONTENT_COMMAND": json.dumps([sys.executable, str(runner)]),
                "XIAOBA_PERSONAL_CONTENT_WORKSPACE": str(root / "pc-workspace"),
            }
            self.assertEqual(run_cli("run", str(generation), cwd=root, env_extra=env).returncode, 0)
            self.assertEqual(run_cli("run", str(generation), cwd=root, env_extra=env).returncode, 0)
            self.assertEqual(run_cli("run", str(generation), cwd=root, env_extra=env).returncode, 0)
            self.assertEqual(run_cli("select-topic", str(generation), "--id", "topic-001", cwd=root, env_extra=env).returncode, 0)

            result = run_cli("run", str(generation), cwd=root, env_extra=env)

            self.assertEqual(result.returncode, 0, result.stderr)
            package = read_json(generation / "content/content-package.yaml")
            self.assertEqual(package["traceability"]["rule_refs"][0]["rule_id"], "rule-approved-001")
            self.assertNotIn("status", package["traceability"]["rule_refs"][0])
            self.assertNotIn("lifecycle_status", package["traceability"]["rule_refs"][0])
            self.assertNotIn("approved", package["traceability"]["rule_refs"][0].values())
            self.assertIn("current_stage: review", read_text(generation / "state.yaml"))
            self.assertFalse((generation / "published").exists())

    def test_set_brief_rejects_non_generation_empty_existing_and_late_change(self):
        with temp_project() as root:
            learning = create_task(root, "learning", "https://example.com/note/1")
            non_generation = run_cli("set-generation-brief", str(learning), "--brief", "x", cwd=root)
            self.assertEqual(non_generation.returncode, 1)
            self.assertIn("only supports generation", non_generation.stderr)

            generation = create_task(root, "generation", brief="已有需求")
            empty = run_cli("set-generation-brief", str(generation), "--brief", "", cwd=root)
            self.assertEqual(empty.returncode, 1)
            self.assertIn("brief is required", empty.stderr)
            duplicate = run_cli("set-generation-brief", str(generation), "--brief", "新需求", cwd=root)
            self.assertEqual(duplicate.returncode, 1)
            self.assertIn("generation brief already exists", duplicate.stderr)

            run_cli("run", str(generation), cwd=root)
            run_cli("run", str(generation), cwd=root)
            late = run_cli("set-generation-brief", str(generation), "--brief", "新需求", cwd=root)
            self.assertEqual(late.returncode, 1)
            self.assertIn("cannot modify brief after topic_generation", late.stderr)

    def test_attach_completed_learning_batch_and_reject_invalid_sources(self):
        with temp_project() as root:
            generation = create_task(root, "generation", brief="基于学习结果生成选题")
            unfinished = create_task(root, "learning", "https://example.com/note/unfinished")
            failed = run_cli("attach-learning", str(generation), "--task", str(unfinished), cwd=root)
            self.assertEqual(failed.returncode, 1)
            self.assertIn("source task must be completed", failed.stderr)

            non_learning = create_task(root, "generation", brief="另一个生成任务")
            wrong_type = run_cli("attach-learning", str(generation), "--task", str(non_learning), cwd=root)
            self.assertEqual(wrong_type.returncode, 1)
            self.assertIn("source task must be learning or learning_batch", wrong_type.stderr)

            completed = prepare_completed_learning(root)
            result = run_cli("attach-learning", str(generation), "--task", str(completed), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            sources = read_json(generation / "content/context-sources.json")
            self.assertEqual(sources["generation_task_id"], task_id_from(generation))
            self.assertEqual(sources["sources"][0]["source_task_type"], "learning")
            self.assertEqual(sources["sources"][0]["summary_path"], "analysis/learning-summary.yaml")
            self.assertEqual(sources["sources"][0]["mechanism_intake_result_path"], "analysis/mechanism-intake-result.json")

            duplicate = run_cli("attach-learning", str(generation), "--task", str(completed), cwd=root)
            self.assertEqual(duplicate.returncode, 1)
            self.assertIn("already attached", duplicate.stderr)

            completed_batch = prepare_completed_learning_batch(root)
            batch_generation = create_task(root, "generation", brief="基于批量学习结果生成选题")
            batch_result = run_cli("attach-learning", str(batch_generation), "--task", str(completed_batch), cwd=root)
            self.assertEqual(batch_result.returncode, 0, batch_result.stderr)
            batch_sources = read_json(batch_generation / "content/context-sources.json")
            self.assertEqual(batch_sources["sources"][0]["source_task_type"], "learning_batch")
            self.assertEqual(batch_sources["sources"][0]["summary_path"], "analysis/batch-learning-summary.yaml")

    def test_context_assembly_uses_explicit_sources_without_scanning(self):
        with temp_project() as root:
            generation = create_task(root, "generation", brief="生成一个选题")
            completed = prepare_completed_learning(root)
            source_before = read_text(completed / "analysis/learning-summary.yaml")

            run_cli("run", str(generation), cwd=root)
            result = run_cli("run", str(generation), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            context = read_json(generation / "content/generation-context.yaml")
            request = read_json(generation / "raw/personal-content/generation-context-request.json")
            self.assertEqual(context["learning_sources"], [])
            self.assertEqual(context["normalization"]["status"], "normalized")
            self.assertTrue(context["warnings"])
            self.assertIn("No learning sources attached", context["warnings"][0])
            self.assertEqual(request["operation"], "assemble_generation_context")
            self.assertIn("learning_sources", request)
            self.assertIn("generate post body", request["forbidden_actions"])
            self.assertFalse(any(completed.name in json.dumps(item) for item in context["learning_sources"]))
            self.assertEqual(read_text(completed / "analysis/learning-summary.yaml"), source_before)

            attached = create_task(root, "generation", brief="生成另一个选题")
            run_cli("attach-learning", str(attached), "--task", str(completed), cwd=root)
            run_cli("run", str(attached), cwd=root)
            result = run_cli("run", str(attached), cwd=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            context = read_json(attached / "content/generation-context.yaml")
            self.assertTrue(context["learning_sources"])
            self.assertIn("mechanism_refs", context)
            self.assertEqual(context["learning_sources"][0]["summary_path"], "analysis/learning-summary.yaml")
            self.assertNotIn("formal_mechanism_state", read_text(attached / "content/generation-context.yaml"))
            self.assertIn("current_stage: topic_generation", read_text(attached / "state.yaml"))
            late_attach = run_cli("attach-learning", str(attached), "--task", str(completed), cwd=root)
            self.assertEqual(late_attach.returncode, 1)
            self.assertIn("cannot attach learning source after topic_generation", late_attach.stderr)

    def test_topic_generation_pauses_for_selection(self):
        with temp_project() as root:
            generation = prepare_context_ready_generation(root)

            result = run_cli("run", str(generation), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            candidates = read_json(generation / "content/topic-candidates.json")
            self.assertGreaterEqual(len(candidates["candidates"]), 5)
            first = candidates["candidates"][0]
            self.assertIn("core_point", first)
            self.assertIn("fit_reason", first)
            self.assertIn("risks", first)
            self.assertIn("limitations", first)
            self.assertIn("mechanism_refs", first)
            self.assertIn("learning_source_refs", first)
            self.assertTrue(first["originality_requirements"])
            self.assertFalse(first["selected"])
            state = read_text(generation / "state.yaml")
            self.assertIn("status: waiting_for_user", state)
            self.assertIn("current_stage: topic_selection", state)
            self.assertIn("type: topic_selection", state)
            self.assertFalse((generation / "content/generated-post.md").exists())

    def test_advance_resume_cannot_bypass_and_select_topic_enters_content_generation(self):
        with temp_project() as root:
            generation = prepare_topic_selection_generation(root)

            advance = run_cli("advance", str(generation), cwd=root)
            resume = run_cli("resume", str(generation), cwd=root)
            self.assertEqual(advance.returncode, 1)
            self.assertIn("waiting_for_user", advance.stderr)
            self.assertEqual(resume.returncode, 1)
            self.assertIn("select-topic", resume.stderr)

            selected = run_cli("select-topic", str(generation), "--id", "topic-003", cwd=root)
            self.assertEqual(selected.returncode, 0, selected.stderr)
            selected_payload = read_json(generation / "content/selected-topic.json")
            self.assertEqual(selected_payload["selected_topic_id"], "topic-003")
            self.assertIn("current_stage: content_generation", read_text(generation / "state.yaml"))
            self.assertFalse((generation / "content/generated-post.md").exists())

    def test_select_topic_rejects_empty_unknown_and_duplicate(self):
        with temp_project() as root:
            generation = prepare_topic_selection_generation(root)

            empty = run_cli("select-topic", str(generation), "--id", "", cwd=root)
            unknown = run_cli("select-topic", str(generation), "--id", "topic-999", cwd=root)
            ok = run_cli("select-topic", str(generation), "--id", "topic-001", cwd=root)
            duplicate = run_cli("select-topic", str(generation), "--id", "topic-002", cwd=root)

            self.assertEqual(empty.returncode, 1)
            self.assertIn("topic id is required", empty.stderr)
            self.assertEqual(unknown.returncode, 1)
            self.assertIn("unknown topic id", unknown.stderr)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(duplicate.returncode, 1)
            self.assertIn("topic already selected", duplicate.stderr)

    def test_content_generation_writes_reviewable_package_and_pauses_for_review(self):
        with temp_project() as root:
            generation = prepare_content_generation_task(root)

            result = run_cli("run", str(generation), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            request = read_json(generation / "raw/personal-content/content-generation-request.json")
            response = read_json(generation / "raw/personal-content/content-generation-response.json")
            package = read_json(generation / "content/content-package.yaml")
            self.assertEqual(request["operation"], "generate_reviewable_content_package")
            self.assertIn("auto publish", request["forbidden_actions"])
            self.assertEqual(response["selected_topic_id"], "topic-003")
            self.assertEqual(package["status"], "draft")
            self.assertEqual(package["selected_topic_id"], "topic-003")
            self.assertIn(package["recommended_title"], package["title_options"])
            self.assertGreaterEqual(len(package["body"]["sections"]), 2)
            self.assertIn("traceability", package)
            self.assertTrue(package["assumptions"])
            self.assertTrue(package["review_questions"])
            package_text = json.dumps(package, ensure_ascii=False)
            self.assertNotIn("客户反馈", package_text)
            self.assertNotIn("转化率", package_text)
            self.assertNotIn("%", package_text)
            self.assertIn("status: waiting_for_user", read_text(generation / "state.yaml"))
            self.assertIn("current_stage: review", read_text(generation / "state.yaml"))
            self.assertIn("type: content_review", read_text(generation / "state.yaml"))
            self.assertFalse((generation / "published").exists())
            self.assertFalse((generation / "content/generated-post.md").exists())
            self.assertFalse(list(generation.rglob("*.png")))
            self.assertFalse(list(generation.rglob("*.mp4")))

    def test_content_generation_without_learning_source_keeps_empty_traceability_and_reuses_artifacts(self):
        with temp_project() as root:
            generation = create_task(root, "generation", brief="不附加学习来源也生成待审草稿")
            run_cli("run", str(generation), cwd=root)
            run_cli("run", str(generation), cwd=root)
            run_cli("run", str(generation), cwd=root)
            selected = run_cli("select-topic", str(generation), "--id", "topic-001", cwd=root)
            self.assertEqual(selected.returncode, 0, selected.stderr)
            first = run_cli("run", str(generation), cwd=root)
            self.assertEqual(first.returncode, 0, first.stderr)
            package_before = read_text(generation / "content/content-package.yaml")

            reset_stage(generation, "content_generation", "review")
            second = run_cli("run", str(generation), cwd=root)

            self.assertEqual(second.returncode, 0, second.stderr)
            package = read_json(generation / "content/content-package.yaml")
            self.assertEqual(package["traceability"]["learning_source_refs"], [])
            self.assertEqual(read_text(generation / "content/content-package.yaml"), package_before)

    def test_content_generation_blocks_on_selected_topic_mismatch_and_partial_artifacts(self):
        with temp_project() as root:
            generation = prepare_content_generation_task(root)
            selected = read_json(generation / "content/selected-topic.json")
            selected["topic"]["topic_id"] = "topic-999"
            write_json(generation / "content/selected-topic.json", selected)

            result = run_cli("run", str(generation), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("selected topic snapshot mismatch", read_text(generation / "state.yaml"))
            self.assertIn("current_stage: content_generation", read_text(generation / "state.yaml"))

        with temp_project() as root:
            generation = prepare_content_generation_task(root)
            write_json(generation / "raw/personal-content/content-generation-request.json", {"partial": True})

            result = run_cli("run", str(generation), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("Incomplete content generation artifacts", read_text(generation / "state.yaml"))

    def test_review_approve_reject_and_request_changes(self):
        with temp_project() as root:
            approved = prepare_review_task(root)
            advance = run_cli("advance", str(approved), cwd=root)
            resume = run_cli("resume", str(approved), cwd=root)
            self.assertEqual(advance.returncode, 1)
            self.assertIn("waiting_for_user", advance.stderr)
            self.assertEqual(resume.returncode, 1)
            self.assertIn("review-content", resume.stderr)

            approve = run_cli("review-content", str(approved), "--decision", "approve", cwd=root)
            self.assertEqual(approve.returncode, 0, approve.stderr)
            decision = read_json(approved / "content/review-decision.json")
            self.assertEqual(decision["decision"], "approve")
            self.assertIn("status: completed", read_text(approved / "state.yaml"))
            self.assertFalse((approved / "published").exists())

        with temp_project() as root:
            rejected = prepare_review_task(root)
            reject = run_cli("review-content", str(rejected), "--decision", "reject", "--feedback", "不适合当前账号", cwd=root)
            self.assertEqual(reject.returncode, 0, reject.stderr)
            decision = read_json(rejected / "content/review-decision.json")
            self.assertEqual(decision["decision"], "reject")
            self.assertIn("status: completed", read_text(rejected / "state.yaml"))

        with temp_project() as root:
            revision = prepare_review_task(root)
            missing_feedback = run_cli("review-content", str(revision), "--decision", "request_changes", cwd=root)
            self.assertEqual(missing_feedback.returncode, 1)
            self.assertIn("feedback is required", missing_feedback.stderr)

            request_changes = run_cli(
                "review-content",
                str(revision),
                "--decision",
                "request_changes",
                "--feedback",
                "开头更具体，降低营销感",
                cwd=root,
            )
            self.assertEqual(request_changes.returncode, 0, request_changes.stderr)
            self.assertTrue((revision / "content/revisions/revision-001/content-package.yaml").is_file())
            self.assertTrue((revision / "content/revisions/revision-001/review-decision.json").is_file())
            self.assertIn("current_stage: content_generation", read_text(revision / "state.yaml"))

            second = run_cli("run", str(revision), cwd=root)
            self.assertEqual(second.returncode, 0, second.stderr)
            request = read_json(revision / "raw/personal-content/content-generation-request.json")
            self.assertEqual(request["revision"]["number"], 2)
            self.assertIn("开头更具体", request["revision"]["feedback"])
            self.assertTrue((revision / "content/revisions/revision-002/content-package.yaml").is_file())

    def test_review_rejects_wrong_task_stage_and_duplicate_decision(self):
        with temp_project() as root:
            learning = create_task(root, "learning", "https://example.com/note/1")
            non_generation = run_cli("review-content", str(learning), "--decision", "approve", cwd=root)
            self.assertEqual(non_generation.returncode, 1)
            self.assertIn("only supports generation", non_generation.stderr)

            generation = prepare_content_generation_task(root)
            wrong_stage = run_cli("review-content", str(generation), "--decision", "approve", cwd=root)
            self.assertEqual(wrong_stage.returncode, 1)
            self.assertIn("not waiting for content review", wrong_stage.stderr)

            review = prepare_review_task(root)
            first = run_cli("review-content", str(review), "--decision", "approve", cwd=root)
            second = run_cli("review-content", str(review), "--decision", "approve", cwd=root)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 1)
            self.assertIn("not waiting for content review", second.stderr)

    def test_invalid_topic_candidate_references_are_rejected(self):
        with temp_project() as root:
            generation = prepare_topic_selection_generation(root)
            candidates_path = generation / "content/topic-candidates.json"
            candidates = read_json(candidates_path)
            candidates["candidates"][0]["learning_source_refs"] = [
                {"source_task_id": "task-not-attached", "source_task_type": "learning"}
            ]
            write_json(candidates_path, candidates)

            result = run_cli("select-topic", str(generation), "--id", "topic-001", cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("unknown learning source", result.stderr)

    def test_context_and_topic_idempotency_and_partial_artifacts_block(self):
        with temp_project() as root:
            generation = create_task(root, "generation", brief="生成选题")
            run_cli("run", str(generation), cwd=root)
            first = run_cli("run", str(generation), cwd=root)
            context_before = read_text(generation / "content/generation-context.yaml")
            reset_stage(generation, "context_assembly", "topic_generation")
            second = run_cli("run", str(generation), cwd=root)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(read_text(generation / "content/generation-context.yaml"), context_before)

        with temp_project() as root:
            generation = create_task(root, "generation", brief="生成选题")
            run_cli("run", str(generation), cwd=root)
            write_json(generation / "raw/personal-content/generation-context-request.json", {"partial": True})
            partial = run_cli("run", str(generation), cwd=root)
            self.assertEqual(partial.returncode, 1)
            self.assertIn("Incomplete generation context artifacts", read_text(generation / "state.yaml"))

        with temp_project() as root:
            generation = prepare_context_ready_generation(root)
            write_json(generation / "raw/personal-content/topic-generation-response.json", {"partial": True})
            partial = run_cli("run", str(generation), cwd=root)
            self.assertEqual(partial.returncode, 1)
            self.assertIn("Incomplete topic generation artifacts", read_text(generation / "state.yaml"))

    def test_learning_flows_still_complete(self):
        with temp_project() as root:
            learning = prepare_completed_learning(root)
            self.assertIn("status: completed", read_text(learning / "state.yaml"))


def prepare_completed_learning(root):
    task_dir = create_task(root, "learning", "https://example.com/note/1")
    for _ in range(7):
        result = run_cli("run", str(task_dir), cwd=root)
        if result.returncode != 0:
            raise AssertionError(result.stderr)
    return task_dir


def prepare_completed_learning_batch(root):
    task_dir = create_task(root, "learning_batch", "https://example.com/user/1")
    for _ in range(2):
        result = run_cli("run", str(task_dir), cwd=root)
        if result.returncode != 0:
            raise AssertionError(result.stderr)
    select = run_cli("select-samples", str(task_dir), "--ids", "sample-001", "sample-003", cwd=root)
    if select.returncode != 0:
        raise AssertionError(select.stderr)
    for _ in range(10):
        result = run_cli("run", str(task_dir), cwd=root)
        if result.returncode != 0:
            raise AssertionError(result.stderr)
    if "status: completed" not in read_text(task_dir / "state.yaml"):
        raise AssertionError(read_text(task_dir / "state.yaml"))
    return task_dir


def prepare_context_ready_generation(root):
    generation = create_task(root, "generation", brief="基于学习沉淀生成选题")
    completed = prepare_completed_learning(root)
    attach = run_cli("attach-learning", str(generation), "--task", str(completed), cwd=root)
    if attach.returncode != 0:
        raise AssertionError(attach.stderr)
    intake = run_cli("run", str(generation), cwd=root)
    if intake.returncode != 0:
        raise AssertionError(intake.stderr)
    context = run_cli("run", str(generation), cwd=root)
    if context.returncode != 0:
        raise AssertionError(context.stderr)
    return generation


def prepare_topic_selection_generation(root):
    generation = prepare_context_ready_generation(root)
    result = run_cli("run", str(generation), cwd=root)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return generation


def prepare_content_generation_task(root):
    generation = prepare_topic_selection_generation(root)
    selected = run_cli("select-topic", str(generation), "--id", "topic-003", cwd=root)
    if selected.returncode != 0:
        raise AssertionError(selected.stderr)
    return generation


def prepare_review_task(root):
    generation = prepare_content_generation_task(root)
    result = run_cli("run", str(generation), cwd=root)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return generation


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


def create_task(root, task_type, source_url=None, brief=None):
    args = ["create-task", "--type", task_type]
    if source_url:
        args.extend(["--source-url", source_url])
    if brief:
        args.extend(["--brief", brief])
    result = run_cli(*args, cwd=root)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    prefix = "Created task: "
    for line in result.stdout.splitlines():
        if line.startswith(prefix):
            return root / line[len(prefix) :]
    raise AssertionError(result.stdout)


def write_fake_personal_content_generation_cli(root):
    runner = root / "fake_personal_content_generation_cli.py"
    calls_path = root / "fake-personal-content-generation-calls.json"
    runner.write_text(
        """
import json
import sys
from pathlib import Path

calls_path = Path("__CALLS_PATH__")
calls = json.loads(calls_path.read_text(encoding='utf-8')) if calls_path.is_file() else []
args = sys.argv[1:]
if 'show-generation-context' not in args:
    print(json.dumps({'ok': False, 'error': 'unsupported command'}))
    sys.exit(1)
profile_id = args[args.index('--profile-id') + 1]
intent = args[args.index('--intent') + 1]
calls.append({'command': 'show-generation-context', 'profile_id': profile_id, 'intent': intent})
calls_path.write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({
    'ok': True,
    'result': {
        'status_category': 'ready',
        'profile_id': profile_id,
        'profile_version': 1,
        'usable_rule_count': 1,
        'excluded_rule_count': 1,
        'risk_warning_count': 0,
        'missing_information_count': 0,
        'machine_summary': {
            'profile_id': profile_id,
            'profile_version': 1,
            'usable_rule_ids': ['rule-approved-001'],
            'excluded_rule_ids': ['rule-candidate-001'],
            'usable_rules': [
                {
                    'rule_id': 'rule-approved-001',
                    'rule_version': 2,
                    'rule_type': 'topic',
                    'summary': '讲 AI 工具时，先翻译成目标用户的 3 个高频任务。',
                    'status': 'approved',
                    'strength': 'medium',
                    'applicable_scenarios': ['小红书内容学习'],
                    'warnings': []
                }
            ],
            'excluded_rules': [
                {
                    'rule_id': 'rule-candidate-001',
                    'summary': '候选规则不应进入生成上下文',
                    'status': 'candidate',
                    'reason': '尚未经过用户确认'
                }
            ],
            'risk_warnings': [],
            'missing_information': [],
            'status_category': 'ready'
        },
        'user_summary': '已读取 1 条可用规则。'
    }
}, ensure_ascii=False))
""".replace("__CALLS_PATH__", str(calls_path)),
        encoding="utf-8",
    )
    return runner


def task_id_from(task_dir):
    for line in read_text(task_dir / "task.yaml").splitlines():
        if line.startswith("task_id:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError("task_id missing")


def reset_stage(task_dir, stage, next_stage):
    state = read_text(task_dir / "state.yaml")
    lines = []
    for line in state.splitlines():
        if line.startswith("status:"):
            lines.append("status: running")
        elif line.startswith("current_stage:"):
            lines.append("current_stage: " + stage)
        elif line.startswith("next_stage:"):
            lines.append("next_stage: " + next_stage)
        elif line.startswith("waiting_for:"):
            lines.append("waiting_for: null")
        else:
            lines.append(line)
    write_text(task_dir / "state.yaml", "\n".join(lines) + "\n")


def read_text(path):
    return path.read_text(encoding="utf-8")


def write_text(path, value):
    path.write_text(value, encoding="utf-8")


def read_json(path):
    return json.loads(read_text(path))


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
