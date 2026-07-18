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


class AnalysisNormalizationTests(unittest.TestCase):
    def test_analysis_markdown_generates_valid_analysis_and_advances(self):
        with temp_project() as root:
            task_dir = prepare_analysis_normalization_task(root)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            analysis = read_json(task_dir / "analysis/analysis.yaml")
            state = read_text(task_dir / "state.yaml")
            evidence = read_json(task_dir / "evidence/evidence.yaml")
            self.assertEqual(analysis["sample_id"], evidence["sample_id"])
            self.assertEqual(analysis["normalization"]["status"], "normalized")
            self.assertEqual(len(analysis["mechanisms"]), 3)
            self.assertIn("current_stage: mechanism_intake", state)

    def test_observed_facts_and_inferences_have_valid_refs(self):
        with temp_project() as root:
            task_dir = prepare_analysis_normalization_task(root)
            run_cli("run", str(task_dir), cwd=root)

            analysis = read_json(task_dir / "analysis/analysis.yaml")
            first = analysis["mechanisms"][0]
            self.assertEqual(first["observed_facts"][0]["evidence_ref"], "evidence.yaml#facts.title")
            self.assertEqual(first["inferences"][0]["raw_analysis_ref"]["file"], "raw/hot-learning/analysis.md")
            self.assertIn("Inferences", first["inferences"][0]["raw_analysis_ref"]["section"])

    def test_transfer_and_suggestions_are_extracted(self):
        with temp_project() as root:
            task_dir = prepare_analysis_normalization_task(root)
            run_cli("run", str(task_dir), cwd=root)

            analysis = read_json(task_dir / "analysis/analysis.yaml")
            self.assertIn("用明确承诺帮助用户快速判断内容价值。", analysis["transfer"]["learnable"])
            self.assertIn("不直接复制标题表述。", analysis["transfer"]["not_copyable"])
            self.assertIn("候选方向：标题承诺必须能在正文中找到明确支撑。", analysis["rule_suggestions"])
            self.assertIn("累积更多样本后，把“标题承诺-正文支撑”结构保存为候选资产。", analysis["asset_suggestions"])
            self.assertIn("用原创案例做一个同类“问题-解决”结构选题。", analysis["content_opportunities"])

    def test_partial_markdown_normalizes_when_at_least_one_mechanism_is_valid(self):
        with temp_project() as root:
            task_dir = prepare_analysis_normalization_task(root)
            markdown_path = task_dir / "raw/hot-learning/analysis.md"
            markdown = read_text(markdown_path)
            markdown = markdown.split("### 机制 2", 1)[0]
            markdown += "\n## 缺失信息与限制\n- 缺失 comments\n"
            write_text(markdown_path, markdown)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            analysis = read_json(task_dir / "analysis/analysis.yaml")
            self.assertEqual(analysis["normalization"]["status"], "partially_normalized")
            self.assertEqual(len(analysis["mechanisms"]), 1)
            self.assertTrue(analysis["normalization"]["warnings"])

    def test_no_valid_mechanism_blocks_as_normalization_failed(self):
        with temp_project() as root:
            task_dir = prepare_analysis_normalization_task(root)
            write_text(task_dir / "raw/hot-learning/analysis.md", "# Empty\n\nNo mechanisms here.\n")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: blocked", state)
            self.assertIn("current_stage: analysis_normalization", state)
            self.assertIn("normalization_failed", state)

    def test_invalid_evidence_reference_blocks(self):
        with temp_project() as root:
            task_dir = prepare_analysis_normalization_task(root)
            path = task_dir / "raw/hot-learning/analysis.md"
            write_text(path, read_text(path).replace("evidence.yaml#facts.title", "evidence.yaml#facts.missing_title", 1))

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("invalid evidence_ref", read_text(task_dir / "state.yaml"))

    def test_analysis_validator_rejects_missing_fact_bad_confidence_forbidden_and_generic_fact(self):
        with temp_project() as root:
            task_dir = prepare_analysis_normalization_task(root)
            analysis_path = task_dir / "analysis/analysis.yaml"
            evidence = read_json(task_dir / "evidence/evidence.yaml")
            invalid = valid_analysis_fixture(evidence["sample_id"])
            invalid["mechanisms"][0]["observed_facts"] = []
            write_json(analysis_path, invalid)
            result = run_cli("run", str(task_dir), cwd=root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("observed fact", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            task_dir = prepare_analysis_normalization_task(root)
            analysis_path = task_dir / "analysis/analysis.yaml"
            evidence = read_json(task_dir / "evidence/evidence.yaml")
            invalid = valid_analysis_fixture(evidence["sample_id"])
            invalid["mechanisms"][0]["confidence"] = "certain"
            write_json(analysis_path, invalid)
            result = run_cli("run", str(task_dir), cwd=root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("invalid confidence", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            task_dir = prepare_analysis_normalization_task(root)
            analysis_path = task_dir / "analysis/analysis.yaml"
            evidence = read_json(task_dir / "evidence/evidence.yaml")
            invalid = valid_analysis_fixture(evidence["sample_id"])
            invalid["approved"] = True
            write_json(analysis_path, invalid)
            result = run_cli("run", str(task_dir), cwd=root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("forbidden analysis field", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            task_dir = prepare_analysis_normalization_task(root)
            analysis_path = task_dir / "analysis/analysis.yaml"
            evidence = read_json(task_dir / "evidence/evidence.yaml")
            invalid = valid_analysis_fixture(evidence["sample_id"])
            invalid["mechanisms"][0]["observed_facts"][0]["text"] = "内容很好"
            write_json(analysis_path, invalid)
            result = run_cli("run", str(task_dir), cwd=root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("generic observed fact", read_text(task_dir / "state.yaml"))

    def test_sample_id_mismatch_blocks(self):
        with temp_project() as root:
            task_dir = prepare_analysis_normalization_task(root)
            analysis_path = task_dir / "analysis/analysis.yaml"
            invalid = valid_analysis_fixture("sample-other")
            write_json(analysis_path, invalid)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("sample_id mismatch", read_text(task_dir / "state.yaml"))

    def test_raw_and_evidence_are_not_modified_and_existing_analysis_is_reused(self):
        with temp_project() as root:
            task_dir = prepare_analysis_normalization_task(root)
            raw_before = read_text(task_dir / "raw/hot-learning/analysis.md")
            evidence_before = read_text(task_dir / "evidence/evidence.yaml")

            first = run_cli("run", str(task_dir), cwd=root)
            analysis_before = read_text(task_dir / "analysis/analysis.yaml")
            replace_line(task_dir / "state.yaml", "current_stage:", "current_stage: analysis_normalization")
            replace_line(task_dir / "state.yaml", "next_stage:", "next_stage: mechanism_intake")
            replace_line(task_dir / "state.yaml", "status:", "status: running")
            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(read_text(task_dir / "raw/hot-learning/analysis.md"), raw_before)
            self.assertEqual(read_text(task_dir / "evidence/evidence.yaml"), evidence_before)
            self.assertEqual(read_text(task_dir / "analysis/analysis.yaml"), analysis_before)

    def test_once_run_does_not_execute_mechanism_intake(self):
        with temp_project() as root:
            task_dir = prepare_analysis_normalization_task(root)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("current_stage: mechanism_intake", read_text(task_dir / "state.yaml"))
            self.assertFalse((task_dir / "raw/personal-content/mechanism-intake-request.json").exists())
            self.assertFalse((task_dir / "analysis/mechanism-intake-result.json").exists())


def prepare_analysis_normalization_task(root):
    task_dir = create_task(root, "learning", "https://example.com/note/1")
    for _ in range(4):
        result = run_cli("run", str(task_dir), cwd=root)
        if result.returncode != 0:
            raise AssertionError(result.stderr)
    return task_dir


def valid_analysis_fixture(sample_id):
    return {
        "sample_id": sample_id,
        "normalization": {"status": "normalized", "warnings": []},
        "mechanisms": [
            {
                "id": "mechanism-001",
                "name": "Specific Promise Title",
                "description": "The title packages the benefit into a direct promise.",
                "problem": "",
                "solution": "",
                "observed_facts": [
                    {"text": "Title: Mock note title", "evidence_ref": "evidence.yaml#facts.title", "source_fragment": "Title: Mock note title"}
                ],
                "inferences": [
                    {
                        "text": "The note likely relies on a clear promise in the title.",
                        "raw_analysis_ref": {"file": "raw/hot-learning/analysis.md", "section": "Inferences"},
                        "source_fragment": "The note likely relies on a clear promise in the title.",
                    }
                ],
                "pattern": [],
                "applicable_scope": [],
                "missing_information": [],
                "limitations": [],
                "alternative_explanations": [],
                "confidence": "medium",
                "source_refs": ["raw/hot-learning/analysis.md#Content Mechanisms"],
            }
        ],
        "transfer": {"learnable": [], "not_copyable": [], "account_fit": [], "originality_requirements": []},
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


def read_text(path):
    return path.read_text(encoding="utf-8")


def write_text(path, value):
    path.write_text(value, encoding="utf-8")


def read_json(path):
    return json.loads(read_text(path))


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def replace_line(path, prefix, replacement):
    lines = read_text(path).splitlines()
    updated = [replacement if line.startswith(prefix) else line for line in lines]
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")
