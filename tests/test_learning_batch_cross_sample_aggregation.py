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


class LearningBatchCrossSampleAggregationTests(unittest.TestCase):
    def test_less_than_two_available_samples_blocks(self):
        with temp_project() as root:
            task_dir = prepare_cross_sample_task(root, ["sample-001"])

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: blocked", state)
            self.assertIn("current_stage: cross_sample_aggregation", state)
            self.assertIn("at least 2 available samples", state)

    def test_generates_markdown_yaml_and_advances_to_mechanism_intake(self):
        with temp_project() as root:
            task_dir = prepare_cross_sample_task(root, ["sample-001", "sample-003"])

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            markdown = read_text(task_dir / "raw/hot-learning/cross-sample-analysis.md")
            invocation = read_json(task_dir / "raw/hot-learning/cross-sample-invocation.json")
            cross = read_json(task_dir / "analysis/cross-sample-analysis.yaml")
            self.assertIn("sample-001: analysis.yaml#mechanisms[0]", markdown)
            self.assertIn("sample-003: evidence.yaml#facts.metrics.likes", markdown)
            self.assertEqual(invocation["adapter"], "mock_hot_learning_cross_sample")
            self.assertTrue(invocation["mock"])
            self.assertEqual(invocation["task_id"], cross["task_id"])
            self.assertEqual(cross["sample_ids"], ["sample-001", "sample-003"])
            self.assertTrue(cross["mechanism_candidates"])
            self.assertIn("current_stage: mechanism_intake", read_text(task_dir / "state.yaml"))
            self.assertFalse((task_dir / "raw/personal-content/mechanism-intake-request.json").exists())

    def test_similar_mechanisms_group_and_singletons_are_unmatched(self):
        with temp_project() as root:
            task_dir = prepare_cross_sample_task(root, ["sample-001", "sample-003"])
            analysis_path = task_dir / "analysis/samples/sample-003/analysis.yaml"
            analysis = read_json(analysis_path)
            analysis["mechanisms"][2]["name"] = "Unique Visual Rhythm"
            analysis["mechanisms"][2]["description"] = "Only this sample shows a unique visual rhythm."
            write_json(analysis_path, analysis)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            cross = read_json(task_dir / "analysis/cross-sample-analysis.yaml")
            candidate = cross["mechanism_candidates"][0]
            self.assertGreaterEqual(candidate["support_count"], 2)
            self.assertEqual(candidate["support_count"], len(candidate["supporting_samples"]))
            self.assertGreaterEqual(len(set(candidate["supporting_samples"])), 2)
            unmatched_refs = [item["analysis_ref"] for item in cross["unmatched_mechanisms"]]
            self.assertIn("sample-003:analysis.yaml#mechanisms[2]", unmatched_refs)

    def test_facts_inferences_counter_evidence_and_differences_are_separate(self):
        with temp_project() as root:
            task_dir = prepare_cross_sample_task(root, ["sample-001", "sample-003"])

            run_cli("run", str(task_dir), cwd=root)

            cross = read_json(task_dir / "analysis/cross-sample-analysis.yaml")
            candidate = cross["mechanism_candidates"][0]
            self.assertTrue(candidate["observed_facts"])
            self.assertTrue(candidate["inferences"])
            self.assertIsInstance(candidate["counter_evidence"], list)
            self.assertTrue(candidate["differences"])
            self.assertIn("sample_id", candidate["observed_facts"][0])
            self.assertIn("analysis_ref", candidate["inferences"][0])

    def test_partial_inputs_limit_confidence_and_counter_evidence_prevents_high(self):
        with temp_project() as root:
            task_dir = prepare_cross_sample_task(root, ["sample-001", "sample-003"])
            analysis_path = task_dir / "analysis/samples/sample-003/analysis.yaml"
            analysis = read_json(analysis_path)
            analysis["mechanisms"][0]["alternative_explanations"] = ["CONFLICT: performance may be topic-only."]
            write_json(analysis_path, analysis)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            cross = read_json(task_dir / "analysis/cross-sample-analysis.yaml")
            confidences = {candidate["confidence"] for candidate in cross["mechanism_candidates"]}
            self.assertNotIn("high", confidences)
            self.assertTrue(any(candidate["counter_evidence"] for candidate in cross["mechanism_candidates"]))

    def test_invalid_existing_cross_sample_yaml_blocks(self):
        with temp_project() as root:
            task_dir = prepare_cross_sample_task(root, ["sample-001", "sample-003"])
            raw_dir = task_dir / "raw/hot-learning"
            write_text(raw_dir / "cross-sample-analysis.md", "# existing\n")
            write_json(raw_dir / "cross-sample-invocation.json", {"adapter": "mock_hot_learning_cross_sample"})
            invalid = valid_cross_sample_fixture(task_dir)
            invalid["mechanism_candidates"][0]["member_mechanisms"][0]["mechanism_id"] = "missing"
            write_json(task_dir / "analysis/cross-sample-analysis.yaml", invalid)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("invalid member mechanism", read_text(task_dir / "state.yaml"))

    def test_forbidden_fields_and_unreferenced_generalization_are_rejected(self):
        with temp_project() as root:
            task_dir = prepare_cross_sample_task(root, ["sample-001", "sample-003"])
            raw_dir = task_dir / "raw/hot-learning"
            write_text(raw_dir / "cross-sample-analysis.md", "# existing\n")
            write_json(raw_dir / "cross-sample-invocation.json", {"adapter": "mock_hot_learning_cross_sample"})
            invalid = valid_cross_sample_fixture(task_dir)
            invalid["rule_card"] = {"status": "approved"}
            write_json(task_dir / "analysis/cross-sample-analysis.yaml", invalid)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("forbidden cross-sample field", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            task_dir = prepare_cross_sample_task(root, ["sample-001", "sample-003"])
            raw_dir = task_dir / "raw/hot-learning"
            write_text(raw_dir / "cross-sample-analysis.md", "# existing\n")
            write_json(raw_dir / "cross-sample-invocation.json", {"adapter": "mock_hot_learning_cross_sample"})
            invalid = valid_cross_sample_fixture(task_dir)
            invalid["mechanism_candidates"][0]["observed_facts"] = [{"text": "多个样本都表明这个机制有效"}]
            write_json(task_dir / "analysis/cross-sample-analysis.yaml", invalid)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("observed fact must reference a sample", read_text(task_dir / "state.yaml"))

    def test_complete_artifacts_are_reused_and_partial_artifacts_block(self):
        with temp_project() as root:
            task_dir = prepare_cross_sample_task(root, ["sample-001", "sample-003"])
            first = run_cli("run", str(task_dir), cwd=root)
            markdown_before = read_text(task_dir / "raw/hot-learning/cross-sample-analysis.md")
            set_running_stage(task_dir, "cross_sample_aggregation", "mechanism_intake")

            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(read_text(task_dir / "raw/hot-learning/cross-sample-analysis.md"), markdown_before)

        with temp_project() as root:
            task_dir = prepare_cross_sample_task(root, ["sample-001", "sample-003"])
            write_text(task_dir / "raw/hot-learning/cross-sample-analysis.md", "# partial\n")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("Incomplete cross-sample aggregation artifacts", read_text(task_dir / "state.yaml"))

    def test_does_not_modify_sample_analysis_or_execute_mechanism_intake(self):
        with temp_project() as root:
            task_dir = prepare_cross_sample_task(root, ["sample-001", "sample-003"])
            before = read_text(task_dir / "analysis/samples/sample-001/analysis.yaml")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(read_text(task_dir / "analysis/samples/sample-001/analysis.yaml"), before)
            self.assertFalse((task_dir / "raw/personal-content/mechanism-intake-response.json").exists())
            self.assertFalse((task_dir / "rules").exists())
            self.assertFalse((task_dir / "content/generated-post.md").exists())


def prepare_cross_sample_task(root, sample_ids):
    task_dir = create_task(root, "learning_batch", "https://example.com/user/1")
    run_cli("run", str(task_dir), cwd=root)
    run_cli("run", str(task_dir), cwd=root)
    result = run_cli("select-samples", str(task_dir), "--ids", *sample_ids, cwd=root)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    for _ in sample_ids:
        assert_ok(run_cli("run", str(task_dir), cwd=root))
    for _ in sample_ids:
        assert_ok(run_cli("run", str(task_dir), cwd=root))
    for _ in sample_ids:
        assert_ok(run_cli("run", str(task_dir), cwd=root))
    for _ in sample_ids:
        assert_ok(run_cli("run", str(task_dir), cwd=root))
    return task_dir


def valid_cross_sample_fixture(task_dir):
    task = read_json(task_dir / "analysis/batch-analysis-index.json")
    sample_ids = task["normalized_analyses"][:2]
    return {
        "task_id": read_task_id(task_dir),
        "aggregation_id": "cross-" + read_task_id(task_dir),
        "sample_ids": sample_ids,
        "normalization": {"status": "normalized", "warnings": []},
        "mechanism_candidates": [
            {
                "candidate_id": "cross-mechanism-001",
                "name": "Specific Promise Title",
                "description": "Candidate shared mechanism only.",
                "member_mechanisms": [
                    {"sample_id": sample_ids[0], "mechanism_id": "mechanism-001", "analysis_ref": sample_ids[0] + ":analysis.yaml#mechanisms[0]"},
                    {"sample_id": sample_ids[1], "mechanism_id": "mechanism-001", "analysis_ref": sample_ids[1] + ":analysis.yaml#mechanisms[0]"},
                ],
                "supporting_samples": sample_ids,
                "support_count": len(sample_ids),
                "observed_facts": [{"sample_id": sample_ids[0], "evidence_ref": "evidence.yaml#facts.title", "text": "Title observed"}],
                "inferences": [{"sample_id": sample_ids[0], "analysis_ref": sample_ids[0] + ":analysis.yaml#mechanisms[0]", "text": "Candidate inference"}],
                "counter_evidence": [],
                "differences": [],
                "applicable_scope": [],
                "limitations": [],
                "alternative_explanations": [],
                "confidence": "low",
                "confidence_basis": ["two samples with partial evidence"],
                "merge_recommendation": "candidate",
            }
        ],
        "unmatched_mechanisms": [],
        "cross_sample_patterns": [],
        "rule_suggestions": [],
        "asset_suggestions": [],
        "content_opportunities": [],
        "questions": [],
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


def read_task_id(task_dir):
    for line in read_text(task_dir / "task.yaml").splitlines():
        if line.startswith("task_id:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError("task_id missing")


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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
