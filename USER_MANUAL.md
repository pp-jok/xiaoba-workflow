# 使用手册

这份手册面向本地使用者和接手的 Codex。目标是先跑通 Mock，再按需接入真实 Lingzao 和 Personal Content。

## 1. 不要直接提交的内容

以下内容只属于本机：

- `lingzao/`
- `hot-learning/`
- `personal-content/`
- `.xhs-personal-content-skill/`
- `.env`
- `tasks/task-*`

这些内容默认被 `.gitignore` 忽略。外部 Skill 由每个用户自己安装。

## 2. 初始化检查

```bash
python3 -m xiaoba_workflow validate-project
python3 -m xiaoba_workflow doctor --skill lingzao
python3 -m xiaoba_workflow doctor --skill personal-content
python3 -m xiaoba_workflow doctor --all
```

默认情况下两个 doctor 都应显示 mock provider。

## 3. 跑一个 Mock learning

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

每次 `run` 只执行一个阶段。完成后 `state.yaml` 应显示 `status: completed`。

也可以使用：

```bash
python3 -m xiaoba_workflow run-until-gate tasks/<task-id>
```

该命令会连续执行普通阶段，遇到人工选择、blocked、completed 或外部额度确认时停止，不会绕过 gate。

## 4. 接入真实 Lingzao

本仓库不提供 Lingzao。安装后配置：

```bash
export XIAOBA_LINGZAO_PROVIDER=real
export XIAOBA_LINGZAO_COMMAND='["python3", "scripts/lingzao_runner.py"]'
export LINGZAO_CLIENT_PATH="/absolute/path/to/lingzao/scripts/lingzao_client.py"
export LINGZAO_API_KEY="..."
export LINGZAO_BASE_URL="..."
python3 -m xiaoba_workflow doctor --skill lingzao
```

doctor 不做采集，只检查 contract、命令和配置。通过后再创建真实测试任务。

真实采集 note detail 后，如果需要评论或视频逐字稿，任务会停在 `external_cost_confirmation`：

```bash
python3 -m xiaoba_workflow run tasks/<task-id>
python3 -m xiaoba_workflow task-status tasks/<task-id>
```

确认额外调用：

```bash
python3 -m xiaoba_workflow confirm-external-cost tasks/<task-id> --decision confirm
python3 -m xiaoba_workflow run tasks/<task-id>
```

跳过额外调用：

```bash
python3 -m xiaoba_workflow confirm-external-cost tasks/<task-id> --decision skip
python3 -m xiaoba_workflow run tasks/<task-id>
```

跳过不会伪造评论或逐字稿，Evidence 会把缺失项写入 coverage、missing 和 warnings。

可选的本地策略：

```yaml
learning:
  collect_comments: ask
  collect_transcript: ask
  allow_auto_paid_calls: false
  transcript_required: false
```

`always` 默认仍会要求确认；只有 `allow_auto_paid_calls: true` 时才会自动调用。`never` 会记录 skipped。`transcript_required: true` 用于明确要求视频逐字稿，失败时任务会 blocked。

## 5. Hot Learning Runner 和手工导入

本项目提供 Hot Learning runner contract：

```bash
python3 scripts/hot_learning_runner.py --capabilities
python3 scripts/hot_learning_runner.py --doctor
```

默认 `mock` 可生成确定性 Markdown。`codex_manual` 会生成手工执行说明，`external` 需要用户配置自己的外部命令。不要把 fake runner 验证说成真实 Hot Learning 在线验证。

如果你用 Codex 或人工按 Prompt 生成了分析 Markdown，可以导入：

```bash
python3 -m xiaoba_workflow import-hot-learning-analysis tasks/<task-id> --markdown /absolute/path/analysis.md
python3 -m xiaoba_workflow run tasks/<task-id>
```

导入只写 `raw/hot-learning/`，标准化由下一次 `run` 完成。

## 5.1 外部内容生成 Provider

默认 generation 使用本地 mock。接入外部 generation runner 时：

```bash
export XIAOBA_GENERATION_PROVIDER=external
export XIAOBA_GENERATION_COMMAND='["python3", "/absolute/path/to/generation_runner.py"]'
```

正文生成使用 `generate_content` operation。第一次生成会写入 `revision-001`；在 `review` 阶段选择 `request_changes` 后，下一次 `run` 会带上上一版内容和 feedback 引用，生成 `revision-002`。`approve` 仍只完成本地任务，不发布内容。

## 6. 接入真实 Personal Content

本仓库不提供 Personal Content。安装后配置：

```bash
export XIAOBA_PERSONAL_CONTENT_PROVIDER=real
export XIAOBA_PERSONAL_CONTENT_COMMAND='["python3", "-m", "app.cli.main"]'
export XIAOBA_PERSONAL_CONTENT_WORKSPACE="/absolute/path/to/personal-content-workspace"
export PYTHONPATH="/absolute/path/to/personal-content-skill"
python3 -m xiaoba_workflow doctor --skill personal-content
```

doctor 会检查这些命令是否可用：

- `import-mechanism`
- `show-generation-context`
- `propose-rule-from-mechanism`
- `create-rule-decision`
- `resolve-decision`

## 7. 从学习到规则沉淀

learning 完成后：

```bash
python3 -m xiaoba_workflow prepare-governance tasks/<learning-task-id> --profile-id creator-main
python3 -m xiaoba_workflow propose-governance-rule tasks/<learning-task-id> --proposal-id rule-proposal-001
python3 -m xiaoba_workflow confirm-governance-rule tasks/<learning-task-id> --proposal-id rule-proposal-001 --decision confirm
```

这会把候选规则交给 Personal Content 的用户决策流。确认后规则可以被后续 GenerationContext 使用。

## 8. 从规则到待审核内容包

```bash
python3 -m xiaoba_workflow create-task --type generation --brief "基于已沉淀规则生成 5 个小红书选题"
python3 -m xiaoba_workflow run tasks/<generation-task-id>
python3 -m xiaoba_workflow run tasks/<generation-task-id>
python3 -m xiaoba_workflow run tasks/<generation-task-id>
python3 -m xiaoba_workflow select-topic tasks/<generation-task-id> --id topic-001
python3 -m xiaoba_workflow run tasks/<generation-task-id>
```

任务会停在 `review`，产物是 `content/content-package.yaml`。它是待审核草稿，不是发布稿。

## 9. 审核和修订

要求修改：

```bash
python3 -m xiaoba_workflow review-content tasks/<generation-task-id> --decision request_changes --feedback "请补充安装步骤"
python3 -m xiaoba_workflow run tasks/<generation-task-id>
```

确认完成：

```bash
python3 -m xiaoba_workflow review-content tasks/<generation-task-id> --decision approve
```

`approve` 只完成本地任务，不发布。

`request_changes` 会生成候选长期偏好：

```bash
python3 -m xiaoba_workflow confirm-feedback-rule tasks/<generation-task-id> \
  --candidate-id feedback-rule-001 \
  --decision confirm
```

该命令只记录用户确认结果，不自动激活规则。后续如需进入 Personal Content 长期规则，仍应走明确治理流程。

## 10. 发布后复盘

Xiaoba 不自动发布。用户手工发布后，可创建复盘任务：

```bash
python3 -m xiaoba_workflow create-task --type post_publish_review --source-url "https://example.com/published-note"
python3 -m xiaoba_workflow run-until-gate tasks/<task-id>
```

当前复盘只生成建议，不自动修改 Personal Content 规则状态。

## 11. 本地配置

复制示例配置：

```bash
cp xiaoba.local.example.yaml xiaoba.local.yaml
```

`xiaoba.local.yaml` 已被 `.gitignore` 忽略。不要把 API Key 写入该文件；secret 使用环境变量。

## 12. 清理本地测试数据

保留目录说明，删除运行任务：

```bash
find tasks -mindepth 1 -maxdepth 1 -type d -name 'task-*' -exec rm -rf {} +
```

发布前检查：

```bash
git ls-files lingzao hot-learning personal-content .xhs-personal-content-skill
git ls-files tasks
```

预期外部 Skill 目录无输出，`tasks` 只显示 `.gitkeep` 和 `README.md`。
