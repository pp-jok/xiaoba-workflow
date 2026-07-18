# Changelog

## 0.2.1 - 2026-07-18

- Added UX Lite interactive `start` flow that shows only four user-facing task entries and automatically runs to the next human gate, blocked state, or completion.
- Added `setup` for conservative local configuration generation without writing secrets.
- Simplified default user progress for learning, learning_batch, generation, and post_publish_review while preserving `--technical` views for internal state and artifacts.
- Updated default local learning policy to `collect_comments: never`, `collect_transcript: ask`, and `allow_auto_paid_calls: false`.
- Added user-facing gate prompts for cost confirmation, sample selection, topic selection, content review, and generation brief collection.
- Added completion summaries for learning, generation, and post_publish_review.
- Kept all existing workflow stages, providers, runners, validators, artifacts, and human gates unchanged.

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
