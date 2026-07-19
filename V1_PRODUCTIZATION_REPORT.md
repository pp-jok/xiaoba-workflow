# Xiaoba Workflow v1.0.0 Productization Report

## 1. 正式版定义

v1.0.0 的“正式”指安装、初始化、用户工作区、任务交互、人工 Gate、结果摘要、恢复流程和能力边界达到稳定状态。它不表示 Lingzao、Hot Learning、Personal Content 或外部生成服务由本仓库完整提供或已全部真实在线验收。

## 2. 旧版问题

- 用户需要知道 `validate-project`、`setup`、`doctor --all`、`start` 等多个命令。
- `tasks/` 与 `xiaoba.local.yaml` 默认依赖当前项目目录。
- 从 wheel 或 Skill 安装目录外运行时，`workflow.yaml`、`prompts/`、`templates/`、`scripts/` 可能缺失。
- 默认 mock 容易让用户误解为真实采集。
- blocked 状态缺少用户态恢复动作。

## 3. 新工作区设计

默认用户工作区：

```text
~/.xiaoba-workflow/
├── config/xiaoba.local.yaml
├── tasks/
├── logs/
└── runtime/project/
```

优先级：

```text
start --workspace PATH
→ XIAOBA_WORKSPACE
→ ~/.xiaoba-workflow
```

`runtime/project/` 保存打包进 wheel 的运行资产，`tasks/` 作为用户数据目录，不写入 Skill 安装目录。

## 4. 首次启动

`xiaoba-workflow` 或 `xiaoba-workflow start` 会自动：

1. 解析用户工作区；
2. 创建目录；
3. 写入安全默认配置；
4. 安装运行资产；
5. 显示当前能力；
6. 进入用户首页。

普通用户不再必须手工执行 `setup`、`validate-project` 或 `doctor --all`。

## 5. 正式模式与演示模式

安全默认配置：

```yaml
providers:
  lingzao:
    mode: unavailable
  hot_learning:
    mode: codex_manual
  personal_content:
    mode: unavailable
  generation:
    mode: codex_manual
```

未配置 Lingzao 时，用户必须显式选择手工输入、演示流程或取消。demo 任务写入 `execution_mode: demo`，raw 中写入 `demo: true`，摘要显示“演示结果”。

## 6. 手工输入降级

单条 learning 支持用户手工输入标题、正文或视频口播稿。手工输入写入 `raw/lingzao/note-detail.json` 和 `invocation.json`，再进入现有 Evidence Normalizer，不建立第二套分析链路。

## 7. Gate 覆盖

`start` 目前覆盖：

- `external_cost_confirmation`
- `sample_selection`
- `topic_selection`
- `content_review`
- `generation_brief`

未知 waiting type 会安全退出并提示使用技术视图。

## 8. blocked 恢复

blocked 时显示：

- 当前用户态步骤；
- 原因；
- 重试；
- 跳过可选步骤；
- 手工补充内容；
- 查看技术详情；
- 暂停任务。

恢复动作写入 `run-log.md` audit 记录。

## 9. 任务恢复

首页支持：

- 新建任务；
- 继续未完成任务；
- 查看最近结果；
- 配置能力；
- 查看系统状态。

任务列表来自 workspace `tasks/` 文件目录，不引入数据库。

## 10. Codex Skill 入口

新增 `SKILL.md`，说明 Codex 应调用 Xiaoba CLI/application API，自动 bootstrap workspace，不要求用户进入安装目录，不绕过状态机，不自动发布，不自动激活长期规则。

## 11. 安装验证

运行资产已复制到 `xiaoba_workflow/assets/`，并通过 `pyproject.toml` 与 `setup.py` package data 打包。wheel 安装后，CLI 可从非仓库目录运行。

## 12. 迁移兼容

本轮不自动移动旧 `tasks/` 或 `xiaoba.local.yaml`。旧数据不会被删除。正式入口使用新的用户工作区；旧项目目录仍可通过技术命令和显式路径排查。

## 13. 测试结果

新增 `tests/test_v1_productization.py` 覆盖工作区解析、bootstrap、非仓库目录启动、demo 标记、任务列表和结果查看。

本轮最终验证结果：

- `python3 -m unittest discover -v`：218 tests passed。
- `PYTHONPYCACHEPREFIX=/tmp/xiaoba-pycache python3 -m compileall xiaoba_workflow scripts tests`：passed。
- `python3 -m xiaoba_workflow validate-project`：passed。
- `python3 -m xiaoba_workflow doctor --all`：passed。
- `python3 -m xiaoba_workflow --help`：passed。
- `git diff --check`：passed。
- `python3 -m build`：sdist 和 wheel 构建成功。
- wheel 安装后从 `/tmp` 运行 `xiaoba-workflow --help`：passed。
- wheel 安装后从 `/tmp` 运行 `python -m xiaoba_workflow start`：passed。
- wheel 安装后从 `/tmp` 运行无子命令 `xiaoba-workflow`：passed。

## 14. 已知限制

- Lingzao 真实采集需要用户自行安装和配置。
- Lingzao 不下载视频文件，自动逐字稿不保证。
- Hot Learning 不声明官方在线 API。
- Personal Content 必须有独立真实 workspace。
- Generation external 未配置时不能视为真实模型能力。
- 不自动发布小红书。
- 不自动激活长期规则。

## 15. 是否满足 v1.0.0 发布条件

本地实现满足 v1.0.0 产品化目标：一个入口启动、独立工作区、首次自动初始化、真实/手工/demo 分离、常见 Gate 交互、blocked 恢复、技术模式保留、无重型基础设施。

## 16. 最终发布前审查结论

五项正式版风险审查结论：

1. `codex_manual` 独立 CLI 行为：通过。Hot Learning `codex_manual` 不再静默生成 mock 分析；非 demo 任务会阻塞并提示导入人工/Codex 分析、配置 external 或显式 demo。Generation 在 Personal Content 未配置时阻塞在上下文阶段，不生成虚假选题或正文。
2. 手工内容输入链路：通过。手工输入写入标准 `raw/lingzao/note-detail.json` 与 `invocation.json`，保留 `manual` / `manually_provided` 标记，随后复用 Evidence Normalizer、Hot Learning、Personal Content intake；缺失字段保持 `null` 或 missing，不标记为 Lingzao real success。
3. demo 隔离：通过。demo task 写入 `execution_mode: demo`，raw 写入 `demo-mode.json`，用户摘要显示“演示结果”。demo 不代表真实采集，不发布，不激活长期规则，不进入真实 Personal Content。
4. workspace 统一：通过。安装后从非仓库目录运行时，普通 CLI 默认使用 `~/.xiaoba-workflow` 或 `XIAOBA_WORKSPACE` / `--workspace`；source checkout 和测试项目根保留技术兼容。运行产物不写回 package assets。
5. Codex Skill 入口：通过。`SKILL.md` 要求 Codex 调用 Xiaoba CLI/application API，自动 bootstrap workspace，不绕过状态机，不直接改 state，不自动发布，不自动激活长期规则，遇到 Gate 暂停询问用户。

安全审查结论：未发现 API Key、Token、Cookie、Authorization、本机绝对路径、真实任务数据、真实 Personal Content workspace 或外部 Skill 源码进入 Git 跟踪范围。`tasks/` 只跟踪 `.gitkeep` 和说明文档，`dist/`、`build/`、外部 Skill 目录均被忽略。

正式发布判定：满足 v1.0.0 GitHub 发布条件；不发布 PyPI。
