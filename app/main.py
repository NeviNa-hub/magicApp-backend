"""FastAPI 应用入口：注册路由、中间件和全局异常处理。"""

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes.router import api_router
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.logging import setup_logging
from app.core.responses import ApiResponse

setup_logging()
logger = logging.getLogger(__name__)
app = FastAPI(title="MagicApp API", version="0.1.0")
# 浏览器跨域联调：来源来自 CORS_ALLOW_ORIGINS，默认只允许 Vite 开发地址。
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
        "X-Request-ID",
        "Idempotency-Key",
    ],
)
# 统一挂载 /api 前缀，具体路径由各功能路由定义。
app.include_router(api_router, prefix="/api")


# 全局请求中间件
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """为请求附加追踪编号，只记录路径和状态，不记录敏感内容。"""
    # 请求方传入追踪编号时沿用，否则由服务端生成，便于串联排查日志。
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    # 存入 request.state，异常处理器才能拿到与响应头一致的编号。
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_id=%s method=%s path=%s status=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
    )
    return response


# 全局异常处理
@app.exception_handler(ApiError)
async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    """把可预期的业务错误转换为统一响应。"""
    del request
    body = ApiResponse(code=exc.code, message=exc.message, data=None)
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """把 404/405 纳入统一响应；其他 HTTP 异常保持原有 detail 结构。"""
    del request
    if exc.status_code == 404:
        body = ApiResponse(code=40401, message="接口不存在", data=None)
    elif exc.status_code == 405:
        body = ApiResponse(code=40501, message="请求方法不被允许", data=None)
    else:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


# 全局参数校验异常处理
@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """把常见字段校验错误转换成中文提示，不回显用户提交的内容。"""
    del request
    messages = []
    for error in exc.errors():
        field = error.get("loc", [None])[-1]
        error_type = error.get("type")

        if field == "username" and error_type == "missing":
            messages.append("请填写用户名")
        elif field == "username" and error_type == "string_too_short":
            messages.append("用户名不能为空")
        elif field == "username" and error_type == "string_too_long":
            messages.append("用户名不能超过 64 个字符")
        elif field == "account" and error_type == "missing":
            messages.append("请填写账号")
        elif field == "account" and error_type in {
            "string_too_short",
            "string_too_long",
            "string_pattern_mismatch",
        }:
            messages.append("账号需为 3–64 位英文字母、数字或下划线")
        elif field == "password" and error_type == "missing":
            messages.append("请填写密码")
        elif field == "password" and error_type == "string_too_short":
            messages.append("密码需为 8–128 位")
        elif field == "password" and error_type == "string_too_long":
            messages.append("密码需为 8–128 位")
        elif field:
            messages.append(f"{field} 格式不正确")
        else:
            messages.append("请求参数格式不正确")

    message = "；".join(dict.fromkeys(messages)) or "请求参数格式不正确"
    body = ApiResponse(code=42201, message=message, data=None)
    return JSONResponse(status_code=422, content=body.model_dump())


# 全局未处理异常处理
@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """服务端记录异常详情，客户端只收到通用错误信息。"""
    # 详细异常只写入服务端日志，响应不给调用方暴露堆栈或数据库信息。
    request_id = getattr(request.state, "request_id", None) or request.headers.get(
        "X-Request-ID",
        "Idempotency-Key", "unknown"
    )
    # 异常处理器内没有活动异常上下文，必须显式传入 exc_info 才会记录堆栈。
    logger.error("request_id=%s unhandled_error=%s", request_id, type(exc).__name__, exc_info=exc)
    body = ApiResponse(code=50001, message="服务异常，请稍后重试", data=None)
    return JSONResponse(status_code=500, content=body.model_dump())
