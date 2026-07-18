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


def task_name(task_type: object) -> str:
    return TASK_NAMES.get(str(task_type), str(task_type))


def stage_name(stage: object) -> str:
    return STAGE_NAMES.get(str(stage), str(stage))


def skill_name(task_type: object, stage: object) -> str:
    return SKILL_BY_STAGE.get((str(task_type), str(stage)), "Xiaoba Workflow")


def progress(task_type: str, current_stage: str, completed_stages: List[object], workflows: Dict[str, Dict[str, object]]) -> str:
    stages = list((workflows.get(task_type) or {}).get("stages", {}).keys())
    total = max(len([stage for stage in stages if stage != "completed"]), 1)
    completed = len([stage for stage in completed_stages if stage in stages and stage != "completed"])
    if current_stage == "completed":
        completed = total
    return "%s / %s" % (completed, total)


def render_task_status(task: Dict[str, object], state: Dict[str, object], workflows: Dict[str, Dict[str, object]], technical: bool = False) -> str:
    if technical:
        return technical_status(task, state)
    task_type = str(task.get("task_type") or state.get("task_type") or "")
    current_stage = str(state.get("current_stage") or "")
    stages = list((workflows.get(task_type) or {}).get("stages", {}).keys())
    completed = list(state.get("completed_stages") or [])
    lines = [
        "任务：" + task_name(task_type),
        "任务 ID：" + str(task.get("task_id") or state.get("task_id") or ""),
        "整体进度：" + progress(task_type, current_stage, completed, workflows),
        "当前阶段：" + stage_name(current_stage),
        "当前执行模块：" + skill_name(task_type, current_stage),
        "",
        "已完成：",
    ]
    finished = [stage for stage in stages if stage in completed and stage != "completed"]
    if finished:
        lines.extend("✓ " + stage_name(stage) for stage in finished)
    else:
        lines.append("无")
    lines.extend(["", "待完成："])
    pending = [stage for stage in stages if stage not in completed and stage != "completed"]
    if current_stage == "completed":
        pending = []
    if pending:
        lines.extend("○ " + stage_name(stage) for stage in pending)
    else:
        lines.append("无")
    lines.extend(["", next_action(task, state)])
    lines.extend(["", "技术信息：", technical_status(task, state)])
    return "\n".join(lines)


def technical_status(task: Dict[str, object], state: Dict[str, object]) -> str:
    keys = ("task_id", "task_type", "status", "current_stage", "current_step", "next_stage")
    return "\n".join("%s: %s" % (key, state.get(key, task.get(key))) for key in keys)


def render_stage_intro(task: Dict[str, object], state: Dict[str, object], workflows: Dict[str, Dict[str, object]]) -> str:
    task_type = str(task.get("task_type") or "")
    stage = str(state.get("current_stage") or "")
    return "\n".join(
        [
            "当前任务：" + task_name(task_type),
            "当前阶段：" + stage_name(stage),
            "正在执行：" + skill_name(task_type, stage),
            "作用：" + STAGE_PURPOSES.get(stage, "完成当前阶段的必要检查和产物写入。"),
            "当前进度：" + progress(task_type, stage, list(state.get("completed_stages") or []), workflows),
        ]
    )


def render_stage_done(task: Dict[str, object], state: Dict[str, object], executed_stage: str) -> str:
    lines = [
        "已完成：" + stage_name(executed_stage),
        "当前状态：" + str(state.get("status")),
        "当前阶段：" + stage_name(state.get("current_stage")),
        "",
        next_action(task, state),
    ]
    return "\n".join(lines)


def next_action(task: Dict[str, object], state: Dict[str, object]) -> str:
    task_id = str(task.get("task_id") or state.get("task_id") or "<task-id>")
    task_dir = "tasks/" + task_id
    status = state.get("status")
    waiting = state.get("waiting_for") if isinstance(state.get("waiting_for"), dict) else {}
    waiting_type = waiting.get("type")
    if status == "completed":
        return "下一步建议：查看任务产物，或新建下一个任务。"
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
            "   xiaoba-workflow create-task --type learning --source-url \"<公开笔记链接>\"",
            "2. 批量学习对标内容",
            "   xiaoba-workflow create-task --type learning_batch --source-url \"<账号或主页链接>\"",
            "3. 基于已沉淀规则生成帖子",
            "   xiaoba-workflow create-task --type generation --brief \"<内容需求>\"",
            "4. 复盘已发布内容",
            "   本地骨架已准备，自动发布不支持，复盘链路仍需用户提供公开链接和数据。",
        ]
    )


def task_dir_label(task_dir: Path) -> str:
    try:
        return str(task_dir.relative_to(Path.cwd()))
    except ValueError:
        return str(task_dir)
