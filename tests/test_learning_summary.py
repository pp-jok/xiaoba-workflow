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


class LearningSummaryTests(unittest.TestCase):
    def test_aggregation_generates_summary_and_completes_learning(self):
        with temp_project() as root:
            task_dir = prepare_aggregation_task(root)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            summary = read_json(task_dir / "analysis/learning-summary.yaml")
            evidence = read_json(task_dir / "evidence/evidence.yaml")
            analysis = read_json(task_dir / "analysis/analysis.yaml")
            state = read_text(task_dir / "state.yaml")
            self.assertEqual(summary["task_id"], read_task_id(task_dir))
            self.assertEqual(summary["sample_id"], evidence["sample_id"])
            self.assertEqual(summary["sample_id"], analysis["sample_id"])
            self.assertEqual(summary["source"]["original_url"], "https://example.com/note/1")
            self.assertEqual(summary["analysis_summary"]["mechanism_count"], len(analysis["mechanisms"]))
            self.assertIn("status: completed", state)
            self.assertIn("current_stage: completed", state)
            self.assertIn("next_stage: null", state)
            self.assertNotIn("generation", state)

    def test_evidence_analysis_and_intake_sections_are_summarized(self):
        with temp_project() as root:
            task_dir = prepare_aggregation_task(root)
            analysis = read_json(task_dir / "analysis/analysis.yaml")
            analysis["rule_suggestions"].append("Candidate rule from analysis only.")
            analysis["asset_suggestions"].append("Candidate asset from analysis only.")
            analysis["content_opportunities"].append("Opportunity from analysis only.")
            analysis["questions"].append("Missing comments?")
            write_json(task_dir / "analysis/analysis.yaml", analysis)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            summary = read_json(task_dir / "analysis/learning-summary.yaml")
            self.assertEqual(summary["evidence_summary"]["normalization_status"], "partially_normalized")
            self.assertIn("comments", summary["evidence_summary"]["missing"])
            self.assertIn("transcript", summary["evidence_summary"]["missing"])
            self.assertEqual(summary["analysis_summary"]["rule_suggestion_count"], len(analysis["rule_suggestions"]))
            self.assertEqual(summary["analysis_summary"]["asset_suggestion_count"], len(analysis["asset_suggestions"]))
            self.assertEqual(summary["analysis_summary"]["content_opportunity_count"], len(analysis["content_opportunities"]))
            self.assertIn("Candidate rule from analysis only.", summary["governance"]["pending_rule_suggestions"])
            self.assertIn("Candidate asset from analysis only.", summary["governance"]["pending_asset_suggestions"])
            self.assertIn("Opportunity from analysis only.", summary["content_opportunities"])
            self.assertIn("Missing comments?", summary["open_questions"])
            self.assertTrue(summary["governance"]["recommended"])

    def test_mechanism_intake_statuses_are_classified_without_omissions(self):
        with temp_project() as root:
            task_dir = prepare_aggregation_task(root, with_status_mix=True)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            summary = read_json(task_dir / "analysis/learning-summary.yaml")
            intake = read_json(task_dir / "analysis/mechanism-intake-result.json")
            classified = []
            for status in ("imported", "matched_existing", "limited", "rejected", "failed"):
                classified.extend(item["source_mechanism_id"] for item in summary["mechanism_intake_summary"][status])
            source_ids = [item["source_mechanism_id"] for item in intake["results"]]
            self.assertCountEqual(classified, source_ids)
            self.assertEqual(len(classified), len(set(classified)))
            self.assertTrue(summary["mechanism_intake_summary"]["imported"])
            self.assertTrue(summary["mechanism_intake_summary"]["matched_existing"])
            self.assertTrue(summary["mechanism_intake_summary"]["limited"])
            self.assertTrue(summary["mechanism_intake_summary"]["rejected"])
            self.assertTrue(summary["mechanism_intake_summary"]["failed"])

    def test_summary_does_not_add_professional_conclusions_or_formal_objects(self):
        with temp_project() as root:
            task_dir = prepare_aggregation_task(root)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            summary_text = read_text(task_dir / "analysis/learning-summary.yaml")
            self.assertNotIn("RuleCard", summary_text)
            self.assertNotIn("ContentAsset", summary_text)
            self.assertNotIn("generated_content", summary_text)
            self.assertNotIn("auto_generation", summary_text)
            self.assertNotIn("new_professional_conclusion", summary_text)

    def test_missing_upstream_artifact_blocks_aggregation(self):
        for relative_path in (
            "evidence/evidence.yaml",
            "analysis/analysis.yaml",
            "analysis/mechanism-intake-result.json",
        ):
            with temp_project() as root:
                task_dir = prepare_aggregation_task(root)
                (task_dir / relative_path).unlink()

                result = run_cli("run", str(task_dir), cwd=root)

                self.assertEqual(result.returncode, 1)
                state = read_text(task_dir / "state.yaml")
                self.assertIn("status: blocked", state)
                self.assertIn("current_stage: aggregation", state)

    def test_task_or_sample_id_mismatch_blocks(self):
        with temp_project() as root:
            task_dir = prepare_aggregation_task(root)
            analysis = read_json(task_dir / "analysis/analysis.yaml")
            analysis["sample_id"] = "sample-other"
            write_json(task_dir / "analysis/analysis.yaml", analysis)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("sample_id mismatch", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            task_dir = prepare_aggregation_task(root)
            intake = read_json(task_dir / "analysis/mechanism-intake-result.json")
            intake["task_id"] = "task-other"
            write_json(task_dir / "analysis/mechanism-intake-result.json", intake)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("task_id mismatch", read_text(task_dir / "state.yaml"))

    def test_existing_invalid_summary_blocks_and_valid_summary_is_reused(self):
        with temp_project() as root:
            task_dir = prepare_aggregation_task(root)
            invalid = {"summary_id": "summary-bad", "task_id": read_task_id(task_dir)}
            write_json(task_dir / "analysis/learning-summary.yaml", invalid)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("sample_id is required", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            task_dir = prepare_aggregation_task(root)
            first = run_cli("run", str(task_dir), cwd=root)
            summary_before = read_text(task_dir / "analysis/learning-summary.yaml")
            set_running_stage(task_dir, "aggregation", "completed")

            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(read_text(task_dir / "analysis/learning-summary.yaml"), summary_before)

    def test_summary_validation_rejects_bad_counts_and_forbidden_fields(self):
        with temp_project() as root:
            task_dir = prepare_aggregation_task(root)
            run_cli("run", str(task_dir), cwd=root)
            set_running_stage(task_dir, "aggregation", "completed")
            summary = read_json(task_dir / "analysis/learning-summary.yaml")
            summary["analysis_summary"]["mechanism_count"] = 999
            write_json(task_dir / "analysis/learning-summary.yaml", summary)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("mechanism_count mismatch", read_text(task_dir / "state.yaml"))

        for forbidden in ("rule_card", "content_asset", "generated_content", "auto_generation"):
            with temp_project() as root:
                task_dir = prepare_aggregation_task(root)
                run_cli("run", str(task_dir), cwd=root)
                set_running_stage(task_dir, "aggregation", "completed")
                summary = read_json(task_dir / "analysis/learning-summary.yaml")
                summary[forbidden] = {}
                write_json(task_dir / "analysis/learning-summary.yaml", summary)

                result = run_cli("run", str(task_dir), cwd=root)

                self.assertEqual(result.returncode, 1)
                self.assertIn("forbidden learning summary field", read_text(task_dir / "state.yaml"))

    def test_completed_task_cannot_run_again_and_learning_does_not_enter_generation(self):
        with temp_project() as root:
            task_dir = prepare_aggregation_task(root)
            first = run_cli("run", str(task_dir), cwd=root)
            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 1)
            self.assertIn("Task is completed and cannot run", second.stderr)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("current_stage: completed", state)
            self.assertNotIn("content_generation", state)
            self.assertFalse((task_dir / "content" / "generated-post.md").exists())

    def test_prepare_governance_exports_candidate_plan_without_formal_objects(self):
        with temp_project() as root:
            task_dir = prepare_aggregation_task(root, with_status_mix=True)
            complete = run_cli("run", str(task_dir), cwd=root)
            self.assertEqual(complete.returncode, 0, complete.stderr)

            result = run_cli("prepare-governance", str(task_dir), "--profile-id", "creator-main", cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            plan_path = task_dir / "governance/personal-content-governance-plan.json"
            self.assertTrue(plan_path.is_file())
            plan = read_json(plan_path)
            summary = read_json(task_dir / "analysis/learning-summary.yaml")
            eligible_statuses = {item["intake_status"] for item in plan["eligible_mechanisms"]}
            text = read_text(plan_path)
            self.assertEqual(plan["task_id"], read_task_id(task_dir))
            self.assertEqual(plan["profile_id"], "creator-main")
            self.assertEqual(plan["status"], "pending_user_review")
            self.assertEqual(len(plan["rule_proposals"]), len(summary["governance"]["pending_rule_suggestions"]))
            self.assertEqual(len(plan["asset_direction_proposals"]), len(summary["governance"]["pending_asset_suggestions"]))
            self.assertTrue(plan["rule_proposals"])
            self.assertIn(plan["rule_proposals"][0]["rule_statement"], summary["governance"]["pending_rule_suggestions"])
            self.assertTrue(plan["rule_proposals"][0]["recommended_source_mechanism_id"])
            self.assertEqual(eligible_statuses, {"imported", "matched_existing", "limited"})
            self.assertNotIn("rejected", json.dumps(plan["eligible_mechanisms"]))
            self.assertNotIn("failed", json.dumps(plan["eligible_mechanisms"]))
            self.assertNotIn("RuleCard", text)
            self.assertNotIn("ContentAsset", text)
            self.assertNotIn("approved", text)
            self.assertNotIn("generated_content", text)

    def test_propose_governance_rule_calls_personal_content_without_approving_rule(self):
        with temp_project() as root:
            task_dir = prepare_aggregation_task(root, with_status_mix=True)
            complete = run_cli("run", str(task_dir), cwd=root)
            self.assertEqual(complete.returncode, 0, complete.stderr)
            prepare = run_cli("prepare-governance", str(task_dir), "--profile-id", "creator-main", cwd=root)
            self.assertEqual(prepare.returncode, 0, prepare.stderr)
            runner = write_fake_personal_content_rule_cli(root)
            workspace = root / "pc-workspace"
            stale_request = task_dir / "governance/rule-proposal-001-request.json"
            write_json(stale_request, {"account_fit_reason": "过泛的旧请求"})

            result = run_cli(
                "propose-governance-rule",
                str(task_dir),
                "--proposal-id",
                "rule-proposal-001",
                cwd=root,
                env_extra={
                    "XIAOBA_PERSONAL_CONTENT_PROVIDER": "real",
                    "XIAOBA_PERSONAL_CONTENT_COMMAND": json.dumps([sys.executable, str(runner)]),
                    "XIAOBA_PERSONAL_CONTENT_WORKSPACE": str(workspace),
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            command_result = read_json(task_dir / "governance/rule-proposal-001-result.json")
            self.assertEqual(command_result["status"], "candidate_created")
            self.assertEqual(command_result["external_rule"]["id"], "candidate-rule-001")
            self.assertEqual(command_result["external_rule"]["status"], "candidate")
            self.assertNotIn("approved", read_text(task_dir / "governance/rule-proposal-001-result.json"))

            calls = read_json(root / "fake-personal-content-rule-calls.json")
            self.assertEqual(len(calls), 1)
            call = calls[0]
            self.assertEqual(call["mechanism_id"], "mock-mechanism-001")
            self.assertEqual(call["creator_id"], "creator-main")
            payload = call["payload"]
            self.assertEqual(payload["rule_statement"], command_result["rule_statement"])
            self.assertTrue(payload["selected_observed_facts"])
            self.assertLessEqual(len(payload["selected_observed_facts"]), 3)
            self.assertIn("标题把用户能获得的好处包装成直接承诺", payload["account_fit_reason"])
            self.assertNotIn("generated_content", json.dumps(payload))

    def test_confirm_governance_rule_resolves_personal_content_decision(self):
        with temp_project() as root:
            task_dir = prepare_aggregation_task(root, with_status_mix=True)
            complete = run_cli("run", str(task_dir), cwd=root)
            self.assertEqual(complete.returncode, 0, complete.stderr)
            prepare = run_cli("prepare-governance", str(task_dir), "--profile-id", "creator-main", cwd=root)
            self.assertEqual(prepare.returncode, 0, prepare.stderr)
            runner = write_fake_personal_content_rule_cli(root)
            workspace = root / "pc-workspace"
            env = {
                "XIAOBA_PERSONAL_CONTENT_PROVIDER": "real",
                "XIAOBA_PERSONAL_CONTENT_COMMAND": json.dumps([sys.executable, str(runner)]),
                "XIAOBA_PERSONAL_CONTENT_WORKSPACE": str(workspace),
            }
            propose = run_cli(
                "propose-governance-rule",
                str(task_dir),
                "--proposal-id",
                "rule-proposal-001",
                cwd=root,
                env_extra=env,
            )
            self.assertEqual(propose.returncode, 0, propose.stderr)

            result = run_cli(
                "confirm-governance-rule",
                str(task_dir),
                "--proposal-id",
                "rule-proposal-001",
                "--decision",
                "confirm",
                cwd=root,
                env_extra=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            confirmation = read_json(task_dir / "governance/rule-proposal-001-confirmation-result.json")
            self.assertEqual(confirmation["status"], "confirmed")
            self.assertEqual(confirmation["external_rule"]["id"], "candidate-rule-001")
            self.assertEqual(confirmation["external_rule"]["status"], "approved")
            self.assertFalse(confirmation["generation_triggered"])
            self.assertFalse(confirmation["published"])
            self.assertNotIn("RuleCard", read_text(task_dir / "governance/rule-proposal-001-confirmation-result.json"))
            self.assertNotIn("generated_content", read_text(task_dir / "governance/rule-proposal-001-confirmation-result.json"))

            calls = read_json(root / "fake-personal-content-rule-calls.json")
            commands = [call["command"] for call in calls]
            self.assertEqual(commands, ["propose-rule-from-mechanism", "create-rule-decision", "resolve-decision"])
            self.assertEqual(calls[1]["rule_id"], "candidate-rule-001")
            self.assertEqual(calls[2]["decision_id"], "decision-candidate-rule-001")
            self.assertEqual(calls[2]["selected_option"], "确认使用")

    def test_reject_governance_rule_resolves_without_generation(self):
        with temp_project() as root:
            task_dir = prepare_aggregation_task(root, with_status_mix=True)
            complete = run_cli("run", str(task_dir), cwd=root)
            self.assertEqual(complete.returncode, 0, complete.stderr)
            prepare = run_cli("prepare-governance", str(task_dir), "--profile-id", "creator-main", cwd=root)
            self.assertEqual(prepare.returncode, 0, prepare.stderr)
            runner = write_fake_personal_content_rule_cli(root)
            workspace = root / "pc-workspace"
            env = {
                "XIAOBA_PERSONAL_CONTENT_PROVIDER": "real",
                "XIAOBA_PERSONAL_CONTENT_COMMAND": json.dumps([sys.executable, str(runner)]),
                "XIAOBA_PERSONAL_CONTENT_WORKSPACE": str(workspace),
            }
            propose = run_cli(
                "propose-governance-rule",
                str(task_dir),
                "--proposal-id",
                "rule-proposal-001",
                cwd=root,
                env_extra=env,
            )
            self.assertEqual(propose.returncode, 0, propose.stderr)

            result = run_cli(
                "confirm-governance-rule",
                str(task_dir),
                "--proposal-id",
                "rule-proposal-001",
                "--decision",
                "reject",
                "--note",
                "当前样本太少，先不沉淀为规则。",
                cwd=root,
                env_extra=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            confirmation = read_json(task_dir / "governance/rule-proposal-001-confirmation-result.json")
            self.assertEqual(confirmation["status"], "rejected")
            self.assertEqual(confirmation["external_rule"]["status"], "rejected")
            self.assertFalse(confirmation["generation_triggered"])
            self.assertFalse(confirmation["published"])


def prepare_aggregation_task(root, with_status_mix=False):
    task_dir = create_task(root, "learning", "https://example.com/note/1")
    for _ in range(5):
        result = run_cli("run", str(task_dir), cwd=root)
        if result.returncode != 0:
            raise AssertionError(result.stderr)
    if with_status_mix:
        analysis_path = task_dir / "analysis/analysis.yaml"
        analysis = read_json(analysis_path)
        analysis["mechanisms"][0]["name"] = "Imported Mechanism"
        analysis["mechanisms"][0]["confidence"] = "high"
        analysis["mechanisms"][1]["name"] = "MATCH_EXISTING Existing Mechanism"
        analysis["mechanisms"][1]["confidence"] = "medium"
        analysis["mechanisms"][2]["name"] = "Limited Mechanism"
        analysis["mechanisms"][2]["confidence"] = "low"
        rejected = duplicate_mechanism(analysis["mechanisms"][0], "mechanism-004", "REJECT Too Broad Mechanism")
        failed = duplicate_mechanism(analysis["mechanisms"][0], "mechanism-005", "MOCK_FAIL Broken Mechanism")
        analysis["mechanisms"].extend([rejected, failed])
        write_json(analysis_path, analysis)
    result = run_cli("run", str(task_dir), cwd=root)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return task_dir


def duplicate_mechanism(source, mechanism_id, name):
    mechanism = json.loads(json.dumps(source))
    mechanism["id"] = mechanism_id
    mechanism["name"] = name
    return mechanism


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


def read_task_id(task_dir):
    for line in read_text(task_dir / "task.yaml").splitlines():
        if line.startswith("task_id:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError("missing task_id")


def read_text(path):
    return path.read_text(encoding="utf-8")


def read_json(path):
    return json.loads(read_text(path))


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_fake_personal_content_rule_cli(root):
    runner = root / "fake_personal_content_rule_cli.py"
    calls_path = root / "fake-personal-content-rule-calls.json"
    runner.write_text(
        """
import json
import sys
from pathlib import Path

calls_path = Path("__CALLS_PATH__")
calls = json.loads(calls_path.read_text(encoding='utf-8')) if calls_path.is_file() else []
args = sys.argv[1:]
if 'propose-rule-from-mechanism' in args:
    command = 'propose-rule-from-mechanism'
elif 'create-rule-decision' in args:
    command = 'create-rule-decision'
elif 'resolve-decision' in args:
    command = 'resolve-decision'
else:
    print(json.dumps({'ok': False, 'error': 'unsupported command'}))
    sys.exit(1)
workspace = args[args.index('--workspace') + 1]
if command == 'propose-rule-from-mechanism':
    mechanism_id = args[args.index('--mechanism-id') + 1]
    creator_id = args[args.index('--creator-id') + 1]
    file_path = args[args.index('--file') + 1]
    payload = json.loads(Path(file_path).read_text(encoding='utf-8'))
    calls.append({'command': command, 'workspace': workspace, 'mechanism_id': mechanism_id, 'creator_id': creator_id, 'file': file_path, 'payload': payload})
    calls_path.write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({
        'ok': True,
        'result': {
            'created_count': 1,
            'user_summary': '已创建候选规则，等待用户确认。',
            'machine_summary': {
                'rule_id': 'candidate-rule-001',
                'rule_status': 'candidate'
            }
        }
    }, ensure_ascii=False))
elif command == 'create-rule-decision':
    rule_id = args[args.index('--rule-id') + 1]
    calls.append({'command': command, 'workspace': workspace, 'rule_id': rule_id})
    calls_path.write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({
        'ok': True,
        'result': {
            'decision_id': 'decision-' + rule_id,
            'reused_existing': False,
            'user_summary': '请确认是否启用这条候选规则。'
        }
    }, ensure_ascii=False))
else:
    decision_id = args[args.index('--decision-id') + 1]
    selected_option = args[args.index('--selected-option') + 1]
    status = 'confirmed' if selected_option == '确认使用' else 'rejected'
    rule_status = 'approved' if selected_option == '确认使用' else 'rejected'
    calls.append({'command': command, 'workspace': workspace, 'decision_id': decision_id, 'selected_option': selected_option})
    calls_path.write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({
        'ok': True,
        'result': {
            'decision_id': decision_id,
            'rule_id': 'candidate-rule-001',
            'status': status,
            'selected_option': selected_option,
            'resulting_state_changes': [
                {
                    'target_object_type': 'rule_card',
                    'target_object_id': 'candidate-rule-001',
                    'field': 'status',
                    'value': rule_status
                }
            ],
            'user_summary': '候选规则已处理。'
        }
    }, ensure_ascii=False))
""".replace("__CALLS_PATH__", str(calls_path)),
        encoding="utf-8",
    )
    return runner


def set_running_stage(task_dir, current_stage, next_stage):
    state_path = task_dir / "state.yaml"
    lines = []
    for line in read_text(state_path).splitlines():
        if line.startswith("status:"):
            lines.append("status: running")
        elif line.startswith("current_stage:"):
            lines.append("current_stage: " + current_stage)
        elif line.startswith("next_stage:"):
            lines.append("next_stage: " + next_stage)
        elif line.startswith("waiting_for:"):
            lines.append("waiting_for: null")
        else:
            lines.append(line)
    state_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
