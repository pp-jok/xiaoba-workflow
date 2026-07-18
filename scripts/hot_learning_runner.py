#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


CONTRACT_VERSION = "1.0"
OPERATIONS = ("analyze_single", "analyze_cross_sample")


def main() -> int:
    parser = argparse.ArgumentParser(description="Xiaoba Hot Learning runner contract.")
    parser.add_argument("--capabilities", action="store_true")
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--output")
    args = parser.parse_args()

    if args.capabilities or args.doctor:
        print(json.dumps(capabilities(), ensure_ascii=False, indent=2))
        return 0
    if not args.input or not args.output:
        print("--input and --output are required", file=sys.stderr)
        return 2

    try:
        request = read_json(Path(args.input))
        validate_request(request, Path(args.output))
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        started_at = now_iso()
        provider = provider_mode()
        if provider == "mock":
            markdown = render_mock_analysis(request)
            warnings: List[str] = []
            model = None
        elif provider == "external":
            markdown, warnings, model = run_external_provider(request)
        else:
            markdown, warnings, model = render_codex_manual_request(request)
        completed_at = now_iso()
        write_text_atomic(output_dir / "analysis.md", markdown)
        manifest = {
            "contract_version": CONTRACT_VERSION,
            "runner": "xiaoba-hot-learning-runner",
            "operation": request["operation"],
            "status": "succeeded",
            "started_at": started_at,
            "completed_at": completed_at,
            "prompt_version": (request.get("prompt") or {}).get("version"),
            "provider": provider,
            "model": model,
            "warnings": warnings,
            "input_refs": request.get("input_refs") or {},
            "output_files": ["analysis.md"],
        }
        write_json_atomic(output_dir / "runner-manifest.json", manifest)
        return 0
    except RunnerError as error:
        print(redact(str(error)), file=sys.stderr)
        return error.exit_code


class RunnerError(Exception):
    def __init__(self, message: str, exit_code: int = 1):
        self.exit_code = exit_code
        super().__init__(message)


def capabilities() -> Dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "runner": "xiaoba-hot-learning-runner",
        "operations": list(OPERATIONS),
        "providers": ["mock", "codex_manual", "external"],
        "default_provider": "mock",
        "requires_auth": False,
    }


def provider_mode() -> str:
    provider = os.environ.get("XIAOBA_HOT_LEARNING_PROVIDER", "mock")
    if provider not in ("mock", "codex_manual", "external"):
        raise RunnerError("unsupported Hot Learning provider: " + provider, 2)
    return provider


def validate_request(request: Dict[str, Any], output_arg: Path) -> None:
    if request.get("contract_version") != CONTRACT_VERSION:
        raise RunnerError("unsupported contract_version", 2)
    if request.get("operation") not in OPERATIONS:
        raise RunnerError("unsupported operation", 2)
    output_dir = request.get("output_dir")
    if not isinstance(output_dir, str) or not Path(output_dir).is_absolute():
        raise RunnerError("output_dir must be absolute", 2)
    if Path(output_dir).resolve() != output_arg.resolve():
        raise RunnerError("--output must match request.output_dir", 2)
    refs = request.get("input_refs")
    if not isinstance(refs, dict):
        raise RunnerError("input_refs are required", 2)
    if request["operation"] == "analyze_single":
        evidence = refs.get("evidence")
        if not evidence or not Path(str(evidence)).is_file():
            raise RunnerError("input_refs.evidence must point to an existing file", 2)
    if request["operation"] == "analyze_cross_sample":
        analyses = refs.get("sample_analyses")
        if not isinstance(analyses, list) or not analyses:
            raise RunnerError("input_refs.sample_analyses must be a non-empty list", 2)
        for item in analyses:
            if not Path(str(item)).is_file():
                raise RunnerError("sample analysis not found: " + str(item), 2)


def render_mock_analysis(request: Dict[str, Any]) -> str:
    if request["operation"] == "analyze_cross_sample":
        return render_mock_cross_sample(request)
    evidence = read_json(Path(str((request.get("input_refs") or {})["evidence"])))
    facts = evidence.get("facts") or {}
    source = evidence.get("source") or {}
    metrics = facts.get("metrics") or {}
    missing = evidence.get("missing") or []
    limitations = ["- 缺失 " + str(item) for item in missing] or ["- 未记录主要缺失。"]
    if (evidence.get("coverage") or {}).get("video_file") == "unsupported":
        limitations.append("- Lingzao 当前不提供视频文件，不能判断真实镜头。")
    return """# Hot Learning 原始分析

Sample ID: {sample_id}
Source URL: {url}

## 可观察事实
- 标题：{title}
  Evidence reference: evidence.yaml#facts.title
- 正文摘要：{body}
  Evidence reference: evidence.yaml#facts.body
- 作者：{author}
  Evidence reference: evidence.yaml#source.author
- 指标：likes={likes}, saves={saves}, comments={comments}, shares={shares}
  Evidence reference: evidence.yaml#facts.metrics

## 推断
- 这条内容可能依赖明确场景承诺来降低理解成本。
- 内容结构把任务拆成几个可执行动作，方便用户判断是否值得收藏。

## 内容机制
### 机制 1：通过明确承诺吸引点击
- 机制 key：specific_promise_title
- 描述：标题把用户能获得的好处包装成直接承诺，降低用户理解成本。
- 证据：evidence.yaml#facts.title
- 置信度：medium
- 替代解释：表现也可能依赖作者信任或平台分发时机。

### 机制 2：用步骤化正文支撑收藏
- 机制 key：stepwise_body_support
- 描述：正文把复杂任务拆成可执行步骤，提高收藏价值。
- 证据：evidence.yaml#facts.body
- 置信度：medium
- 替代解释：选题本身可能已经具备强需求。

### 机制 3：把限制显性化降低误用
- 机制 key：explicit_limitations
- 描述：分析时明确说明缺失信息，避免把推断写成事实。
- 证据：evidence.yaml#facts.metrics
- 置信度：low
- 替代解释：缺少评论或逐字稿时，用户真实动机无法确认。

## 可学习部分
- 用明确承诺帮助用户快速判断内容价值。
- 把复杂任务拆成可执行步骤。

## 不可照搬部分
- 不直接复制原文表达。
- 不编造个人经历、评论或视频细节。

## 规则方向建议
- 候选方向：标题承诺必须能在正文中找到明确支撑。

## 内容资产方向建议
- 建立“场景-步骤-限制”内容资产模板。

## 内容机会
- 用原创案例做一个同类教程型选题。

## 缺失信息与限制
{limitations}
""".format(
        sample_id=evidence.get("sample_id", ""),
        url=source.get("original_url", ""),
        title=facts.get("title") or "",
        body=facts.get("body") or "",
        author=source.get("author") or "",
        likes=metrics.get("likes"),
        saves=metrics.get("saves"),
        comments=metrics.get("comments"),
        shares=metrics.get("shares"),
        limitations="\n".join(limitations),
    )


def render_mock_cross_sample(request: Dict[str, Any]) -> str:
    analyses = (request.get("input_refs") or {}).get("sample_analyses") or []
    lines = ["# Hot Learning 跨样本原始分析", "", "## 样本", *("- " + str(item) for item in analyses)]
    lines.extend(["", "## 共同机制", "- 多个样本都使用明确承诺降低理解成本。"])
    return "\n".join(lines) + "\n"


def render_codex_manual_request(request: Dict[str, Any]) -> tuple:
    markdown = (
        "# Hot Learning Codex 手工执行请求\n\n"
        "当前 provider 为 codex_manual。请按 Prompt 对 input_refs 进行分析，完成后用 "
        "`xiaoba-workflow import-hot-learning-analysis` 导入 Markdown。\n"
    )
    return markdown, ["codex_manual requires a human or Codex to complete real analysis"], None


def run_external_provider(request: Dict[str, Any]) -> tuple:
    command_text = os.environ.get("XIAOBA_HOT_LEARNING_COMMAND")
    if not command_text:
        raise RunnerError("XIAOBA_HOT_LEARNING_COMMAND is required for external provider", 2)
    try:
        command = json.loads(command_text)
    except json.JSONDecodeError as error:
        raise RunnerError("XIAOBA_HOT_LEARNING_COMMAND must be a JSON array: " + str(error), 2)
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        raise RunnerError("XIAOBA_HOT_LEARNING_COMMAND must be a JSON array of strings", 2)
    completed = subprocess.run(command, input=json.dumps(request, ensure_ascii=False), check=False, capture_output=True, text=True, shell=False)
    if completed.returncode != 0:
        raise RunnerError(completed.stderr.strip() or "external Hot Learning provider failed", completed.returncode)
    markdown = completed.stdout.strip()
    if not markdown:
        raise RunnerError("external Hot Learning provider returned empty output")
    return markdown + "\n", [], os.environ.get("XIAOBA_HOT_LEARNING_MODEL")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise RunnerError("JSON file must contain an object: " + str(path), 2)
    return value


def write_text_atomic(path: Path, content: str) -> None:
    temp = path.with_name("." + path.name + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


def write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    temp = path.with_name("." + path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def redact(text: str) -> str:
    result = text
    for key, value in os.environ.items():
        lowered = key.lower()
        if value and ("secret" in lowered or "token" in lowered or "password" in lowered or "key" in lowered):
            result = result.replace(value, "<redacted>")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
