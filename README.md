# Xiaoba Workflow

轻量本地编排层，用于把小红书内容学习、机制沉淀和待审核内容生成串起来。

本仓库只发布编排代码、模板、Prompt、测试和文档。Lingzao、Hot Learning、Personal Content 三个 Skill 不随仓库发布，使用者需要在本地自行安装和配置。

## 当前结论

- `learning` 单样本 Mock 闭环已可跑通。
- Lingzao 已接入 runner contract 1.0，真实采集依赖用户本地 Lingzao、API Key、base URL、登录状态和额度。
- Hot Learning 当前是 Prompt 驱动：Codex/人工生成 Markdown，本地 Normalizer 标准化，不是稳定外部 CLI。
- Personal Content 已支持真实本地 CLI 的机制导入、候选规则提案、候选规则确认、GenerationContext active rule 读取。
- `generation` 可以从 Personal Content 已批准规则组装上下文，生成选题候选和待审核内容包。
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
python3 -m xiaoba_workflow create-task --type learning --source-url "https://example.com/note/1"
python3 -m xiaoba_workflow create-task --type generation --brief "生成 5 个小红书选题"
python3 -m xiaoba_workflow task-status tasks/<task-id>
python3 -m xiaoba_workflow run tasks/<task-id>
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

Lingzao 边界：

- 不保存视频文件；
- 缺失指标保持 `null`；
- 自动逐字稿不保证；
- 手工逐字稿会标记为 `manually_provided`；
- external raw 保留在 `raw/lingzao/external/`。

## Hot Learning

当前 Hot Learning 没有稳定外部 CLI/API。推荐流程是：

1. 由 Codex 或人工按 `prompts/hot-learning-analysis-only.md` 生成原始 Markdown；
2. 用 `import-hot-learning-analysis` 导入；
3. 再用 `run` 标准化为 `analysis/analysis.yaml`。

```bash
python3 -m xiaoba_workflow import-hot-learning-analysis tasks/<task-id> --markdown /absolute/path/analysis.md
python3 -m xiaoba_workflow run tasks/<task-id>
```

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
- `xiaoba_workflow/analysis.py`：Hot Learning Markdown 标准化和 Analysis Validator
- `xiaoba_workflow/personal_content.py`：Personal Content 请求、响应和外部引用适配
- `xiaoba_workflow/generation.py`：待审核内容包生成和 review
- `templates/`：任务和中间对象模板
- `prompts/`：Skill 节点 Prompt
- `tasks/`：运行时任务目录，不提交任务数据
