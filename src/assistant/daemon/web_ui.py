"""Serves the web UI, a single-page app built from `clients/web/` into this package, at /app/. The page is
served from the API's own origin, so its requests need no CORS and carry the client header like
any other client's. The root sends a browser there, so the daemon's address alone opens the app."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

PREFIX = "/app"
# Where `npm run build` in clients/web/ writes the page.
BUILD_DIR = Path(__file__).parent / "webui"


def add_web_ui(app: FastAPI, directory: Path) -> None:
    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(f"{PREFIX}/")

    if (directory / "index.html").is_file():
        app.mount(PREFIX, _SinglePageApp(directory=directory, html=True), name="web-ui")
    else:
        _add_not_built(app)


def is_web_ui(path: str) -> bool:
    """The page and the root that sends a browser to it, which load without the client header or a device."""
    return path in ("/", PREFIX) or path.startswith(f"{PREFIX}/")


class _SinglePageApp(StaticFiles):
    """Answers paths that aren't files (the page's own routes, like /app/jobs) with index.html, so
    reloading a page or opening a link to it works."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as e:
            if e.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


def _add_not_built(app: FastAPI) -> None:
    @app.get(PREFIX + "/{path:path}", include_in_schema=False)
    async def not_built(path: str) -> PlainTextResponse:
        return PlainTextResponse("The web UI isn't built. scripts/run.sh builds it.", status_code=404)
