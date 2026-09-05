# 实际部署状态

## 007 审查分支状态（2026-09-06）
- 新增知识—能力—课程联合架构提案：现场读取知识站 400 节点 / 673 边内嵌数据，确认旧版统计、重复能力域、关系方向和评价策略需要适配。设计见 docs/knowledge-curriculum-architecture.md，未实施迁移。
- 分支 audit/release-readiness-20260906；冻结基线 bab29ae / 数据 1.4。
- 3,671 节点和 6,695 边全量结构筛查，79 条定向语义审阅，24 学科 / 96 个应用层拆解草案。原 PDF、学习实证与全量语义审阅未完成。
- 可视化报告 audits/release-20260906/review.html；结论与发布计划见同目录 REPORT.md。
- anchors/edges 未修改；来源标签修复仅在审查分支，尚未发布。线上仍是下面记录的版本。
- npm run check 与 npm run workbench-test 通过；本地浏览器确认审阅页载入 79 条记录。

## 已核实（2026-09-06，Asia/Seoul）
- 站点 https://k12.yongle.school/workbench/，原首页已添加入口。
- 静态根目录 /var/www/k12.yongle.school；/zhishi/ 仍返回 200。
- 配置 /etc/nginx/sites-available/k12.yongle.school。
- Node 22.22.1；PostgreSQL 18.4。
- 基线 nginx 检查通过，有其他站点既有的重复域名 / hash 警告。

## 本次发布
- 分支 feat/primary-science-mapping-workbench。
- 线上运行提交 f551bfea727da1753e1c04391ba1185274a76451；后续仅交付文档更新不改变运行代码。
- /opt/k12-workbench/current 指向同名 releases 目录。
- systemd 单元 k12-workbench，回环 127.0.0.1:3412；独立 PostgreSQL 数据库 k12_workbench，系统/数据库角色 k12-workbench，通过 peer 连接。
- 发布包 SHA256：d9ac4916d4d1736e4e3d3ff11cb18acf3a35f22a29eecd7ded41039399d9ab60。
- 备份 /var/backups/k12-workbench/20260905T171355Z：nginx.conf、index.html、service、previous-release、database.sql。
- 初次发布因 nginx 旧进程在重载瞬间返回 404 自动恢复。修正健康检查短暂重试后部署成功；初次备份 20260905T153512Z。
- 仅新增工作台代理和首页入口，底座数据未写回。

## 验收
- 公网 HTTPS 从本机与服务器均返回 {ok:true,database:postgresql,datasetVersion:1.4}。
- 实际映射、规范化保存/读回、异会话 404、旧修订 409、原首页入口、/zhishi/ 通过。
- 留有 3 个匿名部署测试项目，均为虚构溶解任务；最终验收项目 b6f06dac-70cb-4eaa-95bb-d7025cf9f5de，修订 2。
- GitHub Actions 33975681558：check / workbench 成功。
- 界面验收使用本地同版本应用；自动浏览器访问生产域名超时，生产 HTTP 检查通过。

## 回退说明
备份包含原站配置和首页，可恢复二者并 nginx -t 后 reload；首次发布前无工作台服务，需 stop k12-workbench。不要把失败的初次发布目录当成已验收的上一版。后续发布继续使用提交归档与安装脚本，先备份。

## 006 公开案例
- /workbench/example.html 已发布；入口在工作台首页和导航。
- /workbench/?example=dissolving 载入经过服务端核验的未保存案例副本，保存由访客主动点击。
- 公开案例与私有项目数据隔离，无新增数据库表。可回退至 b490caa 服务目录，数据库无需回退。

- 006 可视化版 f551bfe：实验 SVG、屏内能力连线、详细依据折叠。已上线并推送 GitHub（包含此前网络失败未推送的案例提交）。上一运行版 1baaa94 可用来回退。
