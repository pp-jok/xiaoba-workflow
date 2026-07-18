# Xiaoba Workflow 优化执行计划

> 目标：在不处理 Personal Content 用户画像读取的前提下，补齐 Xiaoba 的真实执行链路、提升用户体验，并让用户清楚知道当前任务、当前阶段和正在执行的 Skill。

## 一、总目标

当前 Xiaoba 的产品定位是：

```text
Lingzao 负责公开内容采集
→ Hot Learning 负责内容拆解
→ Personal Content 负责机制与规则沉淀
→ Xiaoba 负责工作流编排、校验、人工决策、内容生成和反馈闭环
```

本轮优化不处理 Personal Content 用户画像读取。

在使用 Xiaoba 之前，用户必须已经完成 Personal Content 中的：

- 用户画像建立；
- 账号定位；
- 内容方向；
- 基础偏好；
- 必要规则和约束配置。

Xiaoba 只负责读取已经准备好的规则与上下文，不负责本轮内补建用户画像。

## 二、本轮范围

本轮需要完成：

1. Hot Learning 稳定 Runner；
2. Lingzao 评论和视频逐字稿采集；
3. 真实 Generation Provider；
4. 用户修改反馈沉淀；
5. 发布后复盘基础链路；
6. `doctor --all`；
7. `run-until-gate`；
8. 本地配置体验；
9. `runtime.py` 职责拆分；
10. 并发写入安全；
11. 清理历史配置字段；
12. 开源工程设施；
13. 用户态对话体验；
14. 当前任务、阶段和 Skill 执行提示；
15. 用户引导和下一步建议。

本轮明确不做：

- Personal Content 用户画像读取；
- 自动创建用户画像；
- 自动发布小红书；
- 浏览器 Cookie 抓取；
- 私有内容采集；
- 绕过平台权限；
- 无人工确认的正式规则激活；
- 无人工审核的内容发布。

# 阶段 24：Hot Learning Runner

## 目标

把当前：

```text
Codex / 人工按 Prompt 生成 Markdown
→ import-hot-learning-analysis
```

改造成具备稳定执行契约的节点：

```text
EvidencePackage
→ Hot Learning Runner
→ raw analysis
→ Analysis Normalizer
→ Analysis Validator
```

## 1. Runner Contract

新增：

```text
scripts/hot_learning_runner.py
```

统一接口：

```bash
python3 scripts/hot_learning_runner.py \
  --input /absolute/path/request.json \
  --output /absolute/path/output-dir
```

支持：

```bash
python3 scripts/hot_learning_runner.py --capabilities
python3 scripts/hot_learning_runner.py --doctor
```

Contract version：`1.0`。

## 2. 支持 Operation

至少支持：

```text
analyze_single
analyze_cross_sample
```

## 3. 输入结构

请求至少包含：

```json
{
  "contract_version": "1.0",
  "operation": "analyze_single",
  "task_id": "task-...",
  "input_refs": {
    "evidence": "/absolute/path/evidence.yaml"
  },
  "prompt": {
    "path": "/absolute/path/prompts/hot-learning-analysis-only.md",
    "version": "..."
  },
  "language": "zh-CN",
  "output_dir": "/absolute/path/output-dir"
}
```

跨样本请求至少包含：

```json
{
  "operation": "analyze_cross_sample",
  "input_refs": {
    "sample_analyses": [
      "/absolute/path/sample-001/analysis.yaml"
    ]
  }
}
```

## 4. 输出结构

必须生成：

```text
analysis.md
runner-manifest.json
```

`runner-manifest.json` 至少包含：

```json
{
  "contract_version": "1.0",
  "runner": "xiaoba-hot-learning-runner",
  "operation": "analyze_single",
  "status": "succeeded",
  "started_at": "...",
  "completed_at": "...",
  "prompt_version": "...",
  "provider": "codex|external|mock",
  "model": null,
  "warnings": [],
  "input_refs": [],
  "output_files": []
}
```

## 5. Provider 模式

支持：

```text
mock
codex_manual
external
```

默认仍为 `mock`。

要求：

- `mock`：确定性输出；
- `codex_manual`：生成 request 和待执行说明，进入人工等待状态；
- `external`：调用配置好的外部命令；
- 不伪造 Hot Learning 已存在正式 API；
- Codex 手工执行也必须有 manifest 和版本记录。

## 6. 工作流集成

`analysis` 阶段应：

- 调用 Hot Learning Provider；
- 保存 external raw；
- 保存 invocation；
- 失败时 blocked；
- 不直接生成正式 AnalysisPackage；
- `analysis_normalization` 继续负责标准化和校验。

## 7. 用户提示

进入该阶段时，CLI 必须输出：

```text
当前任务：学习单条笔记
当前阶段：内容机制拆解
正在执行：Hot Learning
作用：分析这条内容为什么有效，并提取可学习机制
```

如果是 `codex_manual`：

```text
Hot Learning 当前需要 Codex 或人工执行。
已生成分析请求：
tasks/<task-id>/raw/hot-learning/request.json

完成分析后，请运行：
xiaoba-workflow import-hot-learning-analysis ...
```

# 阶段 25：Lingzao 评论与视频逐字稿

## 目标

将 Lingzao 采集扩展为：

```text
笔记详情
+ 评论
+ 视频口播逐字稿
→ EvidencePackage
```

## 1. 新增 Runner Operation

增加：

```text
collect_comments
collect_transcript
analyze_profile
search_notes
search_profiles
```

优先实现：

```text
collect_comments
collect_transcript
```

映射到最新版 Lingzao CLI：

```text
get-note-comments
extract-video-copy
```

## 2. 视频流程

不得再假设 `get-note-detail` 一定返回 transcript。

正确流程：

```text
get-note-detail
→ 判断 note 类型
→ 如果是视频且配置允许
→ 调用 extract-video-copy
→ 合并到 internal raw
```

## 3. 额度确认 Gate

逐字稿、评论等可能消耗额度。

新增等待状态：

```text
waiting_for_user: external_cost_confirmation
```

在调用前输出：

```text
当前任务需要调用 Lingzao 的视频口播提取能力。
该操作可能消耗 Lingzao 积分。

将执行：
- Skill：Lingzao
- 能力：extract-video-copy
- 目标：提取公开视频口播文案
- 是否继续：是 / 否
```

不得静默消耗额度。

## 4. Evidence Coverage

统一状态：

```yaml
coverage:
  note_detail: available
  comments: available | missing | skipped | unsupported
  transcript: available | missing | skipped | manually_provided | failed
  video_file: unsupported
```

要求：

- 视频文件明确 `unsupported`；
- 手工逐字稿必须标记 `manually_provided`；
- 自动逐字稿失败不能写成 `missing`；
- 评论未请求和请求失败要区分；
- 不补造评论和逐字稿。

## 5. Invocation

每次外部调用单独记录：

```text
raw/lingzao/invocations/note-detail.json
raw/lingzao/invocations/comments.json
raw/lingzao/invocations/transcript.json
```

记录：

- operation；
- provider；
- source URL；
- exit code；
- started_at；
- completed_at；
- warnings；
- 是否需要积分确认；
- 不记录 API Key。

## 6. 用户提示

执行时显示：

```text
正在执行：Lingzao
当前能力：获取笔记详情
```

随后：

```text
正在执行：Lingzao
当前能力：获取公开评论
```

视频时：

```text
正在执行：Lingzao
当前能力：提取视频口播逐字稿
```

# 阶段 26：真实 Generation Provider

## 目标

把 generation 从确定性 Mock 升级为可切换真实 Provider：

```text
GenerationContext
→ 选题候选
→ 人工选题
→ 内容生成
→ 人工审核
→ 修订
```

## 1. Provider 接口

新增：

```text
xiaoba_workflow/generation_provider.py
```

统一接口：

```python
generate_topics(context) -> TopicCandidatePackage
generate_content(context, selected_topic, previous_revision, feedback) -> ContentPackage
```

支持：

```text
mock
codex
external
```

默认 `mock`。

## 2. Topic Runner Contract

输入：

```json
{
  "operation": "generate_topics",
  "generation_context": "...",
  "brief": "...",
  "count": 5,
  "output_dir": "..."
}
```

输出：

```text
topic-candidates.yaml
runner-manifest.json
```

## 3. Content Runner Contract

输入：

```json
{
  "operation": "generate_content",
  "generation_context": "...",
  "selected_topic": "...",
  "revision_number": 1,
  "previous_content_ref": null,
  "feedback": null
}
```

## 4. Traceability

每次真实生成必须记录：

- provider；
- model；
- prompt version；
- context ref；
- active rule refs；
- learning refs；
- selected topic；
- revision number；
- previous content ref；
- user feedback；
- warnings；
- unsupported claims；
- assumptions。

## 5. 内容边界校验

增加确定性 Validator：

- 不得引用不存在的个人经历；
- 不得使用未批准规则；
- 不得复制来源内容；
- 不得生成未经证据支持的具体数据；
- 不得违反用户禁区；
- 不得遗漏目标受众；
- 必须保留 traceability；
- 内容包不得包含 Personal Content 生命周期状态；
- `approve` 不发布。

## 6. 用户提示

选题生成：

```text
当前任务：生成小红书内容
当前阶段：生成选题
正在执行：内容生成 Provider
使用上下文：
- 已确认规则：5 条
- 学习来源：2 个
- 当前 Brief：已设置
```

正文生成：

```text
当前阶段：生成正文
正在执行：内容生成 Provider
当前选题：topic-002
当前版本：revision-001
```

修订：

```text
当前阶段：按反馈修订
正在执行：内容生成 Provider
上一版本：revision-001
用户反馈：请减少营销感，增加真实经历
```

# 阶段 27：用户反馈沉淀

## 目标

把当前任务中的修改反馈转化为可治理的候选规则。

正确链路：

```text
request_changes
→ 反馈分类
→ 候选偏好 / 候选规则
→ 用户确认
→ Personal Content
```

## 1. 反馈分类

支持：

```text
tone
structure
title_style
opening_style
evidence
personal_experience
marketing_intensity
length
format
forbidden_pattern
other
```

## 2. 候选规则

不得自动激活。

输出：

```text
feedback/governance-candidates.yaml
```

## 3. 用户确认

新增：

```bash
xiaoba-workflow confirm-feedback-rule tasks/<task-id> \
  --candidate-id feedback-rule-001 \
  --decision confirm
```

确认后再调用 Personal Content。

## 4. 用户提示

```text
检测到这次修改可能形成长期偏好：

“减少强营销表达，优先使用经验分享语气”

是否保存为候选规则？
- 保存并进入确认流程
- 仅用于本次修改
- 忽略
```

# 阶段 28：发布后复盘基础链路

## 目标

不实现自动发布，只实现：

```text
用户手工发布
→ 导入发布链接和数据
→ 复盘
→ 候选规则状态建议
```

## 1. 新任务类型

可新增：

```text
post_publish_review
```

或作为 generation 的后续独立任务。

## 2. 输入

支持：

- 发布后的公开链接；
- 24h/48h/7d 数据；
- 后台截图的手工结构化输入；
- 用户主观反馈。

## 3. 复盘输出

至少包含：

- 使用了哪些规则；
- 哪些机制可能有效；
- 哪些机制可能无效；
- 数据不足；
- 外部变量；
- 建议继续 testing；
- 建议升级 validated；
- 建议 deprecated；
- 不得自动修改规则状态。

# 阶段 29：用户体验优化

## 一、统一用户态语言

CLI 默认输出必须使用用户能理解的语言。

禁止默认只输出：

```text
stage=context_assembly
status=waiting_for_user
provider=real
```

应显示：

```text
当前任务：生成小红书内容
当前进度：准备生成上下文
状态：等待你补充内容要求
```

技术字段可以作为附加信息：

```text
技术信息：generation / context_assembly / waiting_for_user
```

## 二、统一任务标题

每个任务创建时生成用户态标题。

示例：

```text
学习单条小红书笔记
批量学习对标账号内容
基于个人规则生成小红书帖子
发布后内容复盘
```

## 三、Skill 执行提示

每个外部或专业节点执行前，必须输出：

```text
正在执行：Lingzao
正在执行：Hot Learning
正在执行：Personal Content
正在执行：内容生成 Provider
```

并说明：

```text
作用：
输入：
预计产物：
是否可能消耗额度：
```

示例：

```text
正在执行：Hot Learning
作用：拆解笔记中的内容机制
输入：已标准化的 EvidencePackage
预计产物：机制、可学习部分、规则建议和内容机会
是否可能消耗额度：否
```

## 四、阶段完成提示

每个阶段结束后输出：

```text
已完成：内容机制拆解
生成产物：
- raw/hot-learning/analysis.md
- analysis/analysis.yaml

下一步：
将机制导入 Personal Content，并进入规则治理
```

## 五、等待用户时的提示

等待状态必须明确说明：

1. 当前为什么停下；
2. 用户要做什么；
3. 具体命令；
4. 完成后会发生什么。

## 六、Blocked 提示

禁止只显示异常栈。

标准输出：

```text
任务未能继续。

失败节点：Lingzao 视频口播提取
原因：API 额度不足
已完成：
- 笔记详情采集
- Evidence 基础字段

未完成：
- 视频逐字稿

可选处理：
1. 充值后重试；
2. 手工补充逐字稿；
3. 跳过逐字稿继续，但分析质量会下降。
```

## 七、下一步引导

所有 CLI 命令结束时必须输出唯一、明确的下一步。

格式：

```text
下一步建议：
xiaoba-workflow run tasks/<task-id>
```

## 八、进度展示

`task-status` 默认显示：

```text
任务：基于个人规则生成小红书帖子
任务 ID：task-...
整体进度：4 / 7
当前阶段：等待选择选题
当前执行模块：Xiaoba 人工 Gate
已完成：
✓ 准备任务
✓ 组装个人上下文
✓ 生成选题
待完成：
○ 选择选题
○ 生成正文
○ 审核
○ 完成
```

增加：

```bash
xiaoba-workflow task-status tasks/<task-id> --technical
```

## 九、交互式命令

在不破坏脚本化使用的前提下，支持：

```bash
xiaoba-workflow start
```

交互式引导：

```text
你想做什么？
1. 学习一条小红书笔记
2. 批量学习对标账号
3. 基于已沉淀规则生成帖子
4. 复盘已发布内容
```

不要一次询问大量问题。

## 十、用户手册

更新：

```text
USER_MANUAL.md
```

按用户任务组织，而不是按代码模块组织。

# 阶段 30：统一诊断与配置

## 1. doctor --all

新增：

```bash
xiaoba-workflow doctor --all
```

输出：

```text
Xiaoba 核心工作流           正常
Lingzao                    可用 / 未配置 / 额度异常
Hot Learning               Mock / Codex 手工 / External
Personal Content           可用 / 未配置
内容生成 Provider          Mock / Codex / External
自动发布                    不支持
```

每项给出当前模式、是否 ready、风险和下一步命令。

## 2. 本地配置文件

支持：

```text
xiaoba.local.yaml
```

示例：

```yaml
providers:
  lingzao:
    mode: real
    skill_root: /path/to/lingzao
    timeout_seconds: 300

  hot_learning:
    mode: codex_manual

  personal_content:
    mode: real
    workspace: /path/to/workspace

  generation:
    mode: mock
```

要求：

- 不保存 API Key；
- secret 使用环境变量；
- 配置文件加入 `.gitignore`；
- 提供 `xiaoba.local.example.yaml`；
- CLI 参数和环境变量可覆盖配置。

# 阶段 31：run-until-gate

新增：

```bash
xiaoba-workflow run-until-gate tasks/<task-id>
```

行为：

- 每次仍只执行一个 executor；
- 自动继续普通阶段；
- 遇到 waiting、blocked、completed、external cost confirmation 时停止；
- 每阶段显示用户态进度；
- 不绕过人工 Gate；
- 不自动确认外部额度；
- 不自动发布；
- 支持 `--max-steps`；
- 支持 `--technical`。

# 阶段 32：代码与并发安全

## 1. 拆分 runtime.py

目标结构：

```text
xiaoba_workflow/
  orchestrator.py
  state_machine.py
  gates.py
  transitions.py
  executors/
    learning.py
    learning_batch.py
    generation.py
    post_publish_review.py
```

要求：

- orchestrator 只负责调度；
- executor 负责阶段业务；
- provider 独立；
- state transition 独立；
- 用户提示独立；
- 不进行大规模框架迁移；
- 不引入工作流引擎。

## 2. 用户提示模块

新增：

```text
xiaoba_workflow/presentation.py
```

负责用户态阶段名称、Skill 名称、当前任务说明、下一步建议、blocked 信息、waiting 信息和 technical 模式。

## 3. 并发写入

对以下操作增加锁或乐观锁：

- state；
- attach-learning；
- review；
- revision；
- governance；
- feedback candidate；
- task metadata。

要求：

- 原子 read-modify-write；
- 冲突时拒绝；
- 不静默覆盖；
- 保留 revision/version；
- 增加并发回归测试。

# 阶段 33：配置和开源工程清理

## 1. 删除历史字段

清理：

```yaml
stage_1_scope:
  mock_flows: false
```

历史开发信息移入 `CHANGELOG.md`。

## 2. 开源设施

补齐：

```text
LICENSE
CHANGELOG.md
CONTRIBUTING.md
.github/workflows/ci.yml
.github/ISSUE_TEMPLATE/
```

CI 至少运行：

```bash
python -m unittest discover -v
python -m compileall xiaoba_workflow scripts tests
python -m xiaoba_workflow validate-project
```

Python 矩阵建议：3.9、3.11、3.12。

## 3. 发布

创建 `v0.2.0`，Release Notes 说明本轮新增能力和仍未实现的边界。

# 测试要求

至少覆盖：

- Hot Learning capabilities、doctor、mock、codex_manual、external fake runner、timeout、partial output、Prompt version、中文输出和跨样本；
- Lingzao 评论、transcript、视频类型、额度确认、手工 transcript、失败状态、video unsupported、secret redaction、多 invocation；
- Generation mock、external fake provider、topic、content、request_changes、revision、unsupported claim、invalid personal claim、unapproved rule、traceability；
- 反馈分类、candidate、不自动激活、confirm、reject；
- 所有阶段用户态名称和 Skill 提示；
- waiting、blocked、technical 模式；
- `run-until-gate` 不绕过人工 Gate；
- `doctor --all`；
- attach-learning、review、state、revision、governance 并发冲突不丢数据。

# 最终验收场景

## 场景 A：单样本学习

```text
输入公开笔记链接
→ Lingzao 笔记详情
→ 可选评论
→ 可选视频逐字稿
→ Evidence
→ Hot Learning
→ Analysis
→ Personal Content mechanism intake
→ governance
→ completed
```

必须显示每个 Skill。

## 场景 B：批量学习

```text
输入账号或关键词
→ Lingzao 候选采集
→ 用户选样
→ 每个样本采集
→ Hot Learning 单样本拆解
→ 跨样本分析
→ Personal Content
→ completed
```

## 场景 C：生成

前置条件：

```text
Personal Content 已有用户画像、账号定位和 active rules
```

流程：

```text
输入 brief
→ 读取 Personal Content 规则上下文
→ 生成选题
→ 用户选题
→ 生成正文
→ 用户 request_changes
→ revision-002
→ approve
→ completed
```

不得发布。

## 场景 D：反馈沉淀

```text
request_changes
→ 候选长期偏好
→ 用户选择仅本次 / 保存候选
→ confirm
→ Personal Content
```

## 场景 E：发布后复盘

```text
用户提供发布链接和数据
→ Lingzao 获取公开信息
→ 复盘
→ 规则状态建议
→ 用户确认
```

# 完成报告格式

Codex 完成后返回：

1. 修改文件；
2. 新增命令；
3. 新增 Provider；
4. Hot Learning Runner 状态；
5. Lingzao 新增能力；
6. Generation Provider 状态；
7. 用户反馈沉淀状态；
8. 发布后复盘状态；
9. 用户态 CLI 示例；
10. Skill 执行提示示例；
11. `doctor --all` 示例；
12. `run-until-gate` 示例；
13. 并发修复；
14. 测试数量和结果；
15. 未完成项；
16. 当前真实 / Prompt / Mock 边界；
17. 是否可以发布 v0.2.0。

不得声称：

- Personal Content 用户画像已由 Xiaoba 自动读取或创建；
- Hot Learning 已有官方 API；
- Lingzao 能下载视频文件；
- Xiaoba 已支持自动发布；
- 三个 Skill 已经全部生产级真实接入。

# Codex 执行原则

1. 按阶段逐步实现；
2. 每阶段独立测试；
3. 不同时大改多个核心模块；
4. 发现架构问题先记录，不擅自扩展；
5. 不改变现有数据权威边界；
6. 不把 Personal Content 长期状态复制进 Xiaoba；
7. 不自动激活规则；
8. 不自动消耗外部额度；
9. 不自动发布；
10. 保留 Mock 模式；
11. 所有真实 Provider 必须可替换；
12. 所有外部输出必须经过 Normalizer 和 Validator；
13. 所有用户态提示必须有技术模式对应；
14. 所有人工 Gate 必须不可绕过；
15. 全部完成前保持版本为开发状态。
