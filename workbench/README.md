# 应用映射工作台（spec 005）

独立应用层：读取底座，只保存调用方的任务映射。数据版 1.4；应用契约 mapping/1。

## 本地运行
需要 Node >=22.13、Python 3。SQLite 内置于 Node，默认文件 `var/workbench.sqlite`（已忽略）。

```sh
npm run workbench
# http://127.0.0.1:3412/workbench/
npm run workbench-test
```

生产 PostgreSQL 才需要 `npm ci --prefix workbench --omit=dev`。通过 PGHOST、PGUSER、PGDATABASE 和 WORKBENCH_DB=postgres 配置连接，密码如果需要仅通过安全环境变量提供。生产使用专用系统用户和 PostgreSQL 本机 peer 认证，无共享业务库凭据。

## 接入
- `core.mjs`：mapTasks、catalog、metadata、validateProject，均只读。
- POST `/workbench/api/map`：`{title,grade,tasks:[{id,text}],limit?}`。
- GET `/workbench/api/catalog?grade=3&q=溶解&limit=30&offset=0`。
- POST `/workbench/api/validate`：核对项目，返回规范化快照，不保存。
- MCP `map_science_tasks`，在原 `node mcp/server.mjs` 中注册；参数与 HTTP 一致，返回 text 和 structuredContent。
- 网页 `/workbench/integration.html` 有完整示例。远程 MCP 尚未开放，HTTP URL 不冒充 MCP endpoint。

## 持久化与隔离
POST `/workbench/api/projects` 仅同源浏览器会话可写；GET 列表和详情仅返回 cookie 所属项目。cookie 为随机 HttpOnly/SameSite=Strict，生产 Secure，数据库仅存其 SHA256。每会话最多 50 个项目。
项目带 revision；更新用 owner+id+revision 条件写入，冲突返回 409，不静默覆盖。当前保存最新快照与修订号，不保存完整历史版本。导出文件不携带会话凭据。
会话不是用户账户，更不是教师身份。清除 cookie / 更换设备会失去当前项目列表入口，请导出迁移。未来组织授权见执行计划。

## 校验与约束
1–8 个任务，每个 4–400 字，候选 limit 1–12。目标年级必须是整数 1–6；底座范围必须全部在 G1–G6，citable 与 grain 复用原定义。输入以 stdin 传 Python，不放入 shell。
映射始终 pending。confirmed 需关系类型、原文摘录和至少 4 字理由。服务端重新读取 ID 对应的出处，不信任客户端的 verifiedBy、原文或年级。
原库分数只用于粗召回，不输出置信度。推导能力显式标识；所有人工确认只表达应用判断。
请求体 128 KB；写方法 20 次/分钟/IP，映射并发上限 2，Python 超时 15 秒。数据库与服务错误不返回内部细节。

## 数据版本
datasetVersion 加 datasetFingerprint 共同标识科学数据和配置。保存 / 导入要求当前版本，否则 409 提示重新召回。已保存项目读取保留原快照；不会在后台替换历史出处。

## 部署
使用 `deploy/workbench-release.sh` 打包已提交分支，再按 `deploy/workbench-install.sh` 安装。工作台单独挂 /workbench/，原站只新增入口。查看 STATE.md 的实际发布记录。
回滚：恢复备份 nginx 与首页，切回旧 release 软链接并重启服务；初次部署可停止服务后移除代理入口。不要删除应用数据库。

## 验证
核心范围与词面检索、恶意/错误输入、出处不可伪造、SQLite 重启、隔离/冲突、真实 HTTP 和 stdio MCP 均有测试。PostgreSQL 在部署环境另跑实际保存读回验证。浏览器验证记录见 docs/workbench-qa.md。
