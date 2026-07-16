# Prompt For Next Codex: Install, Configure, And Test Real Lingzao

Copy the prompt below into a new Codex task after cloning this repository.

---

You are continuing work on the Xiaoba workflow repository.

Your goal is to install/configure real Lingzao locally if available, then validate the minimal real `collect_note` path. Do not expand scope.

## Required Reading

Read these files first:

1. `AGENTS.md`
2. `README.md`
3. `CODEX_HANDOFF.md`
4. `docs/CODEX_LEARNING_GUIDE.md`
5. `MOCK_E2E_ACCEPTANCE_REPORT.md`
6. `workflow.yaml`
7. `xiaoba_workflow/lingzao.py`
8. `scripts/lingzao_runner.py`
9. `tests/test_lingzao_provider.py`

## Hard Boundaries

Do not:

- Commit API keys, cookies, tokens, browser profiles, or private content.
- Guess a Lingzao command if it cannot be found.
- Download or install anything without explicit user approval.
- Run Hot Learning real provider.
- Run Personal Content real provider.
- Publish content.
- Modify workflow scope.
- Change Evidence schema to hide adapter bugs.

## Step 1: Baseline Checks

Run:

```bash
python3 -m unittest tests.test_lingzao_provider -v
python3 -m xiaoba_workflow validate-project
python3 -m xiaoba_workflow doctor --skill lingzao
```

Expected default doctor:

```text
provider: mock
prompt: ok
```

If baseline fails, fix baseline first with focused tests.

## Step 2: Locate Lingzao

Check, in order:

1. User-provided local Lingzao path.
2. `LINGZAO_CLIENT_PATH`.
3. `LINGZAO_SKILL_ROOT`.
4. Existing local directories that clearly contain Lingzao, such as `lingzao-skill-main`.

Do not download or install Lingzao unless the user explicitly asks and approves.

The expected real Lingzao CLI file is usually:

```text
scripts/lingzao_client.py
```

Confirm by reading the actual local files, not by guessing.

## Step 3: Configure Real Doctor

Ask the user to provide credentials through environment variables or an existing local config:

```bash
export LINGZAO_API_KEY="..."
export LINGZAO_BASE_URL="..."
```

or:

```text
~/.lingzao/config.json
```

Never write credentials into repository files.

Run:

```bash
XIAOBA_LINGZAO_PROVIDER=real \
XIAOBA_LINGZAO_COMMAND='["python3", "scripts/lingzao_runner.py"]' \
LINGZAO_CLIENT_PATH="/absolute/path/to/lingzao-skill-main/scripts/lingzao_client.py" \
python3 -m xiaoba_workflow doctor --skill lingzao
```

Doctor must confirm:

- provider is real
- contract version is `1.0`
- operations include `collect_note`, `collect_profile`, `collect_posted_notes`
- runner exists
- Lingzao client exists
- auth/config is ready
- no secret values are printed

If doctor fails, stop. Do not run collection.

## Step 4: Minimal Real Collection

Only if doctor passes, create a new isolated test task using a public, non-sensitive note URL:

```bash
python3 -m xiaoba_workflow create-task \
  --type learning \
  --source-url "<public-test-note-url>"
```

Run only:

```text
task_intake
→ evidence_collection
→ evidence_normalization
```

Use:

```bash
python3 -m xiaoba_workflow run tasks/<task-id>
python3 -m xiaoba_workflow task-status tasks/<task-id>
```

Stop when the task reaches:

```text
status: running
current_stage: analysis
```

Do not run analysis.

## Step 5: Validate Raw Outputs

Confirm these files exist:

```text
raw/lingzao/external/result.json
raw/lingzao/external/runner-manifest.json
raw/lingzao/note-detail.json
raw/lingzao/invocation.json
evidence/evidence.yaml
```

Check:

- operation is `collect_note`
- source URL matches the request
- contract version is `1.0`
- manifest status is `succeeded`
- missing values are `null`, not fabricated `0`
- external raw is preserved
- internal raw can be read by the existing Evidence Normalizer

## Step 6: Validate Evidence

Verify:

- Evidence Validator passes.
- source URL is correct.
- title/body/author/published_at map from real raw.
- metrics missing values stay `null`.
- comments and transcript coverage reflect real returned data.
- source refs point to internal raw files.
- no body, comments, transcript, metrics, or author values were invented.

If real Lingzao return shape differs from adapter assumptions:

1. Add a focused regression test in `tests/test_lingzao_provider.py`.
2. Make the smallest adapter fix in `xiaoba_workflow/lingzao.py` or `scripts/lingzao_runner.py`.
3. Re-run targeted and full tests.

Do not change the Evidence standard just to make bad mapping pass.

## Step 7: Safe Failure Scenario

Validate one safe failure path, preferably doctor with a deliberately invalid temporary credential in the environment, or a clearly unsupported URL if it will not consume credits.

Confirm:

- error is classified
- task does not advance
- task is blocked if collection was attempted
- no complete success raw group is left
- no secret appears in logs

Do not run many failing requests.

## Step 8: Secret Check

Inspect these files for accidental secret leakage:

```text
raw/lingzao/invocation.json
raw/lingzao/execution-stdout.log
raw/lingzao/execution-stderr.log
raw/lingzao/external/result.json
raw/lingzao/external/runner-manifest.json
```

Confirm absent:

- API key
- Authorization header
- Cookie
- browser credentials
- full local config content

## Step 9: Required Final Verification

Run:

```bash
python3 -m unittest tests.test_lingzao_provider -v
python3 -m unittest discover -v
PYTHONPYCACHEPREFIX=/tmp/xiaoba-pycache python3 -m compileall xiaoba_workflow scripts tests
python3 -m xiaoba_workflow validate-project
```

## Final Report

Report:

- whether real Lingzao was found
- actual CLI/runner used
- doctor result
- whether real `collect_note` ran
- public test URL used
- exit code
- external raw generated
- internal raw adapted
- Evidence Normalizer result
- Evidence Validator result
- fields present in real return
- fields missing in real return
- code changes, if any
- secret check result
- failure scenario result
- full test result

Only say:

```text
Lingzao collect_note real minimal loop is verified
```

if real collection and Evidence Validator both passed.

Mark `collect_profile` and `collect_posted_notes` as unverified unless you actually ran them.

---
