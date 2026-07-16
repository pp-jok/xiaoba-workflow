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


class LearningBatchMechanismIntakeTests(unittest.TestCase):
    def test_batch_mechanism_intake_generates_artifacts_and_completes(self):
        with temp_project() as root:
            task_dir = prepare_batch_mechanism_intake_task(root, ["sample-001", "sample-003"])
            cross_before = read_text(task_dir / "analysis/cross-sample-analysis.yaml")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            request = read_json(task_dir / "raw/personal-content/batch-mechanism-intake-request.json")
            response = read_json(task_dir / "raw/personal-content/batch-mechanism-intake-response.json")
            intake = read_json(task_dir / "analysis/batch-mechanism-intake-result.json")
            summary = read_json(task_dir / "analysis/batch-learning-summary.yaml")
            self.assertEqual(request["operation"], "batch_create_or_match_candidate_mechanisms")
            self.assertEqual(request["workspace_ref"], "mock://personal-content/default")
            self.assertTrue(request["candidates"])
            self.assertEqual(len(response["results"]), len(request["candidates"]))
            self.assertEqual(intake["task_id"], request["task_id"])
            self.assertEqual(summary["task_id"], request["task_id"])
            self.assertEqual(read_text(task_dir / "analysis/cross-sample-analysis.yaml"), cross_before)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: completed", state)
            self.assertIn("current_stage: completed", state)
            self.assertIn("next_stage: null", state)

    def test_only_candidates_are_imported_and_cross_sample_fields_are_retained(self):
        with temp_project() as root:
            task_dir = prepare_batch_mechanism_intake_task(root, ["sample-001", "sample-003"])
            cross = read_json(task_dir / "analysis/cross-sample-analysis.yaml")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            request = read_json(task_dir / "raw/personal-content/batch-mechanism-intake-request.json")
            candidate = request["candidates"][0]
            source = cross["mechanism_candidates"][0]
            self.assertEqual(candidate["candidate_id"], source["candidate_id"])
            self.assertEqual(candidate["member_mechanisms"], source["member_mechanisms"])
            self.assertEqual(candidate["supporting_samples"], source["supporting_samples"])
            self.assertEqual(candidate["support_count"], source["support_count"])
            self.assertEqual(candidate["counter_evidence"], source["counter_evidence"])
            self.assertEqual(candidate["differences"], source["differences"])
            self.assertEqual(candidate["operation"], "create_or_match_candidate_mechanism")
            imported_ids = {item["candidate_id"] for item in request["candidates"]}
            unmatched_ids = {item["mechanism_id"] for item in request["unmatched_observations"]}
            self.assertFalse(imported_ids.intersection(unmatched_ids))

    def test_mock_statuses_counts_and_summary(self):
        with temp_project() as root:
            task_dir = prepare_batch_mechanism_intake_task(root, ["sample-001", "sample-003"])
            cross_path = task_dir / "analysis/cross-sample-analysis.yaml"
            cross = read_json(cross_path)
            cross["mechanism_candidates"][0]["name"] = "Imported Cross Candidate"
            cross["mechanism_candidates"][0]["confidence"] = "medium"
            cross["mechanism_candidates"][1]["name"] = "MATCH_EXISTING Cross Candidate"
            cross["mechanism_candidates"][2]["name"] = "Limited Cross Candidate"
            cross["mechanism_candidates"][2]["confidence"] = "low"
            rejected = clone_candidate(cross["mechanism_candidates"][0], "cross-mechanism-004", "REJECT Cross Candidate")
            failed = clone_candidate(cross["mechanism_candidates"][0], "cross-mechanism-005", "MOCK_FAIL Cross Candidate")
            cross["mechanism_candidates"].extend([rejected, failed])
            write_json(cross_path, cross)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            response = read_json(task_dir / "raw/personal-content/batch-mechanism-intake-response.json")
            statuses = {item["source_candidate_id"]: item["status"] for item in response["results"]}
            self.assertEqual(statuses["cross-mechanism-001"], "imported")
            self.assertEqual(statuses["cross-mechanism-002"], "matched_existing")
            self.assertEqual(statuses["cross-mechanism-003"], "limited")
            self.assertEqual(statuses["cross-mechanism-004"], "rejected")
            self.assertEqual(statuses["cross-mechanism-005"], "failed")
            result_data = read_json(task_dir / "analysis/batch-mechanism-intake-result.json")
            self.assertEqual(result_data["counts"]["imported"], 1)
            self.assertEqual(result_data["counts"]["matched_existing"], 1)
            self.assertEqual(result_data["counts"]["limited"], 1)
            self.assertEqual(result_data["counts"]["rejected"], 1)
            self.assertEqual(result_data["counts"]["failed"], 1)
            summary = read_json(task_dir / "analysis/batch-learning-summary.yaml")
            self.assertTrue(summary["mechanism_intake_summary"]["imported"])
            self.assertTrue(summary["governance"]["recommended"])
            self.assertTrue(summary["governance"]["pending_rule_suggestions"])

    def test_all_rejected_failed_or_no_candidates_blocks(self):
        with temp_project() as root:
            task_dir = prepare_batch_mechanism_intake_task(root, ["sample-001", "sample-003"])
            cross_path = task_dir / "analysis/cross-sample-analysis.yaml"
            cross = read_json(cross_path)
            for candidate in cross["mechanism_candidates"]:
                candidate["name"] = "REJECT " + candidate["name"]
            write_json(cross_path, cross)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("no successful batch mechanism intake result", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            task_dir = prepare_batch_mechanism_intake_task(root, ["sample-001", "sample-003"])
            cross_path = task_dir / "analysis/cross-sample-analysis.yaml"
            cross = read_json(cross_path)
            cross["mechanism_candidates"] = []
            write_json(cross_path, cross)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("no mechanism candidates to import", read_text(task_dir / "state.yaml"))

    def test_response_result_validation_rejects_missing_duplicate_and_bad_counts(self):
        with temp_project() as root:
            task_dir = prepare_batch_mechanism_intake_task(root, ["sample-001", "sample-003"])
            build_complete_batch_artifacts(task_dir)
            response_path = task_dir / "raw/personal-content/batch-mechanism-intake-response.json"
            response = read_json(response_path)
            response["results"] = response["results"][:-1]
            write_json(response_path, response)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("response candidates mismatch", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            task_dir = prepare_batch_mechanism_intake_task(root, ["sample-001", "sample-003"])
            build_complete_batch_artifacts(task_dir)
            result_path = task_dir / "analysis/batch-mechanism-intake-result.json"
            result_data = read_json(result_path)
            result_data["counts"]["imported"] = 99
            write_json(result_path, result_data)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("batch mechanism intake counts mismatch", read_text(task_dir / "state.yaml"))

    def test_idempotency_and_partial_artifacts(self):
        with temp_project() as root:
            task_dir = prepare_batch_mechanism_intake_task(root, ["sample-001", "sample-003"])
            first = run_cli("run", str(task_dir), cwd=root)
            request_before = read_text(task_dir / "raw/personal-content/batch-mechanism-intake-request.json")
            set_running_stage(task_dir, "mechanism_intake", "completed")

            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(read_text(task_dir / "raw/personal-content/batch-mechanism-intake-request.json"), request_before)

        with temp_project() as root:
            task_dir = prepare_batch_mechanism_intake_task(root, ["sample-001", "sample-003"])
            write_json(task_dir / "raw/personal-content/batch-mechanism-intake-request.json", {"partial": True})

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("Incomplete batch mechanism intake artifacts exist", read_text(task_dir / "state.yaml"))

    def test_boundaries_and_single_learning_unchanged(self):
        with temp_project() as root:
            task_dir = prepare_batch_mechanism_intake_task(root, ["sample-001", "sample-003"])

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            for forbidden in ("mechanisms", "rules", "assets", "profiles"):
                self.assertFalse((task_dir / forbidden).exists(), forbidden)
            result_text = read_text(task_dir / "analysis/batch-mechanism-intake-result.json")
            self.assertIn("external_object", result_text)
            self.assertNotIn("observed_facts", result_text)
            self.assertFalse((task_dir / "content/generated-post.md").exists())

            learning = create_task(root, "learning", "https://example.com/note/1")
            for _ in range(6):
                single = run_cli("run", str(learning), cwd=root)
                self.assertEqual(single.returncode, 0, single.stderr)
            self.assertIn("current_stage: aggregation", read_text(learning / "state.yaml"))


def prepare_batch_mechanism_intake_task(root, sample_ids):
    task_dir = create_task(root, "learning_batch", "https://example.com/user/1")
    run_cli("run", str(task_dir), cwd=root)
    run_cli("run", str(task_dir), cwd=root)
    assert_ok(run_cli("select-samples", str(task_dir), "--ids", *sample_ids, cwd=root))
    for _ in sample_ids:
        assert_ok(run_cli("run", str(task_dir), cwd=root))
    for _ in sample_ids:
        assert_ok(run_cli("run", str(task_dir), cwd=root))
    for _ in sample_ids:
        assert_ok(run_cli("run", str(task_dir), cwd=root))
    for _ in sample_ids:
        assert_ok(run_cli("run", str(task_dir), cwd=root))
    assert_ok(run_cli("run", str(task_dir), cwd=root))
    return task_dir


def build_complete_batch_artifacts(task_dir):
    cross = read_json(task_dir / "analysis/cross-sample-analysis.yaml")
    request = {
        "task_id": cross["task_id"],
        "aggregation_id": cross["aggregation_id"],
        "workspace_ref": "mock://personal-content/default",
        "operation": "batch_create_or_match_candidate_mechanisms",
        "candidates": [request_candidate_from_cross(item, cross) for item in cross["mechanism_candidates"]],
        "unmatched_observations": cross["unmatched_mechanisms"],
        "rule_suggestions": cross["rule_suggestions"],
        "asset_suggestions": cross["asset_suggestions"],
        "content_opportunities": cross["content_opportunities"],
    }
    results = [
        {
            "source_candidate_id": item["candidate_id"],
            "status": "imported",
            "external_object_type": "content_mechanism",
            "external_object_id": "mock-" + item["candidate_id"],
            "external_version": 1,
            "external_object": {"type": "content_mechanism", "id": "mock-" + item["candidate_id"], "version": 1},
            "workspace_ref": "mock://personal-content/default",
            "reason": "Imported.",
            "warnings": [],
            "retained_counter_evidence": item["counter_evidence"],
            "retained_differences": item["differences"],
        }
        for item in cross["mechanism_candidates"]
    ]
    response = {
        "task_id": cross["task_id"],
        "aggregation_id": cross["aggregation_id"],
        "workspace_ref": "mock://personal-content/default",
        "operation": "batch_create_or_match_candidate_mechanisms",
        "results": results,
    }
    intake = {
        "task_id": cross["task_id"],
        "aggregation_id": cross["aggregation_id"],
        "workspace_ref": "mock://personal-content/default",
        "results": [
            {
                "source_candidate_id": item["source_candidate_id"],
                "status": item["status"],
                "external_object": item["external_object"],
                "reason": item["reason"],
                "warnings": item["warnings"],
            }
            for item in results
        ],
        "unmatched_observations": cross["unmatched_mechanisms"],
        "counts": {"imported": len(results), "matched_existing": 0, "limited": 0, "rejected": 0, "failed": 0},
        "warnings": [],
    }
    summary = {
        "task_id": cross["task_id"],
        "aggregation_id": cross["aggregation_id"],
        "sample_ids": cross["sample_ids"],
        "sample_count": len(cross["sample_ids"]),
        "cross_sample_summary": {
            "candidate_count": len(cross["mechanism_candidates"]),
            "unmatched_count": len(cross["unmatched_mechanisms"]),
            "warnings": [],
        },
        "mechanism_intake_summary": {"imported": [r["source_candidate_id"] for r in results], "matched_existing": [], "limited": [], "rejected": [], "failed": []},
        "governance": {"recommended": False, "reasons": [], "pending_rule_suggestions": [], "pending_asset_suggestions": []},
        "content_opportunities": cross["content_opportunities"],
        "open_questions": cross["questions"],
        "next_recommended_actions": [],
    }
    write_json(task_dir / "raw/personal-content/batch-mechanism-intake-request.json", request)
    write_json(task_dir / "raw/personal-content/batch-mechanism-intake-response.json", response)
    write_json(task_dir / "analysis/batch-mechanism-intake-result.json", intake)
    write_json(task_dir / "analysis/batch-learning-summary.yaml", summary)


def clone_candidate(source, candidate_id, name):
    candidate = json.loads(json.dumps(source))
    candidate["candidate_id"] = candidate_id
    candidate["name"] = name
    for member in candidate["member_mechanisms"]:
        member["analysis_ref"] = member["analysis_ref"]
    return candidate


def request_candidate_from_cross(item, cross):
    return {
        "task_id": cross["task_id"],
        "aggregation_id": cross["aggregation_id"],
        "candidate_id": item["candidate_id"],
        "name": item["name"],
        "description": item["description"],
        "member_mechanisms": item["member_mechanisms"],
        "supporting_samples": item["supporting_samples"],
        "support_count": item["support_count"],
        "observed_facts": item["observed_facts"],
        "inferences": item["inferences"],
        "counter_evidence": item["counter_evidence"],
        "differences": item["differences"],
        "applicable_scope": item["applicable_scope"],
        "limitations": item["limitations"],
        "alternative_explanations": item["alternative_explanations"],
        "confidence": item["confidence"],
        "source_references": item["member_mechanisms"],
        "merge_recommendation": item["merge_recommendation"],
        "account_workspace_reference": "mock://personal-content/default",
        "operation": "create_or_match_candidate_mechanism",
    }


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


def assert_ok(result):
    if result.returncode != 0:
        raise AssertionError(result.stderr)


def set_running_stage(task_dir, stage, next_stage):
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
