# 部署

站点是**纯静态**：两个单文件图谱 + JSONL 数据集。整站 4.6MB，无后端无数据库。

```bash
bash deploy/build.sh                                  # 生成 dist/
tar czf dist.tgz -C dist . && scp dist.tgz 服务器:/tmp/
```

服务器侧（首次）：

```bash
sudo mkdir -p /var/www/k12.yongle.school
sudo tar xzf /tmp/dist.tgz -C /var/www/k12.yongle.school
sudo chown -R www-data:www-data /var/www/k12.yongle.school
sudo cp deploy/nginx.conf /etc/nginx/sites-available/k12.yongle.school
sudo ln -sfn /etc/nginx/sites-available/k12.yongle.school /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d k12.yongle.school --redirect
```

## 踩过的坑

- **这台机器上跑着几十个站点**，`nginx -t` 会连带校验全部。部署前先跑一次记下
  已有的告警（比如 `conflicting server name "skill.qiuyiwu.com"`），
  免得把别人的老问题当成自己引入的。
- **certbot 有两个账户**，`--non-interactive` 会直接失败。要从任一现有站点的
  `/etc/letsencrypt/renewal/*.conf` 里读 `account =` 和 `server =` 显式传进去。
- 更新只需重跑 build.sh 再覆盖 `/var/www/k12.yongle.school`，nginx 不用动。
