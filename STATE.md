# 实际部署状态

## 已核实（2026-09-06，Asia/Seoul）
- 站点 https://k12.yongle.school/workbench/，原首页已添加入口。
- 静态根目录 /var/www/k12.yongle.school；/zhishi/ 仍返回 200。
- 配置 /etc/nginx/sites-available/k12.yongle.school。
- Node 22.22.1；PostgreSQL 18.4。
- 基线 nginx 检查通过，有其他站点既有的重复域名 / hash 警告。

## 本次发布
- 分支 feat/primary-science-mapping-workbench。
- 线上运行提交 1baaa94a4e0f9dd7c4aba9f04a7a795a2334f5a7；后续仅交付文档更新不改变运行代码。
- /opt/k12-workbench/current 指向同名 releases 目录。
- systemd 单元 k12-workbench，回环 127.0.0.1:3412；独立 PostgreSQL 数据库 k12_workbench，系统/数据库角色 k12-workbench，通过 peer 连接。
- 发布包 SHA256：4e3130db57bcc3109f95865504b8a34f32184e085d22f9360b9164778bf9a1a6。
- 备份 /var/backups/k12-workbench/20260905T165858Z：nginx.conf、index.html、service、previous-release、database.sql。
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
