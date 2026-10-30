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

"""Sending email behind a small interface, like storage.py for files (docs/plan-v2.md, part C).

The backend comes from EMAIL_URL: `console://` (the default) logs each message instead of
sending it; `resend://` sends through Resend's HTTP API with RESEND_API_KEY. Callers use
`saumgm.services.emailing`, which adds the sender, templates, the redirect and the log.
"""

import base64
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlparse

from saumgm import __version__
from saumgm.config import get_settings

log = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


class EmailError(Exception):
    """The message could not be sent; the text says why, for the person sending it."""


@dataclass
class Attachment:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"
    # Set for an image shown in the message itself: the HTML refers to it as cid:<inline_id>.
    inline_id: str | None = None


@dataclass
class Message:
    sender: str  # "Name <address>" or a bare address
    to: list[str]
    subject: str
    text: str
    html: str
    cc: list[str] = field(default_factory=list)
    reply_to: str | None = None
    attachments: list[Attachment] = field(default_factory=list)


class EmailBackend(Protocol):
    name: str

    def send(self, message: Message) -> str | None:
        """Send the message; returns the provider's message id. Raises EmailError."""
        ...


class ConsoleBackend:
    """Writes messages to the log instead of sending them (development)."""

    name = "console"

    def send(self, message: Message) -> str | None:
        log.info(
            "Email (not sent, EMAIL_URL=console://) from %s to %s cc %s: %s [%s]\n%s",
            message.sender,
            ", ".join(message.to),
            ", ".join(message.cc) or "-",
            message.subject,
            ", ".join(a.filename for a in message.attachments) or "no attachments",
            message.text,
        )
        return None


class ResendBackend:
    """Resend's HTTP API (https://resend.com/docs/api-reference/emails/send-email)."""

    name = "resend"

    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    def send(self, message: Message) -> str | None:
        if not self.api_key:
            raise EmailError("RESEND_API_KEY is not set in the server's .env file")
        payload: dict[str, object] = {
            "from": message.sender,
            "to": message.to,
            "subject": message.subject,
            "text": message.text,
            "html": message.html,
        }
        if message.cc:
            payload["cc"] = message.cc
        if message.reply_to:
            payload["reply_to"] = message.reply_to
        if message.attachments:
            payload["attachments"] = [_resend_attachment(a) for a in message.attachments]
        request = urllib.request.Request(
            RESEND_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                # Requests without a user agent of their own can be turned away.
                "User-Agent": f"SauMGM/{__version__}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            detail = _resend_error(exc)
            raise EmailError(f"Resend refused the message ({exc.code}): {detail}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            reason = getattr(exc, "reason", exc)
            raise EmailError(f"Could not reach Resend: {reason}") from None
        message_id = body.get("id")
        return str(message_id) if message_id else None


def _resend_attachment(a: Attachment) -> dict[str, str]:
    out = {"filename": a.filename, "content": base64.b64encode(a.content).decode("ascii")}
    if a.inline_id:
        out["content_id"] = a.inline_id
    return out


def _resend_error(exc: urllib.error.HTTPError) -> str:
    try:
        detail = json.loads(exc.read() or b"{}")
    except ValueError:
        return exc.reason or "unknown error"
    return str(detail.get("message") or detail.get("name") or exc.reason)


def backend_from_url(url: str) -> EmailBackend:
    scheme = urlparse(url).scheme
    if scheme == "console":
        return ConsoleBackend()
    if scheme == "resend":
        return ResendBackend(get_settings().resend_api_key)
    raise ValueError(f"Unsupported EMAIL_URL scheme {scheme!r} (supported: console://, resend://)")


_backend: EmailBackend | None = None


def get_backend() -> EmailBackend:
    global _backend
    if _backend is None:
        _backend = backend_from_url(get_settings().email_url)
    return _backend


def set_backend(backend: EmailBackend | None) -> None:
    """Replace the email backend (tests)."""
    global _backend
    _backend = backend


@contextmanager
def use_backend(backend: EmailBackend) -> Iterator[None]:
    """Use another backend for a while (the demo loader records messages without sending)."""
    global _backend
    previous = _backend
    _backend = backend
    try:
        yield
    finally:
        _backend = previous


class NoSendBackend:
    """Accepts every message and sends nothing."""

    name = "none"

    def send(self, message: Message) -> str | None:
        return None
