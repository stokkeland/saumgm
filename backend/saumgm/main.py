# SauMGM - Sauen Management System: billing, sales tax and bookkeeping for small businesses
# Copyright (C) 2026 J. Thomas Stokkeland - https://www.saumgm.com/
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details. You should have received a copy of the
# GNU General Public License along with this program (the LICENSE file); if not, see
# <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""ASGI application. Run in development with:  uvicorn saumgm.main:app --reload"""

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from saumgm import __version__
from saumgm.api import (
    audit,
    auth,
    banking,
    catalog,
    contacts,
    dashboard,
    email,
    expenses,
    files,
    health,
    invoices,
    party_documents,
    payments,
    reminders,
    reports,
    subscriptions,
    tax,
    vendor_subscriptions,
)
from saumgm.api import settings as settings_api
from saumgm.config import get_settings
from saumgm.request_logging import configure_logging, request_id_middleware

# Every module's API, all under /api. A new module adds its router here (the frontend's list of
# modules is frontend/src/modules/index.ts).
ROUTERS = (
    health.router,
    dashboard.router,
    auth.router,
    contacts.router,
    catalog.router,
    invoices.router,
    payments.router,
    expenses.router,
    banking.router,
    subscriptions.router,
    vendor_subscriptions.router,
    tax.router,
    settings_api.router,
    audit.router,
    files.router,
    reports.router,
    party_documents.router,
    email.router,
    reminders.router,
)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="SauMGM API",
        version=__version__,
        description="SauMGM - Sauen Management System. <https://www.saumgm.com/>",
        license_info={
            "name": "GPL-3.0-or-later",
            "url": "https://www.gnu.org/licenses/gpl-3.0.html",
        },
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

    for router in ROUTERS:
        app.include_router(router, prefix="/api")
    return app


app = create_app()
