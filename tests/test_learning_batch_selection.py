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


class LearningBatchSelectionTests(unittest.TestCase):
    def test_task_intake_and_benchmark_screening_pause_for_sample_selection(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning_batch", "https://example.com/user/1")

            intake = run_cli("run", str(task_dir), cwd=root)
            screening = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(intake.returncode, 0, intake.stderr)
            self.assertEqual(screening.returncode, 0, screening.stderr)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: waiting_for_user", state)
            self.assertIn("current_stage: sample_selection", state)
            self.assertIn("type: sample_selection", state)
            self.assertIn("candidates_file: analysis/sample-candidates.json", state)

    def test_mock_profile_posts_and_candidates_are_generated_from_raw(self):
        with temp_project() as root:
            task_dir = prepare_sample_selection_task(root)

            profile = read_json(task_dir / "raw/lingzao/profile.json")
            posted = read_json(task_dir / "raw/lingzao/posted-notes.json")
            invocation = read_json(task_dir / "raw/lingzao/invocation.json")
            candidates = read_json(task_dir / "analysis/sample-candidates.json")
            self.assertEqual(profile["source_url"], "https://example.com/user/1")
            self.assertEqual(len(posted["notes"]), 6)
            self.assertEqual(invocation["adapter"], "mock_lingzao")
            self.assertEqual(len(candidates["candidates"]), 5)
            first = candidates["candidates"][0]
            self.assertEqual(first["sample_id"], "sample-001")
            self.assertIn("title", first)
            self.assertIn("url", first)
            self.assertIn("published_at", first)
            self.assertIn("likes", first["metrics"])
            self.assertIn("saves", first["metrics"])
            self.assertIn("comments", first["metrics"])
            self.assertIn("selection_reason", first)
            self.assertFalse(first["is_selected"])
            self.assertNotIn("mechanisms", json.dumps(candidates))
            self.assertNotIn("rule_suggestions", json.dumps(candidates))

    def test_advance_and_resume_cannot_bypass_sample_selection(self):
        with temp_project() as root:
            task_dir = prepare_sample_selection_task(root)

            advance = run_cli("advance", str(task_dir), cwd=root)
            resume = run_cli("resume", str(task_dir), cwd=root)

            self.assertEqual(advance.returncode, 1)
            self.assertIn("waiting_for_user", advance.stderr)
            self.assertEqual(resume.returncode, 1)
            self.assertIn("select-samples", resume.stderr)
            self.assertIn("current_stage: sample_selection", read_text(task_dir / "state.yaml"))

    def test_select_samples_saves_selection_and_enters_evidence_collection(self):
        with temp_project() as root:
            task_dir = prepare_sample_selection_task(root)
            raw_before = read_text(task_dir / "raw/lingzao/posted-notes.json")

            result = run_cli("select-samples", str(task_dir), "--ids", "sample-003", "sample-001", cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            selected = read_json(task_dir / "analysis/selected-samples.json")
            self.assertEqual([item["sample_id"] for item in selected["selected_samples"]], ["sample-001", "sample-003"])
            self.assertIn("selected_at", selected)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: running", state)
            self.assertIn("current_stage: evidence_collection", state)
            self.assertIn("waiting_for: null", state)
            self.assertEqual(read_text(task_dir / "raw/lingzao/posted-notes.json"), raw_before)

    def test_invalid_selection_inputs_are_rejected(self):
        cases = [
            ([], "at least one sample id"),
            (["sample-999"], "unknown sample id"),
            (["sample-001", "sample-001"], "duplicate sample id"),
        ]
        for ids, message in cases:
            with temp_project() as root:
                task_dir = prepare_sample_selection_task(root)
                result = run_cli("select-samples", str(task_dir), "--ids", *ids, cwd=root)

                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
                self.assertFalse((task_dir / "analysis/selected-samples.json").exists())
                self.assertIn("current_stage: sample_selection", read_text(task_dir / "state.yaml"))

    def test_no_downstream_learning_outputs_are_generated(self):
        with temp_project() as root:
            task_dir = prepare_sample_selection_task(root)

            self.assertFalse((task_dir / "evidence/evidence.yaml").exists())
            self.assertFalse((task_dir / "analysis/analysis.yaml").exists())
            self.assertFalse((task_dir / "analysis/learning-summary.yaml").exists())
            self.assertFalse((task_dir / "content/generated-post.md").exists())
            for forbidden in ("rules", "assets", "profiles", "mechanisms"):
                self.assertFalse((task_dir / forbidden).exists())

    def test_repeated_screening_and_repeated_selection_are_rejected_or_reused(self):
        with temp_project() as root:
            task_dir = create_task(root, "learning_batch", "https://example.com/user/1")
            run_cli("run", str(task_dir), cwd=root)
            first = run_cli("run", str(task_dir), cwd=root)
            candidates_before = read_text(task_dir / "analysis/sample-candidates.json")
            set_running_stage(task_dir, "benchmark_screening", "sample_selection")

            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(read_text(task_dir / "analysis/sample-candidates.json"), candidates_before)

        with temp_project() as root:
            task_dir = prepare_sample_selection_task(root)
            first = run_cli("select-samples", str(task_dir), "--ids", "sample-001", cwd=root)
            set_waiting_sample_selection(task_dir)
            second = run_cli("select-samples", str(task_dir), "--ids", "sample-002", cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 1)
            self.assertIn("selected-samples.json already exists", second.stderr)


def prepare_sample_selection_task(root):
    task_dir = create_task(root, "learning_batch", "https://example.com/user/1")
    for _ in range(2):
        result = run_cli("run", str(task_dir), cwd=root)
        if result.returncode != 0:
            raise AssertionError(result.stderr)
    return task_dir


def temp_project():
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    shutil.copy(PROJECT_ROOT / "workflow.yaml", root / "workflow.yaml")
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


def set_waiting_sample_selection(task_dir):
    state_path = task_dir / "state.yaml"
    lines = []
    skip_waiting_children = False
    for line in read_text(state_path).splitlines():
        if line.startswith("status:"):
            lines.append("status: waiting_for_user")
        elif line.startswith("current_stage:"):
            lines.append("current_stage: sample_selection")
        elif line.startswith("next_stage:"):
            lines.append("next_stage: evidence_collection")
        elif line.startswith("waiting_for:"):
            lines.append("waiting_for:")
            lines.append("  type: sample_selection")
            lines.append("  candidates_file: analysis/sample-candidates.json")
            skip_waiting_children = True
        elif skip_waiting_children and line.startswith("  "):
            continue
        else:
            skip_waiting_children = False
            lines.append(line)
    state_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
