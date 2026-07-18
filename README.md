# Xiaoba Workflow

轻量本地编排层，用于把小红书内容学习、机制沉淀和待审核内容生成串起来。

本仓库只发布编排代码、模板、Prompt、测试和文档。Lingzao、Hot Learning、Personal Content 三个 Skill 不随仓库发布，使用者需要在本地自行安装和配置。

## 当前结论

- `learning` 单样本 Mock 闭环已可跑通。
- Lingzao 已接入 runner contract 1.0，真实采集依赖用户本地 Lingzao、API Key、base URL、登录状态和额度。
- Hot Learning 已有 runner contract 1.0；默认 mock，可切换 `codex_manual` 或用户自配 external runner。未声称存在官方 API。
- Personal Content 已支持真实本地 CLI 的机制导入、候选规则提案、候选规则确认、GenerationContext active rule 读取。
- `generation` 可以从 Personal Content 已批准规则组装上下文，生成选题候选和待审核内容包；topic generation 支持 external fake-runner contract。
- `request_changes` 会生成候选长期偏好，但不会自动激活规则。
- 已有 `post_publish_review` 基础链路，只生成复盘建议，不自动改规则状态。
- `approve` 只完成本地 review 任务，不发布。
- 自动发布未实现。

完整边界见 [CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md)，本地验收步骤见 [LOCAL_END_TO_END_ACCEPTANCE.md](LOCAL_END_TO_END_ACCEPTANCE.md)，面向使用者的步骤见 [USER_MANUAL.md](USER_MANUAL.md)，本轮流程审计见 [FLOW_AUDIT.md](FLOW_AUDIT.md)。

## 安装

要求 Python 3.9.6+。

```bash
python3 -m pip install -e ".[test]"
python3 -m xiaoba_workflow validate-project
```

如果不安装包，也可以在仓库根目录直接运行：

```bash
python3 -m xiaoba_workflow --help
```

## 安全边界

不要提交以下内容：

- `.env`
- API Key、Cookie、Authorization header
- `tasks/task-*`
- `lingzao/`
- `hot-learning/`
- `personal-content/`
- `.xhs-personal-content-skill/`

`.gitignore` 已默认忽略这些本地运行数据和外部 Skill 目录。`tasks/` 只保留 `.gitkeep` 和 `README.md`。

## 常用命令

```bash
python3 -m xiaoba_workflow validate-project
python3 -m xiaoba_workflow doctor --skill lingzao
python3 -m xiaoba_workflow doctor --skill personal-content
python3 -m xiaoba_workflow doctor --all
python3 -m xiaoba_workflow start
python3 -m xiaoba_workflow create-task --type learning --source-url "https://example.com/note/1"
python3 -m xiaoba_workflow create-task --type generation --brief "生成 5 个小红书选题"
python3 -m xiaoba_workflow task-status tasks/<task-id>
python3 -m xiaoba_workflow task-status tasks/<task-id> --technical
python3 -m xiaoba_workflow run tasks/<task-id>
python3 -m xiaoba_workflow run-until-gate tasks/<task-id>
python3 -m xiaoba_workflow select-topic tasks/<task-id> --id topic-001
python3 -m xiaoba_workflow review-content tasks/<task-id> --decision approve
```

`run` 一次只执行当前阶段一次，不会连续跑完整流程。

## Mock learning 快速开始

```bash
python3 -m xiaoba_workflow create-task --type learning --source-url "https://example.com/note/1"
python3 -m xiaoba_workflow run tasks/<task-id>
python3 -m xiaoba_workflow run tasks/<task-id>
python3 -m xiaoba_workflow run tasks/<task-id>
python3 -m xiaoba_workflow run tasks/<task-id>
python3 -m xiaoba_workflow run tasks/<task-id>
python3 -m xiaoba_workflow run tasks/<task-id>
python3 -m xiaoba_workflow run tasks/<task-id>
```

完成后应有：

- `raw/lingzao/note-detail.json`
- `evidence/evidence.yaml`
- `raw/hot-learning/analysis.md`
- `analysis/analysis.yaml`
- `analysis/mechanism-intake-result.json`
- `analysis/learning-summary.yaml`

状态应为 `completed`，且不会自动进入 generation。

## 真实 Lingzao 配置

用户需要自行安装 Lingzao，并配置认证。本仓库不会下载、安装或提交 Lingzao。

示例：

```bash
export XIAOBA_LINGZAO_PROVIDER=real
export XIAOBA_LINGZAO_COMMAND='["python3", "scripts/lingzao_runner.py"]'
export LINGZAO_CLIENT_PATH="/absolute/path/to/lingzao/scripts/lingzao_client.py"
export LINGZAO_API_KEY="..."
export LINGZAO_BASE_URL="..."
export XIAOBA_LINGZAO_TIMEOUT=300

python3 -m xiaoba_workflow doctor --skill lingzao
```

doctor 通过后再运行 learning 的 `evidence_collection`。

真实 Lingzao 在 `learning:evidence_collection` 中采用两段式执行：

```bash
python3 -m xiaoba_workflow run tasks/<task-id>
# 采集 note detail 后，如需要额外评论或逐字稿，会停在 external_cost_confirmation

python3 -m xiaoba_workflow confirm-external-cost tasks/<task-id> --decision confirm
# 或跳过额外调用
python3 -m xiaoba_workflow confirm-external-cost tasks/<task-id> --decision skip

python3 -m xiaoba_workflow run tasks/<task-id>
# 完成 comments/transcript 调用或记录跳过决定，并推进到 evidence_normalization
```

本地采集策略可写入 `xiaoba.local.yaml`：

```yaml
learning:
  collect_comments: ask
  collect_transcript: ask
  allow_auto_paid_calls: false
  transcript_required: false
```

`ask|always|never` 控制是否尝试评论和逐字稿采集。即使设置为 `always`，默认仍会要求确认；只有显式设置 `allow_auto_paid_calls: true` 才会自动调用可能消耗额度的 Lingzao 操作。`transcript_required: true` 时，视频逐字稿失败会阻塞任务。

真实输出会同时保存：

- `raw/lingzao/external/result.json`
- `raw/lingzao/external/runner-manifest.json`
- `raw/lingzao/invocations/index.json`
- `raw/lingzao/note-detail.json`

Lingzao 边界：

- 不保存视频文件；
- 缺失指标保持 `null`；
- 自动逐字稿不保证；
- comments/transcript 需要用户确认后才会额外调用；
- 手工逐字稿会标记为 `manually_provided`；
- external raw 保留在 `raw/lingzao/external/`。

## Hot Learning

本项目提供本地 runner contract：

```bash
python3 scripts/hot_learning_runner.py --capabilities
python3 scripts/hot_learning_runner.py --doctor
```

支持：

- `analyze_single`
- `analyze_cross_sample`

Provider 模式：

- `mock`：默认确定性输出；
- `codex_manual`：生成手工/Codex 执行说明；
- `external`：调用用户自配命令。

如果使用 Codex 或人工按 Prompt 生成 Markdown，可继续用导入流程：

1. 由 Codex 或人工按 `prompts/hot-learning-analysis-only.md` 生成原始 Markdown；
2. 用 `import-hot-learning-analysis` 导入；
3. 再用 `run` 标准化为 `analysis/analysis.yaml`。

```bash
python3 -m xiaoba_workflow import-hot-learning-analysis tasks/<task-id> --markdown /absolute/path/analysis.md
python3 -m xiaoba_workflow run tasks/<task-id>
```

## Generation external provider

默认 generation 使用本地 mock。若用户配置外部 provider，可覆盖选题和正文生成 contract：

```bash
export XIAOBA_GENERATION_PROVIDER=external
export XIAOBA_GENERATION_COMMAND='["python3", "/absolute/path/to/generation_runner.py"]'
```

外部正文生成 operation 为 `generate_content`。编排层会传入：

- `generation_context_ref`
- `selected_topic_ref`
- `revision_number`
- `previous_content_ref`
- `feedback_ref`

当用户在 `review` 阶段执行 `request_changes` 后，下一次 `run` 会生成新的 revision，并保留上一版内容和反馈引用。`approve` 只完成本地任务，不发布。

## 真实 Personal Content 配置

用户需要自行安装 Personal Content Skill，并准备本地 workspace。

```bash
export XIAOBA_PERSONAL_CONTENT_PROVIDER=real
export XIAOBA_PERSONAL_CONTENT_COMMAND='["python3", "-m", "app.cli.main"]'
export XIAOBA_PERSONAL_CONTENT_WORKSPACE="/absolute/path/to/personal-content-workspace"
export PYTHONPATH="/absolute/path/to/personal-content-skill"

python3 -m xiaoba_workflow doctor --skill personal-content
```

支持的真实调用：

- `import-mechanism`
- `propose-rule-from-mechanism`
- `create-rule-decision`
- `resolve-decision`
- `show-generation-context`

主项目只保存请求、响应和外部引用；正式机制、规则和长期账号状态以 Personal Content workspace 为权威。

## Governance 到规则确认

learning 完成后：

```bash
python3 -m xiaoba_workflow prepare-governance tasks/<learning-task-id> --profile-id creator-main
python3 -m xiaoba_workflow propose-governance-rule tasks/<learning-task-id> --proposal-id rule-proposal-001
python3 -m xiaoba_workflow confirm-governance-rule tasks/<learning-task-id> --proposal-id rule-proposal-001 --decision confirm
```

`confirm` 会把 Personal Content 中的候选规则走用户决策流确认成 active rule；不会生成内容或发布。

## Generation 到待审核内容包

```bash
python3 -m xiaoba_workflow create-task --type generation --brief "基于已沉淀规则生成 5 个小红书选题"
python3 -m xiaoba_workflow run tasks/<generation-task-id>
python3 -m xiaoba_workflow run tasks/<generation-task-id>
python3 -m xiaoba_workflow run tasks/<generation-task-id>
python3 -m xiaoba_workflow select-topic tasks/<generation-task-id> --id topic-001
python3 -m xiaoba_workflow run tasks/<generation-task-id>
```

预期停在 `review`，生成 `content/content-package.yaml`。内容包只保留规则 ID、版本和摘要作为 traceability，不保存规则生命周期字段。

审核：

```bash
python3 -m xiaoba_workflow review-content tasks/<generation-task-id> --decision request_changes --feedback "请加强安装步骤"
python3 -m xiaoba_workflow run tasks/<generation-task-id>
python3 -m xiaoba_workflow review-content tasks/<generation-task-id> --decision approve
```

`approve` 只完成本地任务，不发布。

`request_changes` 会额外写入 `feedback/governance-candidates.yaml`。确认候选反馈：

```bash
python3 -m xiaoba_workflow confirm-feedback-rule tasks/<generation-task-id> --candidate-id feedback-rule-001 --decision confirm
```

该命令不自动激活长期规则。

## 发布后复盘

```bash
python3 -m xiaoba_workflow create-task --type post_publish_review --source-url "https://example.com/published-note"
python3 -m xiaoba_workflow run-until-gate tasks/<task-id>
```

产物：`analysis/post-publish-review.yaml`。它只包含复盘建议，不自动修改 Personal Content 规则状态。

## 测试

```bash
python3 -m unittest discover -v
PYTHONPYCACHEPREFIX=/tmp/xiaoba-pycache python3 -m compileall xiaoba_workflow scripts tests
python3 -m xiaoba_workflow validate-project
```

## 目录

- `xiaoba_workflow/cli.py`：CLI 参数解析和命令分发
- `xiaoba_workflow/runtime.py`：状态机和阶段执行器
- `xiaoba_workflow/lingzao.py`：Lingzao provider、doctor 和 raw adapter
- `scripts/lingzao_runner.py`：Lingzao runner contract 1.0 薄桥接层
- `scripts/hot_learning_runner.py`：Hot Learning runner contract 1.0
- `xiaoba_workflow/presentation.py`：用户态 CLI 输出
- `xiaoba_workflow/generation_provider.py`：Generation Provider contract
- `xiaoba_workflow/analysis.py`：Hot Learning Markdown 标准化和 Analysis Validator
- `xiaoba_workflow/personal_content.py`：Personal Content 请求、响应和外部引用适配
- `xiaoba_workflow/generation.py`：待审核内容包生成和 review
- `templates/`：任务和中间对象模板
- `prompts/`：Skill 节点 Prompt
- `tasks/`：运行时任务目录，不提交任务数据
