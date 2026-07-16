import json
from pathlib import Path
from typing import Dict, List, Optional


class AnalysisError(Exception):
    pass


def read_json_file(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_hot_learning_analysis(task_dir: Path, evidence: Dict[str, object]) -> Dict[str, object]:
    markdown_path = task_dir / "raw" / "hot-learning" / "analysis.md"
    invocation_path = task_dir / "raw" / "hot-learning" / "invocation.json"
    return normalize_hot_learning_analysis_from_files(
        markdown_path=markdown_path,
        invocation_path=invocation_path,
        evidence=evidence,
        raw_analysis_ref_file="raw/hot-learning/analysis.md",
    )


def normalize_hot_learning_analysis_from_files(
    markdown_path: Path,
    invocation_path: Path,
    evidence: Dict[str, object],
    raw_analysis_ref_file: str,
) -> Dict[str, object]:
    if not markdown_path.is_file():
        return failed_analysis(evidence, ["normalization_failed: missing " + str(markdown_path)])
    if not invocation_path.is_file():
        return failed_analysis(evidence, ["normalization_failed: missing " + str(invocation_path)])

    markdown = markdown_path.read_text(encoding="utf-8")
    validate_markdown_evidence_refs(markdown, evidence)
    sections = parse_markdown_sections(markdown)
    warnings = []
    mechanisms = parse_mechanisms(sections, warnings, raw_analysis_ref_file)
    if not mechanisms:
        return failed_analysis(evidence, ["normalization_failed: no valid mechanisms extracted"])

    status = "normalized"
    if len(mechanisms) < 3 or warnings:
        status = "partially_normalized"
        if len(mechanisms) < 3:
            warnings.append("Expected 3 mock mechanisms, extracted %s" % len(mechanisms))

    limitations = section_list(sections, "Missing Information And Limitations")
    questions = [item for item in limitations if "Missing" in item]

    return {
        "sample_id": evidence.get("sample_id", ""),
        "normalization": {"status": status, "warnings": warnings},
        "mechanisms": mechanisms,
        "transfer": {
            "learnable": section_list(sections, "Learnable Parts"),
            "not_copyable": section_list(sections, "Not Copyable Parts"),
            "account_fit": [],
            "originality_requirements": section_list(sections, "Not Copyable Parts"),
        },
        "rule_suggestions": section_list(sections, "Rule Direction Suggestions"),
        "asset_suggestions": section_list(sections, "Content Asset Direction Suggestions"),
        "content_opportunities": section_list(sections, "Content Opportunities"),
        "questions": questions,
    }


def failed_analysis(evidence: Dict[str, object], warnings: List[str]) -> Dict[str, object]:
    return {
        "sample_id": evidence.get("sample_id", ""),
        "normalization": {"status": "normalization_failed", "warnings": warnings},
        "mechanisms": [],
        "transfer": {"learnable": [], "not_copyable": [], "account_fit": [], "originality_requirements": []},
        "rule_suggestions": [],
        "asset_suggestions": [],
        "content_opportunities": [],
        "questions": [],
    }


def parse_markdown_sections(markdown: str) -> Dict[str, str]:
    sections = {}
    current = None
    lines = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(lines).strip()
            current = line[3:].strip()
            lines = []
        elif current:
            lines.append(line)
    if current:
        sections[current] = "\n".join(lines).strip()
    return sections


def section_list(sections: Dict[str, str], section: str) -> List[str]:
    values = []
    for line in sections.get(section, "").splitlines():
        text = line.strip()
        if text.startswith("- "):
            values.append(text[2:].strip())
    return values


def parse_mechanisms(sections: Dict[str, str], warnings: List[str], raw_analysis_ref_file: str) -> List[Dict[str, object]]:
    mechanisms = []
    inference_text = first_list_item(sections.get("Inferences", ""))
    chunks = sections.get("Content Mechanisms", "").split("### Mechanism ")
    for chunk in chunks[1:]:
        mechanism = parse_mechanism_chunk(chunk, len(mechanisms) + 1, inference_text, raw_analysis_ref_file)
        if mechanism is None:
            warnings.append("Could not parse mechanism chunk")
            continue
        mechanisms.append(mechanism)
    return mechanisms


def parse_mechanism_chunk(chunk: str, index: int, inference_text: str, raw_analysis_ref_file: str) -> Optional[Dict[str, object]]:
    lines = [line.strip() for line in chunk.splitlines() if line.strip()]
    if not lines:
        return None
    heading = lines[0]
    name = heading.split(":", 1)[1].strip() if ":" in heading else heading.strip()
    description = value_after_prefix(lines, "- Description:")
    evidence_ref = value_after_prefix(lines, "- Evidence:")
    confidence = value_after_prefix(lines, "- Confidence:") or "medium"
    alternative = value_after_prefix(lines, "- Alternative explanation:")
    if not name or not description or not evidence_ref:
        return None

    if evidence_ref == "evidence.yaml#facts.title":
        observed_text = "Title: Mock note title"
    elif evidence_ref == "evidence.yaml#facts.body":
        observed_text = "Body summary: Mock note body for downstream evidence normalization."
    else:
        observed_text = "Evidence cited from %s" % evidence_ref

    return {
        "id": "mechanism-%03d" % index,
        "name": name,
        "description": description,
        "problem": "",
        "solution": "",
        "observed_facts": [{"text": observed_text, "evidence_ref": evidence_ref, "source_fragment": evidence_ref}],
        "inferences": [
            {
                "text": inference_text or description,
                "raw_analysis_ref": {"file": raw_analysis_ref_file, "section": "Inferences"},
                "source_fragment": inference_text or description,
            }
        ],
        "pattern": [description],
        "applicable_scope": [],
        "missing_information": [],
        "limitations": [],
        "alternative_explanations": [alternative] if alternative else [],
        "confidence": confidence,
        "source_refs": [raw_analysis_ref_file + "#Content Mechanisms"],
    }


def value_after_prefix(lines: List[str], prefix: str) -> str:
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def first_list_item(section_text: str) -> str:
    for line in section_text.splitlines():
        text = line.strip()
        if text.startswith("- "):
            return text[2:].strip()
    return ""


def validate_analysis(
    analysis: Dict[str, object],
    analysis_path: Path,
    evidence: Dict[str, object],
    expected_raw_analysis_file: str = "raw/hot-learning/analysis.md",
) -> None:
    forbidden = {"approved", "testing", "validated", "decision", "rule_card", "generated_post", "generated_content", "formal_post", "post_draft"}
    for key in forbidden:
        if key in analysis:
            raise AnalysisError("forbidden analysis field: " + key)
    if not analysis_path.is_file():
        raise AnalysisError("analysis.yaml does not exist")
    if analysis.get("sample_id") != evidence.get("sample_id"):
        raise AnalysisError("sample_id mismatch")
    normalization = analysis.get("normalization")
    if not isinstance(normalization, dict):
        raise AnalysisError("normalization is required")
    status = normalization.get("status")
    if status not in ("normalized", "partially_normalized", "normalization_failed"):
        raise AnalysisError("invalid analysis normalization.status: " + str(status))
    if status == "normalization_failed":
        raise AnalysisError("normalization_failed cannot advance")
    mechanisms = analysis.get("mechanisms")
    if not isinstance(mechanisms, list) or not mechanisms:
        raise AnalysisError("mechanisms must be a non-empty list")
    for mechanism in mechanisms:
        validate_mechanism(mechanism, evidence, expected_raw_analysis_file)
    if not isinstance(analysis.get("rule_suggestions"), list):
        raise AnalysisError("rule_suggestions must be a list")
    if not isinstance(analysis.get("asset_suggestions"), list):
        raise AnalysisError("asset_suggestions must be a list")


def validate_mechanism(
    mechanism: Dict[str, object],
    evidence: Dict[str, object],
    expected_raw_analysis_file: str,
) -> None:
    if not mechanism.get("name"):
        raise AnalysisError("mechanism name is required")
    if mechanism.get("confidence") not in ("low", "medium", "high"):
        raise AnalysisError("invalid confidence: " + str(mechanism.get("confidence")))
    observed = mechanism.get("observed_facts")
    if not isinstance(observed, list) or not observed:
        raise AnalysisError("mechanism must include an observed fact")
    for fact in observed:
        text = str(fact.get("text", ""))
        if text.strip() in {"内容很好", "值得学习", "很有价值", "容易爆", "用户喜欢"}:
            raise AnalysisError("generic observed fact is not allowed: " + text)
        evidence_ref = fact.get("evidence_ref")
        if not evidence_ref or not evidence_ref_exists(str(evidence_ref), evidence):
            raise AnalysisError("invalid evidence_ref: " + str(evidence_ref))
    for inference in mechanism.get("inferences") or []:
        ref_data = inference.get("raw_analysis_ref")
        if not isinstance(ref_data, dict) or ref_data.get("file") != expected_raw_analysis_file:
            raise AnalysisError("inference must reference raw analysis markdown")


def validate_markdown_evidence_refs(markdown: str, evidence: Dict[str, object]) -> None:
    for token in markdown.replace("\n", " ").split():
        if token.startswith("evidence.yaml#"):
            cleaned = token.rstrip(".,;)")
            if not evidence_ref_exists(cleaned, evidence):
                raise AnalysisError("invalid evidence_ref: " + cleaned)


def evidence_ref_exists(evidence_ref: str, evidence: Dict[str, object]) -> bool:
    prefix = "evidence.yaml#"
    if not evidence_ref.startswith(prefix):
        return False
    current = evidence
    for part in evidence_ref[len(prefix):].split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True
