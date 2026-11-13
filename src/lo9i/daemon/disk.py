"""The disk lo9i takes and cleaning it (core/disk/), for Settings → System's Disk use and `lo9i clean`."""

import asyncio

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from lo9i.core.agent import AssistantService, CleanReport, DiskReport, UnknownCategoryError
from lo9i.core.i18n import message
from lo9i.protocol import LANGUAGE_HEADER


class CleanRequest(BaseModel):
    """The categories to clean; none for every one but those cleaned only when named (the plugins' downloads)."""

    categories: list[str] = []


def add_disk_routes(app: FastAPI, service: AssistantService) -> None:
    # One cleaning at a time: a second would plan what the first is removing.
    cleaning = asyncio.Lock()

    @app.get("/system/disk")
    async def disk_usage() -> DiskReport:
        """How much disk lo9i takes by category, what cleaning each frees, and what it removes."""
        return await service.disk_usage()

    @app.post("/system/disk/clean")
    async def clean_disk(request: Request, body: CleanRequest) -> CleanReport:
        """Removes what cleaning the categories frees, then measures again. 400: a category that isn't one."""
        async with cleaning:
            try:
                cleaned = await service.clean_disk(body.categories)
            except UnknownCategoryError as e:
                raise HTTPException(400, message(e)) from e
        return (await service.texts(request.headers.get(LANGUAGE_HEADER))).within(cleaned)
