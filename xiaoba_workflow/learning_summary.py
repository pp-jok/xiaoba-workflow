import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List


SUMMARY_FILE = "learning-summary.yaml"
INTAKE_STATUSES = ("imported", "matched_existing", "limited", "rejected", "failed")
SUCCESS_STATUSES = ("imported", "matched_existing", "limited")
FORBIDDEN_FIELDS = {
    "rule_card",
    "RuleCard",
    "content_asset",
    "ContentAsset",
    "generated_content",
    "generated_post",
    "auto_generation",
    "generation_directive",
}


class LearningSummaryError(Exception):
    pass


def build_learning_summary(
    task: Dict[str, str],
    evidence: Dict[str, object],
    analysis: Dict[str, object],
    intake_result: Dict[str, object],
) -> Dict[str, object]:
    results_by_status = classify_intake_results(intake_result)
    rule_suggestions = list(analysis.get("rule_suggestions") or [])
    asset_suggestions = list(analysis.get("asset_suggestions") or [])
    governance_reasons = governance_reason_list(rule_suggestions, asset_suggestions, results_by_status)

    return {
        "summary_id": "summary-" + task["task_id"],
        "task_id": task["task_id"],
        "sample_id": evidence["sample_id"],
        "created_at": now_iso(),
        "source": {
            "original_url": evidence["source"]["original_url"],
        },
        "evidence_summary": {
            "normalization_status": evidence["normalization"]["status"],
            "available": available_evidence(evidence),
            "missing": list(evidence.get("missing") or []),
            "warnings": list(evidence.get("warnings") or evidence["normalization"].get("warnings") or []),
        },
        "analysis_summary": {
            "normalization_status": analysis["normalization"]["status"],
            "mechanism_count": len(analysis.get("mechanisms") or []),
            "rule_suggestion_count": len(rule_suggestions),
            "asset_suggestion_count": len(asset_suggestions),
            "content_opportunity_count": len(analysis.get("content_opportunities") or []),
            "warnings": list(analysis["normalization"].get("warnings") or []),
        },
        "mechanism_intake_summary": results_by_status,
        "governance": {
            "recommended": bool(governance_reasons),
            "reasons": governance_reasons,
            "pending_rule_suggestions": rule_suggestions,
            "pending_asset_suggestions": asset_suggestions,
        },
        "content_opportunities": list(analysis.get("content_opportunities") or []),
        "open_questions": list(analysis.get("questions") or []),
        "next_recommended_actions": next_actions(governance_reasons, analysis, results_by_status),
    }


def classify_intake_results(intake_result: Dict[str, object]) -> Dict[str, List[Dict[str, object]]]:
    classified = {status: [] for status in INTAKE_STATUSES}
    seen = set()
    results = intake_result.get("results")
    if not isinstance(results, list) or not results:
        raise LearningSummaryError("mechanism intake results are required")

    for item in results:
        if not isinstance(item, dict):
            raise LearningSummaryError("mechanism intake result must be an object")
        source_id = item.get("source_mechanism_id")
        status = item.get("status")
        if not source_id:
            raise LearningSummaryError("source_mechanism_id is required")
        if source_id in seen:
            raise LearningSummaryError("duplicate mechanism intake result: " + str(source_id))
        if status not in INTAKE_STATUSES:
            raise LearningSummaryError("invalid mechanism intake status: " + str(status))
        seen.add(source_id)
        classified[status].append(
            {
                "source_mechanism_id": source_id,
                "external_object": item.get("external_object"),
                "reason": item.get("reason"),
                "warnings": list(item.get("warnings") or []),
            }
        )

    if not any(classified[status] for status in SUCCESS_STATUSES):
        raise LearningSummaryError("no successful mechanism intake result")
    return classified


def validate_intake_result(intake_result: Dict[str, object], task: Dict[str, str]) -> None:
    if intake_result.get("task_id") and intake_result.get("task_id") != task["task_id"]:
        raise LearningSummaryError("task_id mismatch")
    if not intake_result.get("workspace_ref"):
        raise LearningSummaryError("workspace_ref is required")
    classify_intake_results(intake_result)


def validate_learning_summary(
    summary: Dict[str, object],
    summary_path: Path,
    task: Dict[str, str],
    evidence: Dict[str, object],
    analysis: Dict[str, object],
    intake_result: Dict[str, object],
) -> None:
    if not summary_path.is_file():
        raise LearningSummaryError("learning-summary.yaml does not exist")
    reject_forbidden_fields(summary)
    if summary.get("task_id") != task["task_id"]:
        raise LearningSummaryError("task_id mismatch")
    if not summary.get("sample_id"):
        raise LearningSummaryError("sample_id is required")
    if summary.get("sample_id") != evidence.get("sample_id") or summary.get("sample_id") != analysis.get("sample_id"):
        raise LearningSummaryError("sample_id mismatch")
    source = summary.get("source")
    if not isinstance(source, dict) or not source.get("original_url"):
        raise LearningSummaryError("source.original_url is required")
    if source.get("original_url") != evidence["source"]["original_url"]:
        raise LearningSummaryError("source.original_url mismatch")

    analysis_summary = summary.get("analysis_summary")
    if not isinstance(analysis_summary, dict):
        raise LearningSummaryError("analysis_summary is required")
    if analysis_summary.get("mechanism_count") != len(analysis.get("mechanisms") or []):
        raise LearningSummaryError("mechanism_count mismatch")
    if analysis_summary.get("rule_suggestion_count") != len(analysis.get("rule_suggestions") or []):
        raise LearningSummaryError("rule_suggestion_count mismatch")
    if analysis_summary.get("asset_suggestion_count") != len(analysis.get("asset_suggestions") or []):
        raise LearningSummaryError("asset_suggestion_count mismatch")
    if analysis_summary.get("content_opportunity_count") != len(analysis.get("content_opportunities") or []):
        raise LearningSummaryError("content_opportunity_count mismatch")

    expected = classify_intake_results(intake_result)
    actual = summary.get("mechanism_intake_summary")
    if not isinstance(actual, dict):
        raise LearningSummaryError("mechanism_intake_summary is required")
    expected_ids = sorted(flatten_source_ids(expected))
    actual_ids = sorted(flatten_source_ids(actual))
    if actual_ids != expected_ids:
        raise LearningSummaryError("mechanism intake classification mismatch")
    if len(actual_ids) != len(set(actual_ids)):
        raise LearningSummaryError("duplicate mechanism intake classification")

    governance = summary.get("governance")
    if not isinstance(governance, dict):
        raise LearningSummaryError("governance is required")
    if "approved" in governance or "formal_status" in governance:
        raise LearningSummaryError("governance contains formal status")
    if not isinstance(governance.get("recommended"), bool):
        raise LearningSummaryError("governance.recommended must be boolean")


def reject_forbidden_fields(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in FORBIDDEN_FIELDS:
                raise LearningSummaryError("forbidden learning summary field: " + key)
            reject_forbidden_fields(nested)
    elif isinstance(value, list):
        for item in value:
            reject_forbidden_fields(item)


def flatten_source_ids(classified: Dict[str, object]) -> List[str]:
    values = []
    for status in INTAKE_STATUSES:
        items = classified.get(status)
        if not isinstance(items, list):
            raise LearningSummaryError("mechanism_intake_summary.%s must be a list" % status)
        for item in items:
            if not isinstance(item, dict) or not item.get("source_mechanism_id"):
                raise LearningSummaryError("source_mechanism_id is required")
            values.append(str(item["source_mechanism_id"]))
    return values


def available_evidence(evidence: Dict[str, object]) -> List[str]:
    coverage = evidence.get("coverage") or {}
    available = []
    for key, value in coverage.items():
        if value == "available":
            available.append(str(key))
    return available


def governance_reason_list(
    rule_suggestions: List[object],
    asset_suggestions: List[object],
    results_by_status: Dict[str, List[Dict[str, object]]],
) -> List[str]:
    reasons = []
    if rule_suggestions:
        reasons.append("analysis contains pending rule suggestions")
    if asset_suggestions:
        reasons.append("analysis contains pending asset suggestions")
    if results_by_status["limited"]:
        reasons.append("limited mechanism intake results need governance review")
    if results_by_status["rejected"]:
        reasons.append("rejected mechanism intake results should be reviewed")
    return reasons


def next_actions(
    governance_reasons: List[str],
    analysis: Dict[str, object],
    results_by_status: Dict[str, List[Dict[str, object]]],
) -> List[str]:
    actions = []
    if governance_reasons:
        actions.append("Review pending governance suggestions separately.")
    if analysis.get("content_opportunities"):
        actions.append("Keep content opportunities for a future generation task.")
    if results_by_status["limited"] or results_by_status["rejected"]:
        actions.append("Review limited or rejected mechanism intake results before formal use.")
    return actions


def read_json(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, payload: Dict[str, object]) -> None:
    temp_file = path.with_name("." + path.name + ".tmp")
    temp_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_file.replace(path)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
