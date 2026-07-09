# -*- coding: utf-8 -*-
"""FastAPI application: CORS, router mounts, /healthz."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import settings
from app.routers import index as index_router
from app.routers import talk as talk_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Force DB + vector table creation at boot so /healthz reflects readiness.
    from app.db import get_db

    get_db()
    yield


app = FastAPI(title="zread-ai-backend", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz", tags=["meta"])
async def healthz():
    """Liveness + readiness probe (used by Docker HEALTHCHECK)."""
    return {"status": "ok", "name": "zread-ai-backend", "version": __version__}


app.include_router(index_router.router, prefix="/api/v1")
app.include_router(talk_router.router, prefix="/api/v1")
