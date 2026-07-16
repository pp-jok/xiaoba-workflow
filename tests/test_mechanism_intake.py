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


class MechanismIntakeTests(unittest.TestCase):
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
