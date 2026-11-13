# MagicApp 后端

MagicApp 后端是 AI创作应用的服务端，基于 FastAPI 为前端提供账号注册、登录与会话管理、积分余额及流水查询、图片上传、作品浏览和创作任务提交与状态查询等 API。服务使用 PostgreSQL 持久化用户、积分、上传资源、任务和作品数据，并通过后台 worker 处理异步生成任务。图片生成、图片优化和视频生成能力通过硅基流动（SiliconFlow）提供，API 负责校验用户请求、管理任务状态与积分扣减，并向前端返回任务及结果信息。

## 技术栈

- Python 3.10+
- FastAPI、Uvicorn
- PostgreSQL、SQLAlchemy、Alembic
- Pydantic Settings

## 功能与 API

所有 API 路径均以 `/api` 开头。受保护的接口需要在请求头中携带 `Authorization: Bearer <access_token>`。

| 功能 | 方法 | 接口 | 说明 |
| --- | --- | --- | --- |
| 注册 | POST | `/api/auth/register` | 创建用户账号 |
| 登录 | POST | `/api/auth/login` | 登录并获取访问令牌 |
| 登出 | POST | `/api/auth/logout` | 撤销当前访问令牌 |
| 积分 | GET | `/api/points/myInfo` | 查询当前用户积分余额与流水 |
| 文字生图 | POST | `/api/text-to-image/tasks` | 创建文字生图任务 |
| 图片优化 | POST | `/api/image-optimization/tasks` | 创建图片优化任务 |
| 视频生成 | POST | `/api/video/tasks` | 创建文字生视频任务 |
| 任务状态轮询 | GET | `/api/tasks/{task_id}` | 查询当前用户任务状态 |
| 作品库 | GET | `/api/library` | 查询当前用户作品与进行中任务 |
| 图片上传 | POST | `/api/uploads/images` | 上传图片 |
| 图片读取 | GET | `/api/uploads/images/{upload_id}` | 读取当前用户上传的图片 |
| 健康检查 | GET | `/api/health` | 检查 API 进程状态 |
| 就绪检查 | GET | `/api/ready` | 检查数据库连接及迁移状态 |

创作类接口需要配置硅基流动（SiliconFlow）的 API Key，并由后台 worker 执行生成任务。当前配置的模型为：文字生图 `Kwai-Kolors/Kolors`、图片优化 `Qwen/Qwen-Image-Edit-2509`、视频生成 `MiniMaxAI/MiniMax-H3`。服务地址、模型名称和请求超时时间可通过 `.env` 配置。

当前仓库实现了通过硅基流动调用图片生成、图片编辑和视频生成能力；暂未发现独立的大语言模型 Agent 对话或工具调用接口。接口请求和响应字段可在服务启动后查看 Swagger 文档 `/docs`。

## 使用方式

以下命令用于 Linux 服务器。部署前需准备 Python、PostgreSQL 和 Git，并配置好数据库、环境变量及 API 服务进程管理方式。

## 首次部署

首次部署需要准备 Python 3.10+、PostgreSQL、Nginx，并创建数据库及账号。完成这些准备后：

```bash
cd <项目目录>
python3 -m venv magicAppEnv
source magicAppEnv/bin/activate
pip install -e .
cp .env.example .env
nano .env
alembic upgrade head
```

在 `.env` 中至少填写正确的 `DATABASE_URL` 和前端来源 `CORS_ALLOW_ORIGINS`。不要覆盖已有
`.env`，也不要把密钥提交到 Git。

依赖安装并配置 `.env` 后，执行数据库迁移。根据服务器的进程管理方式启动 API；例如已配置
`magicapp-api` systemd 服务和 Nginx 反向代理时：

```bash
sudo systemctl enable --now magicapp-api
sudo systemctl status magicapp-api --no-pager
curl -fsS http://127.0.0.1:8001/api/ready
```

就绪接口应返回 HTTP 200，且 `data.status` 为 `ready`、`data.database` 为 `ok`。

## 后续更新

先在开发机提交并推送代码到服务器使用的 Git 分支。然后在服务器执行：

```bash
cd <项目目录>
git pull --ff-only origin main
source magicAppEnv/bin/activate
pip install -e .
```

如果本次发布包含新的数据库迁移，先备份数据库，再停止 API、应用迁移并启动服务：

```bash
mkdir -p /var/backups/magicapp
chown postgres:postgres /var/backups/magicapp
STAMP=$(date +%F_%H%M%S)
runuser -u postgres -- pg_dump -Fc -d magicapp_db -f "/var/backups/magicapp/magicapp_db_${STAMP}.dump"

systemctl stop magicapp-api
alembic heads
alembic current
alembic upgrade head
systemctl start magicapp-api
```

迁移版本不要写死，以 `alembic heads` 输出为准。若这次没有数据库迁移，只需重启 API：

```bash
sudo systemctl restart magicapp-api
```

启动图片生成 worker：
```bash
python -m app.workers.image_generation
```

每次更新后检查服务和数据库就绪状态：

```bash
sudo systemctl status magicapp-api --no-pager
curl -i --max-time 5 http://127.0.0.1:8001/api/ready
```

查看服务错误：

```bash
sudo journalctl -u magicapp-api -n 100 --no-pager
```

## 前端访问

后端根路径 `/` 没有页面，返回接口不存在是正常的。健康检查地址为 `/api/health`，数据库就绪
检查地址为 `/api/ready`，Swagger 文档地址为 `/docs`（若 Nginx 配置禁用了文档，则通过服务器本机
`http://127.0.0.1:8001/docs` 访问）。前端 API 地址应指向服务器可访问的域名或 IP，并包含 `/api`。

`127.0.0.1` 只表示当前设备自身；部署在其他电脑或手机上的前端不能用它访问服务器。浏览器跨域时，
将前端完整来源（协议、域名、端口）配置到后端 `.env` 的 `CORS_ALLOW_ORIGINS`，修改后重启服务。
HTTPS 前端必须请求 HTTPS API。

## 常用检查

```bash
sudo systemctl status magicapp-api --no-pager
curl -fsS http://127.0.0.1:8001/api/health
curl -fsS http://127.0.0.1:8001/api/ready
alembic heads
alembic current
```
