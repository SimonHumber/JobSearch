"""
Run the API locally with auto-reload.

From the backend directory:
  python dev.py
  pymon dev.py

Do not run `python app/main.py` directly — Python won't resolve the `app` package.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
