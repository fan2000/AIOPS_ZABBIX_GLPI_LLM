"""Point d'entrée principal de l'API Gateway FastAPI AI IT Operations."""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database.connection import init_database
from database.seeds.seed_data import seed_database
from apps.api.src.routers.actions import router as actions_router
from apps.api.src.routers.health import router as health_router
from apps.api.src.routers.incidents import router as incidents_router
from apps.api.src.routers.knowledge import router as knowledge_router
from apps.api.src.routers.lab import router as lab_router
from apps.api.src.routers.webhooks import router as webhooks_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Cycle de vie de l'application : initialisation de la base et des dépendances."""
    try:
        await seed_database()
    except Exception as e:
        print(f"Avertissement au démarrage de la base: {e}")
    yield


app = FastAPI(
    title="AI IT Operations Platform API",
    version="1.0.0",
    description="Plateforme AIOps intelligente connectant Zabbix, GLPI, LangGraph et pgvector",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configuration CORS pour le frontend Next.js
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclusion des routeurs modulaires
app.include_router(health_router)
app.include_router(webhooks_router)
app.include_router(incidents_router)
app.include_router(knowledge_router)
app.include_router(actions_router)
app.include_router(lab_router)


@app.get("/")
async def root():
    return {
        "platform": "AI IT Operations",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health/ready",
    }
