# Mock E2E Acceptance Report

## 1. Environment

- Python: 3.9.6
- Project path: `/Users/lht/纷乱的想法/codex主目录/工作流DEV`
- Provider configuration: Lingzao mock, Hot Learning mock, Personal Content mock
- Network / real Skill use: no real Skill was called, no network access was used, no API key was configured, and no publishing action was attempted.

## 2. Test Tasks

| Task ID | Type | Path | Source / brief | Final status | Run count | Human operations |
| --- | --- | --- | --- | --- | --- | --- |
| `task-20260716-154508-902185-learning` | `learning` | `tasks/task-20260716-154508-902185-learning` | `https://example.com/mock-e2e-acceptance/note-001` | `completed / completed` | 7 | none |
| `task-20260716-154824-742072-learning-batch` | `learning_batch` | `tasks/task-20260716-154824-742072-learning-batch` | `https://example.com/mock-e2e-acceptance/account-001` | `completed / completed` | 16 total including intake/screening; 14 after sample selection | `select-samples sample-001 sample-003 sample-005` |
| `task-20260716-155248-641568-generation` | `generation` | `tasks/task-20260716-155248-641568-generation` | `mock-e2e-acceptance：为包子 IP 生成一篇面向独立开发者的小红书内容` | `completed / completed` | 5 | `attach-learning` x2, `select-topic topic-003`, `review-content request_changes`, `review-content approve` |

Additional diagnostic tasks retained for inspection:

- `task-20260716-155052-524709-generation`: parallel attach diagnostic; stopped at `topic_selection`.
- `task-20260716-160052-762571-generation`: generation brief bypass diagnostic; currently `running / topic_generation`.
- `task-20260716-160226-011974-generation`: normal generation brief gate diagnostic; currently `running / context_assembly`.
- `task-20260716-160333-081367-learning`: mock Lingzao failure diagnostic; blocked at `evidence_collection`.
- `task-20260716-160420-249067-generation`: request_changes missing feedback diagnostic; waiting at `review`.
- `task-20260716-160522-522550-learning`: incomplete raw diagnostic; blocked at `evidence_normalization`.

## 3. Stage Results

### learning: PASS

Observed stage sequence:

```text
task_intake
→ evidence_collection
→ evidence_normalization
→ analysis
→ analysis_normalization
→ mechanism_intake
→ aggregation
→ completed
```

Key checks:

- `raw/lingzao/note-detail.json`: present
- `raw/lingzao/invocation.json`: present
- `evidence/evidence.yaml`: present and Evidence Validator passed
- `raw/hot-learning/analysis.md`: present
- `raw/hot-learning/invocation.json`: present
- `analysis/analysis.yaml`: present and Analysis Validator passed
- `raw/personal-content/mechanism-intake-request.json`: present
- `raw/personal-content/mechanism-intake-response.json`: present
- `analysis/mechanism-intake-result.json`: present
- `analysis/learning-summary.yaml`: present and Learning Summary Validator passed
- Summary mechanism count: 3
- Mechanism intake statuses: imported 2, limited 1, matched_existing 0, rejected 0, failed 0
- Completed task re-run: rejected with `Task is completed and cannot run`
- Forbidden directories: no `mechanisms/`, `rules/`, `assets/`, or `profiles/`
- Generated content / publishing artifacts: none

### learning_batch: PASS

Observed stage sequence:

```text
task_intake
→ benchmark_screening
→ sample_selection
→ evidence_collection
→ evidence_normalization
→ analysis
→ analysis_normalization
→ cross_sample_aggregation
→ mechanism_intake
→ completed
```

Sample selection:

- Candidate count: 5
- Selected sample IDs: `sample-001`, `sample-003`, `sample-005`
- `advance` at `sample_selection`: rejected
- `resume` at `sample_selection`: rejected with `sample_selection requires select-samples`

Single-run granularity:

- `evidence_collection`: succeeded counts progressed 1 → 2 → 3, one sample per run.
- `evidence_normalization`: partially_normalized counts progressed 1 → 2 → 3, one sample per run.
- `analysis`: succeeded counts progressed 1 → 2 → 3, one sample per run.
- `analysis_normalization`: normalized counts progressed 1 → 2 → 3, one sample per run.

Key task-level artifacts:

- `analysis/selected-samples.json`
- `analysis/batch-evidence-progress.json`
- `analysis/batch-evidence-normalization-progress.json`
- `evidence/batch-evidence-index.json`
- `analysis/batch-analysis-progress.json`
- `analysis/batch-analysis-normalization-progress.json`
- `analysis/batch-analysis-index.json`
- `raw/hot-learning/cross-sample-analysis.md`
- `analysis/cross-sample-analysis.yaml`
- `raw/personal-content/batch-mechanism-intake-request.json`
- `raw/personal-content/batch-mechanism-intake-response.json`
- `analysis/batch-mechanism-intake-result.json`
- `analysis/batch-learning-summary.yaml`

Per-selected-sample artifacts were present for all selected samples:

- `raw/lingzao/samples/<sample-id>/note-detail.json`
- `raw/lingzao/samples/<sample-id>/invocation.json`
- `evidence/samples/<sample-id>/evidence.yaml`
- `raw/hot-learning/samples/<sample-id>/analysis.md`
- `raw/hot-learning/samples/<sample-id>/invocation.json`
- `analysis/samples/<sample-id>/analysis.yaml`

Cross-sample boundary checks:

- Cross-sample candidate count: 3
- Unmatched mechanism count: 0
- Counter evidence / differences retained: yes
- Batch mechanism intake statuses: `limited`, `limited`, `limited`
- Forbidden directories: no `mechanisms/`, `rules/`, `assets/`, or `profiles/`
- Generation / publishing artifacts: none

### generation: PASS

Observed stage sequence:

```text
task_intake
→ context_assembly
→ topic_generation
→ topic_selection
→ content_generation
→ review
→ content_generation
→ review
→ completed
```

Learning source attachment:

- Attached sources: 2
- Source tasks: `task-20260716-154508-902185-learning`, `task-20260716-154824-742072-learning-batch`
- Source task files were not modified by generation acceptance operations.

Topic selection:

- Topic candidates: `topic-001`, `topic-002`, `topic-003`, `topic-004`, `topic-005`
- Selected: `topic-003`
- `advance` at `topic_selection`: rejected
- `resume` at `topic_selection`: rejected with `topic_selection requires select-topic`

Content review and revision:

- First content generation entered `waiting_for_user / review`
- `request_changes` returned to `content_generation`
- `revision-001` content package retained
- Review feedback retained
- Second content generation produced `revision-002`
- Second generation request contained revision number, previous content ref, and latest feedback
- Final `approve` completed the task

Key artifacts:

- `content/generation-brief.json`
- `content/context-sources.json`
- `raw/personal-content/generation-context-request.json`
- `raw/personal-content/generation-context-response.json`
- `content/generation-context.yaml`
- `raw/personal-content/topic-generation-response.json`
- `content/topic-candidates.json`
- `content/selected-topic.json`
- `raw/personal-content/content-generation-request.json`
- `raw/personal-content/content-generation-response.json`
- `content/content-package.yaml`
- `content/content-revisions.json`
- `content/revisions/revision-001/content-package.yaml`
- `content/revisions/revision-001/review-decision.json`
- `content/revisions/revision-002/content-package.yaml`
- `content/review-decision.json`

Generation boundaries:

- Image files: none
- Video files: none
- Publish request / upload result / published status: none
- Platform token / Authorization / Cookie text: none found in generation task files
- Formal mechanism/rule/asset/profile directories: none

## 4. Human Gates

| Gate | Result |
| --- | --- |
| `sample_selection` | PASS: `advance` and `resume` rejected; `select-samples` required |
| `topic_selection` | PASS: `advance` and `resume` rejected; `select-topic` required |
| `review` | PASS: `advance` and `resume` rejected; `review-content` required |
| request changes revision | PASS: `request_changes` required feedback, preserved revision-001, generated revision-002 |
| `generation_brief` normal waiting path | PASS: running `context_assembly` without brief set task to `waiting_for_user`; `advance` and `resume` then rejected; `set-generation-brief` restored running state |
| `generation_brief` pre-waiting bypass | RESOLVED in stage 21.1: while `context_assembly` is `running`, `advance` is now rejected and state remains unchanged |

## 5. Key Artifacts

Learning:

- `tasks/task-20260716-154508-902185-learning/evidence/evidence.yaml`
- `tasks/task-20260716-154508-902185-learning/analysis/analysis.yaml`
- `tasks/task-20260716-154508-902185-learning/analysis/learning-summary.yaml`

Learning batch:

- `tasks/task-20260716-154824-742072-learning-batch/evidence/batch-evidence-index.json`
- `tasks/task-20260716-154824-742072-learning-batch/analysis/batch-analysis-index.json`
- `tasks/task-20260716-154824-742072-learning-batch/analysis/cross-sample-analysis.yaml`
- `tasks/task-20260716-154824-742072-learning-batch/analysis/batch-learning-summary.yaml`

Generation:

- `tasks/task-20260716-155248-641568-generation/content/generation-context.yaml`
- `tasks/task-20260716-155248-641568-generation/content/topic-candidates.json`
- `tasks/task-20260716-155248-641568-generation/content/revisions/revision-001/content-package.yaml`
- `tasks/task-20260716-155248-641568-generation/content/revisions/revision-002/content-package.yaml`
- `tasks/task-20260716-155248-641568-generation/content/content-package.yaml`

## 6. Failure Scenarios

| Scenario | Trigger | Result |
| --- | --- | --- |
| Mock Lingzao failure | `learning` source `mock-fail://mock-e2e-acceptance/lingzao-failure` | PASS: task blocked at `evidence_collection`; reason included `execution_error: Mock Lingzao failure requested` |
| Unknown topic ID | `select-topic --id topic-does-not-exist` | PASS: rejected with `unknown topic id` |
| `request_changes` without feedback | `review-content --decision request_changes` | PASS: rejected with `feedback is required for request_changes` |
| Completed task re-run | `run` on completed learning task | PASS: rejected with `Task is completed and cannot run` |
| Incomplete raw artifact group | Removed `raw/lingzao/invocation.json` from an isolated learning failure task | PASS: task blocked at `evidence_normalization`; no silent rebuild |

## 7. Boundary Checks

- Real Skill calls: none
- Network access: none
- API Key / token configuration: none
- Publishing: none
- Formal long-term objects in main project: none
- Personal Content real workspace modification: none
- Learning source tasks modified by generation: no intentional modification observed
- Credential leakage: no API Key, Authorization header, Cookie, browser credential, platform token, or publish credential found in inspected task artifacts

## 8. Issues

### major

#### generation brief can be bypassed by `advance` before entering waiting state

- Reproduction:
  1. `python3 -m xiaoba_workflow create-task --type generation`
  2. `python3 -m xiaoba_workflow run tasks/<task-id>`
  3. `python3 -m xiaoba_workflow advance tasks/<task-id>`
- Actual result: task advanced from `context_assembly` to `topic_generation` without `content/generation-brief.json`.
- Expected result: missing brief should require `set-generation-brief`; `advance` should not bypass this gate.
- Involved files: state machine behavior in `xiaoba_workflow/runtime.py`.
- Suggested immediate fix: yes, because it violates the explicit human gate acceptance requirement.
- Status: resolved in stage 21.1.
- Fix files: `xiaoba_workflow/runtime.py`, `tests/test_generation_flow.py`, `tests/test_state_machine.py`.
- Root cause: generic `advance_task` allowed direct state transition for any `running` non-terminal stage, including stages whose business executor must validate prerequisites.
- Fix: added a centralized protected-stage rule for manual `advance`; executors still call `move_to_next_stage` internally after successful validation.
- Protected stages:
  - `generation:context_assembly`
  - `generation:topic_selection`
  - `generation:review`
  - `learning_batch:sample_selection`
- Regression result:
  - No brief generation at `running/context_assembly`: `advance` rejected with `Stage context_assembly must be executed with run; it cannot be advanced manually.`
  - Running `context_assembly` without brief enters `waiting_for_user`.
  - `advance` and `resume` while waiting are rejected.
  - `set-generation-brief` restores `running/context_assembly`.
  - `run` then generates `content/generation-context.yaml` and advances to `topic_generation`.
  - Generation task with an existing brief also cannot use generic `advance` to skip `context_assembly`; `run` works normally.

### usability

#### concurrent `attach-learning` calls can lose one source

- Reproduction:
  1. Create a generation task.
  2. Run two `attach-learning` commands concurrently against the same generation task.
- Actual result: one run produced `content/context-sources.json` containing only one attached source.
- Expected result: concurrent writes should either serialize, reject stale writes, or preserve both sources.
- Involved files: `xiaoba_workflow/runtime.py` context source write path.
- Suggested immediate fix: not required for sequential CLI usage, but useful before concurrent automation.

## 9. Acceptance Conclusion

PASS WITH MINOR ISSUES

The three main Mock workflows completed end to end, failure sampling behaved correctly, and the `generation_brief` gate bypass found during stage 21 is resolved. The remaining issue is usability-level: concurrent `attach-learning` calls can race and lose one source, but sequential CLI usage works and was used for successful generation acceptance.

## 10. Stage 21.1 Verification Addendum

- CLI regression task: `tasks/task-20260716-164457-469274-generation`
- Full generation regression task: `tasks/task-20260716-164619-248909-generation`
- Other same-class gate review:
  - `sample_selection`: protected by generic waiting-state rejection and `resume` requires `select-samples`.
  - `topic_selection`: protected by generic waiting-state rejection and `resume` requires `select-topic`.
  - `review`: protected by generic waiting-state rejection and `resume` requires `review-content`.
  - `context_assembly`: now protected even before entering `waiting_for_user`.
- Unit regression:
  - `tests.test_generation_flow`: passed.
  - `tests.test_state_machine`: passed.
