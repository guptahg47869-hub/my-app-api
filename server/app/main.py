from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from .websockets import manager
import asyncio

from .routers import trees, waxing, metal_prep, supply, queue, casting, quenching, cutting, reconciliation, metals, scrap, reports, flask_search
from .services.auto_quenching import auto_quenching_loop

app = FastAPI(title="Jewelry Casting API (MVP)")
import os
print("DATABASE_URL (server) =>", os.getenv("DATABASE_URL"))


@app.on_event('startup')
async def _start_background_loops():
    asyncio.create_task(auto_quenching_loop())

@app.get("/_ping")
def ping():
    return {"ok": True}


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

app.include_router(trees.router)
app.include_router(waxing.router)
app.include_router(metal_prep.router)
app.include_router(supply.router)
app.include_router(casting.router)
app.include_router(quenching.router)   
app.include_router(cutting.router)
app.include_router(reconciliation.router)     
app.include_router(queue.router)
app.include_router(metals.router) 
app.include_router(scrap.router)  
app.include_router(reports.router)
app.include_router(flask_search.router)

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)
