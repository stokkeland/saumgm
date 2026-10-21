import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from saumgm import __version__
from saumgm.db import get_session, server_version

router = APIRouter(tags=["system"])
log = logging.getLogger(__name__)


class Health(BaseModel):
    status: Literal["ok", "error"]
    version: str
    database: Literal["ok", "error"]
    database_version: str | None = None


@router.get("/health")
def health(response: Response, session: Annotated[Session, Depends(get_session)]) -> Health:
    """Liveness/readiness check: the API is up and can reach the database."""
    try:
        db_version = server_version(session)
    except SQLAlchemyError:
        log.exception("Health check could not reach the database")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Health(status="error", version=__version__, database="error")
    return Health(status="ok", version=__version__, database="ok", database_version=db_version)
