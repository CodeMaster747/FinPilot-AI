"""FastAPI application: the JSON API under /api/v1 and the prebuilt frontend on the same origin."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import APP_VERSION, FRONTEND_OUT_DIR, NATIVE_ORIGINS, get_settings
from app.jobs import tasks  # noqa: F401  (registers job functions)
from app.jobs.runner import runner
from app.jobs.scheduler import scheduler

log = logging.getLogger("finpilot")
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    settings = get_settings()
    if not settings.testing:
        runner.start(settings.job_workers)
        runner.enqueue("system_warmup")
        runner.enqueue("bootstrap_demo")
        if settings.enable_scheduler:
            scheduler.start()
    yield
    scheduler.stop()
    runner.stop()


class FrontendFiles(StaticFiles):
    """Static export from `next build`; hashed assets are cached forever, HTML never."""

    async def get_response(self, path: str, scope):  # noqa: ANN001, ANN201
        response = await super().get_response(path, scope)
        if path.startswith("_next/static/") or path.startswith("ocr/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif response.media_type == "text/html":
            response.headers["Cache-Control"] = "no-cache"
        return response


def create_app() -> FastAPI:
    app = FastAPI(
        title="FinPilot AI",
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):  # noqa: ANN001, ANN202
        # The web app's cookies are SameSite=Lax; additionally require a custom header that a cross-site form
        # cannot send, so state-changing API calls can only come from our own frontend. The phone app
        # authenticates with a Bearer token (never sent automatically, so not forgeable cross-site) and marks
        # itself with X-FinPilot-Client, a header only our CORS policy lets through.
        if (
            request.method in MUTATING
            and request.url.path.startswith("/api/")
            and request.headers.get("x-requested-with") != "finpilot"
            and not request.headers.get("authorization", "").lower().startswith("bearer ")
            and request.headers.get("x-finpilot-client", "").lower() != "android"
        ):
            return JSONResponse({"detail": "Missing X-Requested-With header"}, status_code=403)
        return await call_next(request)

    # The Android app's WebView serves the bundled UI from http(s)://localhost and calls this server
    # cross-origin. Added after the CSRF guard so it is the outer layer (preflights never reach the guard).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(NATIVE_ORIGINS),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-FinPilot-Client"],
        expose_headers=["Content-Disposition"],
        allow_credentials=False,
        max_age=600,
    )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        log.exception("unhandled error on %s", request.url.path)
        response = JSONResponse({"detail": "Something went wrong on the server. Check the terminal log."}, status_code=500)
        origin = request.headers.get("origin")
        if origin in NATIVE_ORIGINS:  # this handler runs outside the CORS layer; let the phone read the error
            response.headers["Access-Control-Allow-Origin"] = origin
        return response

    app.include_router(api_router, prefix="/api/v1")

    if (FRONTEND_OUT_DIR / "index.html").exists():
        app.mount("/", FrontendFiles(directory=FRONTEND_OUT_DIR, html=True), name="frontend")
    else:

        @app.get("/", include_in_schema=False)
        def no_frontend() -> HTMLResponse:
            return HTMLResponse(
                "<h1>FinPilot AI API is running</h1><p>The frontend build is missing. "
                "Run <code>python3 run.py build-frontend</code> (needs Node.js) or use the prebuilt release.</p>"
                '<p>API docs: <a href="/api/docs">/api/docs</a></p>'
            )

    return app
