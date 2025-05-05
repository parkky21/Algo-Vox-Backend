from fastapi import FastAPI
from app.api.routes import vector_stores, agents
from app.api.routes import ws_routes

app = FastAPI(lifespan=agents.lifespan)

app.include_router(vector_stores.router, prefix="/vector_stores", tags=["Vector Stores"])
app.include_router(agents.router, prefix="/agents", tags=["Agents"])
app.include_router(agents.connect_router, tags=["Agent Connection"])
app.include_router(ws_routes.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, log_level="debug", reload=True)
