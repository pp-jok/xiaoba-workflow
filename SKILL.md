# Xiaoba Workflow

Use this Skill when the user asks to use Xiaoba or 小八 to learn from Xiaohongshu content, batch-learn benchmark content, generate a Xiaohongshu post, or review a published note.

## Default Behavior

1. Prefer calling the Xiaoba CLI or application API instead of manually reproducing workflow logic.
2. Start with:

```bash
xiaoba-workflow start
```

or, inside a source checkout:

```bash
python3 -m xiaoba_workflow start
```

3. Let Xiaoba resolve and bootstrap the user workspace automatically.
4. Do not require the user to enter the Skill install directory.
5. Do not require the user to run `validate-project`, `setup`, or `doctor` before starting.

## User Requests

When the user says “用小八学习这个链接”:

1. Run Xiaoba start/bootstrap.
2. Check whether Lingzao is configured through Xiaoba's own capability summary.
3. If Lingzao is unavailable, ask the user whether to configure Lingzao, paste content manually, run demo, or cancel.
4. If the user chooses demo, make it clear that the result is an演示结果 and not real collection.
5. Create or resume a Xiaoba task through the CLI/application service.
6. Run until a human gate, blocked state, or completion.
7. Ask one user decision at a time.
8. Pass the decision back through Xiaoba commands or runtime APIs.
9. Return the user-facing summary.

## Execution Contract

1. When the user asks Xiaoba to learn a link, call Xiaoba first.
2. Use the user workspace resolved by Xiaoba.
3. Let Xiaoba bootstrap automatically.
4. Do not ask the user to enter the Skill install directory.
5. Do not require `validate-project`, `setup`, or `doctor` before normal use.
6. If Lingzao is not configured, offer manual content input, configuration, demo, or cancel.
7. Mark demo output clearly as demo.
8. Stop at every human gate and ask the user for the required decision.
9. Do not auto-publish.
10. Do not auto-activate long-term Personal Content rules.
11. Do not directly edit task state files.
12. Do not bypass Xiaoba runtime/application APIs.
13. When resuming, prefer continuing an existing unfinished task.
14. Show technical details only when the user asks for them.

## Boundaries

- Do not bypass Xiaoba's state machine.
- Do not directly edit `state.yaml` to skip a gate.
- Do not auto-confirm paid or credit-consuming calls.
- Do not auto-publish Xiaohongshu content.
- Do not auto-activate Personal Content long-term rules.
- Do not present demo or mock output as real collection.
- Do not expose provider, runner, contract, manifest, raw paths, or internal stage IDs unless the user asks for technical details.
- Do not write API Key, Cookie, Token, or Authorization headers to files.

## Failure Recovery

If a task is blocked, show the user the Xiaoba recovery choices:

1. retry current stage;
2. skip optional operation when safe;
3. provide manual content;
4. show technical details;
5. pause.

Use Xiaoba recovery functions or CLI commands; do not manually modify state files.
