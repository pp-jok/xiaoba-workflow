# tasks 目录说明

`tasks/` 是运行时任务目录，不是示例目录。

开发环境中可能包含：

- Mock 端到端验收任务；
- Lingzao 真实 smoke test 任务；
- 手工逐字稿测试任务；
- Personal Content 本地 CLI 机制导入测试任务；
- 失败场景回归任务。

不要将任务数据提交到公共仓库。任务目录可能包含真实链接、raw 输出、分析结果、错误日志或人工提供的逐字稿。

保留规则：

- `tasks/.gitkeep` 用于保留空目录；
- `tasks/README.md` 用于说明目录用途；
- 真实示例应放到专门的 `examples/`，不要把运行时测试任务当作示例提交。

常见测试任务标识：

- `mock-e2e-acceptance`：Mock 全链路验收任务；
- `real-lingzao-smoke-test`：Lingzao 真实最小验证任务；
- `manual-transcript-test`：用户手工提供逐字稿的测试任务。

清理前请确认是否还需要保留 `raw/`、`evidence/`、`analysis/` 或 execution log 供排查。不要自动删除用户希望人工检查的真实 raw。
