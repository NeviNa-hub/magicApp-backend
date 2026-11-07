"""FastAPI 应用入口及统一请求处理。"""

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes.router import api_router
from app.core.errors import ApiError
from app.core.logging import setup_logging
from app.core.responses import ApiResponse

setup_logging()
logger = logging.getLogger(__name__)
app = FastAPI(title="MagicApp API", version="0.1.0")
app.include_router(api_router, prefix="/api")


# 全局请求中间件
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """为请求附加追踪编号，只记录路径和状态，不记录敏感内容。"""
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
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


# 全局参数校验异常处理
@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """返回简洁的参数错误，不回显用户提交的内容。"""
    del request
    fields = ", ".join(str(error["loc"][-1]) for error in exc.errors() if error.get("loc"))
    message = f"参数校验失败：{fields}" if fields else "参数校验失败"
    body = ApiResponse(code=42201, message=message, data=None)
    return JSONResponse(status_code=422, content=body.model_dump())


# 全局未处理异常处理
@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """服务端记录异常详情，客户端只收到通用错误信息。"""
    request_id = request.headers.get("X-Request-ID", "unknown")
    logger.exception("request_id=%s unhandled_error=%s", request_id, type(exc).__name__)
    body = ApiResponse(code=50001, message="服务异常，请稍后重试", data=None)
    return JSONResponse(status_code=500, content=body.model_dump())
