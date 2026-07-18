# Contributing

This project is a lightweight local workflow orchestrator. Keep changes small, tested, and explicit about provider boundaries.

## Development

```bash
python3 -m pip install -e ".[test]"
python3 -m unittest discover -v
PYTHONPYCACHEPREFIX=/tmp/xiaoba-pycache python3 -m compileall xiaoba_workflow scripts tests
python3 -m xiaoba_workflow validate-project
```

## Boundaries

- Do not commit API keys, cookies, browser profiles, or task runtime data.
- Do not vendor Lingzao, Hot Learning, or Personal Content into this repository.
- Do not add databases, web frameworks, queues, or a general workflow engine.
- Do not make `learning` automatically trigger `generation`.
- Do not auto-publish or auto-activate long-term rules.

## Tests

Use `unittest` for repository tests. For behavior changes, add a failing test first, then implement the minimal code needed to pass.
