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


class MockHotLearningTests(unittest.TestCase):
    def test_analysis_stage_writes_raw_hot_learning_files_and_advances(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((task_dir / "raw/hot-learning/analysis.md").is_file())
            self.assertTrue((task_dir / "raw/hot-learning/invocation.json").is_file())
            self.assertIn("current_stage: analysis_normalization", read_text(task_dir / "state.yaml"))

    def test_analysis_markdown_contains_facts_inferences_and_evidence_refs(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            run_cli("run", str(task_dir), cwd=root)

            markdown = read_text(task_dir / "raw/hot-learning/analysis.md")

            self.assertIn("## 可观察事实", markdown)
            self.assertIn("## 推断", markdown)
            self.assertIn("## 内容机制", markdown)
            self.assertIn("Evidence reference: evidence.yaml#facts.title", markdown)
            self.assertIn("置信度：medium", markdown)
            self.assertIn("通过明确承诺吸引点击", markdown)

    def test_new_mock_analysis_business_content_is_chinese(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            run_cli("run", str(task_dir), cwd=root)
            run_cli("run", str(task_dir), cwd=root)

            analysis = read_json(task_dir / "analysis/analysis.yaml")

            self.assertTrue(all(has_chinese(item["name"]) for item in analysis["mechanisms"]))
            self.assertTrue(all(has_chinese(item) for item in analysis["rule_suggestions"]))
            self.assertTrue(all(has_chinese(item) for item in analysis["asset_suggestions"]))
            self.assertTrue(all(has_chinese(item) for item in analysis["content_opportunities"]))

    def test_invocation_json_records_context(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            run_cli("run", str(task_dir), cwd=root)

            invocation = read_json(task_dir / "raw/hot-learning/invocation.json")

            self.assertEqual(invocation["adapter"], "mock_hot_learning")
            self.assertTrue(invocation["mock"])
            self.assertEqual(invocation["task_id"], task_dir.name)
            self.assertEqual(invocation["stage"], "analysis")
            self.assertEqual(invocation["evidence_path"], "evidence/evidence.yaml")
            self.assertTrue(invocation["evidence_sample_id"].startswith("sample-"))
            self.assertEqual(invocation["prompt_path"], "prompts/hot-learning-analysis-only.md")
            self.assertIn("analyze evidence", invocation["allowed_actions"])
            self.assertIn("create formal rules", invocation["forbidden_actions"])
            self.assertEqual(invocation["outputs"], ["raw/hot-learning/analysis.md"])

    def test_import_hot_learning_analysis_validates_raw_and_keeps_stage(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            markdown_path = root / "manual-hot-learning.md"
            write_text(markdown_path, manual_hot_learning_markdown())

            result = run_cli("import-hot-learning-analysis", str(task_dir), "--markdown", str(markdown_path), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((task_dir / "raw/hot-learning/analysis.md").is_file())
            self.assertTrue((task_dir / "raw/hot-learning/invocation.json").is_file())
            invocation = read_json(task_dir / "raw/hot-learning/invocation.json")
            self.assertEqual(invocation["adapter"], "xhs_hot_learning_manual")
            self.assertFalse(invocation["mock"])
            self.assertEqual(invocation["source_markdown"], str(markdown_path))
            self.assertIn("current_stage: analysis", read_text(task_dir / "state.yaml"))

            advance = run_cli("run", str(task_dir), cwd=root)
            normalize = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(advance.returncode, 0, advance.stderr)
            self.assertEqual(normalize.returncode, 0, normalize.stderr)
            self.assertTrue((task_dir / "analysis/analysis.yaml").is_file())
            analysis = read_json(task_dir / "analysis/analysis.yaml")
            self.assertEqual(analysis["normalization"]["status"], "normalized")
            self.assertEqual(len(analysis["mechanisms"]), 3)

    def test_chinese_markdown_can_be_imported_and_normalized(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            markdown_path = root / "manual-hot-learning-cn.md"
            write_text(markdown_path, manual_hot_learning_chinese_markdown())

            imported = run_cli("import-hot-learning-analysis", str(task_dir), "--markdown", str(markdown_path), cwd=root)
            run_cli("run", str(task_dir), cwd=root)
            normalized = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(imported.returncode, 0, imported.stderr)
            self.assertEqual(normalized.returncode, 0, normalized.stderr)
            analysis = read_json(task_dir / "analysis/analysis.yaml")
            self.assertEqual(analysis["mechanisms"][0]["name"], "通过明确承诺吸引点击")
            self.assertIn("标题直接给出可获得的结果", analysis["mechanisms"][0]["description"])
            self.assertTrue(has_chinese(analysis["rule_suggestions"][0]))

    def test_import_hot_learning_analysis_rejects_invalid_refs_and_existing_raw(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            bad_markdown = root / "bad-hot-learning.md"
            write_text(bad_markdown, manual_hot_learning_markdown().replace("evidence.yaml#facts.title", "evidence.yaml#facts.missing_title", 1))

            bad = run_cli("import-hot-learning-analysis", str(task_dir), "--markdown", str(bad_markdown), cwd=root)

            self.assertEqual(bad.returncode, 1)
            self.assertIn("invalid evidence_ref", bad.stderr)
            self.assertFalse((task_dir / "raw/hot-learning/analysis.md").exists())
            self.assertFalse((task_dir / "raw/hot-learning/invocation.json").exists())

            good_markdown = root / "good-hot-learning.md"
            write_text(good_markdown, manual_hot_learning_markdown())
            first = run_cli("import-hot-learning-analysis", str(task_dir), "--markdown", str(good_markdown), cwd=root)
            second = run_cli("import-hot-learning-analysis", str(task_dir), "--markdown", str(good_markdown), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 1)
            self.assertIn("raw hot-learning output already exists", second.stderr)

    def test_partial_evidence_limitations_are_included_in_markdown(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            run_cli("run", str(task_dir), cwd=root)

            markdown = read_text(task_dir / "raw/hot-learning/analysis.md")

            self.assertIn("缺失 comments", markdown)
            self.assertIn("缺失 transcript", markdown)
            self.assertIn("Lingzao 当前不提供视频文件，不能判断真实镜头。", markdown)

    def test_missing_evidence_blocks_and_keeps_analysis_stage(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            (task_dir / "evidence/evidence.yaml").unlink()

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: blocked", state)
            self.assertIn("current_stage: analysis", state)
            self.assertIn("evidence.yaml", state)

    def test_invalid_evidence_blocks(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            write_json(task_dir / "evidence/evidence.yaml", {"sample_id": "x", "mechanisms": []})

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("forbidden evidence field", read_text(task_dir / "state.yaml"))
            self.assertIn("current_stage: analysis", read_text(task_dir / "state.yaml"))

    def test_normalization_failed_evidence_blocks(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            evidence_path = task_dir / "evidence/evidence.yaml"
            evidence = read_json(evidence_path)
            evidence["normalization"]["status"] = "normalization_failed"
            write_json(evidence_path, evidence)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("normalization_failed", read_text(task_dir / "state.yaml"))

    def test_adapter_does_not_modify_evidence_or_downstream_outputs(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            evidence_before = read_text(task_dir / "evidence/evidence.yaml")

            run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(read_text(task_dir / "evidence/evidence.yaml"), evidence_before)
            self.assertFalse((task_dir / "analysis/analysis.yaml").exists())
            self.assertEqual([], list((task_dir / "governance").iterdir()))
            self.assertEqual([], list((task_dir / "content").iterdir()))

    def test_mock_failure_blocks_without_complete_outputs(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            evidence_path = task_dir / "evidence/evidence.yaml"
            evidence = read_json(evidence_path)
            evidence["source"]["original_url"] = "mock-hot-fail://note"
            write_json(evidence_path, evidence)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: blocked", state)
            self.assertIn("current_stage: analysis", state)
            self.assertIn("Mock Hot Learning failure requested", state)
            self.assertFalse((task_dir / "raw/hot-learning/analysis.md").exists())
            self.assertFalse((task_dir / "raw/hot-learning/invocation.json").exists())

    def test_write_failure_does_not_leave_complete_success_outputs(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            os.mkdir(task_dir / "raw/hot-learning/.analysis.md.tmp")

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertFalse((task_dir / "raw/hot-learning/analysis.md").exists())
            self.assertFalse((task_dir / "raw/hot-learning/invocation.json").exists())
            self.assertIn("current_stage: analysis", read_text(task_dir / "state.yaml"))

    def test_repeated_analysis_run_reuses_existing_raw_outputs(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)
            first = run_cli("run", str(task_dir), cwd=root)
            analysis_path = task_dir / "raw/hot-learning/analysis.md"
            invocation_path = task_dir / "raw/hot-learning/invocation.json"
            analysis_before = read_text(analysis_path)
            invocation_before = read_text(invocation_path)

            replace_line(task_dir / "state.yaml", "current_stage:", "current_stage: analysis")
            replace_line(task_dir / "state.yaml", "next_stage:", "next_stage: analysis_normalization")
            replace_line(task_dir / "state.yaml", "status:", "status: running")
            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(read_text(analysis_path), analysis_before)
            self.assertEqual(read_text(invocation_path), invocation_before)

    def test_once_run_does_not_continue_into_analysis_normalization(self):
        with temp_project() as root:
            task_dir = prepare_analysis_task(root)

            run_cli("run", str(task_dir), cwd=root)

            status = run_cli("task-status", str(task_dir), "--technical", cwd=root)
            self.assertIn("current_stage: analysis_normalization", status.stdout)
            self.assertFalse((task_dir / "analysis/analysis.yaml").exists())

    def test_generation_needs_brief_and_learning_batch_completes(self):
        with temp_project() as root:
            generation = create_task(root, "generation")
            batch = create_task(root, "learning_batch", "https://example.com/user/1")

            generation_intake = run_cli("run", str(generation), cwd=root)
            generation_context = run_cli("run", str(generation), cwd=root)
            run_cli("run", str(batch), cwd=root)
            run_cli("run", str(batch), cwd=root)
            run_cli("select-samples", str(batch), "--ids", "sample-001", "sample-003", cwd=root)
            for _ in range(10):
                run_cli("run", str(batch), cwd=root)
            batch_status = run_cli("task-status", str(batch), "--technical", cwd=root)
            completed_run = run_cli("run", str(batch), cwd=root)

            self.assertEqual(generation_intake.returncode, 0, generation_intake.stderr)
            self.assertEqual(generation_context.returncode, 1)
            self.assertIn("generation brief required", generation_context.stderr)
            self.assertIn("status: completed", batch_status.stdout)
            self.assertIn("current_stage: completed", batch_status.stdout)
            self.assertEqual(completed_run.returncode, 1)
            self.assertIn("Task is completed and cannot run", completed_run.stderr)


def prepare_analysis_task(root):
    task_dir = create_task(root, "learning", "https://example.com/note/1")
    run_cli("run", str(task_dir), cwd=root)
    run_cli("run", str(task_dir), cwd=root)
    run_cli("run", str(task_dir), cwd=root)
    return task_dir


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


def write_text(path, content):
    path.write_text(content, encoding="utf-8")


def replace_line(path, prefix, replacement):
    lines = read_text(path).splitlines()
    updated = [replacement if line.startswith(prefix) else line for line in lines]
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def manual_hot_learning_markdown():
    return """# Hot Learning Raw Analysis

Sample ID: sample-manual

## Observable Facts
- Title is available.
  Evidence reference: evidence.yaml#facts.title
- Body is available.
  Evidence reference: evidence.yaml#facts.body
- Metrics are available.
  Evidence reference: evidence.yaml#facts.metrics

## Inferences
- The sample uses a clear promise and compact support.

## Content Mechanisms
### Mechanism 1: Clear Promise
- Description: The title packages a concrete promise.
- Evidence: evidence.yaml#facts.title
- Confidence: medium
- Alternative explanation: Distribution timing may also matter.

### Mechanism 2: Body Support
- Description: The body provides supporting context for the promise.
- Evidence: evidence.yaml#facts.body
- Confidence: medium
- Alternative explanation: Topic demand may matter more than structure.

### Mechanism 3: Engagement Signal
- Description: Metrics make the sample worth studying while not proving causality.
- Evidence: evidence.yaml#facts.metrics
- Confidence: medium
- Alternative explanation: Audience trust may explain performance.

## Learnable Parts
- Use concrete promises.
- Support claims with visible body evidence.

## Not Copyable Parts
- Do not copy exact wording.
- Do not claim causality from one sample.

## Rule Direction Suggestions
- Candidate direction: title promises need body support.

## Content Asset Direction Suggestions
- Save the title-promise pattern as a candidate asset.

## Content Opportunities
- Draft a follow-up using the same problem-solution shape.

## Missing Information And Limitations
- Missing transcript.

## Evidence Warnings
- None
"""


def manual_hot_learning_chinese_markdown():
    return """# Hot Learning 原始分析

Sample ID: sample-manual

## 可观察事实
- 标题已经可用。
  Evidence reference: evidence.yaml#facts.title
- 正文已经可用。
  Evidence reference: evidence.yaml#facts.body
- 指标已经可用。
  Evidence reference: evidence.yaml#facts.metrics

## 推断
- 这个样本使用了明确承诺，并用正文提供紧凑支撑。

## 内容机制
### 机制 1：通过明确承诺吸引点击
- 描述：标题直接给出可获得的结果，让用户快速判断是否值得进入。
- 证据：evidence.yaml#facts.title
- 置信度：medium
- 替代解释：分发时机也可能影响表现。

### 机制 2：用正文支撑标题承诺
- 描述：正文提供支撑信息，降低标题看起来空泛的风险。
- 证据：evidence.yaml#facts.body
- 置信度：medium
- 替代解释：主题需求可能比结构更重要。

### 机制 3：把互动指标作为弱信号
- 描述：指标说明样本值得观察，但不能证明因果。
- 证据：evidence.yaml#facts.metrics
- 置信度：low
- 替代解释：作者信任或平台分发也可能解释表现。

## 可学习部分
- 使用具体承诺。
- 用正文证据支撑标题。

## 不可照搬部分
- 不复制原标题。
- 不从单样本直接推断因果。

## 规则方向建议
- 候选方向：标题承诺必须能在正文中找到对应支撑。

## 内容资产方向建议
- 保存“标题承诺-正文支撑”结构作为候选资产。

## 内容机会
- 用同样的问题-解决结构做一个原创选题。

## 缺失信息与限制
- 缺失 transcript。

## Evidence Warnings
- None
"""


def has_chinese(value):
    return any("\u4e00" <= char <= "\u9fff" for char in str(value))
