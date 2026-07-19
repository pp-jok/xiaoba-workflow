# Changelog

## 1.0.0 - 2026-07-19

- Added productized Xiaoba workspace bootstrap under `~/.xiaoba-workflow/`, with `XIAOBA_WORKSPACE` and `start --workspace` overrides.
- Changed the default CLI behavior so `xiaoba-workflow` without a subcommand enters `start`.
- Added safe first-run defaults: Lingzao and Personal Content start as `unavailable`; Hot Learning and generation start as `codex_manual`.
- Added packaged runtime assets so installed wheels can start from arbitrary directories without requiring users to enter the source checkout or Skill install directory.
- Added user-facing home screen for new tasks, continuing unfinished tasks, viewing recent results, configuration, and system status.
- Added explicit demo/manual mode separation for learning tasks when Lingzao is not configured.
- Added manual content input as a formal fallback for single-note learning.
- Added user-facing blocked recovery prompts and audit entries for retry/skip/manual recovery choices.
- Added `configure`, `status`, `list-tasks`, and `show-result` CLI commands while keeping technical commands for development and CI.
- Added Codex Skill usage guidance and v1 release documentation.
- Tightened final release boundaries so `codex_manual` does not silently produce Hot Learning mock analysis for non-demo user tasks.
- Generation now blocks clearly when Personal Content is not configured instead of producing fake topics or content.
- Unified ordinary CLI workspace behavior for installed usage while preserving source-checkout technical compatibility.

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
