"""FastAPI gateway for the Smart Traffic OS simulation and dashboard."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import httpx
from pydantic import BaseModel, Field
from websockets import connect as websocket_connect

from core.kernel_service import KernelService

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger("smart_traffic.gateway")
kernel = KernelService()
KERNEL_ROLE = os.getenv("KERNEL_ROLE", "gateway")
KERNEL_SERVICE_URL = os.getenv("KERNEL_SERVICE_URL", "").rstrip("/")
_http_client: httpx.AsyncClient | None = None


class EmergencyRequest(BaseModel):
    """Validated body for the operator emergency-preemption action."""

    vehicle_type: Literal["Ambulance", "Fire"] = "Ambulance"


class BankerRequest(BaseModel):
    """Validated three-zone request for one named traffic agent."""

    pid: str = Field(min_length=1)
    request: list[int] = Field(min_length=3, max_length=3)


class TelemetryRequest(BaseModel):
    """Optional body accepted by the emergency endpoint."""

    vehicle_type: Literal["Ambulance"] = "Ambulance"


_telemetry_clients: set[WebSocket] = set()
_telemetry_task: asyncio.Task[None] | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start and stop the kernel simulation with the ASGI application."""
    global _http_client, _telemetry_task
    if KERNEL_ROLE == "core" or not KERNEL_SERVICE_URL:
        await kernel.start()
        _telemetry_task = asyncio.create_task(
            _broadcast_telemetry(), name="telemetry-broadcast-20hz"
        )
        logger.info("Kernel service started in %s role", KERNEL_ROLE)
    else:
        _http_client = httpx.AsyncClient(base_url=KERNEL_SERVICE_URL, timeout=5.0)
        logger.info("Gateway proxy connected to %s", KERNEL_SERVICE_URL)
    try:
        yield
    finally:
        if _telemetry_task is not None:
            _telemetry_task.cancel()
            with suppress(asyncio.CancelledError):
                await _telemetry_task
            _telemetry_task = None
        for client in tuple(_telemetry_clients):
            with suppress(RuntimeError):
                await client.close(code=1001, reason="server shutting down")
        _telemetry_clients.clear()
        if _http_client is not None:
            await _http_client.aclose()
            _http_client = None
        if KERNEL_ROLE == "core" or not KERNEL_SERVICE_URL:
            await kernel.stop()
            logger.info("Kernel service stopped")


app = FastAPI(
    title="Smart Traffic OS Edge Gateway",
    description="Asynchronous simulation telemetry and operator controls.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    """Report process readiness and verify the core from proxy mode."""
    if _is_proxy():
        await _proxy_json("GET", "/health")
    return {"status": "healthy", "role": KERNEL_ROLE}


@app.get("/api/status")
async def status() -> dict[str, object]:
    """Return the live state and requested operator-facing status fields."""
    if _is_proxy():
        return await _proxy_json("GET", "/api/status")
    snapshot = await asyncio.to_thread(kernel.get_system_snapshot)
    cpu = snapshot["cpu"]
    cores = [cpu["core0"], *cpu["cores1_3"]]
    snapshot["active_processes"] = {
        "core0": cpu["core0"]["active_process"],
        "core1": cpu["cores1_3"][0]["active_process"],
    }
    snapshot["queue_depths"] = {
        f"Q{index}": depth for index, depth in enumerate(snapshot["queues"]["mlfq"])
    }
    snapshot["queue_depths"]["priority"] = snapshot["queues"]["priority_depth"]
    snapshot["intersection_lights"] = {
        direction: state["phase"]
        for direction, state in snapshot["traffic"].items()
    }
    snapshot["memory_fault_ratios"] = {
        name: metrics["fault_ratio"]
        for name, metrics in snapshot["memory"]["policy_metrics"].items()
    }
    snapshot["active_core_count"] = len(cores)
    return snapshot


@app.post("/api/emergency")
async def trigger_emergency(
    request: TelemetryRequest | None = None,
) -> dict[str, object]:
    """Trigger an immediate Priority 0 ambulance preemption."""
    vehicle_type = request.vehicle_type if request is not None else "Ambulance"
    if _is_proxy():
        return await _proxy_json(
            "POST", "/api/emergency", json={"vehicle_type": vehicle_type}
        )
    try:
        return await asyncio.to_thread(kernel.trigger_emergency, vehicle_type)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/banker/request", include_in_schema=False)
@app.post("/api/bankers/request")
async def banker_request(request: BankerRequest) -> dict[str, object]:
    """Evaluate a corridor-resource request using Banker's safety algorithm."""
    if any(resource < 0 for resource in request.request):
        raise HTTPException(status_code=422, detail="resources must be non-negative")
    if _is_proxy():
        return await _proxy_json(
            "POST",
            "/api/bankers/request",
            json={"pid": request.pid, "request": request.request},
        )
    try:
        return await asyncio.to_thread(
            kernel.request_corridor,
            request.pid,
            request.request,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.websocket("/ws/telemetry")
async def telemetry(websocket: WebSocket) -> None:
    """Subscribe a dashboard client to the shared 20 Hz telemetry broadcast."""
    await websocket.accept()
    if _is_proxy():
        await _proxy_telemetry(websocket)
        return
    _telemetry_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("Telemetry client disconnected")
    except Exception:
        logger.exception("Telemetry websocket failed")
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass
    finally:
        _telemetry_clients.discard(websocket)


async def _broadcast_telemetry() -> None:
    """Send each kernel snapshot to all connected local clients at 20 Hz."""
    while True:
        if _telemetry_clients:
            snapshot = await asyncio.to_thread(kernel.get_system_snapshot)
            clients = tuple(_telemetry_clients)
            outcomes = await asyncio.gather(
                *(client.send_json(snapshot) for client in clients),
                return_exceptions=True,
            )
            for client, outcome in zip(clients, outcomes):
                if isinstance(outcome, BaseException):
                    _telemetry_clients.discard(client)
        await asyncio.sleep(0.05)


def _is_proxy() -> bool:
    """Return whether this process forwards requests to a separate core."""
    return KERNEL_ROLE != "core" and bool(KERNEL_SERVICE_URL)


async def _proxy_json(method: str, path: str, **kwargs: object) -> dict[str, object]:
    """Forward an API request to the core service and normalize errors."""
    if _http_client is None:
        raise HTTPException(status_code=503, detail="core service is not connected")
    try:
        response = await _http_client.request(method, path, **kwargs)
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=error.response.status_code,
            detail=error.response.text,
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="core service request failed") from error
    return response.json()


async def _proxy_telemetry(websocket: WebSocket) -> None:
    """Forward the core service WebSocket stream to one dashboard client."""
    if not KERNEL_SERVICE_URL:
        await websocket.close(code=1011)
        return
    upstream = KERNEL_SERVICE_URL.replace("https://", "wss://").replace("http://", "ws://")
    try:
        async with websocket_connect(f"{upstream}/ws/telemetry") as connection:
            async for message in connection:
                if isinstance(message, str):
                    await websocket.send_text(message)
                else:
                    await websocket.send_bytes(message)
    except WebSocketDisconnect:
        logger.info("Proxied telemetry client disconnected")
    except Exception:
        logger.exception("Core telemetry websocket unavailable")
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass


app.mount(
    "/",
    StaticFiles(directory=ROOT / "frontend", html=True),
    name="frontend",
)


__all__ = ["app", "kernel"]