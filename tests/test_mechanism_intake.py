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


class MechanismIntakeTests(unittest.TestCase):
    def test_personal_content_doctor_checks_mock_and_real_configuration(self):
        with temp_project() as root:
            mock = run_cli("doctor", "--skill", "personal-content", cwd=root)

            self.assertEqual(mock.returncode, 0, mock.stderr)
            self.assertIn("provider: mock", mock.stdout)

        with temp_project() as root:
            runner = write_fake_personal_content_help_cli(root)
            real = run_cli(
                "doctor",
                "--skill",
                "personal-content",
                cwd=root,
                env_extra={
                    "XIAOBA_PERSONAL_CONTENT_PROVIDER": "real",
                    "XIAOBA_PERSONAL_CONTENT_COMMAND": json.dumps([sys.executable, str(runner)]),
                    "XIAOBA_PERSONAL_CONTENT_WORKSPACE": str(root / "pc-workspace"),
                },
            )

            self.assertEqual(real.returncode, 0, real.stderr)
            self.assertIn("provider: real", real.stdout)
            self.assertIn("workspace: configured", real.stdout)
            self.assertIn("operations: import-mechanism", real.stdout)
            self.assertIn("show-generation-context", real.stdout)

        with temp_project() as root:
            missing = run_cli(
                "doctor",
                "--skill",
                "personal-content",
                cwd=root,
                env_extra={"XIAOBA_PERSONAL_CONTENT_PROVIDER": "real"},
            )

            self.assertEqual(missing.returncode, 1)
            self.assertIn("XIAOBA_PERSONAL_CONTENT_WORKSPACE", missing.stderr)

    def test_mechanism_intake_generates_request_response_result_and_advances(self):
        with temp_project() as root:
            task_dir = prepare_mechanism_intake_task(root)
            analysis_before = read_text(task_dir / "analysis/analysis.yaml")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            request = read_json(task_dir / "raw/personal-content/mechanism-intake-request.json")
            response = read_json(task_dir / "raw/personal-content/mechanism-intake-response.json")
            intake_result = read_json(task_dir / "analysis/mechanism-intake-result.json")
            state = read_text(task_dir / "state.yaml")
            self.assertEqual(request["operation"], "create_or_match_candidate_mechanism")
            self.assertEqual(request["workspace_ref"], "mock://personal-content/default")
            self.assertEqual(len(request["mechanisms"]), 3)
            self.assertEqual(response["workspace_ref"], "mock://personal-content/default")
            self.assertEqual(len(response["results"]), 3)
            self.assertEqual(intake_result["workspace_ref"], "mock://personal-content/default")
            self.assertEqual(read_text(task_dir / "analysis/analysis.yaml"), analysis_before)
            self.assertIn("current_stage: aggregation", state)
            self.assertNotIn("current_stage: completed", state)

    def test_request_fields_come_from_analysis(self):
        with temp_project() as root:
            task_dir = prepare_mechanism_intake_task(root)
            analysis = read_json(task_dir / "analysis/analysis.yaml")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            request = read_json(task_dir / "raw/personal-content/mechanism-intake-request.json")
            requested = request["mechanisms"][0]
            source = analysis["mechanisms"][0]
            self.assertEqual(requested["sample_id"], analysis["sample_id"])
            self.assertEqual(requested["mechanism_id"], source["id"])
            self.assertEqual(requested["name"], source["name"])
            self.assertEqual(requested["description"], source["description"])
            self.assertEqual(requested["observed_facts"], source["observed_facts"])
            self.assertEqual(requested["inferences"], source["inferences"])
            self.assertEqual(requested["confidence"], source["confidence"])
            self.assertNotIn("approved", requested)
            self.assertNotIn("generated_content", requested)

    def test_mock_statuses_are_saved_and_partial_success_advances(self):
        with temp_project() as root:
            task_dir = prepare_mechanism_intake_task(root)
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

            self.assertEqual(result.returncode, 0, result.stderr)
            response = read_json(task_dir / "raw/personal-content/mechanism-intake-response.json")
            statuses = {item["source_mechanism_id"]: item["status"] for item in response["results"]}
            self.assertEqual(statuses["mechanism-001"], "imported")
            self.assertEqual(statuses["mechanism-002"], "matched_existing")
            self.assertEqual(statuses["mechanism-003"], "limited")
            self.assertEqual(statuses["mechanism-004"], "rejected")
            self.assertEqual(statuses["mechanism-005"], "failed")
            self.assertIn("current_stage: aggregation", read_text(task_dir / "state.yaml"))

    def test_all_failed_blocks_and_stays_on_mechanism_intake(self):
        with temp_project() as root:
            task_dir = prepare_mechanism_intake_task(root)
            analysis_path = task_dir / "analysis/analysis.yaml"
            analysis = read_json(analysis_path)
            for mechanism in analysis["mechanisms"]:
                mechanism["name"] = "MOCK_FAIL " + mechanism["name"]
            write_json(analysis_path, analysis)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: blocked", state)
            self.assertIn("current_stage: mechanism_intake", state)
            self.assertIn("all mechanism intake results failed", state)

    def test_all_rejected_or_failed_and_rejected_blocks(self):
        with temp_project() as root:
            task_dir = prepare_mechanism_intake_task(root)
            analysis_path = task_dir / "analysis/analysis.yaml"
            analysis = read_json(analysis_path)
            for mechanism in analysis["mechanisms"]:
                mechanism["name"] = "REJECT " + mechanism["name"]
            write_json(analysis_path, analysis)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: blocked", state)
            self.assertIn("no successful mechanism intake result", state)

        with temp_project() as root:
            task_dir = prepare_mechanism_intake_task(root)
            analysis_path = task_dir / "analysis/analysis.yaml"
            analysis = read_json(analysis_path)
            analysis["mechanisms"][0]["name"] = "REJECT " + analysis["mechanisms"][0]["name"]
            analysis["mechanisms"][1]["name"] = "MOCK_FAIL " + analysis["mechanisms"][1]["name"]
            analysis["mechanisms"][2]["name"] = "REJECT " + analysis["mechanisms"][2]["name"]
            write_json(analysis_path, analysis)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: blocked", state)
            self.assertIn("no successful mechanism intake result", state)

    def test_at_least_one_limited_can_advance(self):
        with temp_project() as root:
            task_dir = prepare_mechanism_intake_task(root)
            analysis_path = task_dir / "analysis/analysis.yaml"
            analysis = read_json(analysis_path)
            analysis["mechanisms"][0]["name"] = "Limited Mechanism"
            analysis["mechanisms"][0]["confidence"] = "low"
            analysis["mechanisms"][1]["name"] = "REJECT " + analysis["mechanisms"][1]["name"]
            analysis["mechanisms"][2]["name"] = "MOCK_FAIL " + analysis["mechanisms"][2]["name"]
            write_json(analysis_path, analysis)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            response = read_json(task_dir / "raw/personal-content/mechanism-intake-response.json")
            statuses = [item["status"] for item in response["results"]]
            self.assertIn("limited", statuses)
            self.assertIn("current_stage: aggregation", read_text(task_dir / "state.yaml"))

    def test_missing_or_invalid_analysis_blocks(self):
        with temp_project() as root:
            task_dir = prepare_mechanism_intake_task(root)
            (task_dir / "analysis/analysis.yaml").unlink()

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("Missing analysis.yaml", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            task_dir = prepare_mechanism_intake_task(root)
            analysis = read_json(task_dir / "analysis/analysis.yaml")
            analysis["approved"] = True
            write_json(task_dir / "analysis/analysis.yaml", analysis)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("forbidden analysis field", read_text(task_dir / "state.yaml"))

    def test_adapter_does_not_create_formal_storage_and_result_only_contains_refs(self):
        with temp_project() as root:
            task_dir = prepare_mechanism_intake_task(root)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            for forbidden in ("rules", "assets", "profiles", "mechanisms"):
                self.assertFalse((task_dir / forbidden).exists(), forbidden)
            result_text = read_text(task_dir / "analysis/mechanism-intake-result.json")
            self.assertIn("external_object", result_text)
            self.assertNotIn("observed_facts", result_text)
            self.assertNotIn("inferences", result_text)
            self.assertNotIn("description", result_text)

    def test_incomplete_idempotency_artifacts_are_rejected(self):
        with temp_project() as root:
            task_dir = prepare_mechanism_intake_task(root)
            raw_dir = task_dir / "raw/personal-content"
            write_json(raw_dir / "mechanism-intake-request.json", {"partial": True})

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("Incomplete mechanism intake artifacts exist", state)
            self.assertIn("current_stage: mechanism_intake", state)

    def test_complete_idempotency_artifacts_are_reused(self):
        with temp_project() as root:
            task_dir = prepare_mechanism_intake_task(root)
            first = run_cli("run", str(task_dir), cwd=root)
            request_before = read_text(task_dir / "raw/personal-content/mechanism-intake-request.json")
            response_before = read_text(task_dir / "raw/personal-content/mechanism-intake-response.json")
            result_before = read_text(task_dir / "analysis/mechanism-intake-result.json")
            set_running_stage(task_dir, "mechanism_intake", "aggregation")

            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(read_text(task_dir / "raw/personal-content/mechanism-intake-request.json"), request_before)
            self.assertEqual(read_text(task_dir / "raw/personal-content/mechanism-intake-response.json"), response_before)
            self.assertEqual(read_text(task_dir / "analysis/mechanism-intake-result.json"), result_before)

    def test_once_run_does_not_execute_aggregation(self):
        with temp_project() as root:
            task_dir = prepare_mechanism_intake_task(root)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("current_stage: aggregation", read_text(task_dir / "state.yaml"))
            self.assertFalse((task_dir / "analysis/learning-summary.yaml").exists())

    def test_real_personal_content_provider_calls_command_and_saves_external_refs(self):
        with temp_project() as root:
            task_dir = prepare_mechanism_intake_task(root)
            runner = write_fake_personal_content_cli(root)
            workspace = root / "pc-workspace"

            result = run_cli(
                "run",
                str(task_dir),
                cwd=root,
                env_extra={
                    "XIAOBA_PERSONAL_CONTENT_PROVIDER": "real",
                    "XIAOBA_PERSONAL_CONTENT_COMMAND": json.dumps([sys.executable, str(runner)]),
                    "XIAOBA_PERSONAL_CONTENT_WORKSPACE": str(workspace),
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            request = read_json(task_dir / "raw/personal-content/mechanism-intake-request.json")
            response = read_json(task_dir / "raw/personal-content/mechanism-intake-response.json")
            intake_result = read_json(task_dir / "analysis/mechanism-intake-result.json")
            self.assertEqual(request["adapter"], "real_personal_content")
            self.assertFalse(request["mock"])
            self.assertEqual(request["workspace_ref"], str(workspace))
            self.assertEqual(response["adapter"], "real_personal_content")
            self.assertFalse(response["mock"])
            self.assertEqual(len(response["results"]), 3)
            self.assertEqual(response["results"][0]["status"], "imported")
            self.assertEqual(response["results"][0]["external_object"]["id"], "pc-mechanism-001")
            self.assertEqual(intake_result["workspace_ref"], str(workspace))
            self.assertIn("current_stage: aggregation", read_text(task_dir / "state.yaml"))
            self.assertFalse((task_dir / "rules").exists())
            self.assertFalse((task_dir / "mechanisms").exists())

            calls = read_json(root / "fake-personal-content-calls.json")
            self.assertEqual(len(calls), 3)
            first_payload = calls[0]["payload"]
            self.assertEqual(first_payload["status"], "candidate")
            self.assertEqual(first_payload["source_refs"][0]["source_type"], "external_analysis")
            self.assertTrue(first_payload["evidence_summary"]["observed_facts"])

    def test_real_personal_content_provider_blocks_when_all_imports_fail(self):
        with temp_project() as root:
            task_dir = prepare_mechanism_intake_task(root)
            runner = write_fake_personal_content_cli(root, fail=True)

            result = run_cli(
                "run",
                str(task_dir),
                cwd=root,
                env_extra={
                    "XIAOBA_PERSONAL_CONTENT_PROVIDER": "real",
                    "XIAOBA_PERSONAL_CONTENT_COMMAND": json.dumps([sys.executable, str(runner)]),
                    "XIAOBA_PERSONAL_CONTENT_WORKSPACE": str(root / "pc-workspace"),
                },
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("all mechanism intake results failed", read_text(task_dir / "state.yaml"))
            self.assertIn("current_stage: mechanism_intake", read_text(task_dir / "state.yaml"))

    def test_real_personal_content_provider_treats_existing_candidate_as_match(self):
        with temp_project() as root:
            task_dir = prepare_mechanism_intake_task(root)
            runner = write_fake_personal_content_cli(root, duplicate=True)
            workspace = root / "pc-workspace"

            result = run_cli(
                "run",
                str(task_dir),
                cwd=root,
                env_extra={
                    "XIAOBA_PERSONAL_CONTENT_PROVIDER": "real",
                    "XIAOBA_PERSONAL_CONTENT_COMMAND": json.dumps([sys.executable, str(runner)]),
                    "XIAOBA_PERSONAL_CONTENT_WORKSPACE": str(workspace),
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            response = read_json(task_dir / "raw/personal-content/mechanism-intake-response.json")
            statuses = [item["status"] for item in response["results"]]
            self.assertEqual(statuses, ["matched_existing", "matched_existing", "matched_existing"])
            self.assertTrue(all(item["external_object"]["id"] for item in response["results"]))
            self.assertIn("current_stage: aggregation", read_text(task_dir / "state.yaml"))


def prepare_mechanism_intake_task(root):
    task_dir = create_task(root, "learning", "https://example.com/note/1")
    for _ in range(5):
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


def read_text(path):
    return path.read_text(encoding="utf-8")


def read_json(path):
    return json.loads(read_text(path))


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_fake_personal_content_cli(root, fail=False, duplicate=False):
    runner = root / "fake_personal_content_cli.py"
    calls_path = root / "fake-personal-content-calls.json"
    runner.write_text(
        """
import json
import sys
from pathlib import Path

calls_path = Path("__CALLS_PATH__")
calls = json.loads(calls_path.read_text(encoding='utf-8')) if calls_path.is_file() else []
args = sys.argv[1:]
if 'import-mechanism' not in args:
    print(json.dumps({'ok': False, 'error': 'unsupported command'}))
    sys.exit(1)
workspace = args[args.index('--workspace') + 1]
file_path = args[args.index('--file') + 1]
payload = json.loads(Path(file_path).read_text(encoding='utf-8'))
calls.append({'workspace': workspace, 'file': file_path, 'payload': payload})
calls_path.write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding='utf-8')
if __FAIL__:
    print(json.dumps({'ok': False, 'error': 'fake failure for ' + payload.get('id', '')}, ensure_ascii=False))
    sys.exit(1)
if __DUPLICATE__:
    target_dir = Path(workspace) / 'content-mechanisms'
    target_dir.mkdir(parents=True, exist_ok=True)
    existing_id = 'existing-' + payload.get('id', '')
    (target_dir / (existing_id + '.json')).write_text(json.dumps({
        'id': existing_id,
        'name': payload.get('name'),
        'version': 3
    }, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'ok': False, 'error': '同名候选内容机制已存在，暂未重复保存。'}, ensure_ascii=False))
    sys.exit(1)
index = len(calls)
status = 'limited_created' if payload.get('confidence_level') == 'low' else 'created'
print(json.dumps({
    'ok': True,
    'result': {
        'mechanism_id': 'pc-mechanism-%03d' % index,
        'status_category': status,
        'mechanism_status': 'candidate',
        'confidence_level': payload.get('confidence_level', 'medium'),
        'missing_information': payload.get('evidence_summary', {}).get('missing_information', []),
        'limitations': payload.get('limitations', []),
        'user_summary': 'saved',
        'machine_summary': {'mechanism_id': 'pc-mechanism-%03d' % index}
    }
}, ensure_ascii=False))
""".replace("__CALLS_PATH__", str(calls_path)).replace("__FAIL__", "True" if fail else "False").replace("__DUPLICATE__", "True" if duplicate else "False"),
        encoding="utf-8",
    )
    return runner


def write_fake_personal_content_help_cli(root):
    runner = root / "fake_personal_content_help_cli.py"
    runner.write_text(
        """
import sys

if '--help' not in sys.argv:
    print('unsupported')
    sys.exit(1)
print('usage: personal-content import-mechanism show-generation-context propose-rule-from-mechanism create-rule-decision resolve-decision')
""",
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
