"""FastAPI application entry point.

Run:
    python -m api.server
    # or
    uvicorn api.server:app --reload --host 127.0.0.1 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import health, session

app = FastAPI(
    title="LJK Facade Platform API",
    description="Adaptive Mold REST API — GH ↔ Dashboard communication backbone",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(session.router)


@app.get("/")
def root() -> dict:
    return {
        "name": "LJK Facade Platform API",
        "docs": "/docs",
        "health": "/api/health",
        "session": "/api/session",
    }


def main() -> None:
    import uvicorn

    uvicorn.run("api.server:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
