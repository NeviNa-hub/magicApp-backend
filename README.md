# MagicApp 后端

后端使用 Python、FastAPI 和 PostgreSQL。日常在本机修改代码并推送到 GitHub；发布时由
服务器拉取代码并重启 API。服务器 PostgreSQL 使用独立的 `magicapp` 数据库，不与其他项目
共用数据库或账号。

## 目录说明

- `app/api`：HTTP 接口和路由。
- `app/core`：配置、统一错误响应和日志。
- `app/db/models`：按业务拆分的数据表模型。
- `migrations`：数据库表结构的版本变更脚本。
- `docker-compose.yml`：仅供本地开发启动 PostgreSQL；服务器使用已有 PostgreSQL。

## 本机开发

需要 Python 3.12 或更新版本。首次在 PowerShell 配置：

```powershell
cd D:\GZHU\HBuilderProjects\magicApp-backend-main\magicApp-backend-main
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

本机开发数据库可选用 Docker Desktop 启动：复制 `.env.example` 为 `.env`，然后设置本机
数据库连接，再运行 `docker compose up -d postgres`。数据库文件保存在被 Git 忽略的
`data/postgres` 目录。

## 发布到服务器

如果 GitHub 后端仓库是私有仓库，先为服务器配置只读 Deploy Key，并在 GitHub 仓库设置中添加
该公钥；服务器 SSH 客户端应能通过 `ssh -T git@github.com` 验证。然后使用 SSH 地址
`git@github.com:NeviNa-hub/magicApp-backend.git` 执行下方 clone 命令。不要把 GitHub Token
写进命令、脚本或 `.env`。

服务器项目目录使用 `/home/NBN/NBN/agent/magicApp-backend-main`。首次部署前，需要服务器
管理员在现有 PostgreSQL 中创建独立的 `magicapp` 数据库和 `magicapp` 登录账号。不要使用
`weekend_planner` 数据库或账号，也不要开放数据库端口给公网。

### 首次部署

在服务器 SSH 终端执行：

```bash
sudo mkdir -p /home/NBN/NBN/agent/magicAppDB
sudo chown "$USER":"$USER" /home/NBN/NBN/agent/magicAppDB
sudo useradd --system --home-dir /home/NBN/NBN/agent/magicApp-backend-main --shell /usr/sbin/nologin magicapp 2>/dev/null || true
cd /home/NBN/NBN/agent
if [ -d magicApp-backend-main/.git ]; then
  cd magicApp-backend-main
  git pull --ff-only origin main
else
  git clone git@github.com:NeviNa-hub/magicApp-backend.git magicApp-backend-main
  cd magicApp-backend-main
fi
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .
cp .env.example .env
sudo chown magicapp:magicapp .env
sudo chmod 600 .env
sudo chown -R magicapp:magicapp /home/NBN/NBN/agent/magicApp-backend-main
nano .env
```

在 `.env` 中设置服务器专用配置：

```env
APP_ENV=production
APP_HOST=127.0.0.1
APP_PORT=8001
APP_LOG_LEVEL=INFO
DATABASE_URL=postgresql+psycopg://magicapp:你的数据库密码@127.0.0.1:5432/magicapp
DATABASE_CONNECT_TIMEOUT=3
```

把数据库密码替换为你创建 PostgreSQL 用户时设置的密码。该账号密码只用于 MagicApp，不能
复用服务器 root 密码。保存退出 nano：按 `Ctrl+O`、回车，再按 `Ctrl+X`。

### 数据库准备

如果 MagicApp 数据库和账号还未创建，由服务器管理员执行：

```bash
sudo -u postgres createuser --login --pwprompt magicapp
sudo -u postgres createdb --owner=magicapp --encoding=UTF8 magicapp
sudo -u postgres psql -d magicapp -c 'GRANT ALL ON SCHEMA public TO magicapp'
```

命令会交互式询问并设置数据库密码。若账号或数据库已存在，不要重复创建；先用
`sudo -u postgres psql -l` 和 `sudo -u postgres psql -c '\\du'` 检查。

应用初始表结构：

```bash
cd /home/NBN/NBN/agent/magicApp-backend-main
.venv/bin/alembic upgrade head
```

### 用 systemd 启动 API

API 只监听服务器本机 `127.0.0.1:8001`，不会占用 Planner 使用的 8000 端口，也不应直接
开放给公网。创建服务文件：

```bash
sudo nano /etc/systemd/system/magicapp-api.service
```

写入以下内容：

```ini
[Unit]
Description=MagicApp API
After=network.target postgresql.service

[Service]
Type=simple
User=magicapp
WorkingDirectory=/home/NBN/NBN/agent/magicApp-backend-main
EnvironmentFile=/home/NBN/NBN/agent/magicApp-backend-main/.env
ExecStart=/home/NBN/NBN/agent/magicApp-backend-main/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

保存后启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now magicapp-api
sudo systemctl status magicapp-api --no-pager
```

查看日志：

```bash
sudo journalctl -u magicapp-api -n 100 --no-pager
sudo journalctl -u magicapp-api -f
```

验证 API 和数据库：

```bash
curl http://127.0.0.1:8001/api/health
curl http://127.0.0.1:8001/api/ready
```

两个接口都应返回 `code: 0`；数据库检查的 `data.database` 应为 `ok`。接口文档在
`http://127.0.0.1:8001/docs`，只在服务器本机或安全隧道中访问。

### 后续更新

本机先提交并推送：

```powershell
git add .
git commit -m "后端功能说明"
git push origin main
```

然后在服务器更新并重启：

```bash
cd /home/NBN/NBN/agent/magicApp-backend-main
git pull --ff-only origin main
.venv/bin/pip install -e .
.venv/bin/alembic upgrade head
sudo systemctl restart magicapp-api
sudo systemctl status magicapp-api --no-pager
curl http://127.0.0.1:8001/api/ready
```

只有数据库表结构变化时才会有新的迁移需要应用。执行迁移前应先备份数据库；不要删除
服务器数据库目录或运行 `docker compose down -v`。

## 本地查看表

本机 PostgreSQL 启动后，可用 DBeaver 连接 `127.0.0.1:5432`，数据库和用户名均为
`magicapp`。服务器数据库不开放公网端口；需要查看服务器表时，用服务器上的 `psql` 或
通过 SSH 隧道安全连接。
