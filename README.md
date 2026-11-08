# MagicApp 后端

后端使用 Python、FastAPI 和 PostgreSQL。日常在本机修改代码并推送到 GitHub；发布时由
服务器拉取代码并重启 API。服务器 PostgreSQL 使用独立的 `magicapp_db` 数据库，不与其他项目
共用数据库或账号（数据库账号仍为 `magicapp`）。

## 目录说明

- `app/api`：HTTP 接口和路由。
- `app/core`：配置、统一错误响应和日志。
- `app/db/models`：按业务拆分的数据表模型。
- `migrations`：数据库表结构的版本变更脚本。
- `docker-compose.yml`：仅供本地开发启动 PostgreSQL；服务器使用已有 PostgreSQL。

## 本机开发

需要 Python 3.10 或更新版本。首次在 PowerShell 配置：

```powershell
cd D:\GZHU\HBuilderProjects\magicApp-backend-main\magicApp-backend-main
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

本机开发数据库可选用 Docker Desktop 启动：复制 `.env.example` 为 `.env`，然后设置本机
数据库连接，再运行 `docker compose up -d postgres`。数据库文件保存在被 Git 忽略的
`data/postgres` 目录。

完整的安装、配置、迁移、启动与注册/登录/登出/积分冒烟验证步骤见
[`docs/runbook.md`](docs/runbook.md)。

## 发布到服务器

如果 GitHub 后端仓库是私有仓库，先为服务器配置只读 Deploy Key，并在 GitHub 仓库设置中添加
该公钥；服务器 SSH 客户端应能通过 `ssh -T git@github.com` 验证。然后使用 SSH 地址
`git@github.com:NeviNa-hub/magicApp-backend.git` 执行下方 clone 命令。不要把 GitHub Token
写进命令、脚本或 `.env`。

服务器项目目录为 `/home/NBN/NBN/agent/magicApp-backend-main`。API 在服务器运行，连接
同一台服务器上的 PostgreSQL；MagicApp 使用独立的 `magicapp_db` 数据库和 `magicapp` 账号。

### 首次部署

后端使用名为 `magicAppEnv` 的独立 Python 虚拟环境；服务器需安装 Python 3.10 和 `venv`。

进入服务器项目父目录：

```bash
cd /home/NBN/NBN/agent
```

首次部署时从 GitHub 克隆后端仓库：

```bash
git clone git@github.com:NeviNa-hub/magicApp-backend.git magicApp-backend-main
```

后续发布时从 GitHub 拉取最新代码：

```bash
cd /home/NBN/NBN/agent/magicApp-backend-main && git pull --ff-only origin main
```

进入后端项目目录：

```bash
cd /home/NBN/NBN/agent/magicApp-backend-main
```

创建名为 `magicAppEnv` 的 Python 虚拟环境：

```bash
python3.10 -m venv magicAppEnv
```

激活虚拟环境；后续 `python` 和 `pip` 命令会使用 `magicAppEnv` 中的程序：

```bash
source magicAppEnv/bin/activate
```

在虚拟环境中升级 pip：

```bash
python -m pip install --upgrade pip
```

安装后端依赖：

```bash
python -m pip install -e .
```

复制服务器配置模板；若 `.env` 已存在，跳过此命令以免覆盖：

```bash
cp .env.example .env
```

限制服务器配置文件权限，避免其他系统用户读取数据库密码：

```bash
chmod 600 .env
```

编辑服务器专用配置：

```bash
nano .env
```

退出虚拟环境；不激活时可用 `magicAppEnv/bin/命令` 直接运行环境中的程序：

```bash
deactivate
```

在 `.env` 中设置服务器专用配置：

```env
APP_ENV=production
APP_HOST=127.0.0.1
APP_PORT=8001
APP_LOG_LEVEL=INFO
DATABASE_URL=postgresql+psycopg://magicapp:你的数据库密码@127.0.0.1:5432/magicapp_db
DATABASE_CONNECT_TIMEOUT=3
```

把数据库密码替换为 MagicApp PostgreSQL 账号的密码，不要使用服务器 root 密码。保存退出
nano：按 `Ctrl+O`、回车，再按 `Ctrl+X`。

### 数据库准备

如果 MagicApp 数据库和账号还未创建，以 root 身份执行以下命令。第一条会提示设置数据库
密码；若数据库或账号已存在，先检查，不要重复创建。

【
查看已有的数据库列表：runuser -u postgres -- psql -l

查某个数据库里面的表和信息：
runuser -u postgres -- psql -d magicapp_db        # 用系统账号
psql -h 127.0.0.1 -U magicapp -d magicapp_db     # 用应用账号，需输密码

进去之后互动式敲这些：
列出所有表：\dt
列出所有表和信息：\dt+ | grep magicapp
看某张表结构：\d users
查数据直接写 SQL：
select id, account, username, is_active, created_at from users order by id desc limit 10;
select count(*) from user_sessions where revoked_at is null;
select version_num from alembic_version;

不想进交互界面的话，加`-c` 一次一条：
runuser -u postgres -- psql -d magicapp_db -c "\dt"
runuser -u postgres -- psql -d magicapp_db -c "select count(*) from users;"
runuser -u postgres -- psql -d magicapp_db -c "select column_name, data_type, is_nullable, column_default from information_schema.columns where table_name='users' order by ordinal_position;"
】

```bash
runuser -u postgres -- createuser --login --pwprompt magicapp
runuser -u postgres -- createdb --owner=magicapp --encoding=UTF8 magicapp_db
runuser -u postgres -- psql -d magicapp_db -c 'GRANT ALL ON SCHEMA public TO magicapp'
```

查看现有数据库，确认 `magicapp_db` 已创建：

```bash
runuser -u postgres -- psql -l
```

在 MagicApp 数据库中创建或升级数据表：

```bash
cd /home/NBN/NBN/agent/magicApp-backend-main && magicAppEnv/bin/alembic upgrade head
```

### 用 systemd 启动 API

API 只监听本机 `127.0.0.1:8001`，不会占用 Planner 使用的 8000 端口。以 root 身份创建
systemd 服务文件：

```bash
nano /etc/systemd/system/magicapp-api.service
```

写入以下内容：

```ini
[Unit]
Description=MagicApp API
After=network.target postgresql.service

[Service]
Type=simple
WorkingDirectory=/home/NBN/NBN/agent/magicApp-backend-main
EnvironmentFile=/home/NBN/NBN/agent/magicApp-backend-main/.env
ExecStart=/home/NBN/NBN/agent/magicApp-backend-main/magicAppEnv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

保存后启用并启动：

```bash
systemctl daemon-reload
systemctl enable --now magicapp-api
systemctl status magicapp-api --no-pager
```

查看日志：

```bash
journalctl -u magicapp-api -n 100 --no-pager
journalctl -u magicapp-api -f
```

验证 API 和数据库：

```bash
curl http://127.0.0.1:8001/api/health
curl http://127.0.0.1:8001/api/ready
```

两个接口都应返回 `code: 200`；数据库检查的 `data.database` 应为 `ok`。接口文档在
`http://127.0.0.1:8001/docs`，只在服务器本机或安全隧道中访问。

### 后续更新

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


