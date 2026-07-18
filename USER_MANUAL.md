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

## 5. 导入 Hot Learning 分析

Hot Learning 当前没有稳定 CLI。把分析 Markdown 保存为本地文件后导入：

```bash
python3 -m xiaoba_workflow import-hot-learning-analysis tasks/<task-id> --markdown /absolute/path/analysis.md
python3 -m xiaoba_workflow run tasks/<task-id>
```

导入只写 `raw/hot-learning/`，标准化由下一次 `run` 完成。

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

## 10. 清理本地测试数据

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
