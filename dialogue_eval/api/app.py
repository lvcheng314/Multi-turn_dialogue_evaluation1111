from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from dialogue_eval.api.routes import router


def _resolve_frontend_dist() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled_root = Path(sys._MEIPASS)
        bundled_dist = bundled_root / "frontend" / "dist"
        if bundled_dist.exists():
            return bundled_dist
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="Multi-turn Dialogue Evaluation")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")

    # Direct fallback for /api/task-sources (bypasses router)
    @app.get("/api/task-sources")
    def _task_sources_fallback():
        from dialogue_eval.task_sources import list_task_sources
        return {"task_sources": list_task_sources()}

    frontend_dist = _resolve_frontend_dist()
    if frontend_dist.exists():
        assets_dir = frontend_dist / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(frontend_dist / "index.html")

        @app.get("/{path:path}", include_in_schema=False, response_model=None)
        def spa_fallback(path: str):
            target = frontend_dist / path
            if target.exists() and target.is_file():
                return FileResponse(target)
            return FileResponse(frontend_dist / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def no_frontend() -> JSONResponse:
            return JSONResponse(
                {
                    "status": "frontend_not_built",
                    "hint": "Run npm.cmd run build in frontend, then restart the API server.",
                }
            )
    return app


app = create_app()
