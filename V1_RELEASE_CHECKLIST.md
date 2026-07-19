# Xiaoba Workflow v1.0.0 Release Checklist

## 必须通过

- [x] `python3 -m unittest discover -v`（218 tests passed）
- [x] `PYTHONPYCACHEPREFIX=/tmp/xiaoba-pycache python3 -m compileall xiaoba_workflow scripts tests`
- [x] `python3 -m xiaoba_workflow validate-project`
- [x] `python3 -m xiaoba_workflow doctor --all`
- [x] `python3 -m xiaoba_workflow --help`
- [x] `git diff --check`
- [x] `python3 -m build`
- [x] wheel 安装后从非仓库目录运行 `xiaoba-workflow --help`
- [x] wheel 安装后从非仓库目录运行 `xiaoba-workflow`

## 安全检查

- [x] 无 API Key、Token、Cookie、Authorization
- [x] 无真实任务数据
- [x] 无真实 Personal Content workspace
- [x] 无外部 Skill 源码
- [x] `tasks/` 只提交 `.gitkeep` 和说明文档
- [x] `lingzao/`、`hot-learning/`、`personal-content/`、`.xhs-personal-content-skill/` 未被 Git 跟踪

## 能力边界

- [x] 不宣称 Lingzao 由本仓库提供
- [x] 不宣称 Hot Learning 官方在线 API 已验收
- [x] 不宣称 Generation external 已完成所有真实服务验收
- [x] 不支持自动发布
- [x] demo 结果明确标记

## 发布动作

本轮不自动执行：

- PyPI 发布

本文件用于发布前审查。正式发布阶段允许在全部检查通过后执行：

- `git push`
- `git tag -a v1.0.0`
- GitHub Release
