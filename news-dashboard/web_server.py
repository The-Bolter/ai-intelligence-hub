"""Production Web API entry point; scheduler is intentionally not started here."""
import os

from waitress import serve

from app import app


if __name__ == "__main__":
    host = os.getenv("BIND_HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5678"))
    serve(app, host=host, port=port, threads=8)
