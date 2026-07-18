# 本地全链路验收说明

本文档用于区分当前链路中的真实调用、Prompt 驱动、本地编排和 Mock。默认不访问网络、不调用真实 Skill。

## 1. 准备

```bash
python3 -m xiaoba_workflow validate-project
python3 -m xiaoba_workflow doctor --skill lingzao
python3 -m xiaoba_workflow doctor --skill personal-content
```

默认输出应显示 mock provider。真实 Skill 需要用户自行安装，不随本仓库发布。

## 2. Mock learning 验收

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

预期：

- `evidence/evidence.yaml` 存在；
- `analysis/analysis.yaml` 存在；
- `analysis/mechanism-intake-result.json` 存在；
- `analysis/learning-summary.yaml` 存在；
- `state.yaml` 为 `status: completed`；
- 不进入 generation；
- 不发布。

## 3. 真实 Lingzao smoke test

配置示例：

```bash
export XIAOBA_LINGZAO_PROVIDER=real
export XIAOBA_LINGZAO_COMMAND='["python3", "scripts/lingzao_runner.py"]'
export LINGZAO_CLIENT_PATH="/absolute/path/to/lingzao/scripts/lingzao_client.py"
export XIAOBA_LINGZAO_TIMEOUT=300
export LINGZAO_API_KEY="..."
export LINGZAO_BASE_URL="..."

python3 -m xiaoba_workflow doctor --skill lingzao
```

只在 doctor 通过后执行：

```bash
python3 -m xiaoba_workflow create-task --type learning --source-url "<public-test-xhs-note-url>"
python3 -m xiaoba_workflow run tasks/<task-id>
python3 -m xiaoba_workflow run tasks/<task-id>
python3 -m xiaoba_workflow run tasks/<task-id>
```

预期停在 `analysis`，并生成：

- `raw/lingzao/external/result.json`
- `raw/lingzao/external/runner-manifest.json`
- `raw/lingzao/note-detail.json`
- `raw/lingzao/invocation.json`
- `evidence/evidence.yaml`

不得把 API Key、Authorization、Cookie 或浏览器凭据写入任务文件。

## 4. Prompt 驱动 Hot Learning

当前没有稳定 Hot Learning CLI/API。可以用以下方式导入人工或 Codex 生成的原始 Markdown 分析：

```bash
python3 -m xiaoba_workflow import-hot-learning-analysis tasks/<task-id> --markdown /absolute/path/analysis.md
python3 -m xiaoba_workflow run tasks/<task-id>
```

预期：

- 原始 Markdown 保存到 `raw/hot-learning/analysis.md`；
- 标准化结果保存到 `analysis/analysis.yaml`；
- Analysis Validator 通过；
- 不直接创建规则、资产或内容。

## 5. 真实 Personal Content governance

配置示例：

```bash
export XIAOBA_PERSONAL_CONTENT_PROVIDER=real
export XIAOBA_PERSONAL_CONTENT_COMMAND='["python3", "-m", "app.cli.main"]'
export XIAOBA_PERSONAL_CONTENT_WORKSPACE="/absolute/path/to/personal-content-workspace"
export PYTHONPATH="/absolute/path/to/personal-content-skill"

python3 -m xiaoba_workflow doctor --skill personal-content
```

单样本 learning 在 `mechanism_intake` 时会调用 `import-mechanism`。任务完成后可准备和确认治理规则：

```bash
python3 -m xiaoba_workflow prepare-governance tasks/<learning-task-id> --profile-id creator-main
python3 -m xiaoba_workflow propose-governance-rule tasks/<learning-task-id> --proposal-id rule-proposal-001
python3 -m xiaoba_workflow confirm-governance-rule tasks/<learning-task-id> --proposal-id rule-proposal-001 --decision confirm
```

边界：

- 主项目只保存请求、响应和外部引用；
- 正式规则状态以 Personal Content workspace 为权威；
- `confirm` 只确认规则，不生成内容、不发布。

## 6. Generation 到待审核内容包

使用已确认规则构建上下文：

```bash
python3 -m xiaoba_workflow create-task --type generation --brief "基于已沉淀规则生成 5 个小红书选题方向"
python3 -m xiaoba_workflow run tasks/<generation-task-id>
python3 -m xiaoba_workflow run tasks/<generation-task-id>
python3 -m xiaoba_workflow run tasks/<generation-task-id>
python3 -m xiaoba_workflow select-topic tasks/<generation-task-id> --id topic-001
python3 -m xiaoba_workflow run tasks/<generation-task-id>
```

预期：

- `content/generation-context.yaml` 只包含 active rules；
- `content/topic-candidates.json` 至少 5 条候选；
- `content/content-package.yaml` 是待审草稿；
- 任务停在 `review`；
- 不生成发布任务、不上传、不发布。

审核：

```bash
python3 -m xiaoba_workflow review-content tasks/<generation-task-id> --decision request_changes --feedback "请加强安装步骤"
python3 -m xiaoba_workflow run tasks/<generation-task-id>
python3 -m xiaoba_workflow review-content tasks/<generation-task-id> --decision approve
```

`approve` 只完成本地任务，不发布内容。

## 7. 回归验证

```bash
python3 -m unittest discover -v
PYTHONPYCACHEPREFIX=/tmp/xiaoba-pycache python3 -m compileall xiaoba_workflow scripts tests
python3 -m xiaoba_workflow validate-project
```

## 7.1 阶段 34 收口验证

本地 fake runner 已覆盖以下真实模式契约：

- Lingzao real provider：`collect_note` 后停在 `external_cost_confirmation`；
- `confirm-external-cost --decision confirm` 后执行 comments/transcript 并合并到内部 raw；
- `confirm-external-cost --decision skip` 后记录跳过，不补造缺失内容；
- Evidence Normalizer 可继续读取内部 `raw/lingzao/note-detail.json`；
- Generation external provider：topic selection 后执行 `generate_content`；
- `request_changes` 后生成第二版 content package；
- `approve` 只完成本地任务，不发布。

这些验证不等同于真实在线 Lingzao 或真实在线生成模型验收。

## 8. 发布前检查

```bash
git status --short
git ls-files lingzao hot-learning personal-content .xhs-personal-content-skill
git ls-files tasks
```

预期：

- 外部 Skill 目录不被 Git 跟踪；
- `tasks/` 只跟踪 `.gitkeep` 和 `README.md`；
- `.env` 不被跟踪。
