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

"""Markdown (knowledge base articles) to HTML for email, to PDF flowables, and to plain text.

The same flavor as the frontend (react-markdown with remark-gfm): CommonMark with tables and
strikethrough. Raw HTML in the text is never passed through, only shown as text, and links to
`javascript:` and the like are dropped, so the output is safe to send.
"""

import io
import re
from collections.abc import Callable
from xml.sax.saxutils import escape

from markdown_it import MarkdownIt
from markdown_it.token import Token
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    Image,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

# Article attachments are referenced by their download address: ![diagram](/api/files/12).
FILE_URL = re.compile(r"^/api/files/(\d+)$")

_md = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])


def parse(text: str) -> list[Token]:
    return _md.parse(text or "")


def file_id(url: str | None) -> int | None:
    match = FILE_URL.match(url or "")
    return int(match.group(1)) if match else None


def _inline_tokens(tokens: list[Token]) -> list[Token]:
    return [child for t in tokens if t.type == "inline" for child in t.children or []]


def referenced_files(text: str) -> list[int]:
    """Ids of the stored files the text shows or links, in order of first use."""
    found: list[int] = []
    for t in _inline_tokens(parse(text)):
        url = t.attrGet("src") if t.type == "image" else t.attrGet("href")
        fid = file_id(str(url) if url else None)
        if fid is not None and fid not in found:
            found.append(fid)
    return found


# -- HTML (email) ---------------------------------------------------------------------------------

# Email clients ignore style sheets; the few styles needed go on the elements.
_EMAIL_STYLES = {
    "table": "border-collapse: collapse; margin: 8px 0",
    "th": "border: 1px solid #ccc; padding: 4px 8px; background: #eef2f7",
    "td": "border: 1px solid #ccc; padding: 4px 8px",
    "pre": "background: #f4f4f4; padding: 8px; white-space: pre-wrap",
    "blockquote": "border-left: 3px solid #ccc; margin: 8px 0; padding-left: 10px; color: #555",
    "img": "max-width: 100%",
}
# An opening tag, with the style markdown-it gives aligned table columns.
_TAG = re.compile(r'<(table|th|td|pre|blockquote|img)(?: style="([^"]*)")?(?=[ >])')


def _styled(match: re.Match[str]) -> str:
    tag, own = match.group(1), match.group(2)
    style = _EMAIL_STYLES[tag] + (f"; {own}" if own else "")
    return f'<{tag} style="{style}"'


def to_html(text: str, rewrite: Callable[[str, bool], str | None] | None = None) -> str:
    """HTML for an email. `rewrite(url, is_image)` may change a link or image address, or return
    None to drop the link (keeping its text) or the image (keeping its description)."""
    tokens = parse(text)
    if rewrite is not None:
        for t in tokens:
            if t.type != "inline" or not t.children:
                continue
            kept: list[Token] = []
            dropped_links = 0
            for child in t.children:
                if child.type == "image":
                    src = rewrite(str(child.attrGet("src") or ""), True)
                    if src is None:
                        alt = Token("text", "", 0)
                        alt.content = child.content
                        kept.append(alt)
                        continue
                    child.attrSet("src", src)
                elif child.type == "link_open":
                    href = rewrite(str(child.attrGet("href") or ""), False)
                    if href is None:
                        dropped_links += 1
                        continue
                    child.attrSet("href", href)
                elif child.type == "link_close" and dropped_links:
                    dropped_links -= 1
                    continue
                kept.append(child)
            t.children = kept
    return _TAG.sub(_styled, _md.renderer.render(tokens, _md.options, {}))


# -- plain text (search snippets) -----------------------------------------------------------------


def plain_text(text: str) -> str:
    """The words of the text without the Markdown, on one line."""
    parts: list[str] = []
    for t in parse(text):
        if t.type in ("fence", "code_block"):
            parts.append(t.content)
        for child in t.children or []:
            if child.type in ("text", "code_inline"):
                parts.append(child.content)
            elif child.type in ("softbreak", "hardbreak"):
                parts.append(" ")
        parts.append(" ")
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def snippet(text: str, terms: list[str], width: int = 220) -> str:
    """The part of the text around the first search term, or its start."""
    plain = plain_text(text)
    lower = plain.lower()
    hits = [i for i in (lower.find(term.lower()) for term in terms) if i >= 0]
    if not hits:
        return plain[:width] + ("…" if len(plain) > width else "")
    start = max(0, min(hits) - width // 3)
    if start:  # begin at a word
        space = plain.find(" ", start)
        start = space + 1 if 0 <= space < min(hits) else start
    end = start + width
    return ("…" if start else "") + plain[start:end] + ("…" if end < len(plain) else "")


# -- PDF flowables --------------------------------------------------------------------------------


class Styles:
    def __init__(self, body: ParagraphStyle, accent: colors.Color) -> None:
        self.accent = accent
        self.body = ParagraphStyle("md-body", parent=body, fontSize=10, leading=13.5, spaceAfter=5)
        sizes = {1: 16, 2: 13.5, 3: 12, 4: 11, 5: 10, 6: 10}
        self.headings = {
            level: ParagraphStyle(
                f"md-h{level}",
                parent=self.body,
                fontName="Helvetica-Bold",
                fontSize=size,
                leading=size * 1.25,
                spaceBefore=8 if level <= 2 else 5,
                spaceAfter=4,
                textColor=accent if level <= 2 else colors.black,
            )
            for level, size in sizes.items()
        }
        self.code = ParagraphStyle(
            "md-code",
            parent=self.body,
            fontName="Courier",
            fontSize=8.5,
            leading=10.5,
            backColor=colors.HexColor("#f4f4f4"),
            borderPadding=4,
            spaceBefore=4,
            spaceAfter=8,
        )
        self.cell = ParagraphStyle(
            "md-cell", parent=self.body, fontSize=9, leading=11, spaceAfter=0
        )
        self.head = ParagraphStyle("md-head", parent=self.cell, fontName="Helvetica-Bold")


def _inline_markup(tokens: list[Token], accent: str) -> str:
    """ReportLab paragraph markup for one inline run."""
    out: list[str] = []
    links: list[str] = []  # the closing tag of each open link
    for t in tokens:
        if t.type == "text":
            out.append(escape(t.content))
        elif t.type == "softbreak":
            out.append(" ")
        elif t.type == "hardbreak":
            out.append("<br/>")
        elif t.type == "code_inline":
            out.append(f'<font face="Courier">{escape(t.content)}</font>')
        elif t.type == "strong_open":
            out.append("<b>")
        elif t.type == "strong_close":
            out.append("</b>")
        elif t.type == "em_open":
            out.append("<i>")
        elif t.type == "em_close":
            out.append("</i>")
        elif t.type == "s_open":
            out.append("<strike>")
        elif t.type == "s_close":
            out.append("</strike>")
        elif t.type == "link_open":
            href = str(t.attrGet("href") or "")
            if href.startswith(("http://", "https://", "mailto:")):
                out.append(f'<a href="{escape(href, {chr(34): "&quot;"})}" color="{accent}">')
                links.append("</a>")
            else:  # an address inside the app means nothing on paper
                out.append("<u>")
                links.append("</u>")
        elif t.type == "link_close" and links:
            out.append(links.pop())
        elif t.type == "image":
            out.append(f"[{escape(t.content or 'image')}]")
    return "".join(out)


def _image(data: bytes, max_width: float, max_height: float = 6 * inch) -> Flowable | None:
    try:
        width, height = ImageReader(io.BytesIO(data)).getSize()
    except Exception:
        return None
    scale = min(1.0, max_width / width, max_height / height)
    return Image(io.BytesIO(data), width=width * scale, height=height * scale, hAlign="LEFT")


def to_flowables(
    text: str,
    styles: Styles,
    width: float,
    image_data: Callable[[str], bytes | None] = lambda url: None,
) -> list[Flowable]:
    """The text as PDF content `width` wide. `image_data(url)` gives an image's bytes, or None
    to show its description instead."""
    accent = styles.accent.hexval().replace("0x", "#")
    story: list[Flowable] = []
    lists: list[list[int]] = []  # per open list: [ordered (0/1), next number]
    bullet: str | None = None  # waiting for the list item's first paragraph
    quote = 0
    heading: int | None = None
    table: list[list[str]] | None = None
    tokens = parse(text)

    def indent() -> float:
        return 16 * len(lists) + 14 * quote

    def style_for(base: ParagraphStyle) -> ParagraphStyle:
        if not lists and not quote:
            return base
        return ParagraphStyle(
            f"{base.name}-{len(lists)}-{quote}",
            parent=base,
            leftIndent=indent(),
            bulletIndent=indent() - 12,
            textColor=colors.HexColor("#555555") if quote else base.textColor,
        )

    for t in tokens:
        kind = t.type
        if kind == "heading_open":
            heading = int(t.tag[1])
        elif kind == "heading_close":
            heading = None
        elif kind in ("bullet_list_open", "ordered_list_open"):
            start = int(t.attrGet("start") or 1)
            lists.append([1 if kind == "ordered_list_open" else 0, start])
        elif kind in ("bullet_list_close", "ordered_list_close"):
            lists.pop()
            if not lists:
                story.append(Spacer(1, 3))
        elif kind == "list_item_open":
            ordered, number = lists[-1]
            bullet = f"{number}." if ordered else "•"
            lists[-1][1] = number + 1
        elif kind == "blockquote_open":
            quote += 1
        elif kind == "blockquote_close":
            quote -= 1
        elif kind == "hr":
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        elif kind in ("fence", "code_block"):
            story.append(
                Preformatted(t.content.rstrip("\n"), style_for(styles.code), maxLineLength=95)
            )
        elif kind == "table_open":
            table = []
        elif kind == "tr_open" and table is not None:
            table.append([])
        elif kind == "inline" and table is not None:
            table[-1].append(_inline_markup(t.children or [], accent))
        elif kind == "table_close" and table is not None:
            story.append(_table(table, styles, width - indent()))
            table = None
        elif kind == "inline":
            children = t.children or []
            images = [c for c in children if c.type == "image"]
            if images and all(c.type == "image" or not c.content.strip() for c in children):
                for c in images:  # a paragraph of only images: show them
                    data = image_data(str(c.attrGet("src") or ""))
                    picture = _image(data, width - indent()) if data else None
                    story.append(
                        picture
                        if picture
                        else Paragraph(f"[{escape(c.content or 'image')}]", styles.body)
                    )
                bullet = None
                continue
            markup = _inline_markup(children, accent)
            base = styles.headings[heading] if heading else styles.body
            story.append(Paragraph(markup, style_for(base), bulletText=bullet))
            bullet = None
    return story


def _table(rows: list[list[str]], styles: Styles, width: float) -> Table:
    # The first row is the header (GFM tables always have one).
    columns = max(len(r) for r in rows) if rows else 1
    data = [
        [
            Paragraph(cell, styles.head if i == 0 else styles.cell)
            for cell in row + [""] * (columns - len(row))
        ]
        for i, row in enumerate(rows)
    ]
    return Table(
        data,
        colWidths=[width / columns] * columns,
        repeatRows=1,
        hAlign="LEFT",
        style=TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        ),
        spaceBefore=4,
        spaceAfter=8,
    )
