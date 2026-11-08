# MagicApp 后端 Runbook（服务器）

约定：项目目录 `/home/NBN/NBN/agent/magicApp-backend-main`，venv `magicAppEnv`，
systemd 服务 `magicapp-api`，PostgreSQL 库 `magicapp_db`、账号 `magicapp`，端口 `8001`。

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
STAMP=$(date +%F_%H%M%S)
runuser -u postgres -- pg_dump -Fc -d magicapp_db -f "/var/backups/magicapp/magicapp_db_${STAMP}.dump"
```

预期：dump 文件生成，`pg_restore -l 文件 | head` 能列出内容。

## 5. 执行迁移（先备份、先停服）

```bash
cd /home/NBN/NBN/agent/magicApp-backend-main
systemctl stop magicapp-api
magicAppEnv/bin/alembic upgrade head
echo "exit=$?"
```

预期：`Running upgrade 0007_works_task_fk_to_primary_key -> 0008_accounts_default_points_100`，`exit=0`。

## 6. 确认迁移是否成功

```bash
cd /home/NBN/NBN/agent/magicApp-backend-main
magicAppEnv/bin/alembic current
magicAppEnv/bin/alembic heads
runuser -u postgres -- psql -d magicapp_db -c "SELECT version_num FROM alembic_version;"
```

预期：前两条都显示 `0008_accounts_default_points_100 (head)`，第三条返回同一版本且只有 1 行。

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

预期：`ready` 的 `database` 为 `ok`；积分为 `points_balance=100`、`used_points=0`、`total=0`；
登出 `code=200`；重复登出 HTTP `401`。

## 11. 迁移失败回退

```bash
systemctl stop magicapp-api
cd /home/NBN/NBN/agent/magicApp-backend-main
magicAppEnv/bin/alembic current
magicAppEnv/bin/alembic downgrade 0007_works_task_fk_to_primary_key
magicAppEnv/bin/alembic current
```

预期：`current` 回到 `0007_works_task_fk_to_primary_key`；服务保持停止，修完数据再重跑第 5 节。

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
