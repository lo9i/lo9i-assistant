"""Runs the session helper (helper.py) until launchd stops it: at logout, or when the daemon asks it to quit after an
update, for launchd to start it again with the new code."""

import asyncio
import logging
import os
import signal

from lo9i.core import login_session
from lo9i.session.helper import SessionHelper


async def main() -> None:
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    helper = SessionHelper(
        login_session.socket_path(), login_session.ssh_agent_link(), os.environ.get("SSH_AUTH_SOCK", "")
    )
    await helper.serve(stop)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
