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


class EvidenceNormalizationTests(unittest.TestCase):
    def test_raw_lingzao_output_generates_valid_evidence_and_advances(self):
        with temp_project() as root:
            task_dir = prepare_evidence_normalization_task(root)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = read_json(task_dir / "evidence/evidence.yaml")
            state = read_text(task_dir / "state.yaml")
            self.assertEqual(evidence["source"]["original_url"], "https://example.com/note/1")
            self.assertIn(evidence["normalization"]["status"], ["normalized", "partially_normalized"])
            self.assertIn("current_stage: analysis", state)
            self.assertFalse((task_dir / "analysis/analysis.yaml").exists())

    def test_maps_title_body_author_and_metrics(self):
        with temp_project() as root:
            task_dir = prepare_evidence_normalization_task(root)
            run_cli("run", str(task_dir), cwd=root)

            evidence = read_json(task_dir / "evidence/evidence.yaml")

            self.assertEqual(evidence["facts"]["title"], "Mock note title")
            self.assertEqual(evidence["facts"]["body"], "Mock note body for downstream evidence normalization.")
            self.assertEqual(evidence["source"]["author"], "Mock Author")
            self.assertEqual(evidence["source"]["author_id"], "mock-author-001")
            self.assertEqual(evidence["facts"]["metrics"]["likes"], 128)
            self.assertEqual(evidence["facts"]["metrics"]["saves"], 64)

    def test_source_refs_cover_key_fields(self):
        with temp_project() as root:
            task_dir = prepare_evidence_normalization_task(root)
            run_cli("run", str(task_dir), cwd=root)

            evidence = read_json(task_dir / "evidence/evidence.yaml")
            targets = {ref["target"] for ref in evidence["source_refs"]}

            for target in [
                "facts.title",
                "facts.body",
                "source.author",
                "source.published_at",
                "facts.metrics.likes",
                "facts.images",
                "coverage.comments",
                "coverage.transcript",
            ]:
                self.assertIn(target, targets)

    def test_missing_comments_and_transcript_are_partial_without_fabrication(self):
        with temp_project() as root:
            task_dir = prepare_evidence_normalization_task(root)
            run_cli("run", str(task_dir), cwd=root)

            evidence = read_json(task_dir / "evidence/evidence.yaml")

            self.assertEqual(evidence["normalization"]["status"], "partially_normalized")
            self.assertEqual(evidence["coverage"]["comments"], "missing")
            self.assertEqual(evidence["coverage"]["transcript"], "missing")
            self.assertEqual(evidence["facts"]["comments"], [])
            self.assertIsNone(evidence["facts"]["transcript"])
            self.assertIn("comments", evidence["missing"])
            self.assertIn("transcript", evidence["missing"])
            self.assertEqual(evidence["coverage"]["video_file"], "unsupported")
            self.assertEqual(evidence["coverage"]["local_video"], "unsupported")
            self.assertIn("video_file", evidence["missing"])

    def test_manually_provided_transcript_is_preserved_with_source_marker(self):
        with temp_project() as root:
            task_dir = prepare_evidence_normalization_task(root)
            raw_path = task_dir / "raw/lingzao/note-detail.json"
            raw = read_json(raw_path)
            raw["transcript"] = {
                "status": "manually_provided",
                "source": "user_input",
                "text": "这是一段用户手工提供的逐字稿。",
            }
            write_json(raw_path, raw)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = read_json(task_dir / "evidence/evidence.yaml")
            self.assertEqual(evidence["facts"]["transcript"], "这是一段用户手工提供的逐字稿。")
            self.assertEqual(evidence["coverage"]["transcript"], "manually_provided")
            self.assertEqual(evidence["coverage"]["transcript_source"], "user_input")
            self.assertNotIn("transcript", evidence["missing"])

    def test_missing_metrics_remain_null(self):
        with temp_project() as root:
            task_dir = prepare_evidence_normalization_task(root)
            raw_path = task_dir / "raw/lingzao/note-detail.json"
            raw = read_json(raw_path)
            raw["metrics"].pop("shares")
            write_json(raw_path, raw)

            run_cli("run", str(task_dir), cwd=root)

            evidence = read_json(task_dir / "evidence/evidence.yaml")
            self.assertIsNone(evidence["facts"]["metrics"]["shares"])
            self.assertIn("metrics.shares", evidence["missing"])

    def test_empty_raw_output_blocks_as_normalization_failed(self):
        with temp_project() as root:
            task_dir = prepare_evidence_normalization_task(root)
            write_json(task_dir / "raw/lingzao/note-detail.json", {})

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: blocked", state)
            self.assertIn("current_stage: evidence_normalization", state)
            self.assertIn("normalization_failed", state)

    def test_missing_source_url_blocks_and_keeps_stage(self):
        with temp_project() as root:
            task_dir = prepare_evidence_normalization_task(root)
            raw_path = task_dir / "raw/lingzao/note-detail.json"
            raw = read_json(raw_path)
            raw["source"]["original_url"] = ""
            raw["source"]["canonical_url"] = ""
            write_json(raw_path, raw)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            state = read_text(task_dir / "state.yaml")
            self.assertIn("status: blocked", state)
            self.assertIn("current_stage: evidence_normalization", state)
            self.assertIn("source.original_url is required", state)

    def test_forbidden_evidence_field_fails_validation_without_overwrite(self):
        with temp_project() as root:
            task_dir = prepare_evidence_normalization_task(root)
            evidence_path = task_dir / "evidence/evidence.yaml"
            write_json(evidence_path, {"sample_id": "sample-x", "mechanisms": []})
            original = read_text(evidence_path)

            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertEqual(read_text(evidence_path), original)
            self.assertIn("forbidden evidence field", read_text(task_dir / "state.yaml"))

    def test_normalizer_does_not_modify_raw_files_and_is_idempotent(self):
        with temp_project() as root:
            task_dir = prepare_evidence_normalization_task(root)
            raw_path = task_dir / "raw/lingzao/note-detail.json"
            raw_before = read_text(raw_path)

            first = run_cli("run", str(task_dir), cwd=root)
            evidence_path = task_dir / "evidence/evidence.yaml"
            evidence_before = read_text(evidence_path)

            replace_line(task_dir / "state.yaml", "current_stage:", "current_stage: evidence_normalization")
            replace_line(task_dir / "state.yaml", "next_stage:", "next_stage: analysis")
            replace_line(task_dir / "state.yaml", "status:", "status: running")
            second = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(read_text(raw_path), raw_before)
            self.assertEqual(read_text(evidence_path), evidence_before)


def prepare_evidence_normalization_task(root):
    task_dir = create_task(root, "learning", "https://example.com/note/1")
    run_cli("run", str(task_dir), cwd=root)
    run_cli("run", str(task_dir), cwd=root)
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


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def replace_line(path, prefix, replacement):
    lines = read_text(path).splitlines()
    updated = [replacement if line.startswith(prefix) else line for line in lines]
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")
