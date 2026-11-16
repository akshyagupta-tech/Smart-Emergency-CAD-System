"""ASGI gateway for the unified Smart Traffic OS engine."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.unified_engine import TICK_SECONDS, UnifiedEngine

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger("smart_traffic.unified_gateway")

engine: UnifiedEngine | None = None
_engine_running = False
_telemetry_task: asyncio.Task[None] | None = None
_telemetry_clients: set[WebSocket] = set()


class CorridorRequest(BaseModel):
    """Validated dynamic claim against the three intersection zones."""

    pid: str = Field(min_length=1)
    request: list[int] = Field(min_length=3, max_length=3)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start the unified engine and broadcaster, then stop them cleanly."""
    global engine, _engine_running, _telemetry_task
    engine = UnifiedEngine()
    await engine.start()
    _engine_running = True
    _telemetry_task = asyncio.create_task(
        _broadcast_telemetry(), name="unified-telemetry-10hz"
    )
    logger.info("UnifiedEngine started at %.0f Hz", 1 / TICK_SECONDS)
    try:
        yield
    finally:
        _engine_running = False
        if _telemetry_task is not None:
            _telemetry_task.cancel()
            with suppress(asyncio.CancelledError):
                await _telemetry_task
            _telemetry_task = None
        for client in tuple(_telemetry_clients):
            with suppress(RuntimeError):
                await client.close(code=1001, reason="gateway shutting down")
        _telemetry_clients.clear()
        if engine is not None:
            await engine.stop()
        engine = None
        logger.info("UnifiedEngine stopped")


app = FastAPI(
    title="Smart Traffic OS Unified Gateway",
    description="Unified 10 Hz edge-engine telemetry and controls.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Return gateway readiness and the latest engine tick."""
    current_engine = engine
    if current_engine is None:
        return {"status": "starting", "engine_running": False, "tick": 0}
    snapshot = await asyncio.to_thread(current_engine.get_live_telemetry)
    return {
        "status": "healthy" if _engine_running else "stopping",
        "engine_running": _engine_running,
        "tick": snapshot["tick"],
        "tick_hz": snapshot["simulation"]["tick_hz"],
        "uptime_seconds": snapshot["uptime_seconds"],
    }


@app.post("/api/emergency")
async def emergency() -> dict[str, Any]:
    """Trigger an immediate Priority 0 task and return switch confirmation."""
    current_engine = engine
    if current_engine is None or not _engine_running:
        raise HTTPException(status_code=503, detail="unified engine is not running")
    snapshot = await asyncio.to_thread(current_engine.trigger_emergency_override)
    override = snapshot["emergency_override"]
    return {
        "accepted": True,
        "priority": override["priority"],
        "pid": override["pid"],
        "direction": override["direction"],
        "context_switch_latency_ns": override["context_switch_latency_ns"],
        "tick": snapshot["tick"],
    }


@app.post("/api/bankers/request")
async def bankers_request(request: CorridorRequest) -> dict[str, Any]:
    """Evaluate a corridor claim and return its grant state and safe sequence."""
    if any(value < 0 for value in request.request):
        raise HTTPException(
            status_code=422, detail="request values must be non-negative"
        )
    current_engine = engine
    if current_engine is None or not _engine_running:
        raise HTTPException(status_code=503, detail="unified engine is not running")
    try:
        result = await asyncio.to_thread(
            current_engine.evaluate_corridor_request,
            request.pid,
            request.request,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "granted": bool(result["granted"]),
        "safe_sequence": result["safe_sequence"],
    }


@app.websocket("/ws/telemetry")
async def telemetry(websocket: WebSocket) -> None:
    """Subscribe a dashboard client to the shared 10 Hz telemetry stream."""
    await websocket.accept()
    _telemetry_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.debug("telemetry client disconnected")
    except Exception:
        logger.exception("telemetry connection failed")
        with suppress(RuntimeError):
            await websocket.close(code=1011)
    finally:
        _telemetry_clients.discard(websocket)


async def _broadcast_telemetry() -> None:
    """Send the same live snapshot to all connected clients every 100 ms."""
    while True:
        current_engine = engine
        if current_engine is not None and _telemetry_clients:
            snapshot = await asyncio.to_thread(current_engine.get_live_telemetry)
            clients = tuple(_telemetry_clients)
            outcomes = await asyncio.gather(
                *(client.send_json(snapshot) for client in clients),
                return_exceptions=True,
            )
            for client, outcome in zip(clients, outcomes):
                if isinstance(outcome, BaseException):
                    _telemetry_clients.discard(client)
        await asyncio.sleep(TICK_SECONDS)


app.mount(
    "/",
    StaticFiles(directory=ROOT / "frontend", html=True),
    name="frontend",
)


__all__ = ["app", "engine"]