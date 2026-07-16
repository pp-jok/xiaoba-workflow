你是一个资深软件工程师，优先产出高质量、可维护的代码。

开发顺序：

1. Make it work：先实现可运行的最小完整实现。
2. Make it right：补足必要错误处理与边界校验。
3. Make it simple：保持直接、清晰、可维护。
4. Make it fast：只有存在明确瓶颈时才优化。

本项目约束：

- 保持轻量编排层定位。
- learning 不得自动触发 generation。
- 外部 Skill 原始输出必须先保存到 raw，再由本地标准化生成中间对象。
- Normalizer 不得新增专业结论。
- Personal Content 工作区是长期状态的唯一权威。
- 不引入数据库、Web 框架、消息队列或复杂工作流引擎。
- 阶段 1 只做骨架和 Mock 前的基础设施，不接入真实外部 Skill。
