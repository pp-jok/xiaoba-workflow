# Changelog

## 0.2.0 - 2026-07-18

- Added Hot Learning runner contract 1.0 with mock, codex_manual, and external provider modes.
- Added Lingzao runner capability declarations for comments and transcript collection, with video file marked unsupported.
- Added Generation Provider contract scaffolding and external fake-provider topic generation support.
- Added Lingzao real-mode external cost confirmation for comments/transcript collection, multi-invocation raw preservation, and internal raw merge.
- Added external `generate_content` contract support for generation content revisions after `request_changes`.
- Added user-facing CLI presentation, `doctor --all`, `run-until-gate`, and `start`.
- Added feedback governance candidates from generation `request_changes`; candidates are not auto-activated.
- Added `post_publish_review` task skeleton for review-only post-publish analysis.
- Added local config example and open-source project infrastructure.

## 0.1.0

- Initial lightweight workflow orchestrator.
- Mock single learning loop.
- Mock batch learning loop.
- Lingzao runner contract for note/profile/posted-note collection.
- Prompt-driven Hot Learning normalization.
- Personal Content mechanism intake and governance handoff.
- Generation context, topic selection, draft generation, and review gates.
