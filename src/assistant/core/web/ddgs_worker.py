"""Child process for DuckDuckGoProvider: `python -m assistant.core.web.ddgs_worker <query> <limit>`.
Prints the results as JSON on stdout."""

import json
import sys

from ddgs import DDGS


def _main(query: str, limit: int) -> None:
    rows = DDGS().text(query, max_results=limit)
    results = [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")} for r in rows]
    print(json.dumps(results))


if __name__ == "__main__":
    _main(sys.argv[1], int(sys.argv[2]))
