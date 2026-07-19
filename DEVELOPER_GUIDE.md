# Developer Guide

这份文档保留技术细节，面向接手开发者和 Codex 排障任务。普通用户请优先阅读 `README.md` 和 `USER_MANUAL.md`。

## 技术命令

```bash
python3 -m xiaoba_workflow validate-project
python3 -m xiaoba_workflow doctor --all
python3 -m xiaoba_workflow task-status tasks/<task-id> --technical
python3 -m xiaoba_workflow run tasks/<task-id> --technical
python3 -m xiaoba_workflow run-until-gate tasks/<task-id> --technical
```

## 开发模式

仓库根目录仍可作为开发 root 使用：

```bash
python3 -m unittest discover -v
python3 -m xiaoba_workflow create-task --type learning --source-url "https://example.com/note/1"
python3 -m xiaoba_workflow run tasks/<task-id> --technical
```

## Mock / Demo / Contract

- `demo`：用户明确选择的演示流程，产物必须标记 `demo: true`。
- `mock`：开发和测试中的确定性实现，不面向普通用户默认展示。
- `codex_manual`：由当前 Codex 按 Prompt/Skill 执行，不声称外部 API。
- `external`：用户自配命令，按 contract 调用。
- `real`：用户本地真实 Skill 或服务。

## Runner / Provider / Contract

这些术语只应出现在技术文档、测试和 `--technical` 输出中。普通用户文档不应要求理解它们。

## Package Data

wheel 安装后，CLI 从 `xiaoba_workflow/assets/` 复制运行资产到用户 workspace：

- `workflow.yaml`
- `prompts/`
- `templates/`
- `scripts/`

不要让运行时依赖源码 checkout 中的这些目录。

## 发布前检查

见 `V1_RELEASE_CHECKLIST.md`。
