"""集中注册功能路由；新功能路由必须在这里挂载才能被访问。"""

from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.image_optimization import router as image_optimization_router
from app.api.routes.library import router as library_router
from app.api.routes.points import router as points_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.text_to_image import router as text_to_image_router
from app.api.routes.uploads import router as uploads_router
from app.api.routes.video import router as video_router

api_router = APIRouter()

# 各功能模块维护自己的路径，这里只负责汇总。
api_router.include_router(auth_router)
api_router.include_router(health_router)
api_router.include_router(library_router)
api_router.include_router(image_optimization_router)
api_router.include_router(points_router)

api_router.include_router(tasks_router)
api_router.include_router(text_to_image_router)
api_router.include_router(uploads_router)
api_router.include_router(video_router)
