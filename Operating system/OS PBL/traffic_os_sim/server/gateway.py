import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List
from core.unified_engine import engine

app = FastAPI(title="Smart Traffic OS Edge Gateway")

class CorridorRequest(BaseModel):
    pid: str
    request: List[int]

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(engine.run_loop())

@app.get("/api/health")
def health():
    return {"status": "ONLINE", "module": "CCSE0303A OS PBL"}

@app.post("/api/emergency")
def emergency():
    return engine.trigger_emergency_override()

@app.post("/api/reset")
def reset():
    engine.reset_emergency()
    return {"status": "RESET"}

@app.post("/api/bankers/request")
def bankers_request(req: CorridorRequest):
    return engine.evaluate_corridor_request(req.pid, req.request)

@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(engine.get_live_telemetry())
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
def get_dashboard():
    return FileResponse("frontend/index.html")
