# Codex Handoff

## Current Status

This repository contains the lightweight Xiaoba workflow orchestrator.

Implemented and verified:

- Mock `learning` end-to-end flow.
- Mock `learning_batch` end-to-end flow.
- Mock `generation` flow with explicit learning-source attachment, topic selection, content generation, review, request changes, and approval.
- Lingzao real-provider runner contract scaffolding.
- Mock E2E acceptance report: `MOCK_E2E_ACCEPTANCE_REPORT.md`.

Latest local verification before handoff:

```bash
python3 -m unittest discover -v
PYTHONPYCACHEPREFIX=/tmp/xiaoba-pycache python3 -m compileall xiaoba_workflow scripts tests
python3 -m xiaoba_workflow validate-project
```

Expected result: all pass.

## Important Boundaries

- Do not commit API keys, cookies, browser profiles, or tokens.
- Do not run real Lingzao, Hot Learning, or Personal Content unless the user explicitly provides credentials and approves the scope.
- Mock provider is the default.
- `learning` must not automatically trigger `generation`.
- External Skill output must be saved to `raw/` before local normalization.
- Personal Content remains the future authority for long-term mechanism/rule/asset state.

## Next Recommended Work

1. Configure and validate real Lingzao:

```bash
export LINGZAO_API_KEY="..."
export LINGZAO_BASE_URL="..."
export XIAOBA_LINGZAO_PROVIDER=real
export XIAOBA_LINGZAO_COMMAND='["python3", "scripts/lingzao_runner.py"]'
export LINGZAO_CLIENT_PATH="/absolute/path/to/lingzao-skill-main/scripts/lingzao_client.py"
python3 -m xiaoba_workflow doctor --skill lingzao
```

2. If doctor passes, run one public non-sensitive `collect_note` test through:

```text
task_intake
→ evidence_collection
→ evidence_normalization
```

Stop when the task reaches `analysis`; do not run Hot Learning or Personal Content real providers.

3. Add regression tests for any adapter fixes discovered during real validation.

## Useful CLI

```bash
python3 -m xiaoba_workflow --help
python3 -m xiaoba_workflow validate-project
python3 -m xiaoba_workflow doctor --skill lingzao
python3 -m xiaoba_workflow create-task --type learning --source-url "https://example.com/note/1"
python3 -m xiaoba_workflow run tasks/<task-id>
python3 -m xiaoba_workflow task-status tasks/<task-id>
```
