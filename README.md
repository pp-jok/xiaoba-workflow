# 小八努力工作的一天

轻量多 Skill 编排系统，用于串联小红书内容学习沉淀和按需内容生成。

当前阶段提供 learning 单样本 Mock 闭环，以及 learning_batch 候选筛选与人工选择骨架：

- 项目配置
- 模板文件
- 节点 Prompt
- 最小 CLI
- 项目基线校验

## CLI

```bash
python -m xiaoba_workflow --help
python -m xiaoba_workflow validate-project
python -m xiaoba_workflow doctor --skill lingzao
python -m xiaoba_workflow create-task --type learning --source-url "https://example.com/note/1"
python -m xiaoba_workflow task-status tasks/<task-id>
python -m xiaoba_workflow advance tasks/<task-id>
python -m xiaoba_workflow run tasks/<task-id>
python -m xiaoba_workflow select-samples tasks/<task-id> --ids sample-001 sample-003
python -m xiaoba_workflow resume tasks/<task-id>
python -m xiaoba_workflow block tasks/<task-id> --reason "需要人工检查"
python -m xiaoba_workflow unblock tasks/<task-id>
```

`validate-project` 只检查必要目录、模板、Prompt 和 `workflow.yaml` 是否存在，不执行业务流程。

`doctor --skill lingzao` 只检查 Lingzao provider 配置，不安装依赖、不修改配置、不输出 secret。

`create-task` 只创建任务目录和初始 `task.yaml`、`state.yaml`，不推进流程。

`advance` 只按 `workflow.yaml` 推进状态，不执行 Skill 或业务处理。

`run` 只执行当前阶段一次。目前支持 learning 的以下阶段：

- `task_intake`：校验任务基础信息并推进到 `evidence_collection`
- `evidence_collection`：写入 Mock Lingzao 原始输出到 `raw/lingzao/`，然后推进到 `evidence_normalization`
- `evidence_normalization`：将 `raw/lingzao/note-detail.json` 标准化为 `evidence/evidence.yaml`，运行 Evidence 校验，通过后推进到 `analysis`
- `analysis`：读取并校验 `evidence/evidence.yaml`，写入 Mock Hot Learning 原始 Markdown 分析到 `raw/hot-learning/`，然后推进到 `analysis_normalization`
- `analysis_normalization`：将 `raw/hot-learning/analysis.md` 标准化为 JSON 兼容的 `analysis/analysis.yaml`，运行 Analysis 校验，通过后推进到 `mechanism_intake`
- `mechanism_intake`：读取并校验 `analysis/analysis.yaml`，构建 Mock Personal Content 机制导入请求，保存原始响应和任务级外部对象引用，然后推进到 `aggregation`
- `aggregation`：汇总当前单样本 learning 的 Evidence、Analysis 和机制导入结果，生成 `analysis/learning-summary.yaml`，通过校验后完成任务

当前支持 learning_batch 的以下阶段：

- `task_intake`：校验账号来源并推进到 `benchmark_screening`
- `benchmark_screening`：写入 Mock Lingzao 账号与帖子原始输出，生成 `analysis/sample-candidates.json`，然后在 `sample_selection` 人工节点暂停
- `evidence_collection`：按 `analysis/selected-samples.json` 的顺序一次处理一个样本，写入 `raw/lingzao/samples/<sample-id>/`，更新 `analysis/batch-evidence-progress.json`；全部处理结束且至少一个成功后推进到 `evidence_normalization`
- `evidence_normalization`：按已采集成功样本一次标准化一个 Evidence，写入 `evidence/samples/<sample-id>/evidence.yaml`，更新 `analysis/batch-evidence-normalization-progress.json`；全部处理结束且至少一个 Evidence 可用后生成 `evidence/batch-evidence-index.json` 并推进到 `analysis`
- `analysis`：按 `evidence/batch-evidence-index.json` 中可分析样本顺序一次生成一个 Mock Hot Learning 原始分析，写入 `raw/hot-learning/samples/<sample-id>/`，更新 `analysis/batch-analysis-progress.json`；全部处理结束且至少一个成功后推进到 `analysis_normalization`
- `analysis_normalization`：按原始分析成功样本一次标准化一个 AnalysisPackage，写入 `analysis/samples/<sample-id>/analysis.yaml`，更新 `analysis/batch-analysis-normalization-progress.json`；全部处理结束且至少一个 Analysis 可用后生成 `analysis/batch-analysis-index.json` 并推进到 `cross_sample_aggregation`
- `cross_sample_aggregation`：读取至少两个逐样本 AnalysisPackage，生成 Mock Hot Learning 跨样本原始综合 `raw/hot-learning/cross-sample-analysis.md`、调用记录 `raw/hot-learning/cross-sample-invocation.json` 和标准化候选综合 `analysis/cross-sample-analysis.yaml`，通过校验后推进到 `mechanism_intake`
- `mechanism_intake`：读取并校验 `analysis/cross-sample-analysis.yaml`，只导入跨样本 `mechanism_candidates`，保存 Mock Personal Content 批量请求、响应、外部引用和 `analysis/batch-learning-summary.yaml`，通过校验后完成任务

`sample_selection` 不能用 `resume` 跳过，必须通过 `select-samples` 提交候选 ID。成功后写入 `analysis/selected-samples.json` 并进入 `evidence_collection`。当前批量流程只保存多样本 Lingzao raw、标准 Evidence、Hot Learning 原始 Markdown、逐样本标准 AnalysisPackage、跨样本候选综合、Personal Content Mock 请求/响应和外部引用；不创建正式规则、资产、画像或帖子。

当前支持 generation 的以下阶段：

- `task_intake`：校验 generation 任务未启用自动生成或自动发布，推进到 `context_assembly`
- `context_assembly`：读取 `content/generation-brief.json` 和显式附加的学习任务引用，生成 `raw/personal-content/generation-context-request.json`、`raw/personal-content/generation-context-response.json` 和 JSON 兼容的 `content/generation-context.yaml`，通过校验后推进到 `topic_generation`
- `topic_generation`：读取 GenerationContext，生成 `raw/personal-content/topic-generation-response.json` 和至少 5 条 `content/topic-candidates.json`，然后在 `topic_selection` 人工节点暂停
- `topic_selection`：必须通过 `select-topic` 选择一个候选，成功后写入 `content/selected-topic.json` 并进入 `content_generation`

`generation` 可在创建时传入 `--brief`，也可在 `context_assembly` 等待时通过 `set-generation-brief` 补充。学习来源必须通过 `attach-learning` 显式引用 completed 的 `learning` 或 `learning_batch` 任务，不会自动扫描历史任务。本轮不生成正式正文，不发布内容，不创建正式规则、资产或机制。

## Lingzao Provider

Lingzao 默认使用 Mock provider：

```yaml
skills:
  lingzao:
    provider: mock
```

默认 Mock 不会调用外部 Skill，也不会访问网络。真实 Lingzao 需要用户单独安装并配置稳定 runner，本项目不会自动下载 GitHub 仓库、安装 Skill、登录账号、读取浏览器隐私数据或发布小红书。

可以通过环境变量显式切换到 real：

```bash
export XIAOBA_LINGZAO_PROVIDER=real
export XIAOBA_LINGZAO_COMMAND='["python3", "/absolute/path/to/xiaoba/scripts/lingzao_runner.py"]'
export LINGZAO_CLIENT_PATH="/absolute/path/to/lingzao-skill-main/scripts/lingzao_client.py"
export XIAOBA_LINGZAO_TIMEOUT=300
python -m xiaoba_workflow doctor --skill lingzao
python -m xiaoba_workflow run tasks/<task-id>
```

Runner contract version 为 `1.0`。Real provider 使用参数数组执行命令，不使用 `shell=True`，并只调用固定入口：

```bash
lingzao-runner --input request.json --output /absolute/output-dir
lingzao-runner --capabilities
```

请求 JSON 至少包含：

```json
{
  "contract_version": "1.0",
  "operation": "collect_note",
  "task_id": "task-...",
  "sample_id": null,
  "source": "https://example.com/note/1",
  "output_dir": "/absolute/output-dir",
  "prompt_path": "/absolute/prompts/lingzao-evidence-only.md",
  "options": {
    "collect_comments": false,
    "collect_transcript": false
  }
}
```

支持的 operation：

- `collect_note`
- `collect_profile`
- `collect_posted_notes`

Runner 必须在 output directory 写入：

- `result.json`
- `runner-manifest.json`

`doctor --skill lingzao` 在 real 模式下会检查命令可执行、`--capabilities` 输出、contract version、三种 operation、超时配置和 prompt 是否存在。输出示例：

```text
provider: real
prompt: ok
command: configured
contract_version: 1.0
operations: collect_note, collect_profile, collect_posted_notes
requires_auth: True
login_state: configured
timeout_seconds: 300.0
```

仓库提供的 `scripts/lingzao_runner.py` 是一个薄桥接层：它把上述 runner contract 转换为真实 Lingzao CLI 的 `get-note-detail`、`get-user-info` 和 `get-user-posted-notes` 三个命令，再把返回 JSON 包装为 `result.json` 和 `runner-manifest.json`。它要求设置 `LINGZAO_CLIENT_PATH` 或 `LINGZAO_SKILL_ROOT`，真实 Lingzao 仍需 `~/.lingzao/config.json` 或 `LINGZAO_API_KEY`/`LINGZAO_BASE_URL`。

外部输出先进入任务目录 `.tmp/lingzao-*/`，通过 contract 校验后再写入 `raw/lingzao/` 或 `raw/lingzao/samples/<sample-id>/`。真实 runner 原始结果保留在 `raw/lingzao/external/`；内部兼容 contract 继续写为 `note-detail.json`、`profile.json`、`posted-notes.json` 和 `invocation.json`，因此 Evidence Normalizer 不需要感知 provider。缺失值保持为 `null`，不会补成 `0`。

失败时任务会阻塞在当前阶段，并在 `state.yaml` 的 `waiting_for.reason` 中记录错误分类，例如 `configuration_error`、`execution_error`、`timeout`、`nonzero_exit`、`invalid_output`、`incomplete_output` 或 `contract_adaptation_error`。stdout/stderr 会保存到 raw 目录的 execution log，日志会截断并脱敏，不输出 token、cookie、密码或完整敏感环境变量。

当前真实环境验证状态：已在本地定位到 Lingzao Skill 目录和真实 CLI 入口，但如果本机缺少 API Key、base URL、登录状态或可用积分，则不会执行真实采集。未执行真实采集时，只能说明 runner contract、doctor 和 fake runner 测试通过，不能推断真实 Lingzao 服务端采集能力已验证。

## Code Layout

- `xiaoba_workflow/cli.py`：参数解析、命令分发、输出结果
- `xiaoba_workflow/runtime.py`：当前状态机、阶段执行器、Mock Lingzao、Evidence 处理的运行时实现
- `xiaoba_workflow/batch.py`：learning_batch Mock 账号筛选、候选样本和样本选择处理
- `xiaoba_workflow/lingzao.py`：Lingzao Mock/Real provider 配置、doctor、子进程调用、raw contract adapter 和 manifest
- `scripts/lingzao_runner.py`：Lingzao runner contract 1.0 到真实 Lingzao CLI 的薄桥接入口
- `xiaoba_workflow/analysis.py`：Mock Hot Learning Markdown 到 AnalysisPackage 的标准化与 Analysis Validator
- `xiaoba_workflow/personal_content.py`：Mock Personal Content 机制导入请求、原始响应和外部对象引用生成
- `xiaoba_workflow/learning_summary.py`：单样本 learning 任务级汇总和 Learning Summary Validator

当前自定义 YAML 读取逻辑只用于简单的 `workflow.yaml`、`task.yaml` 和 `state.yaml` 元数据。业务 `.yaml` 文件从 `evidence/evidence.yaml` 开始采用 JSON 兼容内容：文件名保留 `.yaml`，内容用 `json.dump` 写入并用 `json.load` 读取。`analysis/analysis.yaml` 也沿用 JSON 兼容写法，不扩展为复杂自研解析器。

## 测试

```bash
python -m pytest
```

如果本地尚未安装 pytest，可先安装测试依赖：

```bash
python -m pip install -e ".[test]"
```
