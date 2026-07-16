# Codex Learning Guide

This file is for a new Codex instance that needs to understand the project before continuing real Skill installation and validation.

## 1. Project Purpose

This repository is a lightweight local workflow orchestrator for Xiaoba content learning and generation.

It coordinates three task types:

- `learning`: learn from one public note and produce a local learning summary.
- `learning_batch`: learn from multiple selected samples from one benchmark account.
- `generation`: generate a reviewable content package from explicitly attached completed learning tasks.

The project is intentionally not a database, web app, queue, or general workflow engine.

## 2. Core Boundaries

Keep these constraints intact:

- `learning` must not automatically trigger `generation`.
- External Skill output must be saved under `raw/` first.
- Local Normalizers convert raw output into intermediate objects.
- Normalizers must not invent professional conclusions or fill missing facts with fake values.
- Missing numeric metrics must stay `null`, not `0`.
- Personal Content is the future authority for long-term mechanisms, rules, assets, and profiles.
- This repository must not store API keys, cookies, browser profiles, platform tokens, or real private content.
- Do not publish content from this tool.

## 3. Important Files

- `README.md`: CLI overview and provider configuration.
- `CODEX_HANDOFF.md`: current handoff status and next recommended work.
- `MOCK_E2E_ACCEPTANCE_REPORT.md`: latest Mock E2E acceptance results.
- `IMPLEMENTATION_PLAN.md`: original staged implementation plan.
- `workflow.yaml`: workflow stage configuration.
- `xiaoba_workflow/runtime.py`: state machine and stage execution entry points.
- `xiaoba_workflow/lingzao.py`: Lingzao mock/real provider adapter and runner contract validation.
- `scripts/lingzao_runner.py`: thin bridge from this repo's runner contract to the real Lingzao CLI.
- `tests/test_lingzao_provider.py`: fake runner tests for Lingzao real-provider infrastructure.
- `tests/test_generation_flow.py`: generation flow and gate tests.

## 4. Current Verified State

Mock flows are implemented and tested:

- Mock `learning` end to end.
- Mock `learning_batch` end to end.
- Mock `generation` end to end.
- Human gates for sample selection, topic selection, review, and generation brief.
- Lingzao real-provider contract scaffolding.

Latest known verification:

```bash
python3 -m unittest discover -v
PYTHONPYCACHEPREFIX=/tmp/xiaoba-pycache python3 -m compileall xiaoba_workflow scripts tests
python3 -m xiaoba_workflow validate-project
```

Expected:

```text
unittest: OK
compileall: OK
validate-project: Project baseline is valid.
```

## 5. Provider Modes

Default provider mode is Mock.

```bash
python3 -m xiaoba_workflow doctor --skill lingzao
```

Expected default output:

```text
provider: mock
prompt: ok
```

Real Lingzao mode requires explicit environment configuration and must not be guessed:

```bash
export XIAOBA_LINGZAO_PROVIDER=real
export XIAOBA_LINGZAO_COMMAND='["python3", "scripts/lingzao_runner.py"]'
export LINGZAO_CLIENT_PATH="20 20 12 61 79 80 81 98 701 33 100 204 250 395 398 399 400pwd)/lingzao/scripts/lingzao_client.py"
export LINGZAO_API_KEY="..."
export LINGZAO_BASE_URL="..."
python3 -m xiaoba_workflow doctor --skill lingzao
```

Do not write these values into repository files.

## 6. Lingzao Runner Contract

Contract version: `1.0`.

The real provider calls a runner with:

```bash
runner --input request.json --output /absolute/output-dir
runner --capabilities
```

Supported operations:

- `collect_note`
- `collect_profile`
- `collect_posted_notes`

Runner output must include:

- `result.json`
- `runner-manifest.json`

The provider validates:

- `contract_version`
- operation
- source URL
- manifest status
- output completeness

External raw is preserved under `raw/lingzao/external/`. Internal raw remains compatible with current Normalizers:

- `raw/lingzao/note-detail.json`
- `raw/lingzao/profile.json`
- `raw/lingzao/posted-notes.json`
- `raw/lingzao/invocation.json`

## 7. Safe Real Validation Scope

The next Codex should validate only this minimal Lingzao real path first:

```text
task_intake
→ evidence_collection
→ evidence_normalization
→ stop at analysis
```

Do not run:

- Hot Learning real provider.
- Personal Content real provider.
- mechanism intake against a real external workspace.
- generation publishing or platform upload.

Use only a public, non-sensitive, non-production test note URL.

## 8. What To Do If Real Lingzao Fails

If doctor fails:

- Stop.
- Report missing config, missing API key, invalid base URL, missing client, or unsupported operation.
- Do not run real collection.

If collection fails:

- Check `state.yaml` for the blocked reason.
- Check `raw/lingzao/execution-stderr.log` only for non-secret diagnostics.
- Confirm no token/cookie/header was written to task artifacts.
- Add or update a regression test before changing adapter code.

## 9. Common Commands

Create and run a Mock learning task:

```bash
python3 -m xiaoba_workflow create-task --type learning --source-url "https://example.com/note/1"
python3 -m xiaoba_workflow run tasks/<task-id>
python3 -m xiaoba_workflow task-status tasks/<task-id>
```

Create a generation task:

```bash
python3 -m xiaoba_workflow create-task --type generation --brief "Generate a reviewable XHS content package"
python3 -m xiaoba_workflow attach-learning tasks/<generation-task> --task tasks/<completed-learning-task>
python3 -m xiaoba_workflow run tasks/<generation-task>
python3 -m xiaoba_workflow select-topic tasks/<generation-task> --id topic-001
python3 -m xiaoba_workflow review-content tasks/<generation-task> --decision approve
```

## 10. Known Remaining Issue

`MOCK_E2E_ACCEPTANCE_REPORT.md` records one remaining usability issue:

- Concurrent `attach-learning` calls can race and lose one source.

Sequential CLI use works and is the expected current usage.

