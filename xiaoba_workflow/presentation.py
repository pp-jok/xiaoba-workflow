from pathlib import Path
from typing import Dict, List, Optional


TASK_NAMES = {
    "learning": "学习单条小红书笔记",
    "learning_batch": "批量学习对标内容",
    "generation": "基于个人规则生成小红书帖子",
    "post_publish_review": "复盘已发布内容",
}

STAGE_NAMES = {
    "task_intake": "准备任务",
    "evidence_collection": "采集公开内容",
    "evidence_normalization": "整理采集证据",
    "analysis": "内容机制拆解",
    "analysis_normalization": "整理内容拆解结果",
    "mechanism_intake": "将学习机制交给 Personal Content",
    "aggregation": "生成学习汇总",
    "benchmark_screening": "筛选候选样本",
    "sample_selection": "等待选择样本",
    "cross_sample_aggregation": "跨样本综合",
    "context_assembly": "准备个性化生成上下文",
    "topic_generation": "生成选题候选",
    "topic_selection": "等待选择选题",
    "content_generation": "生成待审核正文",
    "review": "等待审核内容",
    "completed": "完成",
}

SKILL_BY_STAGE = {
    ("learning", "evidence_collection"): "Lingzao",
    ("learning", "analysis"): "Hot Learning",
    ("learning", "mechanism_intake"): "Personal Content",
    ("learning_batch", "benchmark_screening"): "Lingzao",
    ("learning_batch", "evidence_collection"): "Lingzao",
    ("learning_batch", "analysis"): "Hot Learning",
    ("learning_batch", "cross_sample_aggregation"): "Hot Learning",
    ("learning_batch", "mechanism_intake"): "Personal Content",
    ("generation", "context_assembly"): "Personal Content",
    ("generation", "topic_generation"): "内容生成 Provider",
    ("generation", "content_generation"): "内容生成 Provider",
}

STAGE_PURPOSES = {
    "evidence_collection": "读取标题、正文、作者、公开互动数据，以及可选评论和逐字稿。",
    "analysis": "分析内容为什么有效，并提取可学习机制。",
    "mechanism_intake": "把候选机制导入 Personal Content，由长期工作区负责沉淀。",
    "context_assembly": "读取已准备好的 brief、学习来源和 active rules，组装生成上下文。",
    "topic_generation": "基于已确认上下文生成待选择的选题候选。",
    "content_generation": "基于用户选择的选题生成待审核内容包。",
}

USER_PROGRESS = {
    "learning": [
        ("获取内容", {"task_intake", "evidence_collection", "evidence_normalization"}),
        ("分析内容", {"analysis", "analysis_normalization"}),
        ("提炼方法", {"mechanism_intake"}),
        ("保存学习结果", {"aggregation"}),
        ("完成", {"completed"}),
    ],
    "generation": [
        ("准备个人规则", {"task_intake", "context_assembly"}),
        ("生成选题", {"topic_generation"}),
        ("选择选题", {"topic_selection"}),
        ("生成正文", {"content_generation", "review"}),
        ("审核完成", {"completed"}),
    ],
    "learning_batch": [
        ("准备样本", {"task_intake", "benchmark_screening", "sample_selection"}),
        ("获取内容", {"evidence_collection", "evidence_normalization"}),
        ("分析单条内容", {"analysis", "analysis_normalization"}),
        ("综合共同方法", {"cross_sample_aggregation"}),
        ("保存学习结果", {"mechanism_intake", "completed"}),
    ],
    "post_publish_review": [
        ("获取发布内容", {"task_intake"}),
        ("整理表现数据", set()),
        ("复盘内容表现", {"review_analysis"}),
        ("生成改进建议", set()),
        ("完成", {"completed"}),
    ],
}

USER_STAGE_PURPOSES = {
    "获取内容": "获取公开内容",
    "分析内容": "拆解内容结构",
    "提炼方法": "提炼可学习方法",
    "保存学习结果": "保存学习结果",
    "准备个人规则": "读取你的内容规则",
    "生成选题": "生成选题",
    "选择选题": "等待你选择选题",
    "生成正文": "生成正文",
    "审核完成": "审核完成",
    "准备样本": "准备样本",
    "分析单条内容": "分析单条内容",
    "综合共同方法": "综合共同方法",
    "获取发布内容": "获取发布内容",
    "整理表现数据": "整理表现数据",
    "复盘内容表现": "复盘内容表现",
    "生成改进建议": "生成改进建议",
    "完成": "完成",
}


def task_name(task_type: object) -> str:
    return TASK_NAMES.get(str(task_type), str(task_type))


def stage_name(stage: object) -> str:
    return STAGE_NAMES.get(str(stage), str(stage))


def skill_name(task_type: object, stage: object) -> str:
    return SKILL_BY_STAGE.get((str(task_type), str(stage)), "Xiaoba Workflow")


def progress(task_type: str, current_stage: str, completed_stages: List[object], workflows: Dict[str, Dict[str, object]]) -> str:
    steps = USER_PROGRESS.get(task_type)
    if not steps:
        stages = list((workflows.get(task_type) or {}).get("stages", {}).keys())
        total = max(len([stage for stage in stages if stage != "completed"]), 1)
        completed = len([stage for stage in completed_stages if stage in stages and stage != "completed"])
        if current_stage == "completed":
            completed = total
        return "%s / %s" % (completed, total)
    total = len(steps)
    current_index = user_step_index(task_type, current_stage)
    completed = current_index
    if current_stage == "completed":
        completed = total
    return "%s / %s" % (completed, total)


def render_task_status(task: Dict[str, object], state: Dict[str, object], workflows: Dict[str, Dict[str, object]], technical: bool = False) -> str:
    if technical:
        return technical_status(task, state)
    task_type = str(task.get("task_type") or state.get("task_type") or "")
    current_stage = str(state.get("current_stage") or "")
    completed = list(state.get("completed_stages") or [])
    lines = [
        "任务：" + task_name(task_type),
        "整体进度：" + progress(task_type, current_stage, completed, workflows),
        "当前步骤：" + user_stage_name(task_type, current_stage),
        "使用能力：" + skill_name(task_type, current_stage),
        "",
        "进度：",
    ]
    lines.extend(render_user_progress_lines(task_type, current_stage))
    lines.extend(["", render_gate_prompt(task, state) or next_action(task, state)])
    return "\n".join(lines)


def technical_status(task: Dict[str, object], state: Dict[str, object]) -> str:
    keys = ("task_id", "task_type", "status", "current_stage", "current_step", "next_stage")
    return "\n".join("%s: %s" % (key, state.get(key, task.get(key))) for key in keys)


def render_stage_intro(task: Dict[str, object], state: Dict[str, object], workflows: Dict[str, Dict[str, object]]) -> str:
    task_type = str(task.get("task_type") or "")
    stage = str(state.get("current_stage") or "")
    action = USER_STAGE_PURPOSES.get(user_stage_name(task_type, stage), user_stage_name(task_type, stage))
    return "\n".join(
        [
            "正在" + action,
            "使用能力：" + skill_name(task_type, stage),
            "当前进度：" + progress(task_type, stage, list(state.get("completed_stages") or []), workflows),
        ]
    )


def render_stage_done(task: Dict[str, object], state: Dict[str, object], executed_stage: str) -> str:
    lines = [
        "已完成：" + user_stage_name(str(task.get("task_type") or ""), executed_stage),
        "当前步骤：" + user_stage_name(str(task.get("task_type") or ""), state.get("current_stage")),
        "",
        render_completion_summary(Path("tasks") / str(task.get("task_id") or ""), task, state)
        if state.get("status") == "completed"
        else (render_gate_prompt(task, state) or next_action(task, state)),
    ]
    return "\n".join(lines)


def next_action(task: Dict[str, object], state: Dict[str, object]) -> str:
    task_id = str(task.get("task_id") or state.get("task_id") or "<task-id>")
    task_dir = "tasks/" + task_id
    status = state.get("status")
    waiting = state.get("waiting_for") if isinstance(state.get("waiting_for"), dict) else {}
    waiting_type = waiting.get("type")
    if status == "completed":
        return "下一步：查看结果摘要，或新建下一个任务。"
    if status == "blocked":
        return "下一步建议：处理 blocked 原因后运行 xiaoba-workflow unblock %s" % task_dir
    if waiting_type == "generation_brief":
        return "下一步建议：xiaoba-workflow set-generation-brief %s --brief \"你的内容需求\"" % task_dir
    if waiting_type == "sample_selection":
        return "下一步建议：xiaoba-workflow select-samples %s --ids sample-001" % task_dir
    if waiting_type == "topic_selection":
        return "下一步建议：xiaoba-workflow select-topic %s --id topic-001" % task_dir
    if waiting_type == "content_review":
        return "下一步建议：xiaoba-workflow review-content %s --decision approve" % task_dir
    return "下一步建议：xiaoba-workflow run %s" % task_dir


def render_start() -> str:
    return "\n".join(
        [
            "你想做什么？",
            "1. 学习一条小红书笔记",
            "2. 学习一批对标内容",
            "3. 生成一篇小红书帖子",
            "4. 复盘一篇已发布内容",
        ]
    )


def user_stage_name(task_type: object, stage: object) -> str:
    stage_text = str(stage)
    for name, internal_stages in USER_PROGRESS.get(str(task_type), []):
        if stage_text in internal_stages:
            return name
    return stage_name(stage)


def user_step_index(task_type: str, stage: str) -> int:
    for index, (_name, internal_stages) in enumerate(USER_PROGRESS.get(task_type, [])):
        if stage in internal_stages:
            return index
    return 0


def render_user_progress_lines(task_type: str, current_stage: str) -> List[str]:
    steps = USER_PROGRESS.get(task_type)
    if not steps:
        return ["- " + stage_name(current_stage)]
    current_index = user_step_index(task_type, current_stage)
    lines = []
    for index, (name, _stages) in enumerate(steps):
        marker = "✓" if current_stage == "completed" or index < current_index else ("→" if index == current_index else "○")
        lines.append("%s %s. %s" % (marker, index + 1, name))
    return lines


def render_gate_prompt(task: Dict[str, object], state: Dict[str, object], task_dir: Optional[Path] = None) -> str:
    if state.get("status") != "waiting_for_user":
        return ""
    waiting = state.get("waiting_for") if isinstance(state.get("waiting_for"), dict) else {}
    waiting_type = waiting.get("type")
    if waiting_type == "external_cost_confirmation":
        operations = str(waiting.get("operations") or "")
        is_video = "collect_transcript" in operations
        intro = "这是一个视频笔记。" if is_video else "这是一条公开笔记。"
        items = ["- 必要的公开评论"]
        if is_video:
            items.insert(0, "- 公开视频口播文案")
        return "\n".join(
            [intro, "", "为了更准确地分析，我可以额外获取："]
            + items
            + ["", "这些操作可能消耗 Lingzao 积分。", "", "请选择：", "1. 获取后继续", "2. 只使用当前内容"]
        )
    if waiting_type == "sample_selection":
        return "已准备好候选样本。\n\n请选择要学习的样本。"
    if waiting_type == "topic_selection" and task_dir is not None:
        return render_topic_gate(task_dir)
    if waiting_type == "topic_selection":
        return "已生成选题。\n\n请选择一个选题。"
    if waiting_type == "content_review":
        return "\n".join(["正文已经生成。", "", "请选择：", "1. 通过", "2. 修改", "3. 暂不处理"])
    if waiting_type == "generation_brief":
        return "请告诉我这次想生成什么内容。"
    return next_action(task, state)


def render_topic_gate(task_dir: Path) -> str:
    import json

    path = task_dir / "content" / "topic-candidates.json"
    if not path.is_file():
        return "已生成选题。\n\n请选择一个选题。"
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates = payload.get("candidates") or []
    lines = ["已生成 %s 个选题：" % len(candidates), ""]
    for index, item in enumerate(candidates, 1):
        lines.append("%s. %s" % (index, item.get("title_direction") or item.get("title") or "未命名选题"))
        lines.append("   " + str(item.get("fit_reason") or item.get("core_point") or "适合继续生成正文"))
        lines.append("")
    lines.append("请选择 1 到 %s。" % len(candidates))
    return "\n".join(lines).rstrip()


def render_completion_summary(task_dir: Path, task: Dict[str, object], state: Dict[str, object]) -> str:
    task_type = str(task.get("task_type") or state.get("task_type") or "")
    if task_type == "learning":
        return "\n".join(
            [
                "学习完成。",
                "",
                "本次得到：",
                "- 可学习的内容机制已整理",
                "- 规则候选已保留在学习结果中",
                "- 不建议照搬的做法已记录",
                "",
                "使用能力：",
                "- Lingzao：获取公开内容",
                "- Hot Learning：拆解内容",
                "- Personal Content：保存学习结果",
                "",
                "下一步：可以基于这些学习结果生成一篇帖子。",
            ]
        )
    if task_type == "generation":
        return "\n".join(
            [
                "内容已完成审核。",
                "",
                "结果：",
                "- 最终选题：已选择",
                "- 内容版本：已保存",
                "- 使用规则：已按上下文引用",
                "- 修改次数：已记录",
                "",
                "说明：",
                "内容只保存在本地，没有自动发布。",
            ]
        )
    if task_type == "post_publish_review":
        return "\n".join(
            [
                "复盘完成。",
                "",
                "本次建议：",
                "- 继续保留：见复盘建议",
                "- 建议观察：见复盘建议",
                "- 建议调整：见复盘建议",
                "",
                "这些只是建议，不会自动修改 Personal Content 中的规则。",
            ]
        )
    return "任务已完成。"


def task_dir_label(task_dir: Path) -> str:
    try:
        return str(task_dir.relative_to(Path.cwd()))
    except ValueError:
        return str(task_dir)
