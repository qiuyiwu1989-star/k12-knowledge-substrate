# 实际部署状态

## 已核实（2026-09-05）
- 现站 k12.yongle.school，静态根目录 /var/www/k12.yongle.school。
- 配置 /etc/nginx/sites-available/k12.yongle.school。
- Node 22.22.1；PostgreSQL 18.4。
- 基线 nginx 检查通过，有其他站点既有的重复域名 / hash 警告。

## 本次发布
- 分支 feat/primary-science-mapping-workbench；本任务负责工作台发布。
- 工作台尚未部署；目标 /workbench/、回环 3412、独立数据库 k12_workbench。
- 不覆盖静态全站和其他站点配置。

## 发布后记录
补充实际提交、备份位置、服务状态与健康检查。
