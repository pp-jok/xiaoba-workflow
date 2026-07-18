# 能力矩阵

本矩阵描述当前仓库的真实能力边界。不要把 `mock_verified` 或 `prompt_driven` 理解为外部 Skill 已完整真实接入。

## 状态枚举

- `real`：真实本地代码或真实外部命令已接入。
- `partially_real`：已有真实入口或局部真实验证，但能力不完整。
- `prompt_driven`：由 Codex 按 Prompt 产出原始分析，再由本地代码标准化。
- `mock`：确定性 Mock 实现。
- `local_workflow`：本地状态机、校验、人工 gate 等真实代码。
- `not_implemented`：未实现。
- `contract_verified`：本地 runner/provider 契约和 fake runner 已验证，但未真实在线调用。

## 当前能力

| 能力 | 当前实现 | 模式 | 验证状态 | 已知限制 |
| --- | --- | --- | --- | --- |
| `learning` 单样本闭环 | Lingzao raw -> Evidence -> Hot Learning raw -> Analysis -> Personal Content intake -> summary | `partially_real` + `local_workflow` | `verified` | Hot Learning 仍是 Prompt/本地标准化，不是外部程序 |
| Lingzao `collect_note` | Real Provider + runner contract 1.0 | `partially_real` | `contract_verified` | fake runner 已验收；真实在线受 API、登录、额度影响；不下载视频文件 |
| Lingzao `collect_comments` / `collect_transcript` | 成本确认 gate + 多 invocation 保存 + 内部 raw 合并 | `partially_real` | `contract_verified` | fake runner 已验收；真实在线 comments/transcript 未完整验收 |
| Lingzao `collect_profile` / `collect_posted_notes` | runner contract 已定义 | `partially_real` | `fake_runner_verified` | 真实账号采集未完整验收 |
| Lingzao transcript | 真实返回、用户跳过或手工输入 | `partially_real` | `contract_verified` | 自动逐字稿不保证；跳过或失败会进入 coverage/missing；手工逐字稿标记为 `manually_provided` |
| Lingzao video file | 明确不支持 | `not_implemented` | `not_verified` | `coverage.video_file` 为 `unsupported` |
| Evidence Normalizer | 本地标准化与 Validator | `local_workflow` | `verified` | 不补造事实；缺失指标保持 `null` |
| Hot Learning Runner | `scripts/hot_learning_runner.py` contract 1.0 | `mock` / `codex_manual` / `external` | `contract_verified` | 没有声称官方 API；external 需要用户自配命令 |
| Hot Learning 单样本分析 | Runner/Prompt + 本地 Normalizer | `prompt_driven` + `mock` | `verified` | mock/codex_manual 可用；真实 external 未在线验证 |
| Hot Learning 批量分析 | Mock 原始分析 + 本地 Normalizer | `mock` | `mock_verified` | 不调用真实 Hot Learning |
| Personal Content mechanism intake | 本地 CLI `import-mechanism` + 编排适配 | `partially_real` | `verified` | 主项目只保存请求、响应和外部引用 |
| Personal Content governance rule | `propose-governance-rule` + `confirm-governance-rule` | `partially_real` | `verified` | 只接规则候选/确认；资产治理未接 |
| Personal Content generation context | `show-generation-context` 读取 active rules | `partially_real` | `verified` | 只读取 approved/testing/validated 规则；不扫描候选规则 |
| `learning_batch` | 多样本 Mock 采集、标准化、分析、跨样本综合、机制导入 | `mock` + `local_workflow` | `mock_verified` | 真实批量 Skill 未验证 |
| `generation` context assembly | Mock 或 real Personal Content context | `partially_real` | `verified` | real 只读取规则上下文，不调用真实生成模型 |
| `generation` topic generation | 本地候选选题生成或 external provider contract | `mock` / `external` | `mock_verified` + `fake_runner_verified` | external 仅契约验证，未接真实模型 |
| `generation` content package | 本地待审内容包生成或 external `generate_content` contract | `mock` / `external` | `mock_verified` + `fake_runner_verified` | request changes 可生成 revision 2；真实模型未在线验证；不发布 |
| review/revision | 本地人工 gate | `local_workflow` | `verified` | `approve` 只完成任务，不发布 |
| feedback governance candidates | `request_changes` 生成候选偏好，`confirm-feedback-rule` 记录决策 | `local_workflow` | `verified` | 不自动激活，不自动写入长期规则 |
| post_publish_review | 用户提供公开发布链接后生成复盘建议 | `local_workflow` | `mock_verified` | 不自动改规则状态，不发布 |
| `doctor --all` | 汇总核心、Lingzao、Hot Learning、Personal Content、Generation、发布状态 | `local_workflow` | `verified` | doctor 不执行真实采集 |
| `run-until-gate` | 自动执行普通阶段直到 waiting/blocked/completed | `local_workflow` | `verified` | 不绕过人工 gate，不确认外部额度 |
| UX Lite `start` | 四入口交互、创建任务并运行到下一人工 gate 或完成 | `local_workflow` | `verified` | 只优化本地交互，不新增 Skill、Provider 或发布能力 |
| UX Lite `setup` | 生成保守本地配置，不写入 secret | `local_workflow` | `verified` | 已有 `xiaoba.local.yaml` 不会被静默覆盖 |
| 用户态进度与摘要 | 默认隐藏内部 stage、runner、contract 和 artifact 路径；technical 模式保留细节 | `local_workflow` | `verified` | 不改变底层 workflow 和文件产物 |
| publishing | 未实现 | `not_implemented` | `not_verified` | 明确不支持自动发布 |

## 当前不应宣称

- 不要说“三个 Skill 已完整真实接入”。
- 不要说“Hot Learning 有真实程序调用”。
- 不要说“可自动发布小红书内容”。
- 不要把手工逐字稿当成 Lingzao 自动获取成功。
- 不要把 Lingzao fake runner 的 comments/transcript 验收当成真实在线验收。
- 不要把 Generation external fake runner 验收当成真实模型验收。
- 不要把本项目目录当成 Personal Content 长期数据库；长期状态仍以 Personal Content workspace 为权威。
