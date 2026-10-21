"""ASGI application. Run in development with:  uvicorn saumgm.main:app --reload"""

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from saumgm import __version__
from saumgm.api import (
    audit,
    auth,
    catalog,
    contacts,
    expenses,
    health,
    invoices,
    payments,
    subscriptions,
    tax,
)
from saumgm.api import settings as settings_api
from saumgm.config import get_settings
from saumgm.request_logging import configure_logging, request_id_middleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="SauMGM API",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.middleware("http")(request_id_middleware)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        # Unique constraints (duplicate short code, SKU, number...) and similar database rules.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "This conflicts with existing data (for example a duplicate code)."},
        )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(contacts.router, prefix="/api")
    app.include_router(catalog.router, prefix="/api")
    app.include_router(invoices.router, prefix="/api")
    app.include_router(payments.router, prefix="/api")
    app.include_router(expenses.router, prefix="/api")
    app.include_router(subscriptions.router, prefix="/api")
    app.include_router(tax.router, prefix="/api")
    app.include_router(settings_api.router, prefix="/api")
    app.include_router(audit.router, prefix="/api")
    return app


app = create_app()
