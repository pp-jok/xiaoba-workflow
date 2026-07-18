import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from xiaoba_workflow import lingzao as lingzao_module


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


class LingzaoProviderTests(unittest.TestCase):
    def test_doctor_mock_mode_passes_and_default_provider_is_mock(self):
        with temp_project() as root:
            doctor = run_cli("doctor", "--skill", "lingzao", cwd=root)
            task_dir = create_task(root, "learning", "https://example.com/note/1")
            run_cli("run", str(task_dir), cwd=root)
            result = run_cli("run", str(task_dir), cwd=root)

            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            self.assertIn("provider: mock", doctor.stdout)
            self.assertEqual(result.returncode, 0, result.stderr)
            invocation = read_json(task_dir / "raw/lingzao/invocation.json")
            self.assertEqual(invocation["provider"], "mock")
            self.assertEqual(invocation["operation"], "collect_note")

    def test_doctor_real_without_command_fails(self):
        with temp_project() as root:
            result = run_cli("doctor", "--skill", "lingzao", cwd=root, env_extra={"XIAOBA_LINGZAO_PROVIDER": "real"})

            self.assertEqual(result.returncode, 1)
            self.assertIn("real command is required", result.stderr)

    def test_real_fake_runner_collects_note_and_preserves_external_raw(self):
        with temp_project() as root:
            runner = write_fake_runner(root, mode="success")
            task_dir = create_task(root, "learning", "https://example.com/note/real")
            run_cli("run", str(task_dir), cwd=root)

            result = run_cli("run", str(task_dir), cwd=root, env_extra=real_env(runner))

            self.assertEqual(result.returncode, 0, result.stderr)
            note = read_json(task_dir / "raw/lingzao/note-detail.json")
            invocation = read_json(task_dir / "raw/lingzao/invocation.json")
            self.assertEqual(note["source"]["original_url"], "https://example.com/note/real")
            self.assertEqual(invocation["provider"], "real")
            self.assertEqual(invocation["adapter"], "lingzao")
            self.assertEqual(invocation["contract_version"], "1.0")
            self.assertEqual(invocation["exit_code"], 0)
            self.assertIn("raw/lingzao/note-detail.json", invocation["raw_files"])
            self.assertTrue((task_dir / "raw/lingzao/external/result.json").is_file())
            self.assertTrue((task_dir / "raw/lingzao/external/runner-manifest.json").is_file())
            self.assertIsNone(note["metrics"]["comments"])
            self.assertTrue((task_dir / "raw/lingzao/execution-stdout.log").is_file())
            self.assertTrue((task_dir / "raw/lingzao/execution-stderr.log").is_file())
            self.assertNotIn("SECRET_VALUE", read_text(task_dir / "raw/lingzao/invocation.json"))
            self.assertNotIn("SECRET_VALUE", read_text(task_dir / "raw/lingzao/execution-stdout.log"))

            normalize = run_cli("run", str(task_dir), cwd=root)
            self.assertEqual(normalize.returncode, 0, normalize.stderr)
            self.assertTrue((task_dir / "evidence/evidence.yaml").is_file())

    def test_real_fake_runner_supports_batch_screening_and_sample_note(self):
        with temp_project() as root:
            runner = write_fake_runner(root, mode="success")
            task_dir = create_task(root, "learning_batch", "https://example.com/user/real")
            run_cli("run", str(task_dir), cwd=root)

            screening = run_cli("run", str(task_dir), cwd=root, env_extra=real_env(runner))
            self.assertEqual(screening.returncode, 0, screening.stderr)
            self.assertTrue((task_dir / "raw/lingzao/profile.json").is_file())
            self.assertTrue((task_dir / "raw/lingzao/posted-notes.json").is_file())
            self.assertEqual(read_json(task_dir / "raw/lingzao/invocation.json")["provider"], "real")
            self.assertTrue((task_dir / "raw/lingzao/external/collect_profile/result.json").is_file())
            self.assertTrue((task_dir / "raw/lingzao/external/collect_posted_notes/result.json").is_file())

            selected = run_cli("select-samples", str(task_dir), "--ids", "sample-001", cwd=root)
            self.assertEqual(selected.returncode, 0, selected.stderr)
            collect = run_cli("run", str(task_dir), cwd=root, env_extra=real_env(runner))
            self.assertEqual(collect.returncode, 0, collect.stderr)
            sample_invocation = read_json(task_dir / "raw/lingzao/samples/sample-001/invocation.json")
            self.assertEqual(sample_invocation["provider"], "real")
            self.assertEqual(sample_invocation["sample_id"], "sample-001")

    def test_real_runner_failures_block_without_complete_raw_group(self):
        cases = [
            ("nonzero", "nonzero_exit"),
            ("invalid_json", "invalid_output"),
            ("missing_output", "incomplete_output"),
            ("timeout", "timeout"),
        ]
        for mode, expected in cases:
            with self.subTest(mode=mode):
                with temp_project() as root:
                    runner = write_fake_runner(root, mode=mode)
                    task_dir = create_task(root, "learning", "https://example.com/note/fail")
                    run_cli("run", str(task_dir), cwd=root)

                    timeout = "0.2" if mode == "timeout" else "5"
                    result = run_cli("run", str(task_dir), cwd=root, env_extra=real_env(runner, timeout=timeout))

                    self.assertEqual(result.returncode, 1)
                    self.assertIn(expected, read_text(task_dir / "state.yaml"))
                    self.assertFalse((task_dir / "raw/lingzao/note-detail.json").exists())
                    self.assertFalse((task_dir / "raw/lingzao/invocation.json").exists())

    def test_real_runner_rejects_contract_version_operation_and_source_mismatch(self):
        cases = [
            ("bad_contract_version", "contract_version"),
            ("bad_operation", "operation"),
            ("bad_source", "source"),
        ]
        for mode, expected in cases:
            with self.subTest(mode=mode):
                with temp_project() as root:
                    runner = write_fake_runner(root, mode=mode)
                    task_dir = create_task(root, "learning", "https://example.com/note/contract")
                    run_cli("run", str(task_dir), cwd=root)

                    result = run_cli("run", str(task_dir), cwd=root, env_extra=real_env(runner))

                    self.assertEqual(result.returncode, 1)
                    state = read_text(task_dir / "state.yaml")
                    self.assertIn("contract_adaptation_error", state)
                    self.assertIn(expected, state)
                    self.assertFalse((task_dir / "raw/lingzao/note-detail.json").exists())

    def test_doctor_real_reads_capabilities_and_rejects_missing_operation(self):
        with temp_project() as root:
            runner = write_fake_runner(root, mode="success")

            result = run_cli("doctor", "--skill", "lingzao", cwd=root, env_extra=real_env(runner))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("contract_version: 1.0", result.stdout)
            self.assertIn("collect_note", result.stdout)
            self.assertIn("collect_profile", result.stdout)
            self.assertIn("collect_posted_notes", result.stdout)

        with temp_project() as root:
            runner = write_fake_runner(root, mode="missing_operation")

            result = run_cli("doctor", "--skill", "lingzao", cwd=root, env_extra=real_env(runner))

            self.assertEqual(result.returncode, 1)
            self.assertIn("unsupported Lingzao operation", result.stderr)

    def test_lingzao_runner_passes_xhs_note_type_from_source_url(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake_client = root / "fake_lingzao_client.py"
            argv_path = root / "argv.json"
            fake_client.write_text(
                textwrap.dedent(
                    """
                    import json
                    import os
                    import sys
                    from pathlib import Path

                    Path(os.environ["FAKE_LINGZAO_ARGV"]).write_text(
                        json.dumps(sys.argv[1:], ensure_ascii=False),
                        encoding="utf-8",
                    )
                    print(json.dumps({
                        "ok": True,
                        "data": {
                            "note": {
                                "id": "note-video",
                                "url": "https://www.xiaohongshu.com/explore/abc?type=video",
                                "title": "Video title",
                                "body": "Video body",
                                "author": {"id": "author-1", "name": "Author"},
                                "published_at": None,
                                "metrics": {"likes": None},
                                "images": []
                            }
                        }
                    }, ensure_ascii=False))
                    """
                ),
                encoding="utf-8",
            )
            request = {
                "contract_version": "1.0",
                "operation": "collect_note",
                "task_id": "task-runner-test",
                "sample_id": None,
                "source": "https://www.xiaohongshu.com/explore/abc?type=video",
                "output_dir": str((root / "out").resolve()),
                "prompt_path": str((root / "prompt.md").resolve()),
                "options": {"collect_comments": False, "collect_transcript": False},
            }
            request_path = root / "request.json"
            write_json(request_path, request)
            env = os.environ.copy()
            env["LINGZAO_CLIENT_PATH"] = str(fake_client)
            env["FAKE_LINGZAO_ARGV"] = str(argv_path)

            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "scripts" / "lingzao_runner.py"),
                    "--input",
                    str(request_path),
                    "--output",
                    request["output_dir"],
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            argv = read_json(argv_path)
            self.assertIn("--xhs-note-type", argv)
            self.assertEqual(argv[argv.index("--xhs-note-type") + 1], "video")
            runner_result = read_json(root / "out" / "result.json")
            self.assertEqual(runner_result["operation"], "collect_note")

    def test_adapt_external_contract_accepts_canonical_note_url_and_maps_real_metrics(self):
        source_url = "https://www.xiaohongshu.com/explore/abc?type=video&debug_param=1"
        canonical_url = "https://www.xiaohongshu.com/explore/abc"
        result = {
            "operation": "collect_note",
            "source": source_url,
            "note": {
                "id": "abc",
                "url": canonical_url,
                "title": "Real title",
                "body": "Real body.",
                "author": {"id": "author-1", "name": "Real Author"},
                "published_at": None,
                "metrics": {"liked": 23, "collected": 12, "commented": 15, "shared": 4},
                "images": [],
                "comments": {"status": "missing", "items": []},
                "transcript": {"status": "missing", "text": None},
            },
            "warnings": [],
        }
        runner_manifest = {"completed_at": "2026-07-16T20:40:48+08:00"}

        adapted = lingzao_module.adapt_external_contract(
            result,
            runner_manifest,
            "collect_note",
            source_url,
            None,
        )

        note = adapted["note-detail.json"]
        self.assertEqual(note["source"]["original_url"], source_url)
        self.assertEqual(note["source"]["canonical_url"], canonical_url)
        self.assertEqual(
            note["metrics"],
            {"likes": 23, "saves": 12, "comments": 15, "shares": 4},
        )

    def test_real_runner_rejects_existing_raw_and_path_traversal(self):
        with temp_project() as root:
            runner = write_fake_runner(root, mode="success")
            task_dir = create_task(root, "learning", "https://example.com/note/1")
            run_cli("run", str(task_dir), cwd=root)
            raw_dir = task_dir / "raw/lingzao"
            write_json(raw_dir / "note-detail.json", {"partial": True})

            result = run_cli("run", str(task_dir), cwd=root, env_extra=real_env(runner))

            self.assertEqual(result.returncode, 1)
            self.assertIn("incomplete_output", read_text(task_dir / "state.yaml"))

        with temp_project() as root:
            runner = write_fake_runner(root, mode="traversal")
            task_dir = create_task(root, "learning", "https://example.com/note/1")
            run_cli("run", str(task_dir), cwd=root)

            result = run_cli("run", str(task_dir), cwd=root, env_extra=real_env(runner))

            self.assertEqual(result.returncode, 1)
            self.assertIn("contract_adaptation_error", read_text(task_dir / "state.yaml"))


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


def real_env(runner, timeout="5"):
    return {
        "XIAOBA_LINGZAO_PROVIDER": "real",
        "XIAOBA_LINGZAO_COMMAND": json.dumps([sys.executable, str(runner)]),
        "XIAOBA_LINGZAO_TIMEOUT": timeout,
        "XIAOBA_SECRET_TOKEN": "SECRET_VALUE",
    }


def write_fake_runner(root, mode):
    runner = root / "fake_lingzao_runner.py"
    runner.write_text(
        textwrap.dedent(
            """
            import argparse
            import json
            import sys
            import time
            from pathlib import Path

            parser = argparse.ArgumentParser()
            parser.add_argument("--capabilities", action="store_true")
            parser.add_argument("--doctor", action="store_true")
            parser.add_argument("--input")
            parser.add_argument("--output")
            args = parser.parse_args()
            mode = "__MODE__"
            if args.capabilities or args.doctor:
                operations = ["collect_note", "collect_profile", "collect_posted_notes"]
                if mode == "missing_operation":
                    operations = ["collect_note", "collect_profile"]
                print(json.dumps({
                    "contract_version": "1.0",
                    "runner": "fake-lingzao-runner",
                    "operations": operations,
                    "requires_auth": False,
                    "required_env": [],
                    "login_state": "not_required"
                }, ensure_ascii=False))
                sys.exit(0)
            request = json.loads(Path(args.input).read_text(encoding="utf-8"))
            out = Path(args.output)
            print("fake stdout without secrets")
            print("fake stderr without secrets", file=sys.stderr)
            if mode == "timeout":
                time.sleep(2)
            if mode == "nonzero":
                sys.exit(7)
            if mode == "missing_output":
                sys.exit(0)
            if mode == "traversal":
                (out / "manifest.json").write_text(json.dumps({"files": ["../escape.json"]}), encoding="utf-8")
                sys.exit(0)
            out.mkdir(parents=True, exist_ok=True)
            manifest = {
                "contract_version": "0.9" if mode == "bad_contract_version" else "1.0",
                "runner": "fake-lingzao-runner",
                "operation": "collect_profile" if mode == "bad_operation" else request["operation"],
                "started_at": "2026-07-16T00:00:00+08:00",
                "completed_at": "2026-07-16T00:00:01+08:00",
                "status": "succeeded",
                "warnings": [],
                "source_files": []
            }
            if request["operation"] == "collect_note":
                if mode == "invalid_json":
                    (out / "result.json").write_text("{invalid", encoding="utf-8")
                else:
                    source = "https://example.com/other" if mode == "bad_source" else request["source"]
                    (out / "result.json").write_text(json.dumps({
                        "operation": "collect_profile" if mode == "bad_operation" else "collect_note",
                        "source": source,
                        "note": {
                            "id": None,
                            "url": source,
                            "title": "Real fake title",
                            "body": "Real fake body.",
                            "author": {"id": "real-author", "name": "Real Fake Author"},
                            "published_at": "2026-07-15T00:00:00+08:00",
                            "metrics": {"likes": 10, "saves": 2, "comments": None, "shares": None},
                            "images": [],
                            "comments": {"status": "missing", "items": []},
                            "transcript": {"status": "missing", "text": None}
                        },
                        "warnings": []
                    }, ensure_ascii=False), encoding="utf-8")
            elif request["operation"] == "collect_profile":
                (out / "result.json").write_text(json.dumps({
                    "operation": "collect_profile",
                    "source": request["source"],
                    "profile": {
                        "id": "real-profile",
                        "url": request["source"],
                        "name": "Real Fake Account",
                        "bio": "fake bio",
                        "metrics": {"followers": 100, "notes": 6}
                    },
                    "warnings": []
                }, ensure_ascii=False), encoding="utf-8")
            elif request["operation"] == "collect_posted_notes":
                notes = []
                for index in range(1, 7):
                    notes.append({
                        "id": "real-note-%03d" % index,
                        "title": "Real fake note %03d" % index,
                        "url": request["source"].rstrip("/") + "/notes/%03d" % index,
                        "published_at": "2026-07-%02dT09:00:00+08:00" % (index + 1),
                        "metrics": {"likes": 100 - index, "saves": 20, "comments": 5, "shares": 1}
                    })
                (out / "result.json").write_text(json.dumps({
                    "operation": "collect_posted_notes",
                    "source": request["source"],
                    "notes": notes
                }, ensure_ascii=False), encoding="utf-8")
            (out / "runner-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            """
        ).replace("__MODE__", mode),
        encoding="utf-8",
    )
    return runner


def read_text(path):
    return path.read_text(encoding="utf-8")


def read_json(path):
    return json.loads(read_text(path))


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
