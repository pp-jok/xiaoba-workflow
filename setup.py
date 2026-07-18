from pathlib import Path
import re

from setuptools import find_packages, setup


ROOT = Path(__file__).parent
VERSION_RE = re.compile(r'__version__\s*=\s*"([^"]+)"')


def read_version() -> str:
    match = VERSION_RE.search((ROOT / "xiaoba_workflow" / "__init__.py").read_text(encoding="utf-8"))
    if not match:
        raise RuntimeError("Unable to read package version")
    return match.group(1)


setup(
    name="xiaoba-workflow",
    version=read_version(),
    description="Lightweight orchestration baseline for XHS content learning workflows.",
    packages=find_packages(include=["xiaoba_workflow", "xiaoba_workflow.*"]),
    python_requires=">=3.9",
    extras_require={"test": ["pytest>=7"]},
    entry_points={"console_scripts": ["xiaoba-workflow=xiaoba_workflow.cli:main"]},
)
