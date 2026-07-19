# Xiaoba Workflow 使用手册

## 1. 第一次使用

安装后直接运行：

```bash
xiaoba-workflow
```

Xiaoba 会自动创建本地工作区、写入安全默认配置，并显示当前能力。

默认工作区：

```text
~/.xiaoba-workflow/
```

如需指定工作区：

```bash
XIAOBA_WORKSPACE="/absolute/path/to/workspace" xiaoba-workflow
```

## 2. 学习一条小红书笔记

在首页选择：

```text
新建任务 → 学习一条小红书笔记
```

如果 Lingzao 已配置，Xiaoba 会按流程获取公开内容并继续分析。

如果 Lingzao 未配置，Xiaoba 会询问：

1. 手工粘贴笔记正文；
2. 手工粘贴视频口播稿；
3. 运行演示流程；
4. 取消。

演示流程会明确标记为演示结果，不代表真实读取了链接。

## 3. 学习一批对标内容

在首页选择：

```text
新建任务 → 学习一批对标内容
```

批量学习会先准备候选样本，并在需要你选择样本时暂停。选择后继续执行。

## 4. 生成一篇小红书帖子

在首页选择：

```text
新建任务 → 生成一篇小红书帖子
```

Xiaoba 会读取可用的个人内容规则，生成选题候选。你需要选择一个选题，然后进入正文生成和审核。

审核时可以：

1. 通过；
2. 修改；
3. 暂不处理。

选择修改时，Xiaoba 会单独询问修改意见，并生成新版本。

## 5. 复盘一篇已发布内容

在首页选择：

```text
新建任务 → 复盘一篇已发布内容
```

Xiaoba 只生成复盘建议，不会自动修改 Personal Content 规则，也不会发布内容。

## 6. 继续未完成任务

运行：

```bash
xiaoba-workflow
```

选择：

```text
继续未完成任务
```

Xiaoba 会展示最近未完成任务，并从原来的人工确认或暂停位置继续。

## 7. 查看最近结果

运行：

```bash
xiaoba-workflow
```

选择：

```text
查看最近结果
```

你可以直接查看完成摘要，不需要打开 YAML 文件。

## 8. 配置真实能力

运行：

```bash
xiaoba-workflow configure
```

配置项包括：

1. Lingzao；
2. Personal Content；
3. 内容分析方式；
4. 内容生成方式；
5. 恢复安全默认设置。

Xiaoba 不会把 API Key、Token、Cookie 写入配置文件。请使用环境变量或本地 `.env`。

## 9. 任务暂停怎么办

blocked 时，Xiaoba 会给出有限恢复选项：

1. 重试；
2. 跳过可选步骤继续；
3. 手工补充内容；
4. 查看技术详情；
5. 暂停任务。

不要手工修改 `state.yaml`。

## 10. 查看技术信息

普通使用不需要这些命令。排障时可用：

```bash
xiaoba-workflow status --technical
xiaoba-workflow doctor --all
xiaoba-workflow task-status <task-dir> --technical
```

开发者请阅读 [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)。

## 11. 重要边界

- Lingzao 真实采集需要用户自行安装和配置。
- Lingzao 不下载视频文件，逐字稿不保证自动成功。
- Hot Learning 不声明官方在线 API。
- Personal Content 必须有独立真实 workspace。
- 不自动发布小红书。
- 不自动激活长期规则。
- 演示结果不能视为真实学习结果。
