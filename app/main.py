import logging
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings, load_settings
from app.database import Base, database
from app.errors import ServiceError
from app.routes import agent_runs, analytics, urls
from app.security import RateLimiter, URLSafetyPolicy
from orchestration.audit import AgentStore


def create_app(settings: Settings | None = None, safety: URLSafetyPolicy | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine, session_factory = database(settings.database_url)
    store = AgentStore(settings.agent_data_dir)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    application = FastAPI(title="Agentic URL Shortener", version="1.0.0", lifespan=lifespan)
    application.state.settings = settings
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.safety = safety or URLSafetyPolicy(settings.dns_check)
    application.state.agent_store = store
    limiter = RateLimiter(settings.creation_rate_limit)
    logging.basicConfig(level=settings.log_level)
    # Suppress outbound-library request logging to avoid accidentally logging query strings.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)

    @application.exception_handler(ServiceError)
    async def domain_error(request: Request, exc: ServiceError):
        return JSONResponse(
            {"error": {"code": exc.code, "message": str(exc)}}, status_code=exc.status
        )

    @application.exception_handler(RequestValidationError)
    async def input_error(request: Request, exc: RequestValidationError):
        # Do not echo rejected input values, which can contain sensitive data.
        issues = [{"location": list(item["loc"]), "type": item["type"]} for item in exc.errors()]
        return JSONResponse(
            {"error": {"code": "validation_failed", "issues": issues}}, status_code=422
        )

    @application.exception_handler(SQLAlchemyError)
    async def persistence_error(request: Request, exc: SQLAlchemyError):
        return JSONResponse(
            {"error": {"code": "storage_unavailable", "message": "Storage is unavailable"}},
            status_code=503,
        )

    @application.middleware("http")
    async def protections(request: Request, call_next):
        raw_size = request.headers.get("content-length", "0")
        try:
            size = int(raw_size)
        except ValueError:
            return JSONResponse({"error": {"code": "invalid_length"}}, status_code=400)
        if size < 0 or size > 16384:
            return JSONResponse({"error": {"code": "body_too_large"}}, status_code=413)
        if request.method == "POST" and request.url.path == "/api/urls":
            if not limiter.allow(request.client.host if request.client else "unknown"):
                return JSONResponse(
                    {"error": {"code": "rate_limited", "message": "Retry after one minute"}},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @application.get("/health", tags=["health"])
    def health():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return {"status": "ok", "database": "ready"}
        except (SQLAlchemyError, sqlite3.Error):
            return JSONResponse({"status": "unavailable"}, status_code=503)

    application.include_router(urls.router)
    application.include_router(analytics.router)
    application.include_router(agent_runs.router)
    application.include_router(urls.redirect_router)
    return application


app = create_app()
