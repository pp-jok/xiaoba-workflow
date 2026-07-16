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
