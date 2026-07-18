# UX Lite Implementation Report

## 1. 实施摘要

本轮完成 Xiaoba Workflow v0.2.1 UX Lite 优化。改动只集中在 CLI 交互、用户态展示、保守默认配置和文档说明，不新增 Skill、Provider、数据库、Web 后台、自动发布或复杂 TUI。

现有 workflow、Provider、Runner、Validator、人工 gate 和文件产物保持不变。

## 2. start 新体验

`python3 -m xiaoba_workflow start` 首屏只展示四个用户任务：

1. 学习一条小红书笔记
2. 学习一批对标内容
3. 生成一篇小红书帖子
4. 复盘一篇已发布内容

用户选择后，`start` 只询问当前任务必需信息，创建任务，并复用现有 `run_until_gate` 逻辑自动运行到 waiting、blocked 或 completed。

## 3. setup 新体验

新增：

```bash
python3 -m xiaoba_workflow setup
```

它生成保守的 `xiaoba.local.yaml`，不写入 API Key、Cookie 或 token。已有 `xiaoba.local.yaml` 时拒绝静默覆盖。

默认策略：

```yaml
learning:
  collect_comments: never
  collect_transcript: ask
  allow_auto_paid_calls: false
  transcript_required: false
```

## 4. 用户进度映射

用户态进度集中在 `xiaoba_workflow/presentation.py`。

`learning`：

1. 获取内容
2. 分析内容
3. 提炼方法
4. 保存学习结果
5. 完成

`generation`：

1. 准备个人规则
2. 生成选题
3. 选择选题
4. 生成正文
5. 审核完成

`learning_batch`：

1. 准备样本
2. 获取内容
3. 分析单条内容
4. 综合共同方法
5. 保存学习结果

`post_publish_review`：

1. 获取发布内容
2. 整理表现数据
3. 复盘内容表现
4. 生成改进建议
5. 完成

## 5. Skill 提示

默认输出显示当前用户动作和使用能力，例如：

```text
正在获取公开内容
使用能力：Lingzao
```

默认不展示 provider mode、contract version、runner command、manifest、subprocess、internal stage ID 或内部文件路径。

## 6. Gate 交互

已补充用户态 gate 文案：

- 外部费用确认：合并为“获取后继续 / 只使用当前内容”。
- 样本选择：提示选择候选样本，仍由 `select-samples` 执行。
- 选题选择：显示标题和一句说明，默认隐藏 topic ID。
- 内容审核：显示“通过 / 修改 / 暂不处理”。
- 生成 brief：提示用户补充本次生成目标。

底层 gate 仍由现有命令处理，不绕过费用确认、样本选择、选题选择、审核和规则确认。

## 7. 完成摘要

完成时按任务类型输出用户可读摘要：

- `learning`：说明内容机制、规则候选、不建议照搬内容和下一步。
- `generation`：说明最终选题、内容版本、规则引用和不自动发布。
- `post_publish_review`：说明复盘建议不会自动修改 Personal Content 长期规则。

## 8. 默认轻量策略

`xiaoba.local.example.yaml` 已更新为：

- 默认不采集评论；
- 视频逐字稿默认询问；
- 默认不自动产生外部费用；
- 逐字稿不是必需项。

没有修改用户本地 `xiaoba.local.yaml`。

## 9. 保留的技术模式

以下命令继续支持技术视图：

```bash
python3 -m xiaoba_workflow task-status tasks/<task-id> --technical
python3 -m xiaoba_workflow run tasks/<task-id> --technical
python3 -m xiaoba_workflow run-until-gate tasks/<task-id> --technical
```

技术模式保留 task ID、task type、internal stage、状态和内部调试信息。

## 10. 测试结果

本轮验证命令：

```bash
python3 -m unittest discover -v
PYTHONPYCACHEPREFIX=/tmp/xiaoba-pycache python3 -m compileall xiaoba_workflow scripts tests
python3 -m xiaoba_workflow validate-project
python3 -m xiaoba_workflow doctor --all
python3 -m xiaoba_workflow --help
```

当前结果：

- unittest：209 tests OK
- compileall：通过
- validate-project：通过
- doctor --all：通过
- --help：通过

## 11. 未完成项

- `start` 仍是轻量命令行交互，不是完整 TUI。
- 已生成任务后的后续人工 gate 专用命令仍需用户按提示执行。
- 不支持自动发布小红书内容。
- 不新增真实在线 Skill 验收结论；真实 Lingzao、Hot Learning external、Generation external 仍受用户本地配置和服务状态影响。

## 12. v0.2.1 发布条件

本轮满足 v0.2.1 本地发布准备条件：

- 普通用户可以优先使用 `setup` 和 `start`；
- `start` 自动运行到人工 gate；
- 默认只展示简化进度；
- 默认不采集评论；
- 默认不自动产生外部费用；
- 技术模式保留；
- 没有新增数据库、Web 服务、复杂框架或自动发布；
- 全量测试通过。
