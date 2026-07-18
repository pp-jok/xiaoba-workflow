# 能力矩阵

本矩阵描述当前仓库的真实能力边界。不要把 `mock_verified` 或 `prompt_driven` 理解为外部 Skill 已完整真实接入。

## 状态枚举

- `real`：真实本地代码或真实外部命令已接入。
- `partially_real`：已有真实入口或局部真实验证，但能力不完整。
- `prompt_driven`：由 Codex 按 Prompt 产出原始分析，再由本地代码标准化。
- `mock`：确定性 Mock 实现。
- `local_workflow`：本地状态机、校验、人工 gate 等真实代码。
- `not_implemented`：未实现。

## 当前能力

| 能力 | 当前实现 | 模式 | 验证状态 | 已知限制 |
| --- | --- | --- | --- | --- |
| `learning` 单样本闭环 | Lingzao raw -> Evidence -> Hot Learning raw -> Analysis -> Personal Content intake -> summary | `partially_real` + `local_workflow` | `verified` | Hot Learning 仍是 Prompt/本地标准化，不是外部程序 |
| Lingzao `collect_note` | Real Provider + runner contract 1.0 | `partially_real` | `partially_verified` | 受 API、登录、额度影响；不下载视频文件 |
| Lingzao `collect_profile` / `collect_posted_notes` | runner contract 已定义 | `partially_real` | `fake_runner_verified` | 真实账号采集未完整验收 |
| Lingzao transcript | 真实返回或手工输入 | `partially_real` | `partially_verified` | 自动逐字稿不保证；手工逐字稿标记为 `manually_provided` |
| Lingzao video file | 明确不支持 | `not_implemented` | `not_verified` | `coverage.video_file` 为 `unsupported` |
| Evidence Normalizer | 本地标准化与 Validator | `local_workflow` | `verified` | 不补造事实；缺失指标保持 `null` |
| Hot Learning 单样本分析 | Prompt + 本地 Normalizer | `prompt_driven` | `verified` | 当前没有稳定 CLI/API runner |
| Hot Learning 批量分析 | Mock 原始分析 + 本地 Normalizer | `mock` | `mock_verified` | 不调用真实 Hot Learning |
| Personal Content mechanism intake | 本地 CLI `import-mechanism` + 编排适配 | `partially_real` | `verified` | 主项目只保存请求、响应和外部引用 |
| Personal Content governance rule | `propose-governance-rule` + `confirm-governance-rule` | `partially_real` | `verified` | 只接规则候选/确认；资产治理未接 |
| Personal Content generation context | `show-generation-context` 读取 active rules | `partially_real` | `verified` | 只读取 approved/testing/validated 规则；不扫描候选规则 |
| `learning_batch` | 多样本 Mock 采集、标准化、分析、跨样本综合、机制导入 | `mock` + `local_workflow` | `mock_verified` | 真实批量 Skill 未验证 |
| `generation` context assembly | Mock 或 real Personal Content context | `partially_real` | `verified` | real 只读取规则上下文，不调用真实生成模型 |
| `generation` topic generation | 本地候选选题生成 | `mock` | `mock_verified` | 不是外部生成服务 |
| `generation` content package | 本地待审内容包生成 | `mock` | `mock_verified` | 生成 reviewable package，不发布 |
| review/revision | 本地人工 gate | `local_workflow` | `verified` | `approve` 只完成任务，不发布 |
| publishing | 未实现 | `not_implemented` | `not_verified` | 明确不支持自动发布 |

## 当前不应宣称

- 不要说“三个 Skill 已完整真实接入”。
- 不要说“Hot Learning 有真实程序调用”。
- 不要说“可自动发布小红书内容”。
- 不要把手工逐字稿当成 Lingzao 自动获取成功。
- 不要把本项目目录当成 Personal Content 长期数据库；长期状态仍以 Personal Content workspace 为权威。
