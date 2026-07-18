import argparse
import sys
from pathlib import Path
from typing import Iterable

from . import runtime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xiaoba_workflow",
        description="Lightweight project baseline tools for the Xiaoba workflow.",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "validate-project",
        help="Check required baseline directories, templates, prompts, and workflow.yaml.",
    )
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Check local provider configuration without installing or modifying anything.",
    )
    doctor_parser.add_argument("--skill", default="lingzao")

    create_parser = subparsers.add_parser(
        "create-task",
        help="Create a task directory with task.yaml, state.yaml, and working folders.",
    )
    create_parser.add_argument("--type", required=True, choices=runtime.TASK_TYPES, dest="task_type")
    create_parser.add_argument("--source-url")
    create_parser.add_argument("--brief")

    status_parser = subparsers.add_parser(
        "task-status",
        help="Read and display the core task and state fields.",
    )
    status_parser.add_argument("task_dir")

    advance_parser = subparsers.add_parser(
        "advance",
        help="Advance a task by one configured workflow stage without running stage business logic.",
    )
    advance_parser.add_argument("task_dir")

    resume_parser = subparsers.add_parser(
        "resume",
        help="Resume a task waiting at a configured human gate and move to its next stage.",
    )
    resume_parser.add_argument("task_dir")

    block_parser = subparsers.add_parser(
        "block",
        help="Mark a task blocked without changing its current stage.",
    )
    block_parser.add_argument("task_dir")
    block_parser.add_argument("--reason", required=True)

    unblock_parser = subparsers.add_parser(
        "unblock",
        help="Clear blocked status without advancing the task.",
    )
    unblock_parser.add_argument("task_dir")

    run_parser = subparsers.add_parser(
        "run",
        help="Execute the current stage once without running a full workflow.",
    )
    run_parser.add_argument("task_dir")

    import_hot_learning_parser = subparsers.add_parser(
        "import-hot-learning-analysis",
        help="Import a manually produced Hot Learning raw Markdown analysis for the current analysis stage.",
    )
    import_hot_learning_parser.add_argument("task_dir")
    import_hot_learning_parser.add_argument("--markdown", required=True)

    select_parser = subparsers.add_parser(
        "select-samples",
        help="Submit selected sample IDs for a learning_batch sample_selection gate.",
    )
    select_parser.add_argument("task_dir")
    select_parser.add_argument("--ids", nargs="*", required=True)

    brief_parser = subparsers.add_parser(
        "set-generation-brief",
        help="Set the brief for a generation task that does not have one yet.",
    )
    brief_parser.add_argument("task_dir")
    brief_parser.add_argument("--brief", required=True)

    attach_parser = subparsers.add_parser(
        "attach-learning",
        help="Attach a completed learning task as an explicit generation context source.",
    )
    attach_parser.add_argument("task_dir")
    attach_parser.add_argument("--task", required=True, dest="source_task_dir")

    topic_parser = subparsers.add_parser(
        "select-topic",
        help="Select one generated topic candidate for a generation task.",
    )
    topic_parser.add_argument("task_dir")
    topic_parser.add_argument("--id", required=True, dest="topic_id")

    review_parser = subparsers.add_parser(
        "review-content",
        help="Submit a content review decision for a generation task.",
    )
    review_parser.add_argument("task_dir")
    review_parser.add_argument("--decision", required=True, choices=("approve", "request_changes", "reject"))
    review_parser.add_argument("--feedback")

    governance_parser = subparsers.add_parser(
        "prepare-governance",
        help="Prepare a review-only Personal Content governance plan from a completed learning task.",
    )
    governance_parser.add_argument("task_dir")
    governance_parser.add_argument("--profile-id", required=True)

    propose_rule_parser = subparsers.add_parser(
        "propose-governance-rule",
        help="Create a Personal Content candidate rule from one governance plan rule proposal.",
    )
    propose_rule_parser.add_argument("task_dir")
    propose_rule_parser.add_argument("--proposal-id", required=True)

    confirm_rule_parser = subparsers.add_parser(
        "confirm-governance-rule",
        help="Confirm or reject a Personal Content candidate rule created from a governance proposal.",
    )
    confirm_rule_parser.add_argument("task_dir")
    confirm_rule_parser.add_argument("--proposal-id", required=True)
    confirm_rule_parser.add_argument("--decision", required=True, choices=("confirm", "reject"))
    confirm_rule_parser.add_argument("--note", default="")
    return parser


def main(argv: Iterable[str] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate-project":
        missing = runtime.validate_project(Path.cwd())
        if missing:
            print("Project baseline is invalid. Missing:")
            for item in missing:
                print("- " + item)
            return 1
        print("Project baseline is valid.")
        return 0

    if args.command == "doctor":
        try:
            messages = runtime.doctor(Path.cwd(), args.skill)
        except (runtime.WorkflowError, FileNotFoundError) as error:
            print(str(error), file=sys.stderr)
            return 1
        for message in messages:
            print(message)
        return 0

    if args.command == "create-task":
        try:
            task_dir = runtime.create_task(Path.cwd(), args.task_type, args.source_url, args.brief)
        except ValueError as error:
            parser.error(str(error))
        except (OSError, runtime.WorkflowError, FileNotFoundError) as error:
            print("Failed to create task: " + str(error))
            return 1
        print("Created task: " + str(task_dir.relative_to(Path.cwd())))
        return 0

    if args.command == "task-status":
        try:
            status = runtime.read_task_status(Path(args.task_dir))
        except (FileNotFoundError, runtime.WorkflowError) as error:
            print(str(error), file=sys.stderr)
            return 1
        for key in ("task_id", "task_type", "status", "current_stage", "current_step", "next_stage"):
            print("%s: %s" % (key, status[key]))
        return 0

    if args.command == "advance":
        return run_state_command(lambda: runtime.advance_task(Path.cwd(), Path(args.task_dir)), "Advanced task")
    if args.command == "resume":
        return run_state_command(lambda: runtime.resume_task(Path.cwd(), Path(args.task_dir)), "Resumed task")
    if args.command == "block":
        return run_state_command(lambda: runtime.block_task(Path(args.task_dir), args.reason), "Blocked task")
    if args.command == "unblock":
        return run_state_command(lambda: runtime.unblock_task(Path(args.task_dir)), "Unblocked task")
    if args.command == "run":
        return run_state_command(lambda: runtime.run_task(Path.cwd(), Path(args.task_dir)), "Ran stage")
    if args.command == "import-hot-learning-analysis":
        return run_state_command(
            lambda: runtime.import_hot_learning_analysis(Path.cwd(), Path(args.task_dir), Path(args.markdown)),
            "Imported Hot Learning analysis",
        )
    if args.command == "select-samples":
        return run_state_command(lambda: runtime.select_samples(Path.cwd(), Path(args.task_dir), args.ids), "Selected samples")
    if args.command == "set-generation-brief":
        return run_state_command(lambda: runtime.set_generation_brief(Path(args.task_dir), args.brief), "Set generation brief")
    if args.command == "attach-learning":
        return run_state_command(lambda: runtime.attach_learning_source(Path.cwd(), Path(args.task_dir), Path(args.source_task_dir)), "Attached learning")
    if args.command == "select-topic":
        return run_state_command(lambda: runtime.select_topic(Path.cwd(), Path(args.task_dir), args.topic_id), "Selected topic")
    if args.command == "review-content":
        return run_state_command(lambda: runtime.review_content(Path.cwd(), Path(args.task_dir), args.decision, args.feedback), "Reviewed content")
    if args.command == "prepare-governance":
        return run_state_command(lambda: runtime.prepare_governance(Path.cwd(), Path(args.task_dir), args.profile_id), "Prepared governance")
    if args.command == "propose-governance-rule":
        return run_state_command(
            lambda: runtime.propose_governance_rule(Path.cwd(), Path(args.task_dir), args.proposal_id),
            "Proposed governance rule",
        )
    if args.command == "confirm-governance-rule":
        return run_state_command(
            lambda: runtime.confirm_governance_rule(Path.cwd(), Path(args.task_dir), args.proposal_id, args.decision, args.note),
            "Confirmed governance rule",
        )

    parser.print_help()
    return 0


def run_state_command(action, label: str) -> int:
    try:
        state = action()
    except (FileNotFoundError, runtime.WorkflowError) as error:
        print(str(error), file=sys.stderr)
        return 1
    reported_stage = state.get("_executed_stage", state["current_stage"])
    print("%s: %s" % (label, reported_stage))
    return 0
