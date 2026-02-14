import os
import threading
import time
import uvicorn

from app.config import HOST, PORT, LOG_LEVEL


def open_browser():
    """Open browser after a short delay to let the server start."""
    time.sleep(1.5)
    import webbrowser
    webbrowser.open(f"http://localhost:{PORT}")


if __name__ == "__main__":
    # Auto-open browser unless suppressed (e.g. when start.bat manages it)
    if not os.environ.get("LU_NO_BROWSER"):
        threading.Thread(target=open_browser, daemon=True).start()

    use_reload = os.environ.get("LU_NO_RELOAD", "").lower() not in ("1", "true", "yes")
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=use_reload,
        log_level=LOG_LEVEL,
    )
