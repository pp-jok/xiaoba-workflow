import os
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Dict, Optional


SAFE_DEFAULT_CONFIG = """providers:
  lingzao:
    mode: unavailable

  hot_learning:
    mode: codex_manual
    command: []
    timeout_seconds: 300

  personal_content:
    mode: unavailable

  generation:
    mode: codex_manual
    command: []
    timeout_seconds: 300

learning:
  collect_comments: never
  collect_transcript: ask
  allow_auto_paid_calls: false
  transcript_required: false

features:
  auto_publish: false
"""


@dataclass(frozen=True)
class XiaobaWorkspace:
    base: Path

    @property
    def config_dir(self) -> Path:
        return self.base / "config"

    @property
    def config_path(self) -> Path:
        return self.config_dir / "xiaoba.local.yaml"

    @property
    def tasks_dir(self) -> Path:
        return self.base / "tasks"

    @property
    def logs_dir(self) -> Path:
        return self.base / "logs"

    @property
    def runtime_dir(self) -> Path:
        return self.base / "runtime"

    @property
    def project_root(self) -> Path:
        return self.runtime_dir / "project"


def resolve_workspace(explicit: Optional[str] = None, env: Optional[Dict[str, str]] = None, home: Optional[Path] = None) -> XiaobaWorkspace:
    values = env if env is not None else os.environ
    if explicit:
        return XiaobaWorkspace(Path(explicit).expanduser().resolve())
    configured = values.get("XIAOBA_WORKSPACE")
    if configured:
        return XiaobaWorkspace(Path(configured).expanduser().resolve())
    base_home = home if home is not None else Path.home()
    return XiaobaWorkspace((base_home / ".xiaoba-workflow").expanduser().resolve())


def workspace_env_present(env: Optional[Dict[str, str]] = None) -> bool:
    values = env if env is not None else os.environ
    return bool(values.get("XIAOBA_WORKSPACE"))


def bootstrap_workspace(base: Path) -> XiaobaWorkspace:
    workspace = XiaobaWorkspace(base.expanduser().resolve())
    for directory in (workspace.base, workspace.config_dir, workspace.tasks_dir, workspace.logs_dir, workspace.runtime_dir, workspace.project_root):
        directory.mkdir(parents=True, exist_ok=True)
        try:
            directory.chmod(0o700)
        except OSError:
            pass
    if not workspace.config_path.exists():
        workspace.config_path.write_text(SAFE_DEFAULT_CONFIG, encoding="utf-8")
        try:
            workspace.config_path.chmod(0o600)
        except OSError:
            pass
    install_runtime_assets(workspace)
    return workspace


def install_runtime_assets(workspace: XiaobaWorkspace) -> None:
    assets = resources.files("xiaoba_workflow").joinpath("assets")
    copy_asset(assets / "workflow.yaml", workspace.project_root / "workflow.yaml")
    copy_tree_asset(assets / "prompts", workspace.project_root / "prompts")
    copy_tree_asset(assets / "templates", workspace.project_root / "templates")
    copy_tree_asset(assets / "scripts", workspace.project_root / "scripts")
    ensure_runtime_link(workspace.tasks_dir, workspace.project_root / "tasks")
    ensure_runtime_link(workspace.config_path, workspace.project_root / "xiaoba.local.yaml")


def copy_asset(source, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with resources.as_file(source) as source_path:
        shutil.copy2(source_path, target)


def copy_tree_asset(source, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    with resources.as_file(source) as source_path:
        shutil.copytree(source_path, target)


def ensure_runtime_link(source: Path, target: Path) -> None:
    if target.exists() or target.is_symlink():
        if target.is_symlink() and target.resolve() == source.resolve():
            return
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
    try:
        target.symlink_to(source, target_is_directory=source.is_dir())
    except OSError:
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            shutil.copy2(source, target)


def legacy_data_exists(root: Path) -> bool:
    return (root / "xiaoba.local.yaml").exists() or any((root / "tasks").glob("task-*")) if (root / "tasks").exists() else (root / "xiaoba.local.yaml").exists()
