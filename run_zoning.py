"""Start the Zoning Assessment web app (Uvicorn) and open the browser."""

from __future__ import annotations

import os
import sys
import webbrowser
from threading import Timer

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

HOST = os.environ.get("ZONING_HOST", "127.0.0.1")
PORT = int(os.environ.get("ZONING_PORT", "8000"))


def _open_browser() -> None:
    webbrowser.open(f"http://{HOST}:{PORT}/")


def main() -> None:
    import uvicorn

    # Delay so the server is listening before the browser opens
    Timer(1.25, _open_browser).start()
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
