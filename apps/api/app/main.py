from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocket, WebSocketDisconnect

from app.api.routes import router
from app.core.container import agent_office_service
from app.core.middleware import OptionalAuthMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware
from app.core.settings import settings


app = FastAPI(
    title="ANN (Agentic Neural Network) API",
    version="0.1.0",
    description="Approval-gated autonomous software engineering orchestration API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, settings=settings)
app.add_middleware(OptionalAuthMiddleware, settings=settings)

app.include_router(router, prefix="/api")


@app.websocket("/ws/agent-office")
async def agent_office_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(agent_office_service.state())
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
