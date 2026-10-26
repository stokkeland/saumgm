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

"""Write THIRD-PARTY-NOTICES.md: the libraries SauMGM uses and their licenses.

Run with the backend's Python after installing the backend (pip install -e "backend[dev]") and the
frontend (npm ci in frontend/), whenever dependencies change:

    backend/.venv/Scripts/python tools/third_party_notices.py      (Windows)
    backend/.venv/bin/python tools/third_party_notices.py          (Linux)
"""

import json
import re
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
OUT = ROOT / "THIRD-PARTY-NOTICES.md"


# -- Python ---------------------------------------------------------------------------------------


def _key(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _python_license(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    if expression := meta.get("License-Expression"):
        return str(expression)
    classifiers = [
        c.split("::")[-1].strip()
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::") and "OSI Approved" != c.split("::")[-1].strip()
    ]
    if classifiers:
        return " / ".join(classifiers)
    first = (meta.get("License") or "").strip().splitlines()
    return first[0][:60] if first else "see project"


def _python_url(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() in {"homepage", "home", "source", "repository", "source code"}:
            return url.strip()
    return str(meta.get("Home-page") or f"https://pypi.org/project/{meta['Name']}/")


def _python_closure(requirements: list[Requirement]) -> dict[str, metadata.Distribution]:
    found: dict[str, metadata.Distribution] = {}
    stack = [(r.name, tuple(r.extras)) for r in requirements]
    while stack:
        name, extras = stack.pop()
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        key = _key(dist.metadata["Name"])
        if key in found and not extras:
            continue
        found[key] = dist
        for raw in dist.requires or []:
            req = Requirement(raw)
            wanted = ("",) + extras
            if req.marker and not any(req.marker.evaluate({"extra": e}) for e in wanted):
                continue
            stack.append((req.name, tuple(req.extras)))
    return found


def python_packages() -> tuple[list[metadata.Distribution], list[metadata.Distribution]]:
    app = metadata.distribution("saumgm")
    requirements = [Requirement(r) for r in app.requires or []]
    runtime = [r for r in requirements if not r.marker]
    dev = [r for r in requirements if r.marker and "dev" in str(r.marker)]
    run = _python_closure(runtime)
    tools = {k: v for k, v in _python_closure(dev).items() if k not in run and k != "saumgm"}
    by_name = lambda d: d.metadata["Name"].lower()  # noqa: E731
    return sorted(run.values(), key=by_name), sorted(tools.values(), key=by_name)


# -- npm ------------------------------------------------------------------------------------------


def _package_json(name: str, start: Path) -> tuple[Path, dict[str, object]] | None:
    folder = start
    while True:
        candidate = folder / "node_modules" / name / "package.json"
        if candidate.is_file():
            return candidate.parent, json.loads(candidate.read_text(encoding="utf-8"))
        if folder == FRONTEND or folder.parent == folder:
            return None
        folder = folder.parent


def _npm_closure(names: list[str]) -> dict[str, dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    stack = [(n, FRONTEND) for n in names]
    while stack:
        name, start = stack.pop()
        located = _package_json(name, start)
        if located is None:
            continue
        folder, package = located
        key = f"{package['name']}@{package['version']}"
        if key in found:
            continue
        found[key] = package
        deps = package.get("dependencies") or {}
        assert isinstance(deps, dict)
        stack.extend((dep, folder) for dep in deps)
    return found


def _npm_license(package: dict[str, object]) -> str:
    value = package.get("license")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("type", "see project"))
    licenses = package.get("licenses")
    if isinstance(licenses, list):
        return " OR ".join(str(item.get("type")) for item in licenses if isinstance(item, dict))
    return "see project"


def _npm_url(package: dict[str, object]) -> str:
    repo = package.get("repository")
    url = repo.get("url") if isinstance(repo, dict) else repo
    if isinstance(url, str) and url:
        url = re.sub(r"^git\+|\.git$", "", url).replace("git://", "https://")
        if url.startswith("github:"):
            url = "https://github.com/" + url[len("github:") :]
        if re.fullmatch(r"[\w.-]+/[\w.-]+", url):
            url = "https://github.com/" + url
        return url
    homepage = package.get("homepage")
    if isinstance(homepage, str):
        return homepage
    return f"https://www.npmjs.com/package/{package['name']}"


def npm_packages() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    manifest = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    bundled = _npm_closure(list(manifest.get("dependencies", {})))
    tools = {
        k: v
        for k, v in _npm_closure(list(manifest.get("devDependencies", {}))).items()
        if k not in bundled
    }

    def order(p: dict[str, object]) -> str:
        return str(p["name"]).lower()

    return sorted(bundled.values(), key=order), sorted(tools.values(), key=order)


# -- output ---------------------------------------------------------------------------------------


def table(rows: list[tuple[str, str, str, str]]) -> str:
    lines = ["| Package | Version | License | Project |", "|---|---|---|---|"]
    lines += [f"| {n} | {v} | {lic} | <{url}> |" for n, v, lic, url in rows]
    return "\n".join(lines)


def main() -> None:
    py_run, py_dev = python_packages()
    js_run, js_dev = npm_packages()

    def py_rows(dists: list[metadata.Distribution]) -> list[tuple[str, str, str, str]]:
        return [(d.metadata["Name"], d.version, _python_license(d), _python_url(d)) for d in dists]

    def js_rows(packages: list[dict[str, object]]) -> list[tuple[str, str, str, str]]:
        return [(str(p["name"]), str(p["version"]), _npm_license(p), _npm_url(p)) for p in packages]

    licenses = sorted(
        {r[2] for r in py_rows(py_run) + py_rows(py_dev) + js_rows(js_run) + js_rows(js_dev)}
    )
    text = f"""# Third-party notices

SauMGM is licensed under the GNU General Public License, version 3 or (at your option) any later
version; see [LICENSE](LICENSE). Copyright (C) 2026 J. Thomas Stokkeland -
<https://www.saumgm.com/>.

SauMGM uses the open-source libraries listed below. They are **not copied into this repository**:
pip and npm download them from PyPI and the npm registry when SauMGM is installed or built. Each
remains under its own license, chosen by its authors, and the full license texts come with each
package (in the Python environment's `site-packages/*.dist-info/` folders and in
`frontend/node_modules/*/`). Anyone who redistributes SauMGM together with these libraries (for
example a built `frontend/dist`, which bundles the frontend libraries, or a container image) must
keep their copyright notices and license texts with them.

All of the licenses below are permissive or weak-copyleft licenses that are compatible with
GPL-3.0-or-later: {", ".join(licenses)}.

This file is generated by `tools/third_party_notices.py`; regenerate it when dependencies change.

## Other material in this repository

| What | Source and license |
|---|---|
| `LICENSE` | The text of the GNU General Public License v3, (C) Free Software Foundation, Inc.; copying and distributing verbatim copies is permitted. |
| `.gitignore` | Based on GitHub's public-domain `Python.gitignore` template (CC0-1.0). |
| Lists of US states, Canadian provinces and their codes (`backend/saumgm/seed.py`) | Public facts (ISO 3166-2 codes); no copyright claimed. |
| PDF fonts | Invoices use the standard PDF fonts (Helvetica) that every PDF reader provides; no font files are included or embedded. |
| `frontend/public/favicon.svg` | Made for SauMGM; under the project's license. |

Everything else in the repository is original work under the project's license.

## Backend (Python): installed with the application

{table(py_rows(py_run))}

## Frontend (JavaScript): bundled into the built web app

{table(js_rows(js_run))}

## Development and build tools (not part of the running application)

### Python

{table(py_rows(py_dev))}

### JavaScript

{table(js_rows(js_dev))}

## Optional

| Package | License | Used for |
|---|---|---|
| pyodbc | MIT | Only the one-time import from MS Access (`pip install -e "backend[legacy]"`, Windows) |
| Microsoft Access Database Engine | Microsoft license (proprietary, free download) | Only for that import; not part of SauMGM and never distributed with it |
"""
    OUT.write_text(text, encoding="utf-8", newline="\n")
    counts = (len(py_run), len(js_run), len(py_dev) + len(js_dev))
    print(f"Wrote {OUT.name}: {counts[0]} Python, {counts[1]} frontend, {counts[2]} dev packages")


if __name__ == "__main__":
    main()
