import json
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import config as local_config
from . import presentation
from . import runtime
from . import workspace as workspace_module


InputFunc = Callable[[str], str]
OutputFunc = Callable[[str], None]


TASK_BY_CHOICE = {
    "1": ("learning", "学习一条小红书笔记"),
    "2": ("learning_batch", "学习一批对标内容"),
    "3": ("generation", "生成一篇小红书帖子"),
    "4": ("post_publish_review", "复盘一篇已发布内容"),
}


def run_start(
    explicit_workspace: Optional[str] = None,
    input_func: InputFunc = input,
    output_func: OutputFunc = print,
    technical: bool = False,
) -> int:
    workspace = workspace_module.bootstrap_workspace(workspace_module.resolve_workspace(explicit_workspace).base)
    root = workspace.project_root
    output_func("Xiaoba 已完成首次初始化。")
    output_func("")
    output_func(render_capability_summary(root, technical=technical))
    output_func("")
    return run_home(root, workspace, input_func, output_func)


def run_home(root: Path, workspace: workspace_module.XiaobaWorkspace, input_func: InputFunc, output_func: OutputFunc) -> int:
    while True:
        output_func(
            "\n".join(
                [
                    "你想做什么？",
                    "",
                    "1. 新建任务",
                    "2. 继续未完成任务",
                    "3. 查看最近结果",
                    "4. 配置能力",
                    "5. 查看系统状态",
                    "6. 退出",
                ]
            )
        )
        choice = ask_number(input_func, output_func, "请选择：", {str(i): str(i) for i in range(1, 7)}, "请输入 1 到 6。")
        if choice in (None, "6"):
            return 0
        if choice == "1":
            return start_new_task(root, input_func, output_func)
        if choice == "2":
            task_dir = choose_task(workspace.tasks_dir, completed=False, input_func=input_func, output_func=output_func)
            if task_dir:
                return run_task_session(root, task_dir, input_func, output_func)
        if choice == "3":
            task_dir = choose_task(workspace.tasks_dir, completed=True, input_func=input_func, output_func=output_func)
            if task_dir:
                task, state = runtime.read_task_files(task_dir)
                output_func(presentation.render_completion_summary(task_dir, task, state))
                return 0
        if choice == "4":
            return run_configure(workspace, input_func, output_func)
        if choice == "5":
            output_func(render_capability_summary(root, technical=False))


def start_new_task(root: Path, input_func: InputFunc, output_func: OutputFunc) -> int:
    output_func(presentation.render_start())
    choice = ask_number(input_func, output_func, "请选择：", {key: key for key in TASK_BY_CHOICE}, "请输入 1、2、3 或 4。")
    if choice is None:
        return 0
    task_type, _label = TASK_BY_CHOICE[choice]
    if task_type == "learning":
        return start_learning(root, input_func, output_func)
    if task_type == "generation":
        try:
            brief = input_func("请告诉我这次想生成什么内容：").strip()
        except EOFError:
            return 0
        if not brief:
            output_func("没有收到必要信息，任务未创建。")
            return 1
        task_dir = runtime.create_task(root, "generation", None, brief)
        output_func("\n已创建任务。\n")
        return run_task_session(root, task_dir, input_func, output_func)
    source_question = "请粘贴对标账号或主页链接：" if task_type == "learning_batch" else "请粘贴已发布内容链接："
    try:
        source_url = input_func(source_question).strip()
    except EOFError:
        return 0
    if not source_url:
        output_func("没有收到必要信息，任务未创建。")
        return 1
    task_dir = runtime.create_task(root, task_type, source_url)
    output_func("\n已创建任务。\n")
    return run_task_session(root, task_dir, input_func, output_func)


def start_learning(root: Path, input_func: InputFunc, output_func: OutputFunc) -> int:
    try:
        source_url = input_func("请粘贴公开小红书笔记链接：").strip()
    except EOFError:
        return 0
    if not source_url:
        output_func("没有收到必要信息，任务未创建。")
        return 1
    lingzao_mode = provider_mode(root, "lingzao")
    if lingzao_mode in ("real", "external"):
        task_dir = runtime.create_task(root, "learning", source_url, execution_mode="real")
        output_func("\n已创建任务。\n")
        return run_task_session(root, task_dir, input_func, output_func)
    output_func(
        "\n".join(
            [
                "当前未配置 Lingzao，无法读取这个链接的真实内容。",
                "",
                "你可以：",
                "1. 手工粘贴笔记正文",
                "2. 手工粘贴视频口播稿",
                "3. 运行演示流程",
                "4. 取消",
            ]
        )
    )
    decision = ask_number(input_func, output_func, "请选择：", {"1": "manual_body", "2": "manual_transcript", "3": "demo", "4": "cancel"}, "请输入 1 到 4。")
    if decision in (None, "cancel"):
        return 0
    if decision == "demo":
        task_dir = runtime.create_task(root, "learning", source_url, execution_mode="demo")
        output_func("\n已创建演示任务。演示结果不会被视为真实采集或真实学习结果。\n")
        return run_task_session(root, task_dir, input_func, output_func)
    return start_manual_learning(root, source_url, decision, input_func, output_func)


def start_manual_learning(root: Path, source_url: str, mode: str, input_func: InputFunc, output_func: OutputFunc) -> int:
    try:
        title = input_func("请粘贴标题：").strip()
        body = input_func("请粘贴正文或口播稿：").strip()
    except EOFError:
        return 0
    if not title or not body:
        output_func("标题和正文不能为空。")
        return 1
    task_dir = runtime.create_task(root, "learning", source_url, execution_mode="manual")
    runtime.run_task(root, task_dir)
    write_manual_lingzao_raw(task_dir, source_url, title, body, mode)
    runtime.advance_task(root, task_dir)
    output_func("\n已创建手工输入任务。\n")
    return run_task_session(root, task_dir, input_func, output_func)


def write_manual_lingzao_raw(task_dir: Path, source_url: str, title: str, body: str, mode: str) -> None:
    raw_dir = task_dir / "raw" / "lingzao"
    raw_dir.mkdir(parents=True, exist_ok=True)
    transcript = {"status": "available", "text": body, "source": "manually_provided"} if mode == "manual_transcript" else {"status": "missing", "text": None}
    note = {
        "manual": True,
        "sample_id": None,
        "source": {"source_type": "xhs_note", "original_url": source_url, "canonical_url": source_url},
        "author": {"name": None, "id": None},
        "content": {"title": title, "body": body, "tags": [], "images": []},
        "published_at": None,
        "captured_at": runtime.now_iso(),
        "metrics": {"likes": None, "saves": None, "comments": None, "shares": None},
        "comments": {"status": "missing", "items": []},
        "transcript": transcript,
    }
    invocation = {
        "adapter": "manual_content_input",
        "mode": "manual",
        "manual": True,
        "source_url": source_url,
        "raw_files": ["raw/lingzao/note-detail.json", "raw/lingzao/invocation.json"],
        "executed_at": runtime.now_iso(),
    }
    runtime.write_json_atomic(raw_dir / "note-detail.json", note)
    runtime.write_json_atomic(raw_dir / "invocation.json", invocation)


def run_task_session(root: Path, task_dir: Path, input_func: InputFunc, output_func: OutputFunc) -> int:
    while True:
        state, messages = runtime.run_until_gate(root, task_dir)
        for message in messages:
            output_func(message)
            output_func("")
        task, latest_state = runtime.read_task_files(task_dir)
        if latest_state.get("status") == "completed":
            output_func(presentation.render_completion_summary(task_dir, task, latest_state))
            return 0
        if latest_state.get("status") == "blocked":
            return handle_blocked(root, task_dir, input_func, output_func)
        if latest_state.get("status") != "waiting_for_user":
            return 0
        if not handle_waiting_gate(root, task_dir, input_func, output_func):
            return 0


def handle_waiting_gate(root: Path, task_dir: Path, input_func: InputFunc, output_func: OutputFunc) -> bool:
    task, state = runtime.read_task_files(task_dir)
    waiting = state.get("waiting_for") if isinstance(state.get("waiting_for"), dict) else {}
    waiting_type = waiting.get("type")
    output_func(presentation.render_gate_prompt(task, state, task_dir))
    if waiting_type == "external_cost_confirmation":
        decision = ask_number(input_func, output_func, "请选择：", {"1": "confirm", "2": "skip"}, "请输入 1 或 2。")
        if decision is None:
            return False
        runtime.confirm_external_cost(task_dir, decision)
        output_func("已记录选择。\n")
        return True
    if waiting_type == "sample_selection":
        sample_ids = ask_sample_ids(task_dir, input_func, output_func)
        if not sample_ids:
            return False
        runtime.select_samples(root, task_dir, sample_ids)
        output_func("已选择样本。\n")
        return True
    if waiting_type == "topic_selection":
        topic_id = ask_topic_id(task_dir, input_func, output_func)
        if topic_id is None:
            return False
        runtime.select_topic(root, task_dir, topic_id)
        output_func("已选择选题。\n")
        return True
    if waiting_type == "content_review":
        decision = ask_number(input_func, output_func, "请选择：", {"1": "approve", "2": "request_changes", "3": "stop"}, "请输入 1、2 或 3。")
        if decision is None or decision == "stop":
            return False
        feedback = None
        if decision == "request_changes":
            try:
                feedback = input_func("请告诉我需要修改什么。").strip()
            except EOFError:
                return False
            if not feedback:
                output_func("没有收到修改意见，暂不继续。")
                return False
        runtime.review_content(root, task_dir, decision, feedback)
        output_func("已记录审核结果。\n")
        return True
    if waiting_type == "generation_brief":
        try:
            brief = input_func("请告诉我这次想生成什么内容。").strip()
        except EOFError:
            return False
        if not brief:
            output_func("没有收到内容需求，暂不继续。")
            return False
        runtime.set_generation_brief(task_dir, brief)
        output_func("已记录内容需求。\n")
        return True
    output_func("当前任务需要人工处理，但 Xiaoba 暂不认识这个等待类型：" + str(waiting_type))
    output_func("你可以稍后使用 task-status --technical 查看细节。")
    return False


def handle_blocked(root: Path, task_dir: Path, input_func: InputFunc, output_func: OutputFunc) -> int:
    task, state = runtime.read_task_files(task_dir)
    waiting = state.get("waiting_for") if isinstance(state.get("waiting_for"), dict) else {}
    output_func(
        "\n".join(
            [
                "任务暂停在：" + presentation.user_stage_name(task.get("task_type"), state.get("current_stage")),
                "",
                "原因：",
                str(waiting.get("reason") or waiting.get("type") or "未知"),
                "",
                "你可以：",
                "1. 重试",
                "2. 跳过可选步骤继续",
                "3. 手工补充内容",
                "4. 查看技术详情",
                "5. 暂停任务",
            ]
        )
    )
    decision = ask_number(input_func, output_func, "请选择：", {"1": "retry", "2": "skip", "3": "manual", "4": "technical", "5": "stop"}, "请输入 1 到 5。")
    if decision == "retry":
        runtime.unblock_task(task_dir)
        append_audit(task_dir, "retry current stage")
        return run_task_session(root, task_dir, input_func, output_func)
    if decision == "skip":
        runtime.unblock_task(task_dir)
        append_audit(task_dir, "skip optional blocked step")
        return run_task_session(root, task_dir, input_func, output_func)
    if decision == "manual":
        output_func("请使用新建学习任务的手工输入流程补充内容；当前任务已保留。")
        append_audit(task_dir, "manual recovery requested")
        return 0
    if decision == "technical":
        output_func(presentation.technical_status(task, state))
    return 0


def append_audit(task_dir: Path, message: str) -> None:
    path = task_dir / "run-log.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("- %s: %s\n" % (runtime.now_iso(), message))


def ask_topic_id(task_dir: Path, input_func: InputFunc, output_func: OutputFunc) -> Optional[str]:
    path = task_dir / "content" / "topic-candidates.json"
    candidates = []
    if path.is_file():
        candidates = list(json.loads(path.read_text(encoding="utf-8")).get("candidates") or [])
    mapping = {str(index): str(item.get("topic_id")) for index, item in enumerate(candidates, 1) if item.get("topic_id")}
    if not mapping:
        output_func("没有可选择的选题，暂不继续。")
        return None
    return ask_number(input_func, output_func, "请选择：", mapping, "请输入有效的选题序号。")


def ask_sample_ids(task_dir: Path, input_func: InputFunc, output_func: OutputFunc) -> List[str]:
    path = task_dir / "analysis" / "sample-candidates.json"
    if not path.is_file():
        output_func("没有候选样本，暂不继续。")
        return []
    candidates = list(json.loads(path.read_text(encoding="utf-8")).get("candidates") or [])
    for index, item in enumerate(candidates, 1):
        output_func("%s. %s" % (index, item.get("title") or item.get("sample_id")))
    try:
        raw = input_func("请选择样本序号，可用空格分隔：").strip()
    except EOFError:
        return []
    ids = []
    for part in raw.split():
        if part.isdigit() and 1 <= int(part) <= len(candidates):
            ids.append(str(candidates[int(part) - 1]["sample_id"]))
    return ids


def choose_task(tasks_dir: Path, completed: bool, input_func: InputFunc, output_func: OutputFunc) -> Optional[Path]:
    tasks = sorted([path for path in tasks_dir.glob("task-*") if (path / "state.yaml").is_file()], key=lambda path: path.stat().st_mtime, reverse=True)
    filtered = []
    for path in tasks:
        task, state = runtime.read_task_files(path)
        is_completed = state.get("status") == "completed"
        if is_completed == completed:
            filtered.append((path, task, state))
    title = "最近结果" if completed else "未完成任务"
    output_func(title + "：")
    if not filtered:
        output_func("暂无")
        return None
    for index, (_path, task, state) in enumerate(filtered[:10], 1):
        output_func("%s. %s · %s · %s" % (index, presentation.task_name(task.get("task_type")), presentation.user_stage_name(task.get("task_type"), state.get("current_stage")), state.get("status")))
    choice = ask_number(input_func, output_func, "请选择：", {str(i): str(i) for i in range(1, len(filtered[:10]) + 1)}, "请输入有效序号。")
    if choice is None:
        return None
    return filtered[int(choice) - 1][0]


def provider_mode(root: Path, provider_name: str) -> str:
    settings = local_config.provider_settings(root, provider_name)
    return str(settings.get("mode") or "unavailable")


def render_capability_summary(root: Path, technical: bool = False) -> str:
    lines = ["当前能力：", "", "✓ 本地工作流：可用"]
    lingzao = provider_mode(root, "lingzao")
    personal = provider_mode(root, "personal_content")
    hot = provider_mode(root, "hot_learning")
    generation = provider_mode(root, "generation")
    lines.append(("✓" if lingzao == "real" else "○") + " Lingzao 真实采集：" + ("可用" if lingzao == "real" else "未配置"))
    lines.append(("✓" if personal == "real" else "○") + " Personal Content：" + ("可用" if personal == "real" else "未配置"))
    lines.append("✓ Codex 内容分析：" + ("可用" if hot in ("codex_manual", "demo", "mock") else "需要配置"))
    lines.append("✓ Codex 内容生成：" + ("可用" if generation in ("codex_manual", "demo", "mock", "codex") else "需要配置"))
    if technical:
        lines.extend(["", "技术配置：", "lingzao=" + lingzao, "personal_content=" + personal, "hot_learning=" + hot, "generation=" + generation])
    return "\n".join(lines)


def run_configure(workspace: workspace_module.XiaobaWorkspace, input_func: InputFunc = input, output_func: OutputFunc = print) -> int:
    output_func(
        "\n".join(
            [
                "配置真实能力",
                "",
                "1. 配置 Lingzao",
                "2. 配置 Personal Content",
                "3. 配置内容分析方式",
                "4. 配置内容生成方式",
                "5. 恢复安全默认设置",
                "6. 返回",
            ]
        )
    )
    choice = ask_number(input_func, output_func, "请选择：", {str(i): str(i) for i in range(1, 7)}, "请输入 1 到 6。")
    if choice == "5":
        workspace.config_path.write_text(workspace_module.SAFE_DEFAULT_CONFIG, encoding="utf-8")
        output_func("已恢复安全默认设置。")
    else:
        output_func("本轮不会自动安装外部 Skill。请按 USER_MANUAL 配置环境变量后再运行。")
    return 0


def run_setup(root: Path, input_func: InputFunc = input, output_func: OutputFunc = print) -> int:
    workspace = workspace_module.bootstrap_workspace(root)
    return run_configure(workspace, input_func, output_func)


def ask_number(input_func: InputFunc, output_func: OutputFunc, question: str, mapping: Dict[str, str], error_message: str) -> Optional[str]:
    while True:
        try:
            value = input_func(question).strip()
        except EOFError:
            return None
        if value in mapping:
            return mapping[value]
        output_func(error_message)
