# 小八努力工作的一天：轻量多 Skill 编排实施方案

> 建议文件名：`IMPLEMENTATION_PLAN.md`  
> 用途：作为新 Codex 项目的主实施规格。  
> 版本：v1.0

---

## 1. 项目目标

在一个新的 Codex 项目中，实现一套轻量、可持续、可恢复的小红书内容学习与生成工作流，串联以下三个外部 Skill：

1. `atian-create/lingzao-skill`
2. `popspacececilia-cmd/xhs-hot-learning`
3. `pp-jok/xhs-personal-content-skill`

本系统不是“一次分析一篇对标内容，然后立即生成一篇帖子”的固定流水线。

真实业务由两个独立但互相关联的循环组成：

```text
持续学习沉淀循环
        +
按需内容生成循环
```

### 持续学习沉淀循环

```text
对标账号 / 对标帖子
        ↓
Lingzao 获取公开证据
        ↓
本地标准化为 EvidencePackage
        ↓
XHS Hot Learning 进行单篇或跨样本分析
        ↓
本地标准化为 AnalysisPackage
        ↓
XHS Personal Content 导入 ContentMechanism
        ↓
持续积累证据、反例、机制和内容机会
        ↓
按需进入规则与内容资产治理
```

这条流程默认不生成帖子。

### 按需内容生成循环

```text
用户提出创作需求
        ↓
XHS Personal Content 读取长期沉淀
        ↓
构建 GenerationContext
        ↓
生成选题
        ↓
用户选择
        ↓
生成图文 / 插图 / 视频脚本 / 口播稿
        ↓
用户审阅和局部修改
        ↓
发布后反馈重新进入学习体系
```

内容生成依赖长期积累后的账号知识状态，而不是依赖最近分析的一条对标内容。

---

## 2. 项目定位

本项目是一个轻量编排层。

它只负责：

- 区分学习任务、批量学习任务和生成任务；
- 控制三个 Skill 的执行顺序；
- 为每个 Skill 提供当前节点的局部任务说明；
- 保存外部 Skill 的原始输出；
- 将原始输出标准化为本地中间对象；
- 校验中间对象是否合格；
- 保存任务状态；
- 在人工节点暂停；
- 接收人工决定后恢复；
- 保留必要的执行和映射记录。

它不负责：

- 替代三个 Skill 的专业能力；
- 建立通用工作流平台；
- 建立第二套账号画像；
- 建立第二套正式规则库；
- 自动批准候选规则；
- 自动发布小红书；
- 建设 Web UI；
- 引入数据库、消息队列或复杂工作流引擎；
- 自动大规模抓取或监控账号。

---

## 3. 核心职责边界

### 3.1 Lingzao

在本项目中负责：

```text
获取公开事实和原始素材
```

允许：

- 获取笔记详情；
- 获取账号公开资料；
- 获取账号近期帖子；
- 获取公开评论；
- 获取视频逐字稿；
- 获取公开互动数据；
- 返回标题、正文、图片、评论、逐字稿、指标和来源。

不依赖 Lingzao 稳定输出本项目定义的标准格式。

禁止由本项目直接接受其输出作为正式 EvidencePackage。

### 3.2 XHS Hot Learning

在本项目中负责：

```text
基于已有证据进行专业分析
```

允许：

- 区分事实、推断、缺失和限制；
- 分析标题、封面、正文、评论和数据关系；
- 提炼内容机制；
- 给出证据强度和替代解释；
- 判断账号适配；
- 给出原创迁移方向；
- 提出规则方向；
- 提出内容资产方向；
- 提出内容机会；
- 进行跨样本机制综合。

不依赖 Hot Learning 稳定输出本项目定义的标准 YAML。

禁止让其直接创建正式 RuleCard、批准规则、激活资产或生成正式帖子。

### 3.3 XHS Personal Content

在本项目中负责：

```text
长期机制、规则、内容资产、决策和正式生成
```

允许：

- 导入 ContentMechanism；
- 校验机制证据；
- 将机制转成候选规则；
- 将机制转成候选内容资产；
- 记录用户决定；
- 管理规则和资产生命周期；
- 构建 GenerationContext；
- 生成选题；
- 生成草稿；
- 执行局部修改；
- 保存来源和版本关系。

正式账号画像、机制、规则、内容资产、用户决定和生成记录，以该 Skill 的工作区为唯一权威。

本项目不得复制其正式领域模型并建立第二套长期状态。

---

## 4. 外部 Skill 不受控原则

三个 Skill 都是外部 Skill。

不能假设它们：

- 知道其他 Skill 的存在；
- 知道自己处于工作流哪个节点；
- 稳定遵守本项目的数据格式；
- 稳定输出 JSON 或 YAML；
- 不越过当前节点职责；
- 不输出额外建议；
- 不改变输出结构。

因此，本项目采用以下固定链路：

```text
标准输入
→ 节点约束 Prompt
→ 外部 Skill
→ 原始输出
→ 本地 Normalizer
→ 标准化中间对象
→ Validator
→ Orchestrator 决定推进 / 暂停 / 阻塞
```

不允许：

```text
外部 Skill 输出
→ 直接成为正式工作流对象
```

节点 Prompt 只是软约束。

真正可靠的控制来自：

- 原始输出单独保存；
- 本地 Normalizer；
- 本地 Validator；
- 任务状态文件；
- 目录写入边界；
- Personal Content 自身领域校验；
- 人工确认节点。

---

## 5. 责任模型

```text
外部 Skill
负责专业原始结果

Adapter
负责组装输入、调用 Skill、保存原始输出

Normalizer
负责字段提取、重命名、分类和格式转换

Validator
负责格式、边界、来源和最低质量校验

Orchestrator
负责流程推进、暂停、阻塞和恢复

Personal Content
负责长期对象的最终校验和持久化
```

### 5.1 Skill 的权力

Skill 可以判断：

- 内容是什么；
- 机制是什么；
- 哪些是推断；
- 哪些可能可迁移；
- 哪些方向可能成为规则或资产。

### 5.2 Normalizer 的权力

Normalizer 只能：

- 提取已有内容；
- 分类已有内容；
- 重命名字段；
- 统一类型；
- 标记缺失；
- 保存来源片段；
- 记录无法映射项。

Normalizer 不得：

- 新增机制；
- 新增专业结论；
- 为通过校验补造事实；
- 将推断改成事实；
- 自动提高置信度；
- 自行创建正式规则。

### 5.3 Validator 的权力

Validator 只能判断：

- 是否满足最低结构要求；
- 是否包含越界字段；
- 是否能回链来源；
- 是否允许进入下一节点。

Validator 不修改专业结论。

### 5.4 Orchestrator 的权力

Orchestrator 只决定：

- 当前执行哪个节点；
- 当前节点是否完成；
- 是否暂停；
- 是否阻塞；
- 是否进入下一阶段；
- 是否结束当前任务。

Orchestrator 不重新执行专业分析。

---

## 6. 任务类型

第一版至少支持三种任务。

### 6.1 `learning`

处理一个或少量对标帖子。

默认流程：

```text
task_intake
→ evidence_collection
→ evidence_normalization
→ analysis
→ analysis_normalization
→ mechanism_intake
→ aggregation
→ completed
```

默认不进入内容生成。

治理是可选分支。

### 6.2 `learning_batch`

处理一个对标账号或一批帖子。

流程：

```text
task_intake
→ benchmark_screening
→ sample_selection
→ 多篇 evidence_collection
→ 多篇 analysis
→ cross_sample_aggregation
→ mechanism_intake
→ optional_governance
→ completed
```

需要用户选择具体帖子时必须暂停。

### 6.3 `generation`

基于已有沉淀生成内容。

流程：

```text
task_intake
→ context_assembly
→ topic_generation
→ topic_selection
→ content_generation
→ review
→ focused_revision
→ completed
```

生成任务可以没有任何新的对标链接。

---

## 7. 治理策略

不能每分析一篇帖子就强制用户审批规则。

### 单篇学习完成时默认执行

- 保存样本；
- 导入机制；
- 给已有机制补充支持证据；
- 记录反例；
- 保存规则建议；
- 保存内容资产建议；
- 保存内容机会；
- 更新待验证问题。

### 进入治理的条件

满足以下任一条件时，可以创建治理提案：

- 用户明确要求沉淀为规则或资产；
- 同一机制在多个样本中重复出现；
- 已有明显正例和反例；
- 与账号画像高度相关；
- 可能显著影响后续生成；
- 到达定期治理时间；
- 跨样本综合明确推荐进入治理。

### 治理原则

- 单篇机制默认先积累；
- 规则和内容资产必须分开；
- 候选规则不得自动生效；
- 候选资产不得自动激活；
- 治理支持批量和延迟决策；
- 未完成治理不阻止后续继续学习；
- generation 只使用正式有效规则。

---

## 8. 轻量仓库结构

Codex 可以在不改变职责边界的前提下微调内部结构。

建议初始结构：

```text
xiaoba-content-workflow/
├── AGENTS.md
├── IMPLEMENTATION_PLAN.md
├── README.md
├── workflow.yaml
├── orchestrator.py
├── normalizers.py
├── validate.py
├── pyproject.toml 或 requirements.txt
│
├── adapters/
│   ├── lingzao_adapter.py
│   ├── hot_learning_adapter.py
│   └── personal_content_adapter.py
│
├── prompts/
│   ├── lingzao-evidence-only.md
│   ├── hot-learning-analysis-only.md
│   ├── hot-learning-cross-sample.md
│   ├── personal-content-governance.md
│   └── personal-content-generation.md
│
├── templates/
│   ├── task.yaml
│   ├── state.yaml
│   ├── evidence.yaml
│   ├── analysis.yaml
│   └── learning-summary.yaml
│
├── tasks/
│   └── .gitkeep
│
├── examples/
│   └── mock-task/
│
└── tests/
```

第一版不要引入：

- 数据库；
- Web UI；
- 消息队列；
- 通用 Agent 框架；
- 复杂事件总线；
- 分布式执行；
- 自动发布；
- 多 Agent 并行写同一任务。

---

## 9. 任务目录结构

```text
tasks/<task-id>/
├── task.yaml
├── state.yaml
├── feedback.md
├── run-log.md
│
├── raw/
│   ├── lingzao/
│   ├── hot-learning/
│   └── personal-content/
│
├── evidence/
│   └── evidence.yaml
│
├── analysis/
│   ├── analysis.yaml
│   └── learning-summary.yaml
│
├── governance/
│   └── proposals.md
│
└── content/
```

原则：

- 外部 Skill 原始输出永远保留；
- 标准化文件可以重新生成；
- 外部 Skill 不直接修改 `state.yaml`；
- Orchestrator 是任务流程状态的唯一写入者；
- Personal Content 工作区是长期内容状态的唯一权威。

---

## 10. 核心数据文件

### 10.1 `task.yaml`

```yaml
task_id: task-20260715-001
task_type: learning

source_type: xhs_note

sources:
  - type: url
    value: ""

goal: 持续学习并沉淀，不生成帖子

requested_outputs: []

generation_policy:
  auto_generate: false

created_at: ""
```

`task_type` 允许：

```text
learning
learning_batch
generation
```

第一版固定：

```yaml
generation_policy:
  auto_generate: false
```

任何学习任务完成后不得自动生成帖子。

### 10.2 `state.yaml`

只保留少量状态：

```text
running
waiting_for_user
blocked
completed
terminated
```

建议结构：

```yaml
task_id: task-20260715-001
task_type: learning

status: running
current_stage: evidence_collection
current_step: invoke_skill

completed_stages: []

waiting_for: null
next_stage: evidence_normalization

last_updated_at: ""
```

`current_step` 可使用：

```text
invoke_skill
normalize
validate
transition
```

### 10.3 `evidence.yaml`

```yaml
sample_id: sample-001

normalization:
  status: normalized
  warnings: []

source:
  source_type: xhs_note
  original_url: ""
  canonical_url: ""
  author: ""
  author_id: ""
  published_at: ""
  captured_at: ""

facts:
  title: ""
  body: ""
  tags: []
  cover: {}
  images: []
  transcript: ""

  metrics:
    likes:
    saves:
    comments:
    shares:

  comments: []

basic_structure:
  content_type: ""
  sections: []
  visible_cta: []

coverage:
  note_detail: available
  comments: missing
  transcript: missing
  local_video: missing

missing: []
warnings: []

source_paths: []
```

要求：

- 未获取值使用空值，不得伪造为 `0`；
- 只保存事实和基础结构；
- 不保存规则；
- 不保存账号适配；
- 不保存生成内容；
- 尽量保留原始字段路径。

### 10.4 `analysis.yaml`

```yaml
sample_id: sample-001

normalization:
  status: normalized
  warnings: []

mechanisms:
  - id: mechanism-001
    name: ""
    description: ""
    problem: ""
    solution: ""

    observed_facts:
      - text: ""
        source_ref: ""
        source_fragment: ""

    inferences:
      - text: ""
        source_fragment: ""

    pattern: []
    applicable_scope: []
    missing_information: []
    limitations: []
    alternative_explanations: []

    confidence: medium
    source_refs: []

transfer:
  learnable: []
  not_copyable: []
  account_fit: []
  originality_requirements: []

rule_suggestions: []
asset_suggestions: []
content_opportunities: []
questions: []
```

要求：

- 每个机制至少包含一条可观察事实；
- 事实尽量回链 `evidence.yaml`；
- 推断不得写入 `observed_facts`；
- `confidence` 只能为 `low`、`medium`、`high`；
- 不包含正式规则状态；
- 不包含用户决定；
- 不包含正式帖子；
- 无法映射字段进入 `normalization.warnings`。

### 10.5 `learning-summary.yaml`

```yaml
summary_id: summary-001
updated_at: ""

included_samples: []

mechanism_updates:
  - mechanism_ref: ""
    supporting_samples: []
    counter_samples: []
    observed_scope: []
    unsupported_scope: []
    confidence_before: low
    confidence_after: medium
    recommendation: continue_observing

new_mechanisms: []
governance_candidates: []
content_opportunities: []
open_questions: []

recommend_governance: false
```

---

## 11. 外部 Skill 标准化方式

### 11.1 Lingzao

优先采用确定性处理：

```text
Lingzao 实际命令或 JSON 输出
→ 保存 raw/lingzao/
→ Python 字段映射
→ evidence.yaml
```

Codex 必须检查 Lingzao 的实际：

- SKILL.md；
- Python 脚本；
- CLI；
- 命令参数；
- 返回结构；
- 测试。

不得只根据 README 猜测字段。

如果存在机器可读输出，应优先使用机器可读输出。

Lingzao Normalizer 负责：

- 字段映射；
- URL 规范化；
- 时间格式统一；
- 指标空值处理；
- 评论结构统一；
- coverage；
- missing；
- warnings；
- 原始字段路径。

不得根据标题、正文或逐字稿猜测缺失事实。

### 11.2 Hot Learning

其输出可能是 Markdown 或自然语言。

采用二次结构化提取：

```text
Hot Learning 原始分析
→ 保存 raw/hot-learning/
→ HotLearning Normalizer
→ analysis.yaml
```

Normalizer 可以使用窄职责提取 Prompt，但必须遵守：

- 只提取已有分析；
- 不新增机制；
- 不新增事实；
- 不新增规则建议；
- 原文未提供则留空；
- 无法判断则记录 warning；
- 每条事实和推断尽量保留来源片段；
- 不为了通过校验补内容。

### 11.3 Personal Content

正式领域对象必须通过其真实 CLI、服务或领域方法创建。

正确方式：

```text
analysis.yaml
→ PersonalContentAdapter 构建 payload
→ Personal Content 自身校验
→ 持久化 ContentMechanism / RuleCard / ContentAsset
```

不得：

- 直接编辑其存储文件；
- 绕过其校验；
- 在编排仓库复制正式规则；
- 自行模拟正式 RuleCard。

如果导入失败：

- 保存错误；
- 记录到治理结果；
- 不自行补造领域字段。

---

## 12. 标准化结果状态

Normalizer 返回以下状态之一：

```text
normalized
partially_normalized
normalization_failed
```

### `normalized`

满足当前节点全部最低要求，可以推进。

### `partially_normalized`

部分字段缺失，但可以进行有限分析。

必须把限制传给下游。

例如：

- 没有评论；
- 没有逐字稿；
- 没有本地视频；
- 无法验证真实镜头。

### `normalization_failed`

例如：

- 原始输出为空；
- 完全无法识别来源；
- 无法分开事实和推断；
- 无法找到任何可观察事实；
- 输出只有泛泛建议；
- 结构变化导致字段无法映射。

此时进入：

```yaml
status: blocked
waiting_for:
  type: normalization_review
```

可选动作：

- 重新调用 Skill；
- 调整节点 Prompt；
- 补充输入；
- 人工修正标准文件；
- 放弃当前样本。

---

## 13. 节点执行模式

每个外部 Skill 节点内部至少包含四个子步骤：

```text
invoke
normalize
validate
transition
```

### Lingzao 节点

```text
读取 task.yaml
→ Adapter 组装 Lingzao 调用
→ 原始输出保存到 raw/lingzao/
→ Lingzao Normalizer 生成 evidence.yaml
→ Evidence Validator
→ Orchestrator 推进或阻塞
```

### Hot Learning 节点

```text
读取 evidence.yaml
→ Adapter 组装分析上下文
→ 调用 Hot Learning
→ 原始输出保存到 raw/hot-learning/
→ Hot Learning Normalizer 生成 analysis.yaml
→ Analysis Validator
→ Orchestrator 推进或阻塞
```

### Personal Content 节点

```text
读取 analysis.yaml 或 generation task
→ Adapter 组装真实 payload
→ 调用 Personal Content
→ 保存原始响应
→ Personal Content 自身领域校验和持久化
→ Orchestrator 更新任务引用和状态
```

---

## 14. 跨样本聚合

持续学习必须支持跨样本综合。

Hot Learning 负责：

- 比较多个 AnalysisPackage；
- 判断机制是否相似；
- 识别重复模式；
- 识别正例和反例；
- 判断适用范围；
- 提出机制合并建议；
- 提出是否值得进入治理。

Personal Content 负责：

- 查找已有 ContentMechanism；
- 判断是否重复；
- 导入新机制；
- 给已有机制补充来源；
- 保存版本和来源；
- 创建候选规则或内容资产；
- 管理长期状态。

Orchestrator 负责：

- 选择需要参与综合的样本；
- 调用跨样本分析；
- 标准化 `learning-summary.yaml`；
- 判断是否发起治理任务；
- 不自动批准治理结果。

---

## 15. 生成流程

generation 任务通常只需要调用 Personal Content。

Orchestrator 提供：

- 本次创作目标；
- 内容形式；
- 数量；
- 长度；
- 时间要求；
- 用户指定内容机会；
- 用户显式指定的资产；
- 当前局部反馈。

Personal Content 提供：

- 当前账号画像；
- 有效规则；
- 相关机制；
- 已激活资产；
- 历史反馈；
- GenerationContext；
- 选题和草稿审计链。

正式生成只能使用：

- `approved`
- `testing`
- `validated`

不得默认使用：

- `candidate`
- `rejected`
- `deprecated`

不得自动选择候选规则。

不得自动激活资产。

不得自动发布。

---

## 16. 人工节点

必须暂停的情况：

- 账号主页候选帖子需要选择；
- 批量学习样本需要确认；
- 治理提案需要决定；
- 候选规则需要批准、测试、保留或拒绝；
- 内容资产需要激活、保留或废弃；
- 生成选题需要选择；
- 最终内容需要审阅；
- 用户反馈可能形成长期规则但含义不明确。

学习任务默认不因没有治理决定而无法完成。

治理提案可以保留在待处理池中。

---

## 17. Validator 最低要求

第一版不强制完整 JSON Schema。

Codex 可选择普通 Python、Pydantic、轻量 JSON Schema 或组合方式。

### Evidence 校验

至少检查：

- 文件存在；
- `sample_id` 存在；
- 原始 URL 存在；
- coverage 存在；
- 未获取指标没有伪造为 `0`；
- 不包含规则建议；
- 不包含正式规则状态；
- 不包含生成内容；
- 事实有可追踪来源。

### Analysis 校验

至少检查：

- 文件存在；
- mechanisms 是列表；
- 每个机制至少有一条 observed fact；
- confidence 合法；
- 事实可回链 Evidence；
- 推断没有混入 facts；
- 不包含正式规则状态；
- 不包含用户决定；
- 不包含正式帖子；
- 规则建议与资产建议分开。

### 状态校验

至少检查：

- 不允许跳过阶段；
- `waiting_for_user` 不能自动继续；
- 当前标准产物不存在不能推进；
- `completed` 不重复运行；
- `terminated` 不自动恢复；
- generation 不得由 learning 自动触发。

---

## 18. Skill 调用 Prompt

### `prompts/lingzao-evidence-only.md`

```text
你当前处于“小八努力工作的一天”工作流的公开证据采集节点。

当前只负责获取公开内容和可观察事实。

允许：

- 获取笔记详情；
- 获取账号公开信息；
- 获取近期帖子；
- 获取公开评论；
- 获取视频逐字稿；
- 返回标题、正文、图片、指标、评论和来源；
- 标记无法获取的信息。

禁止：

- 分析为什么爆；
- 提炼内容机制；
- 判断账号适配；
- 生成规则；
- 生成内容资产；
- 改写内容；
- 生成帖子；
- 修改 Personal Content 工作区。

请将完整原始结果输出到当前任务指定的 raw/lingzao/ 目录。

不要求你生成 evidence.yaml。
完成原始结果输出后停止。
```

### `prompts/hot-learning-analysis-only.md`

```text
你当前处于“小八努力工作的一天”工作流的内容分析节点。

上游已经完成证据采集和标准化。

必须读取当前任务的 evidence/evidence.yaml。

不得：

- 重新扫描素材收件箱；
- 重新调用 Lingzao；
- 重复采集已有字段；
- 修改素材状态。

当前只负责：

- 区分事实、推断、缺失和限制；
- 分析标题、封面、正文、评论和数据关系；
- 提炼 3 至 5 个核心机制；
- 给出证据强度；
- 给出替代解释；
- 判断可学习和不可照搬部分；
- 提出规则方向；
- 提出内容资产方向；
- 提出内容机会。

禁止：

- 创建正式规则；
- 批准规则；
- 激活资产；
- 修改账号画像；
- 生成正式帖子；
- 创建发布任务。

请将完整原始分析输出到当前任务指定的 raw/hot-learning/ 目录。

不要求你直接生成 analysis.yaml。
完成原始分析后停止。
```

### `prompts/hot-learning-cross-sample.md`

```text
你当前负责跨样本内容学习综合。

输入是多份已经标准化并通过校验的 analysis.yaml。

你的任务：

- 比较多个样本；
- 识别重复机制；
- 识别支持证据；
- 识别反例；
- 识别仅依赖特定作者人设或资源的因素；
- 判断机制适用范围；
- 给出现有机制应合并、拆分、补证据或继续观察的建议；
- 提出是否值得进入规则或内容资产治理。

禁止：

- 修改正式机制；
- 创建正式规则；
- 批准规则；
- 自动激活内容资产；
- 生成正式帖子。

输出完整原始综合分析到 raw/hot-learning/。

不要求直接生成 learning-summary.yaml。
```

### `prompts/personal-content-governance.md`

```text
你当前处于机制和规则治理节点。

读取：

- 当前任务 analysis.yaml 或 learning-summary.yaml；
- 当前账号必要画像；
- 当前账号已有机制、规则和内容资产摘要。

目标：

1. 导入合法 ContentMechanism；
2. 给已有机制补充来源或证据；
3. 判断哪些内容应：
   - 仅保留为机制；
   - 转为候选规则；
   - 转为候选内容资产；
   - 同时形成规则和资产；
   - 因证据不足继续观察；
4. 使用 Personal Content 已有领域能力；
5. 生成面向用户的治理提案。

禁止：

- 自动批准规则；
- 自动进入 testing；
- 自动激活内容资产；
- 自动生成帖子；
- 绕过已有校验直接修改存储文件。

正式对象必须通过 Personal Content 自身 CLI、服务或领域方法创建。

完成治理提案后停止，等待用户决定。
```

### `prompts/personal-content-generation.md`

```text
你当前处于正式内容生成节点。

只能使用：

- 当前账号画像；
- approved、testing、validated 规则；
- 用户显式授权的一次性候选规则；
- 用户显式选择的 active 内容资产；
- 当前 generation 任务要求；
- 当前局部反馈；
- 选定内容机会和必要样本摘要。

禁止：

- 使用未经授权的 candidate 规则；
- 自动选择候选资产；
- 使用 rejected 或 deprecated 规则；
- 修改规则或资产状态；
- 重新采集对标内容；
- 直接复制对标帖子；
- 虚构个人经历、案例和结果；
- 自动发布。

根据 task.yaml 中 requested_outputs 生成内容。

输出到当前任务 content/ 目录，并保留：

- 使用的有效规则；
- 使用的内容资产；
- 参考机制；
- 缺失信息；
- 风险；
- 审计信息。

完成后停止，等待用户审阅。
```

---

## 19. Codex 自主发挥范围

Codex 可以自主决定：

- Python 内部模块如何拆分；
- 是否保留单文件实现或少量模块；
- YAML 使用哪个成熟库；
- 是否使用 dataclass、TypedDict 或 Pydantic；
- 日志格式；
- CLI 参数；
- 测试目录；
- 错误类型；
- 任务 ID 和时间戳方式；
- Adapter 的调用封装；
- Normalizer 的具体提取方式；
- Lingzao 原始字段映射；
- Hot Learning 结构化提取 Prompt；
- Personal Content 真实接口调用方式；
- 部分标准化判定规则；
- 是否增加少量必要辅助文件。

Codex 自主调整必须满足：

- 简单；
- 可逆；
- 可测试；
- 可观察；
- 不增加不必要基础设施；
- 不改变核心业务边界；
- 调整原因写入文档或执行报告。

---

## 20. Codex 不得自主改变

未经用户确认，不得：

- 把学习和生成重新合并为一条强制流水线；
- 学习完成后自动生成帖子；
- 删除原始输出留存；
- 删除 evidence.yaml；
- 删除 analysis.yaml；
- 删除 state.yaml；
- 让外部 Skill 直接成为正式对象；
- 让 Normalizer 新增专业结论；
- 自动批准规则；
- 自动激活资产；
- 自动发布；
- 建立第二套正式规则库；
- 修改三个上游 Skill 的核心职责；
- 引入数据库；
- 引入 Web UI；
- 引入消息队列；
- 引入复杂工作流引擎；
- 用模型自动决定替代用户治理决策；
- 多 Agent 并行修改同一执行链路。

---

## 21. 实施阶段

### 阶段一：轻量骨架和 Mock 闭环

必须完成：

- 仓库结构；
- AGENTS.md；
- workflow.yaml；
- 任务类型；
- 数据模板；
- Adapter 接口；
- raw 目录；
- Normalizer；
- Validator；
- Orchestrator；
- 节点 Prompt；
- Mock learning；
- Mock learning_batch；
- Mock generation；
- 暂停和恢复；
- 基础测试。

不得调用真实外部 Skill。

### 阶段二：真实 Skill 接入

依次接入：

```text
Lingzao
→ Hot Learning
→ Personal Content
```

原则：

- 先确认真实调用方式；
- 不虚构 API；
- 不只看 README；
- 检查 Skill、脚本、CLI、模型和测试；
- 保存原始输出；
- 标准化与校验分离；
- 默认测试不消耗真实额度；
- 不修改上游仓库，除非有明确证据表明无法适配。

### 阶段三：真实场景验证

至少验证：

1. 单篇图文 learning；
2. 单篇视频 learning；
3. 对标账号 learning_batch；
4. 评论缺失；
5. 逐字稿缺失；
6. 本地视频缺失；
7. 重复样本；
8. 重复机制；
9. 支持证据与反例；
10. 延迟治理；
11. 规则冲突；
12. 独立 generation；
13. 局部反馈；
14. 明确长期反馈；
15. 任务中断和恢复。

只有真实问题证明有必要时，再增加更重的工程设施。

---

## 22. 阶段一 Codex 执行 Prompt

将本文件保存为项目根目录 `IMPLEMENTATION_PLAN.md` 后，向 Codex 提交：

```text
你负责实现“小八努力工作的一天”轻量多 Skill 编排系统。

首先完整阅读：

1. IMPLEMENTATION_PLAN.md
2. 当前仓库全部文件
3. 三个上游仓库中与本任务相关的实际实现：
   - atian-create/lingzao-skill
   - popspacececilia-cmd/xhs-hot-learning
   - pp-jok/xhs-personal-content-skill

研究上游仓库时不得只看 README。
需要检查相关 SKILL.md、references、playbooks、scripts、CLI、领域模型和测试。

本轮只执行阶段一：轻量骨架和 Mock 闭环。

必须完成：

1. 创建轻量仓库结构。
2. 创建 AGENTS.md。
3. 创建 workflow.yaml。
4. 实现 task_type：
   - learning
   - learning_batch
   - generation
5. 创建 task.yaml、state.yaml、evidence.yaml、analysis.yaml、learning-summary.yaml 模板。
6. 创建 Adapter、Normalizer、Validator 和 Orchestrator 的轻量实现。
7. 外部 Skill 原始输出必须保存到 raw/。
8. 正式 evidence.yaml 和 analysis.yaml 只能由本地 Normalizer 生成。
9. 实现状态推进、阻塞、暂停和恢复。
10. learning 任务默认在机制导入和聚合后完成，不得进入 generation。
11. governance 为可选和可延迟节点。
12. generation 必须是独立任务。
13. 实现节点 Prompt。
14. 实现 Mock learning 流程。
15. 实现 Mock learning_batch 流程。
16. 实现 Mock generation 流程。
17. 为以下场景编写测试：
    - 正常 learning；
    - 正常 learning_batch；
    - 正常 generation；
    - evidence 缺字段；
    - analysis 没有 observed facts；
    - 外部 Skill 输出越界；
    - 标准化失败；
    - 部分标准化；
    - 非法跳步；
    - waiting_for_user 时继续执行；
    - 用户决定后恢复；
    - learning 自动触发 generation；
    - completed 后重复执行。
18. 运行测试并修复失败。

本轮不得：

- 调用真实 API；
- 接入真实 Skill；
- 修改上游仓库；
- 实现 Web UI；
- 引入数据库；
- 引入消息队列；
- 引入复杂工作流引擎；
- 自动发布；
- 开始阶段二。

自主发挥：

你可以根据工程实际调整内部模块、CLI、日志、数据模型和轻量校验技术。

但不得改变：

- 学习和生成双循环；
- 外部 Skill 原始输出先保存再标准化；
- Normalizer 不新增专业结论；
- 候选规则人工确认；
- Personal Content 是长期状态唯一权威；
- learning 不自动生成内容；
- generation 独立启动。

当实现细节与方案冲突时：

1. 先检查上游真实实现；
2. 选择简单、可逆、可测试的方案；
3. 记录调整原因；
4. 不擅自改变核心业务边界；
5. 不影响阶段一的问题记录为后续事项，不提前实现。

完成后必须输出：

- 创建和修改文件；
- 关键实现；
- 三类 Mock 流程；
- 测试命令和结果；
- 自主调整内容；
- 明确未实现项；
- 阶段二接入前需要确认的问题。

测试未通过不得声称完成。
```

---

## 23. 阶段二 Codex 执行 Prompt

阶段一验收通过后提交：

```text
继续实现“小八努力工作的一天”轻量多 Skill 编排系统。

完整阅读：

1. AGENTS.md
2. IMPLEMENTATION_PLAN.md
3. 当前实现和测试
4. 三个上游 Skill 的实际源码和测试

本轮只执行阶段二：真实 Skill 接入。

按顺序完成：

1. Lingzao；
2. XHS Hot Learning；
3. XHS Personal Content。

要求：

一、Lingzao

- 使用真实存在的调用方式；
- 不虚构 Skill API；
- 只负责原始证据采集；
- 原始输出保存到 raw/lingzao/；
- 由本地 Normalizer 生成 evidence.yaml；
- 不分析机制；
- 不生成规则；
- 不生成帖子；
- 普通测试不得消耗真实额度；
- 真实测试必须显式启用。

二、Hot Learning

- 读取已有 evidence.yaml；
- 不重新调用 Lingzao；
- 原始输出保存到 raw/hot-learning/；
- 由本地 Normalizer 生成 analysis.yaml；
- 不创建正式规则；
- 不生成正式帖子；
- 无法映射的内容必须保留 warning 和来源片段；
- 不得为通过校验补造分析。

三、Personal Content

- 使用其已有机制、规则、内容资产和生成能力；
- 不在主仓库复制正式领域模型；
- 不绕过校验直接写存储文件；
- 候选规则不自动生效；
- 候选资产不自动激活；
- 用户决定前暂停；
- 正式生成只使用有效规则；
- 多次 learning 任务共享同一长期工作区；
- generation 不依赖最近一次分析。

允许自主决定：

- Adapter 结构；
- 原始输出格式；
- 调用封装；
- 错误处理；
- 少量辅助模块；
- Hot Learning 结构化提取方式；
- Personal Content payload 映射。

不得自主改变：

- 三个 Skill 的职责边界；
- 学习和生成双循环；
- 原始输出与标准化输出分离；
- 人工治理；
- Personal Content 单一权威；
- 禁止自动发布。

至少完成：

- 一条真实单篇 learning；
- 一次真实机制导入；
- 一次跨样本综合的最小验证；
- 一个独立 generation 任务；
- 不发布内容。

完成后输出：

- 三个 Skill 的真实调用方式；
- 原始输出位置；
- 字段映射；
- 标准化警告；
- 真实验证结果；
- 测试结果；
- 仍为 Mock 的能力；
- 已真实验证的能力；
- 存在限制；
- 阶段三场景清单。
```

---

## 24. 完成标准

只有同时满足以下条件，项目才算完成：

1. 支持 `learning`、`learning_batch` 和 `generation`；
2. learning 默认不生成内容；
3. 多次学习可以共享同一长期 Personal Content 工作区；
4. Lingzao 输出先保存 raw，再生成 EvidencePackage；
5. Hot Learning 输出先保存 raw，再生成 AnalysisPackage；
6. Normalizer 不新增专业结论；
7. 标准化失败不会静默推进；
8. 支持跨样本机制综合；
9. 单篇机制默认先积累；
10. 治理可以延迟和批量进行；
11. 候选规则不会自动生效；
12. generation 读取累计沉淀；
13. generation 不依赖最近一次学习任务；
14. 人工节点能够暂停和恢复；
15. Personal Content 是长期状态唯一权威；
16. 任务状态不依赖聊天记忆；
17. 失败不会伪装成成功；
18. 至少完成一个真实 learning 和一个独立 generation 验证；
19. 不自动发布；
20. 系统保持轻量、可读、可修改和可恢复。

---

## 25. 最终架构结论

```text
Lingzao
负责获取“看到了什么”

Hot Learning
负责分析“这些事实说明什么”

Personal Content
负责决定“哪些内容值得长期保留、哪些规则可以生效，以及如何生成自己的内容”

Adapter
负责“怎么调用外部 Skill”

Normalizer
负责“怎么把不受控输出变成标准对象”

Validator
负责“结果是否足以进入下一节点”

Orchestrator
负责“现在执行什么、何时暂停、何时结束”

用户
负责“哪些规则和资产真正进入长期使用”
```

系统运行频率：

```text
高频：
采集 → 分析 → 机制积累 → 跨样本修正

阶段性：
候选规则 / 内容资产治理

按需：
读取沉淀 → 生成内容 → 审阅 → 反馈
```

不要把系统重新实现成：

```text
分析一篇
→ 立即沉淀规则
→ 立即生成一篇帖子
```
