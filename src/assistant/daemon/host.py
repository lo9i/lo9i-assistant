"""The computer the daemon runs on, for the apps' Host card: system, versions and current use."""

import asyncio
import os
import platform
import time
from importlib.metadata import version
from pathlib import Path

import psutil

from assistant.core.config import settings
from assistant.protocol import HostStatus

# CPU use is measured over this long, in a thread, so the reading is current rather than since the last call.
_CPU_SAMPLE_SECONDS = 0.5


async def status() -> HostStatus:
    cpu = await asyncio.to_thread(psutil.cpu_percent, _CPU_SAMPLE_SECONDS)
    memory = psutil.virtual_memory()
    # The disk holding the assistant's data, where running out of space matters.
    disk = psutil.disk_usage(str(Path(settings.database_path).expanduser().parent))
    return HostStatus(
        os=f"{platform.system()} {platform.release()}",
        arch=platform.machine(),
        hostname=platform.node(),
        python=f"{platform.python_implementation()} {platform.python_version()}",
        version=version("assistant"),
        cpu_cores=psutil.cpu_count() or 0,
        cpu_percent=cpu,
        memory_used=memory.total - memory.available,
        memory_total=memory.total,
        disk_used=disk.used,
        disk_total=disk.total,
        uptime_seconds=int(time.time() - psutil.boot_time()),
        load_average=_load_average(),
    )


def _load_average() -> list[float]:
    return list(os.getloadavg()) if hasattr(os, "getloadavg") else []
