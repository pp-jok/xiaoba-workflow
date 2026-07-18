# 流程问题审计与修复记录

本文记录本轮对 `input link -> Lingzao -> Hot Learning -> Personal Content -> generation` 流程的审计结果。

## 已修复问题

### 1. 外部 Skill 被 Git 跟踪

问题：根目录 `lingzao/` 曾被 Git 跟踪，存在发布到 GitHub 的风险。

修复：

- 从 Git 索引移除 `lingzao/`；
- `.gitignore` 增加：
  - `lingzao/`
  - `hot-learning/`
  - `personal-content/`
  - `.xhs-personal-content-skill/`

结果：外部 Skill 保留在本机，GitHub 仓库不发布这些目录。

### 2. Personal Content 缺少 doctor

问题：用户只能检查 Lingzao 配置，不能在真实机制导入、规则确认、GenerationContext 前检查 Personal Content CLI。

修复：

- 新增 `python3 -m xiaoba_workflow doctor --skill personal-content`；
- mock 模式显示默认 provider；
- real 模式检查 command、workspace 和必要 CLI operation；
- doctor 只执行 `--help`，不导入机制、不生成内容、不修改 workspace。

### 3. 候选规则不能安全进入正式规则流程

问题：机制导入后只能停在候选机制，缺少从治理提案到 Personal Content 候选规则再到用户确认的闭环。

修复：

- 新增 `prepare-governance`；
- 新增 `propose-governance-rule`；
- 新增 `confirm-governance-rule`；
- `confirm` 调用 Personal Content 决策流，把候选规则确认成 `approved`；
- `reject` 调用相同决策流拒绝候选规则。

边界：确认规则不会生成内容，也不会发布。

### 4. Personal Content 决策选项适配错误

问题：Personal Content 的 `resolve-decision` 要求完整中文选项，例如 `确认使用` / `暂不使用`，不是 `confirm` / `reject`。

修复：编排层继续对用户暴露 `confirm` / `reject`，内部转换为 Personal Content 需要的完整选项文本。

### 5. GenerationContext 未读取真实 active rules

问题：generation 上下文原先只使用本地 Mock 规则引用，不能读取 Personal Content 已批准规则。

修复：

- real Personal Content provider 下，`context_assembly` 调用 `show-generation-context`；
- 只把 `approved`、`testing`、`validated` 规则写入 `content/generation-context.yaml`；
- `candidate`、`rejected`、`deprecated` 不进入正式 GenerationContext。

### 6. 内容包误写规则生命周期状态

问题：真实 active rule 带 `status: approved`，进入内容包 traceability 时被校验器拒绝。更深层问题是内容包不应携带规则生命周期状态。

修复：

- 内容包 `traceability.rule_refs` 只保留 `rule_id`、`rule_version`、`summary`；
- 校验器改为禁止正式对象/发布相关字段，而不是全文禁普通字符串；
- 增加回归测试，防止生命周期字段再次进入内容包。

### 7. 临时任务数据残留

问题：本地 `tasks/task-*` 中包含真实链接、raw 输出、分析、错误日志和手工逐字稿，不应提交。

修复：

- 清理 `tasks/task-*`；
- 保留 `tasks/.gitkeep` 和 `tasks/README.md`；
- 文档补充清理命令和发布前检查命令。

## 仍然保留的边界

- Hot Learning 仍是 Prompt 驱动，不是外部 CLI/API。
- Lingzao 不下载视频文件。
- Lingzao 自动逐字稿能力不保证。
- learning_batch 真实账号批量采集未完整验证。
- generation 生成的是待审核内容包，不是发布稿。
- 发布功能未实现。
- Personal Content content asset 治理未接入。

## 发布前必查

```bash
git ls-files lingzao hot-learning personal-content .xhs-personal-content-skill
git ls-files tasks
python3 -m unittest discover -v
PYTHONPYCACHEPREFIX=/tmp/xiaoba-pycache python3 -m compileall xiaoba_workflow scripts tests
python3 -m xiaoba_workflow validate-project
```
