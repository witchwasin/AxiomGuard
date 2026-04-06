"""
Axiom Studio v2 — Entry point.

Serves the SPA frontend + FastAPI backend on a single port.

Run:
    pip install "axiomguard[studio-v2]"
    python -m axiomguard.studio.app

    # Or with uvicorn directly:
    uvicorn axiomguard.studio.app:app --reload --port 8000
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    import uvicorn

    _HAS_DEPS = True
except ImportError:
    _HAS_DEPS = False

from axiomguard.studio.api import create_app


def create_full_app() -> "FastAPI":
    """Create app with both API routes and static file serving."""
    api_app = create_app()

    # Serve static files (SPA)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        api_app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @api_app.get("/")
        async def serve_index():
            index_path = static_dir / "index.html"
            if index_path.exists():
                return FileResponse(str(index_path))
            return {"error": "index.html not found"}

    return api_app


# Module-level app for uvicorn
app = create_full_app() if _HAS_DEPS else None


def main():
    """Run the Axiom Studio server."""
    if not _HAS_DEPS:
        print("Axiom Studio v2 requires FastAPI + uvicorn.")
        print("Install with: pip install 'axiomguard[studio-v2]'")
        return

    port = int(os.environ.get("AXIOM_STUDIO_PORT", "8000"))
    print(f"\n  Axiom Studio v2 starting on http://localhost:{port}")
    print(f"  API docs: http://localhost:{port}/docs")
    print(f"  Powered by AxiomGuard v0.7.2 + Z3 Theorem Prover\n")

    uvicorn.run(
        "axiomguard.studio.app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
