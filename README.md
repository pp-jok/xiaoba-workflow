# Xiaoba Workflow

Xiaoba Workflow 是一个本地轻量编排层，用于把小红书内容学习、方法沉淀、待审核内容生成和发布后复盘串起来。

v1.0.0 的“正式”指安装、初始化、工作区、任务交互、人工确认、结果摘要和恢复流程稳定可用；不表示所有第三方服务都由本仓库提供或已完成真实在线验收。

## 安装

```bash
python3 -m pip install "git+https://github.com/pp-jok/xiaoba-workflow.git@v1.0.0"
xiaoba-workflow
```

如果系统 pip 过旧，建议使用虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install "git+https://github.com/pp-jok/xiaoba-workflow.git@v1.0.0"
xiaoba-workflow
```

源码开发模式：

```bash
python3 -m pip install -e ".[test]"
python3 -m xiaoba_workflow start
```

## 开始使用

普通用户只需要运行：

```bash
xiaoba-workflow
```

或：

```bash
xiaoba-workflow start
```

首次启动会自动：

1. 创建用户工作区；
2. 写入安全默认配置；
3. 检查当前可用能力；
4. 显示任务首页；
5. 创建或恢复任务；
6. 自动运行到人工确认、暂停或完成。

默认用户工作区：

```text
~/.xiaoba-workflow/
```

可用环境变量覆盖：

```bash
export XIAOBA_WORKSPACE="/absolute/path/to/workspace"
```

## 支持的任务

首页包含：

1. 新建任务
2. 继续未完成任务
3. 查看最近结果
4. 配置能力
5. 查看系统状态
6. 退出

新建任务包含：

1. 学习一条小红书笔记
2. 学习一批对标内容
3. 生成一篇小红书帖子
4. 复盘一篇已发布内容

## 配置真实能力

```bash
xiaoba-workflow configure
```

Xiaoba 不会自动下载或安装外部 Skill。Lingzao、Hot Learning、Personal Content 需要用户按自己的本地环境配置。

API Key、Cookie、Token 不应写入配置文件或 Git 仓库。请使用环境变量或本地 `.env` 管理 secret。

## 演示、手工和真实结果

未配置 Lingzao 时，Xiaoba 不会假装读取真实链接。学习单条笔记时会询问：

1. 手工粘贴笔记正文；
2. 手工粘贴视频口播稿；
3. 运行演示流程；
4. 取消。

演示流程会明确标记为 `demo`，结果摘要显示“演示结果”。演示结果不能视为真实采集或真实学习结果。

## 能力边界

- Lingzao 真实采集需要用户自行安装和配置。
- Lingzao 能力受登录、API、额度和服务状态影响。
- Lingzao 不下载视频文件，自动逐字稿不保证。
- Hot Learning 不声明存在官方在线 API。
- Personal Content 必须有独立真实 workspace。
- Generation external 未配置时不能视为真实模型能力。
- 不自动发布小红书。
- 不自动激活长期规则。
- demo 结果不能视为真实学习结果。

完整边界见 [CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md)。

## 故障处理

任务暂停时，Xiaoba 会显示原因和恢复选项：

1. 重试；
2. 跳过可选步骤；
3. 手工补充内容；
4. 查看技术详情；
5. 暂停任务。

技术排查命令：

```bash
xiaoba-workflow status --technical
xiaoba-workflow doctor --all
xiaoba-workflow task-status <task-dir> --technical
```

更多开发与测试细节见 [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)。

## 安全边界

不要提交以下内容：

- `.env`
- API Key、Cookie、Authorization header
- `tasks/task-*`
- `lingzao/`
- `hot-learning/`
- `personal-content/`
- `.xhs-personal-content-skill/`

`.gitignore` 已默认忽略这些本地运行数据和外部 Skill 目录。
