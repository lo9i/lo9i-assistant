"""Child process for MetasearchProvider: `python -m assistant.core.internet.ddgs_worker <query> <limit> <engines>`.
Prints the results as JSON on stdout. `engines` is a comma-separated list such as "brave,bing,google"."""

import json
import sys

from ddgs import DDGS

_ENGINE_TIMEOUT = 10


def _main(query: str, limit: int, engines: str) -> None:
    rows = DDGS(timeout=_ENGINE_TIMEOUT).text(query, backend=engines, max_results=limit)
    results = [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")} for r in rows]
    print(json.dumps(results))


if __name__ == "__main__":
    _main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
