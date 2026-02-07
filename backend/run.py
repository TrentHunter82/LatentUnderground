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
    # Auto-open browser in background
    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=True,
        log_level=LOG_LEVEL,
    )
