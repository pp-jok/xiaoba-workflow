# v0.2.0 Implementation Report

## 1. 执行摘要

本轮按 `XIAOBA_OPTIMIZATION_EXECUTION_PLAN.md` 对 Xiaoba Workflow 做了一次 v0.2.0 优化实施。重点完成稳定 runner/provider 契约、用户态 CLI、统一诊断、连续执行到 gate、反馈候选治理、发布后复盘骨架、配置体验、开源工程文件和写入锁。

本轮未处理 Personal Content 用户画像读取，未自动创建画像，未实现自动发布，也未把 Lingzao、Hot Learning、Personal Content 目录纳入仓库。

## 2. 实际完成的阶段

- 阶段 24：Hot Learning Runner contract 1.0，支持 `analyze_single` / `analyze_cross_sample`。
- 阶段 25：Lingzao runner capabilities 增加 `collect_comments` / `collect_transcript`，并声明 `video_file` unsupported。
- 阶段 26：Generation Provider contract 基础模块，topic generation 支持 external fake runner。
- 阶段 27：`request_changes` 生成 feedback governance candidate，`confirm-feedback-rule` 记录用户决策。
- 阶段 28：新增 `post_publish_review` 任务骨架，生成复盘建议。
- 阶段 29：新增用户态 presentation，改造 `task-status`，新增 `start`。
- 阶段 30：新增 `doctor --all` 和 `xiaoba.local.example.yaml`。
- 阶段 31：新增 `run-until-gate`。
- 阶段 32：新增轻量文件锁，覆盖核心 state/JSON 写入。
- 阶段 33：补齐 LICENSE、CHANGELOG、CONTRIBUTING、GitHub CI 和 issue template。
- 阶段 34：收口 Lingzao 真实最小链路和 Generation external content 链路：
  - `learning:evidence_collection` 在 real Lingzao 模式下先采集 note detail，再进入外部额度确认 gate；
  - 用户确认后执行 `collect_comments` / `collect_transcript`，保存多 invocation 索引并合并为内部 raw；
  - 用户跳过后记录可追溯的 skip decision，Evidence coverage 保留缺失原因；
  - `generation:content_generation` 支持 external `generate_content`，覆盖 revision 1、request changes 后 revision 2、approve 闭环。

## 3. 未完成项

- Hot Learning external provider 未真实在线验证，仅 contract/fake verified。
- Lingzao `collect_comments` / `collect_transcript` 已接入任务内 gate、调用、合并和 Evidence 链路，但仍未做真实在线验收。
- Generation external provider 已覆盖 topic 和 content generation fake runner contract；真实在线模型/服务未验收。
- 发布后复盘为基础骨架，未实现真实数据导入表单、截图结构化和规则状态候选确认命令。
- runtime 未做大规模文件拆分，只新增 presentation/config/generation_provider/locks，避免一次性重写状态机。

## 4. 修改文件

- `workflow.yaml`
- `pyproject.toml`
- `.gitignore`
- `.env.example`
- `README.md`
- `USER_MANUAL.md`
- `CAPABILITY_MATRIX.md`
- `FLOW_AUDIT.md`
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- `LICENSE`
- `.github/workflows/ci.yml`
- `.github/ISSUE_TEMPLATE/bug_report.md`
- `xiaoba.local.example.yaml`
- `XIAOBA_OPTIMIZATION_EXECUTION_PLAN.md`
- `V0_2_0_IMPLEMENTATION_REPORT.md`
- `scripts/hot_learning_runner.py`
- `scripts/lingzao_runner.py`
- `xiaoba_workflow/cli.py`
- `xiaoba_workflow/runtime.py`
- `xiaoba_workflow/config.py`
- `xiaoba_workflow/generation.py`
- `xiaoba_workflow/generation_provider.py`
- `xiaoba_workflow/lingzao.py`
- `xiaoba_workflow/locks.py`
- `xiaoba_workflow/personal_content.py`
- `xiaoba_workflow/presentation.py`
- `tests/test_v020_ux_and_contracts.py`

## 5. 新增命令

- `python3 -m xiaoba_workflow doctor --all`
- `python3 -m xiaoba_workflow task-status tasks/<task-id> --technical`
- `python3 -m xiaoba_workflow run-until-gate tasks/<task-id> [--max-steps N] [--technical]`
- `python3 -m xiaoba_workflow start`
- `python3 -m xiaoba_workflow confirm-feedback-rule tasks/<task-id> --candidate-id feedback-rule-001 --decision confirm`
- `python3 -m xiaoba_workflow confirm-external-cost tasks/<task-id> --decision confirm`
- `python3 -m xiaoba_workflow confirm-external-cost tasks/<task-id> --decision skip`

## 6. 新增 Provider

- `xiaoba_workflow/generation_provider.py`
- 支持 provider mode：`mock`、`codex`、`external`
- `external` 使用 JSON request/runner-manifest contract；当前 topic generation 已接入 fake runner 验证。

## 7. Hot Learning Runner

- 文件：`scripts/hot_learning_runner.py`
- contract version：`1.0`
- operations：`analyze_single`、`analyze_cross_sample`
- provider：`mock`、`codex_manual`、`external`
- 输出：`analysis.md`、`runner-manifest.json`

## 8. Lingzao 评论和逐字稿

- runner capabilities 增加：
  - `collect_comments`
  - `collect_transcript`
- `unsupported_outputs` 显示 `video_file`
- real provider 在 `evidence_collection` 中使用两段式执行：
  - 第一次 `run` 采集 `collect_note`，保存 `raw/lingzao/external/` 和内部 `note-detail.json`；
  - 随后停在 `waiting_for_user: external_cost_confirmation`；
  - `confirm-external-cost --decision confirm` 后继续采集 comments/transcript，并更新 `raw/lingzao/invocations/index.json`；
  - `confirm-external-cost --decision skip` 后记录跳过决定，不伪造评论或逐字稿。
- 多 invocation 结果只合并进内部 raw，Normalizer 仍只读取既有内部契约。
- 本地策略支持：
  - `learning.collect_comments: ask|always|never`
  - `learning.collect_transcript: ask|always|never`
  - `learning.allow_auto_paid_calls: false`
  - `learning.transcript_required: false`
- 即使策略为 `always`，默认也会进入确认；只有显式允许自动付费时才会自动调用。
- `transcript_required: true` 时，视频逐字稿失败会阻塞任务；普通 comments/transcript 失败只记录 warning 并继续。

## 9. Generation Provider

- topic generation 可通过 external fake runner contract 输出 `topic-candidates.yaml`。
- content generation 可通过 external fake runner contract 执行 `generate_content`。
- request changes 后第二次 `run` 会带上上一版内容引用和 feedback 引用，生成 `revision-002`。
- `approve` 不发布。

## 10. 用户反馈沉淀

- `review-content --decision request_changes` 写入 `feedback/governance-candidates.yaml`。
- 候选默认 `status: candidate`。
- `auto_activated: false`。
- `confirm-feedback-rule` 只记录用户决策，不自动激活长期规则。

## 11. 发布后复盘

- 新增任务类型：`post_publish_review`
- 产物：`analysis/post-publish-review.yaml`
- 只记录复盘建议和数据不足，不自动修改规则状态。

## 12. 用户态 CLI

- `task-status` 默认展示任务名、阶段名、进度、执行模块和下一步。
- `--technical` 保留原始状态字段。
- `run-until-gate` 每阶段输出当前任务、当前阶段、正在执行、作用和进度。
- `start` 展示四类常用入口。

## 13. Skill 执行提示

当前 presentation 映射覆盖：

- Lingzao：采集公开内容、筛选样本、批量采集；
- Hot Learning：内容机制拆解、跨样本综合；
- Personal Content：机制导入、生成上下文；
- 内容生成 Provider：选题和正文生成。

## 14. `doctor --all`

汇总：

- Xiaoba 核心工作流；
- Lingzao；
- Hot Learning；
- Personal Content；
- 内容生成 Provider；
- 自动发布。

doctor 不执行真实采集，不消耗额度。

## 15. `run-until-gate`

执行普通阶段，遇到以下状态停止：

- `waiting_for_user`
- `blocked`
- `completed`

不会绕过 `sample_selection`、`topic_selection`、`review` 或 `generation_brief`。

## 16. 配置体验

- 新增 `xiaoba.local.example.yaml`；
- `xiaoba.local.yaml` 已加入 `.gitignore`；
- secret 仍使用环境变量，不写入配置文件。

## 17. runtime 拆分

本轮没有大规模拆分 `runtime.py`，只抽出：

- `presentation.py`
- `config.py`
- `generation_provider.py`
- `locks.py`

原因：现有测试覆盖面较大，直接重写 runtime 风险高。后续可以在测试保护下继续拆 `orchestrator/state_machine/executors`。

## 18. 并发安全

- 新增 `.xiaoba-write.lock` 文件锁；
- 核心 state/JSON 写入在锁内完成；
- 继续使用临时文件 + replace 原子写入。

## 19. 测试结果

已通过：

```bash
python3 -m unittest discover -v
# Ran 202 tests in 396.689s
# OK

PYTHONPYCACHEPREFIX=/tmp/xiaoba-pycache python3 -m compileall xiaoba_workflow scripts tests
# OK

python3 -m xiaoba_workflow validate-project
# Project baseline is valid.

python3 -m xiaoba_workflow doctor --all
# OK，默认 provider 均为 mock/contract 状态，自动发布不支持。
```

## 20. E2E 验收结果

已通过 targeted 验证：

- Mock learning `run-until-gate` 到 completed；
- generation 无 brief 停在 `generation_brief` gate；
- Hot Learning runner mock contract；
- Lingzao runner v0.2.0 capabilities；
- Generation external fake topic provider；
- Generation external fake content revision provider；
- Lingzao real-mode cost gate、ask/always/never 策略、optional invocation merge、skip 和 Evidence 链路；
- feedback candidate；
- post publish review skeleton。

## 21. 当前真实、Prompt、Contract、Mock 边界

- Lingzao：`collect_note`、comments、transcript 已有 real provider contract 和 fake runner 验收；真实在线仍未完整验收。
- Hot Learning：runner contract + mock/codex_manual/external；未声称官方真实 API。
- Personal Content：机制导入、规则提案/确认、GenerationContext 读取已有真实 CLI 适配；不处理画像创建。
- Generation：mock 默认；topic/content external fake runner verified；真实在线生成未验收。
- Publishing：不支持。

## 22. 是否满足 v0.2.0 发布条件

当前代码满足 `v0.2.0` 本地发布条件，建议 Release Notes 标记为 `PASS WITH MINOR ISSUES`，因为部分真实外部能力未在线验证。

## 23. 发布前仍需人工完成的事项

- 用户自行安装 Lingzao、Hot Learning、Personal Content。
- 用户自行配置 API Key、base URL、workspace。
- 如要真实 comments/transcript，必须提供真实 Lingzao runner、额度和授权，并完成在线验证。
- 如要真实 generation，必须提供 external generation command 并完成在线验证。
- 不要创建 GitHub Release 或 tag，除非最终测试通过并人工确认发布。
