# MagicApp 后端

MagicApp 后端是 AI创作应用的 API 服务。FastAPI 负责账号、积分、创作任务、作品和草稿等业务；后台 worker 调用硅基流动处理图片生成、图片优化与视频生成。

## 技术要点

- Python、FastAPI、Pydantic：REST API、请求校验和统一响应。
- PostgreSQL、SQLAlchemy、Alembic：业务持久化与数据库迁移。
- Bearer 会话鉴权、用户资源隔离、事务与幂等键：保护用户数据并避免重复扣费。
- 图片/视频后台 worker：异步执行生成任务、更新任务状态并处理失败退款。
- SiliconFlow：对接图片生成、图片编辑、视频生成及提示词优化模型。

## 已实现功能

- **账号与资料**：注册、登录、登出、个人资料/头像、永久注销；注销文件清理失败时由 worker 退避重试。
- **积分与任务**：余额及流水查询、按提示词/视频时长报价、任务创建/查询/取消/重试、失败退款。
- **AI 创作流程**：文字生图、图片优化、文字生视频；提示词优化返回可编辑候选，不创建任务、不扣积分。
- **作品管理**：分页筛选、标题或提示词搜索、类型过滤、创建时间排序、改名、删除、媒体地址读取和视频封面管理。
- **草稿**：创建、分页列表、详情、修改、删除；草稿提交时沿用任务记录，并与扣费和积分流水在同一事务中转换为生成任务。
- **通知与模板**：完成通知分页/未读数/标记已读；内置图片和视频创作模板查询。
- **运维接口**：健康检查 `/api/health`、数据库和迁移就绪检查 `/api/ready`。

## Agent 与模型调用

- 图片、视频生成以及提示词优化均通过服务端调用硅基流动；后端校验参数、执行报价与扣费，再由 worker 异步跟踪生成状态并保存结果。
- 当前这条业务链路包含模型调用和任务流程编排；Agent 独立项目若接入 LangChain、知识检索或工具调用，应以对应代码为准。本仓库当前 README 只列入本仓库实际提供的 API 与模型调用能力。

## API 概览

所有接口以 `/api` 开头；受保护接口使用 `Authorization: Bearer <access_token>`。完整字段可通过服务的 `/docs` 查看。

| 功能 | 接口 |
| --- | --- |
| 账号注册、登录、登出、注销 | `POST /api/auth/register`、`/login`、`/logout`、`/delete-account` |
| 个人资料 | `GET/PUT /api/profile` |
| 积分及报价 | `GET /api/points/myInfo`、`POST /api/pricing/quote` |
| 图片/优化/视频任务 | `POST /api/text-to-image/tasks`、`/api/image-optimization/tasks`、`/api/video/tasks` |
| 任务查询、取消、重试 | `GET /api/tasks/{task_id}`、`POST /api/tasks/{task_id}/cancel`、`/retry` |
| 作品库与媒体 | `GET /api/library`、`GET /api/library/works/{work_id}/media` |
| 草稿 | `GET/POST /api/drafts`、`GET/PUT/DELETE /api/drafts/{draft_id}` |
| 通知、模板、提示词优化 | `/api/notifications`、`/api/templates`、`POST /api/prompts/optimize` |
| 图片上传及读取 | `POST /api/uploads/images`、`GET /api/uploads/images/{upload_id}` |

## 本地运行与部署

准备 Python 3.10+ 和 PostgreSQL，复制 `.env.example` 为 `.env` 并填写数据库、跨域来源及所需模型配置。

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e .
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

图片与视频任务由两个 worker 分别处理，部署时需同时常驻：

```bash
python -m app.workers.image_generation
python -m app.workers.video_generation
```

Swagger 文档为 `/docs`；生产环境建议通过进程管理器托管 API 和两个 worker，并将前端可访问的 API 地址配置为包含 `/api` 的服务地址。

## 后续更新
```bash
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
若这次没有数据库迁移，只需重启 API：

```bash
sudo systemctl restart magicapp-api
```

启动后台 worker（图片与视频各一个进程，需同时运行）：
```bash
python -m app.workers.image_generation
python -m app.workers.video_generation
```

每次更新后检查服务和数据库就绪状态：

```bash
sudo systemctl status magicapp-api --no-pager
curl -i --max-time 5 http://127.0.0.1:8001/api/ready
```

修改 Nginx 配置或发现前端代理连接被拒绝时，重启并检查 Nginx：

```bash
sudo systemctl restart nginx
sudo systemctl status nginx --no-pager
```

查看服务错误：

```bash
sudo journalctl -u magicapp-api -n 100 --no-pager
```


### git 推送
git config --local http.proxy http://127.0.0.1:7890
git config --local https.proxy http://127.0.0.1:7890
git push origin main