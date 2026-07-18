import json
from pathlib import Path
from typing import Callable, Dict, Optional

from . import presentation
from . import runtime


InputFunc = Callable[[str], str]
OutputFunc = Callable[[str], None]


TASK_BY_CHOICE = {
    "1": ("learning", "请粘贴公开小红书笔记链接："),
    "2": ("learning_batch", "请粘贴对标账号或主页链接："),
    "3": ("generation", "请告诉我这次想生成什么内容："),
    "4": ("post_publish_review", "请粘贴已发布内容链接："),
}


def run_start(root: Path, input_func: InputFunc = input, output_func: OutputFunc = print) -> int:
    output_func(presentation.render_start())
    choice = ask_choice(input_func, output_func)
    if choice is None:
        return 0
    task_type, question = TASK_BY_CHOICE[choice]
    try:
        answer = input_func(question).strip()
    except EOFError:
        return 0
    if not answer:
        output_func("没有收到必要信息，任务未创建。")
        return 1
    if task_type == "generation":
        task_dir = runtime.create_task(root, task_type, None, answer)
    else:
        task_dir = runtime.create_task(root, task_type, answer)
    output_func("")
    output_func("已创建任务。")
    output_func("")
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
            waiting = latest_state.get("waiting_for") if isinstance(latest_state.get("waiting_for"), dict) else {}
            output_func("任务已暂停。\n\n原因：" + str(waiting.get("reason") or "未知"))
            return 0
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
        output_func("已记录选择。")
        output_func("")
        return True
    if waiting_type == "topic_selection":
        topic_id = ask_topic_id(task_dir, input_func, output_func)
        if topic_id is None:
            return False
        runtime.select_topic(root, task_dir, topic_id)
        output_func("已选择选题。")
        output_func("")
        return True
    if waiting_type == "content_review":
        decision = ask_number(
            input_func,
            output_func,
            "请选择：",
            {"1": "approve", "2": "request_changes", "3": "stop"},
            "请输入 1、2 或 3。",
        )
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
        output_func("已记录审核结果。")
        output_func("")
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
        output_func("已记录内容需求。")
        output_func("")
        return True
    return 0


def ask_choice(input_func: InputFunc, output_func: OutputFunc) -> Optional[str]:
    while True:
        try:
            choice = input_func("请选择：").strip()
        except EOFError:
            return None
        if choice in TASK_BY_CHOICE:
            return choice
        output_func("请输入 1、2、3 或 4。")


def ask_number(
    input_func: InputFunc,
    output_func: OutputFunc,
    question: str,
    mapping: Dict[str, str],
    error_message: str,
) -> Optional[str]:
    while True:
        try:
            value = input_func(question).strip()
        except EOFError:
            return None
        if value in mapping:
            return mapping[value]
        output_func(error_message)


def ask_topic_id(task_dir: Path, input_func: InputFunc, output_func: OutputFunc) -> Optional[str]:
    path = task_dir / "content" / "topic-candidates.json"
    candidates = []
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        candidates = list(payload.get("candidates") or [])
    mapping = {str(index): str(item.get("topic_id")) for index, item in enumerate(candidates, 1) if item.get("topic_id")}
    if not mapping:
        output_func("没有可选择的选题，暂不继续。")
        return None
    return ask_number(input_func, output_func, "请选择：", mapping, "请输入有效的选题序号。")


def run_setup(root: Path, input_func: InputFunc = input, output_func: OutputFunc = print) -> int:
    config_path = root / "xiaoba.local.yaml"
    if config_path.exists():
        raise runtime.WorkflowError("xiaoba.local.yaml 已存在；为避免覆盖，请先手工检查后再修改。")
    answers: Dict[str, str] = {}
    questions = [
        ("lingzao", "Lingzao 是否已安装？\n1. 已安装\n2. 暂不配置\n请选择："),
        ("personal_content", "Personal Content 是否已准备？\n1. 已准备\n2. 暂不配置\n请选择："),
        ("generation", "Generation 使用哪种模式？\n1. mock\n2. external\n请选择："),
        ("transcript", "视频笔记是否默认询问获取逐字稿？\n1. 询问\n2. 不询问\n请选择："),
    ]
    for key, question in questions:
        answers[key] = ask_binary(input_func, output_func, question)
    config = render_local_config(answers)
    config_path.write_text(config, encoding="utf-8")
    output_func("已生成 xiaoba.local.yaml。")
    output_func("API Key、Token 和 Cookie 不会写入该文件，请继续使用环境变量或本地 .env。")
    return 0


def ask_binary(input_func: InputFunc, output_func: OutputFunc, question: str) -> str:
    while True:
        try:
            value = input_func(question).strip()
        except EOFError:
            return "2"
        if value in ("1", "2"):
            return value
        output_func("请输入 1 或 2。")


def render_local_config(answers: Dict[str, str]) -> str:
    lingzao_mode = "real" if answers.get("lingzao") == "1" else "mock"
    personal_mode = "real" if answers.get("personal_content") == "1" else "mock"
    generation_mode = "external" if answers.get("generation") == "2" else "mock"
    transcript_policy = "ask" if answers.get("transcript") == "1" else "never"
    return (
        "providers:\n"
        "  lingzao:\n"
        "    mode: %s\n"
        "    skill_root: /absolute/path/to/lingzao\n"
        "    timeout_seconds: 300\n"
        "\n"
        "  hot_learning:\n"
        "    mode: mock\n"
        "    command: []\n"
        "    timeout_seconds: 300\n"
        "\n"
        "  personal_content:\n"
        "    mode: %s\n"
        "    workspace: /absolute/path/to/personal-content-workspace\n"
        "\n"
        "  generation:\n"
        "    mode: %s\n"
        "    command: []\n"
        "    timeout_seconds: 300\n"
        "\n"
        "learning:\n"
        "  collect_comments: never\n"
        "  collect_transcript: %s\n"
        "  allow_auto_paid_calls: false\n"
        "  transcript_required: false\n"
        "\n"
        "features:\n"
        "  auto_publish: false\n"
    ) % (lingzao_mode, personal_mode, generation_mode, transcript_policy)
