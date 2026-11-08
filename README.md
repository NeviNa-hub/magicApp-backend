# MagicApp 后端

基于 FastAPI + PostgreSQL 的账号与积分后端。当前提供注册、登录、登出、当前用户积分查询，
以及健康/就绪检查；图片上传、生成任务、作品库等功能表结构已预留，但尚没有对应接口。

- 接口文档（服务启动后）：`/docs`、`/openapi.json`
- 部署与运维速查：[`docs/runbook.md`](docs/runbook.md)

## 1. 能力边界

| 已实现 | 说明 |
| --- | --- |
| 注册 | 创建用户并同时创建积分余额行，新用户默认 100 积分 |
| 登录 | 校验账号密码，签发 Bearer 令牌，数据库只保存令牌摘要 |
| 登出 | 撤销当前会话，重复登出按未登录处理 |
| 积分查询 | 查询当前用户余额与扣减流水，支持分页 |
| 健康检查 | `/api/health` 纯进程存活，不查库 |
| 就绪检查 | `/api/ready` 检查数据库连通性 + Alembic 版本是否与代码一致 |


## 2. 技术栈与版本

| 组件 | 版本要求 |
| --- | --- |
| Python | >= 3.10 |
| FastAPI | >= 0.115, < 1.0 |
| SQLAlchemy | >= 2.0, < 3.0 |
| Alembic | >= 1.14, < 2.0 |
| PostgreSQL 驱动 | `psycopg[binary]` >= 3.2 |
| 密码哈希 | `pwdlib[argon2]` |
| 配置 | `pydantic-settings` >= 2.7 |
| ASGI 服务器 | `uvicorn[standard]` >= 0.34 |

依赖以 [`pyproject.toml`](pyproject.toml) 为准。

## 3. 目录结构

```text
app/
├── main.py              # 应用入口：路由挂载、CORS、请求 ID、全局异常处理
├── api/
│   ├── deps.py          # Bearer 令牌鉴权依赖
│   ├── routes/          # 路由：auth / points / health / router 汇总
│   └── schemas/         # 请求与响应字段定义（Pydantic）
├── core/                # 配置、密码与令牌工具、统一响应、错误、日志
└── db/
    ├── session.py       # 引擎、连接池、请求级 Session
    ├── base.py          # SQLAlchemy Base
    └── models/          # 用户、会话、余额、流水、资产、任务、作品
migrations/versions/     # Alembic 迁移，0001–0009，单 head
docs/                    # runbook、教程、历史评审记录
```

## 4. 环境准备

### 本机（Windows PowerShell）

```powershell
cd D:\GZHU\HBuilderProjects\magicApp-backend-main\magicApp-backend-main
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

### 服务器（Linux）

服务器使用独立虚拟环境 `magicAppEnv`，项目目录 `/home/NBN/NBN/agent/magicApp-backend-main`：

```bash
cd /home/NBN/NBN/agent/magicApp-backend-main
python3 -m venv magicAppEnv
magicAppEnv/bin/pip install -e .
```

`pip install -e .` 会按 `pyproject.toml` 安装全部依赖，不需要另外手装 FastAPI/SQLAlchemy。

## 5. 配置项（`.env`）ss

| 配置项 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `DATABASE_URL` | 是 | 本机示例值 | PostgreSQL 连接串，库名用 `magicapp_db`，账号 `magicapp` |
| `APP_ENV` | 否 | `development` | 环境标识，当前仅用于标记 |
| `APP_LOG_LEVEL` | 否 | `INFO` | 日志级别 |
| `DATABASE_CONNECT_TIMEOUT` | 否 | `3` | 数据库连接/取连接超时秒数 |
| `SESSION_EXPIRE_DAYS` | 否 | `7` | 登录令牌有效期，允许 1–90 天 |
| `CORS_ALLOW_ORIGINS` | 否 | `http://localhost:5173` | 允许跨域的前端来源，逗号分隔 |
| `POSTGRES_PASSWORD` | 否 | 无 | 仅 `docker-compose.yml` 本地起库使用，应用不读取 |

服务器 `.env` 示例：

```env
APP_ENV=production
APP_LOG_LEVEL=INFO
DATABASE_URL=postgresql+psycopg://magicapp:你的数据库密码@127.0.0.1:5432/magicapp_db
DATABASE_CONNECT_TIMEOUT=3
SESSION_EXPIRE_DAYS=14
CORS_ALLOW_ORIGINS=http://localhost:5173,https://你的前端域名
```

CORS 来源必须与浏览器地址栏逐字一致：协议、域名、端口不能差，末尾不能带 `/`。
`http://localhost:5173`、`https://localhost:5173`、`http://127.0.0.1:5173` 是三个不同来源。
前端与 API 同域部署或使用 Vite `server.proxy` 时，浏览器视角同源，不需要配置 CORS。

## 6. 数据库与迁移

首次需先创建数据库和账号（以 `postgres` 管理身份执行一次即可）：

```bash
runuser -u postgres -- createdb -O magicapp magicapp_db
```

迁移命令（在项目目录、激活虚拟环境后执行；服务器用 `magicAppEnv/bin/alembic`）：

```bash
alembic upgrade head        # 首次/升级：应用全部未执行迁移
alembic current             # 当前库版本
alembic heads               # 代码中的 head，当前为 0009_alembic_version_255
alembic downgrade -1        # 回退一步；指定版本用 alembic downgrade <revision>
```

- 首次部署从 `0001` 依次升到 `0009`；之后每次发布只跑 `upgrade head`。
- 迁移前先备份，迁移时先停服务；具体命令见 [runbook](docs/runbook.md)。
- 只改模型不建迁移会导致真实库缺列，接口报 500；已应用的迁移不要回头修改，新增变更请新建迁移。
- 新增迁移的 revision id 必须 ≤ 32 字符（0009 已把版本表字段扩到 255，但仍建议保持简短）。

确认是否成功：`alembic current` 与 `alembic heads` 输出一致，且 `/api/ready` 返回
`data.status=ready`。不一致时 `/api/ready` 会返回 503 并带 `data.reason`
（`missing_table` / `unversioned` / `behind` / `ahead` / `multiple_heads`）。

## 7. 启动与重启

服务器（systemd）：

```bash
systemctl start magicapp-api
systemctl restart magicapp-api
systemctl status magicapp-api
journalctl -u magicapp-api -n 50 --no-pager
```

手动前台启动（调试用）：

```bash
magicAppEnv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
```

本机：

```powershell
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8001
```

`--host 127.0.0.1` 表示只监听本机，外部必须经 Nginx 等反向代理访问。**监听地址和端口不通过
`.env` 配置项控制**，以 systemd 的 `ExecStart` 或上面的 uvicorn 启动命令为准。

## 8. Nginx 反向代理

仓库已提供 [`deploy/nginx/magicapp.conf`](deploy/nginx/magicapp.conf)：监听内网
`172.22.121.135:80`，只转发 `/api/`，默认把 `/docs`、`/redoc`、`/openapi.json` 返回 404。
部署：

```bash
cp deploy/nginx/magicapp.conf /etc/nginx/sites-available/magicapp.conf
ln -s /etc/nginx/sites-available/magicapp.conf /etc/nginx/sites-enabled/magicapp.conf
nginx -t && systemctl reload nginx
```

关键两行（`proxy_pass` 末尾不能带 `/`，否则 `/api` 前缀会被吃掉导致全站 404）：

```nginx
location /api/ {
    proxy_pass http://magicapp_api;
}
```

需要浏览器访问 Swagger 时，注释掉配置里的 `return 404` 块并启用下方被注释的 `proxy_pass`。
该配置是内网 HTTP；若要绑定公网域名，需另加 `server_name` 与 HTTPS（证书），前端为 https 时
API 也必须是 https。跨域仍需 `CORS_ALLOW_ORIGINS`，HTTPS 不能替代 CORS。

## 9. 接口清单与鉴权

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | 否 | 注册，body：`username`、`account`、`password` |
| POST | `/api/auth/login` | 否 | 登录，body：`account`、`password` |
| POST | `/api/auth/logout` | 是 | 登出，无 body |
| GET | `/api/points/myInfo` | 是 | 积分查询，query：`page`、`page_size` |
| GET | `/api/health` | 否 | 进程存活 |
| GET | `/api/ready` | 否 | 数据库与迁移版本就绪 |

受保护接口请求头：

```http
Authorization: Bearer <access_token>
```

令牌来自登录响应的 `data.access_token`，默认 7 天过期（`SESSION_EXPIRE_DAYS` 可调）。
登出后同一令牌立即失效。积分查询参数：`page` 默认 1（≥1），`page_size` 默认 20（1–100），
流水按时间倒序。

统一响应格式：

```json
{"code": 200, "message": "操作成功", "data": {}}
```

## 10. 错误码

| HTTP | `code` | 含义 |
| --- | --- | --- |
| 200 | `200` | 成功 |
| 401 | `40101` | 密码错误 |
| 401 | `40102` | 未登录：令牌缺失、格式错误、无效、过期或已登出 |
| 401 | `40103` | 账号不存在，请注册 |
| 403 | `40301` | 账号已停用 |
| 404 | `40401` | 接口不存在（路径未匹配） |
| 405 | `40501` | 请求方法不被允许 |
| 409 | `40902` | 账号已注册 |
| 422 | `42201` | 请求参数不合法 |
| 500 | `50001` | 服务端或数据库异常 |
| 503 | `50001` | `/api/ready` 数据库不可用或迁移版本不一致 |

## 11. 常见故障排查

| 现象 | 常见原因 | 处理 |
| --- | --- | --- |
| 接口 500，日志 `column ... does not exist` | 模型有新增列，库没跑迁移 | `alembic current` / `alembic heads`，执行 `alembic upgrade head` |
| `/api/ready` 503，`reason=behind/missing_table` | 迁移落后或没建版本表 | 停服后 `alembic upgrade head`，再启动 |
| `/api/ready` 503，`reason=database_unavailable` | 库未启动、连接串/密码/库名错误 | 查 `DATABASE_URL`、`pg_isready`、数据库日志 |
| 502 Bad Gateway | uvicorn 没启动或端口不一致 | `systemctl status magicapp-api`、`ss -ltnp \| grep 8001` |
| 404，路径变成 `/auth/login` | 反向代理吃掉了 `/api` | `proxy_pass` 不要带路径后缀，保留原始 URI |
| 浏览器跨域报错 | 来源不在白名单或写法不完全一致 | 配置 `CORS_ALLOW_ORIGINS` 并重启；注意协议/端口/末尾斜杠 |
| 401 `40102` | 未带令牌、令牌过期或已登出 | 重新登录并替换本地令牌 |

更完整的迁移、备份、回退步骤见 [docs/runbook.md](docs/runbook.md)。

## 12. 已知限制

- 无登录/注册速率限制，账号枚举（登录区分“账号不存在/密码错误”）是有意保留的取舍。
- 历史用户可能没有 `accounts` 行，积分接口按 0 返回；不会自动补行。
- 无自动化测试与 CI；发布前按 runbook 冒烟。
- 积分流水分页缺少 `(user_id, created_at)` 复合索引，大数据量下会多扫。
- 监听地址/端口不来自配置文件，改端口需改 systemd 或 uvicorn 启动命令。

## 13. 文档

- 部署、备份、迁移验证、回退：[docs/runbook.md](docs/runbook.md)
- 代码逐层讲解：[docs/backend_tutorial.md](docs/backend_tutorial.md)
- 2026-11-07 历史评审记录：[docs/code_review_2026-11-07.md](docs/code_review_2026-11-07.md)（历史文档，结论以当前代码为准）



# 后续更新的操作流程

本机先提交并推送：

```powershell
git add .
git commit -m "后端功能说明"
git push origin main
```

然后在服务器更新代码、同步依赖、应用迁移并重启 API：

```bash
cd /home/NBN/NBN/agent/magicApp-backend-main && git pull --ff-only origin main

source magicAppEnv/bin/activate

magicAppEnv/bin/pip install -e .
magicAppEnv/bin/alembic upgrade head
systemctl restart magicapp-api
systemctl status magicapp-api --no-pager
curl http://127.0.0.1:8001/api/ready
```

只有数据库表结构变化时才会有新的迁移需要应用。执行迁移前应先备份数据库；不要删除
服务器数据库目录或运行 `docker compose down -v`。


## 数据库迁移和重启
```bash
cd /home/NBN/NBN/agent/magicApp-backend-main
systemctl stop magicapp-api
git pull --ff-only origin main

mkdir -p /var/backups/magicapp
chown postgres:postgres /var/backups/magicapp
STAMP=$(date +%F_%H%M%S)
runuser -u postgres -- pg_dump -Fc -d magicapp_db -f "/var/backups/magicapp/magicapp_db_${STAMP}.dump"
ls -lh /var/backups/magicapp/

magicAppEnv/bin/alembic current    # 应为 0003_user_account_and_name
magicAppEnv/bin/alembic heads      # 应为 0009_alembic_version_255 (head)
magicAppEnv/bin/alembic upgrade head
magicAppEnv/bin/alembic current    # 应为 0009_alembic_version_255 (head)

systemctl start magicapp-api
curl -s http://127.0.0.1:8001/api/ready
```

## 本地查看表

本机 PostgreSQL 启动后，可用 DBeaver 连接 `127.0.0.1:5432`，数据库名为 `magicapp_db`，
用户名为 `magicapp`。服务器数据库不开放公网端口；需要查看服务器表时，用服务器上的 `psql` 或
通过 SSH 隧道安全连接。

# 查看接口文档
## 用 Swagger 页面查看接口并发请求：
curl http://127.0.0.1:8001/docs
## 或者通过 SSH 隧道把服务器端口安全转到本机，再用本机浏览器打开 Swagger 页面： 
ssh -L 8001:127.0.0.1:8001 root@li-AI