# K12 能力底座与应用映射工作台

## 目标与技术
让教育应用用稳定课标 ID 描述任务能力，保留来源与人工映射判断。
底座沿用 Node ESM + Python 零依赖；`workbench/` 使用原生网页、Node HTTP、生产 PostgreSQL、开发 SQLite（Node >=22.13）。

## 约定
- 开工读 TASKS.md、STATE.md、相关 spec；收工更新。
- 检索算法复用 tools/mapper.py，对外呈现复用 mcp/present.mjs。
- 新只读查询模块登记 scripts/no-writeback.mjs；遵守 CONTRACT.md。
- 仅提交本次明确改动的文件，不使用 git add . 或 git add -A。
- 工作台新增需求先记 spec，再实现；执行 npm run workbench-test 和底座检查。

## 边界
- 映射只存独立应用数据库，不能写回 anchors/、edges/、ledger/。
- 应用映射确认不等于教师审定，也不等于学生掌握。
- 不收集学生身份与成绩；不把字面召回分数当置信度。
- 密钥、密码、个人数据不入 git、文档或日志。
- 不修改其他站点；部署先备份并核对产物，再健康检查。

## 档位与部署
G3：持久化服务需验证输入、会话隔离、协议和实际 UI。
本任务负责 /workbench/ 发布，STATE.md 是实际状态。原静态图谱保留，不执行旧发布脚本覆盖全站。

## 已完成阶段
005 于 2026-09-06 完成。后续从 TASKS.md Next 与 docs/primary-science-plan.md 继续；线上精确版本和备份以 STATE.md 为准。
