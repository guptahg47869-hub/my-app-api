from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from .websockets import manager
from .routers import trees, waxing, supply, queue, casting, quenching, cutting, metals, scrap, reports

app = FastAPI(title="Jewelry Casting API (MVP)")

@app.get("/_ping")
def ping():
    return {"ok": True}


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

app.include_router(trees.router)
app.include_router(waxing.router)
app.include_router(supply.router)
app.include_router(casting.router)
app.include_router(quenching.router)   
app.include_router(cutting.router)     
app.include_router(queue.router)
app.include_router(metals.router) 
app.include_router(scrap.router)  
app.include_router(reports.router)

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)
