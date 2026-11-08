# MagicApp 后端 Runbook（服务器）

约定：项目目录 `/home/NBN/NBN/agent/magicApp-backend-main`，venv `magicAppEnv`，
systemd 服务 `magicapp-api`，PostgreSQL 库 `magicapp_db`、账号 `magicapp`，端口 `8001`，
内网反向代理 `172.22.121.135:80`（nginx，见第 14 节）。

## 1. 查现有数据库

```bash
runuser -u postgres -- psql -l
```

预期：列表中有 `magicapp_db`；没有则执行第 2 节。

## 2. 首次装库

```bash
runuser -u postgres -- createuser --login --pwprompt magicapp
runuser -u postgres -- createdb --owner=magicapp --encoding=UTF8 magicapp_db
runuser -u postgres -- psql -d magicapp_db -c 'GRANT ALL ON SCHEMA public TO magicapp'
```

预期：无报错，`psql -l` 能看到 `magicapp_db`。

## 3. 配置 .env

```bash
cd /home/NBN/NBN/agent/magicApp-backend-main
cp -n .env.example .env && chmod 600 .env
nano .env
```

必填一行（密码换成真实值）：

```env
DATABASE_URL=postgresql+psycopg://magicapp:真实密码@127.0.0.1:5432/magicapp_db
```

预期：下面命令输出 `127.0.0.1:5432/magicapp_db`。

```bash
magicAppEnv/bin/python -c "from app.core.config import get_settings; print(get_settings().database_url.split('@')[-1])"
```

## 4. 日常备份

```bash
mkdir -p /var/backups/magicapp
chown postgres:postgres /var/backups/magicapp
STAMP=$(date +%F_%H%M%S)
runuser -u postgres -- pg_dump -Fc -d magicapp_db -f "/var/backups/magicapp/magicapp_db_${STAMP}.dump"
```

预期：dump 文件生成，`pg_restore -l 文件 | head` 能列出内容。若提示 `Permission denied`，说明备份目录不属于 `postgres`，先执行上面的 `chown`。

## 5. 执行迁移（先备份、先停服）

```bash
cd /home/NBN/NBN/agent/magicApp-backend-main
systemctl stop magicapp-api
magicAppEnv/bin/alembic upgrade head
echo "exit=$?"
```

预期：最后一条为 `Running upgrade 0008_accounts_default_points_100 -> 0009_alembic_version_255`，`exit=0`。

## 6. 确认迁移是否成功

```bash
cd /home/NBN/NBN/agent/magicApp-backend-main
magicAppEnv/bin/alembic current
magicAppEnv/bin/alembic heads
runuser -u postgres -- psql -d magicapp_db -c "SELECT version_num FROM alembic_version;"
```

预期：前两条都显示 `0009_alembic_version_255 (head)`，第三条返回同一版本且只有 1 行。

## 7. schema 抽查

```bash
runuser -u postgres -- psql -d magicapp_db <<'SQL'
SELECT column_name, data_type, column_default FROM information_schema.columns
WHERE table_name = 'users' AND column_name IN ('created_at', 'is_active') ORDER BY 1;
SELECT column_default FROM information_schema.columns
WHERE table_name = 'accounts' AND column_name = 'points_balance';
SELECT data_type FROM information_schema.columns
WHERE table_name = 'works' AND column_name = 'task_id';
SELECT conname FROM pg_constraint WHERE conname IN
('ck_generation_tasks_status', 'ck_works_status', 'uq_users_account', 'uq_accounts_user_id');
SELECT indexname FROM pg_indexes WHERE indexname IN
('ix_users_account', 'ix_user_sessions_token_hash', 'ix_generation_tasks_task_id');
SQL
```

预期：`is_active=true`、`created_at=now()`、`points_balance=100`、`task_id=integer`；
4 个约束都在；最后一条返回 0 行。

## 8. 启动 / 重启服务

```bash
systemctl start magicapp-api      # 首次
systemctl restart magicapp-api    # 更新后
systemctl status magicapp-api --no-pager
```

预期：`active (running)`。

## 9. 看日志

```bash
journalctl -u magicapp-api -n 100 --no-pager
journalctl -u magicapp-api -f
```

预期：没有 `UndefinedColumn`、`ProgrammingError`。

## 10. 冒烟验证

```bash
BASE=http://127.0.0.1:8001/api
curl -s "$BASE/health"; echo
curl -s "$BASE/ready"; echo

ACCOUNT="smoke_$(date +%s)"
curl -s -X POST "$BASE/auth/register" -H 'Content-Type: application/json' \
  -d "{\"username\":\"smoke\",\"account\":\"$ACCOUNT\",\"password\":\"SmokePass123\"}"; echo

LOGIN=$(curl -s -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
  -d "{\"account\":\"$ACCOUNT\",\"password\":\"SmokePass123\"}")
TOKEN=$(printf '%s' "$LOGIN" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["access_token"])')

curl -s "$BASE/points/myInfo" -H "Authorization: Bearer $TOKEN"; echo
curl -s -X POST "$BASE/auth/logout" -H "Authorization: Bearer $TOKEN"; echo
curl -s -o /dev/null -w 'repeat_logout=%{http_code}\n' \
  -X POST "$BASE/auth/logout" -H "Authorization: Bearer $TOKEN"
```

预期：`ready` 的 `database` 为 `ok`、`status` 为 `ready`；积分为 `points_balance=100`、`used_points=0`、`total=0`；登出 `code=200`；重复登出 HTTP `401`。
`ready` 若返回 503，看 `data.reason`：`missing_table`/`unversioned`/`behind`/`ahead`/`multiple_heads`，分别按第 5、6 节补齐或修正后再冒烟。

## 11. 迁移失败回退

```bash
systemctl stop magicapp-api
cd /home/NBN/NBN/agent/magicApp-backend-main
magicAppEnv/bin/alembic current
magicAppEnv/bin/alembic downgrade 0007_works_task_fk_to_pk
magicAppEnv/bin/alembic current
```

预期：`current` 回到 `0007_works_task_fk_to_pk`；服务保持停止，修完数据再重跑第 5 节。

## 12. 恢复备份（结构或数据损坏时）

```bash
systemctl stop magicapp-api
runuser -u postgres -- pg_restore --clean --if-exists -d magicapp_db \
  "/var/backups/magicapp/magicapp_db_<时间>.dump"
runuser -u postgres -- psql -d magicapp_db -c "SELECT version_num FROM alembic_version;"
```

预期：`alembic_version` 与备份时一致，确认后再启动服务。

## 13. 降级到指定版本

```bash
magicAppEnv/bin/alembic downgrade 0003_user_account_and_name
```

预期：`current` 显示 `0003_user_account_and_name`；执行前必须先备份。

## 14. Nginx 反向代理（内网 172.22.121.135:80）

配置文件在仓库 `deploy/nginx/magicapp.conf`。`172.22.121.135` 是 RFC1918 私网地址，
只在同一内网或 VPN 内可达，公网和手机流量访问不到，不能当作「已上线」。

### 14.1 判断是否已装

```bash
nginx -v
systemctl status nginx --no-pager
```

预期：`nginx/1.18.0`，`active (running)`。未装则 `apt install -y nginx`（Ubuntu 自带源即 1.18 系列）。

### 14.2 配置放哪里

Ubuntu 的 `nginx.conf` 会同时引入 `/etc/nginx/conf.d/*.conf` 和 `/etc/nginx/sites-enabled/*`：

- `sites-available/`：只存放，不生效；
- `sites-enabled/`：软链到这里才生效（推荐，便于启停）；
- `conf.d/`：同样生效，但文件名必须以 `.conf` 结尾，且没有 available/enabled 两段式。

两种都可用，优先 `sites-available` + 软链，避免与 `sites-enabled/default` 混放出现重复 server 块。

```bash
cd /home/NBN/NBN/agent/magicApp-backend-main
cp deploy/nginx/magicapp.conf /etc/nginx/sites-available/magicapp.conf
ln -s /etc/nginx/sites-available/magicapp.conf /etc/nginx/sites-enabled/magicapp.conf
nginx -t
systemctl reload nginx
```

预期：`syntax is ok`、`test is successful`。若报 `bind() to 172.22.121.135:80 failed`，
说明该 IP 不在这台机器网卡上，先 `ip addr show` 核对，不要改配置硬凑。

`sites-enabled/default` 可以保留：它监听 `*:80`，本配置按 IP 精确监听，请求会命中更具体的地址，
两者不冲突。之后改配置只需 `cp` → `nginx -t` → `reload`。

### 14.3 验证顺序（由近到远，定位层级）

1）服务器本机直连上游，确认应用本身正常：

```bash
curl -s http://127.0.0.1:8001/api/health; echo
curl -s http://127.0.0.1:8001/api/ready; echo
```

预期 `code=200`，`ready` 的 `data.status=ready`、`data.database=ok`。

2）服务器本机经 nginx：

```bash
curl -s http://172.22.121.135/api/health; echo
```

3）内网另一台机器（走真实网络）：

```bash
curl -s http://172.22.121.135/api/health; echo
curl -s http://172.22.121.135/api/ready; echo
```

预期与第 1 步一致。第 1 步通、第 3 步不通 → 问题在 nginx 或防火墙/路由，不在应用。

4）浏览器打开 `http://172.22.121.135/api/health` 应看到 JSON；`http://172.22.121.135/docs`
默认应是 404。

### 14.4 确认 8001 只绑回环

```bash
ss -ltnp | grep 8001
```

预期 `LISTEN 127.0.0.1:8001`。若出现 `0.0.0.0:8001` 或 `*:8001`：

```bash
systemctl cat magicapp-api
```

把 `ExecStart` 改为 `--host 127.0.0.1`，然后：

```bash
systemctl daemon-reload && systemctl restart magicapp-api
ss -ltnp | grep 8001
```

预期回到 `127.0.0.1:8001`。同时查防火墙是否放通过 8001，有则删除：

```bash
ufw status
ufw delete allow 8001/tcp
```

验证：内网另一台机器 `curl -m 3 http://172.22.121.135:8001/api/health` 应连接被拒或超时。

### 14.5 常见故障

- **502 Bad Gateway**：nginx 连不上 8001。查 `systemctl status magicapp-api`、
  `journalctl -u magicapp-api -n 50 --no-pager`、`ss -ltnp` 里的 8001、
  `curl http://127.0.0.1:8001/api/health`。
- **504 Gateway Timeout**：上游超过 `proxy_read_timeout` 60s。先看应用日志和数据库是否卡住
  （`/api/ready` 是否 503），确认是真慢查询再调超时，不要盲调。
- **404（被吃掉 `/api` 前缀）**：通常把 `proxy_pass` 写成了 `http://magicapp_api/;`（末尾带斜杠），
  location 前缀被替换。改成不带 URI 的写法后 `nginx -t`、reload。应用自身返回的 404 现在是
  统一结构 `{"code":40401,"message":"接口不存在","data":null}`；若看到 Nginx 的 HTML 404 页面，
  说明请求根本没到应用。
- **浏览器跨域报错**：页面在 `http://localhost:5173`，接口请求 `http://172.22.121.135`，属于跨源。
  两种解法：把页面来源精确加进 `.env` 的 `CORS_ALLOW_ORIGINS` 并 `systemctl restart magicapp-api`；
  或前端也经这个 nginx 提供、与 `/api` 同源，此时不需要 CORS。

### 14.6 文档路径是否开放

`/docs`、`/openapi.json`、`/redoc` 在配置里默认 `return 404`，理由是它们描述全部接口、参数与错误码，
而本服务没有鉴权门槛，schema 泄露会降低探测成本。需要联调时按配置文件注释切换成反代，reload 后生效，
用完恢复关闭。Swagger 页面的资源来自公网 CDN，纯内网浏览器里可能白屏，`/openapi.json` 不受影响。

### 14.7 正式上线差异（仅说明，不实现）

公网域名 + HTTPS 时：`server_name` 换域名；`listen 80` 只做 301 跳 443，业务放 `listen 443 ssl`；
证书用 Let's Encrypt 或企业证书；`CORS_ALLOW_ORIGINS` 换成真实前端 https 来源。nginx 始终是唯一入口，
8001 继续只绑 `127.0.0.1`。本仓库不含证书与公网配置。
