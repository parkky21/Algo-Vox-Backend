from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import vector_stores, agents
from app.api.routes.ws_routes import agent_ws

app = FastAPI(
    title="Algo Vox API",
    description="Voice agent system with vector search integration",
    version="1.0.0",
    lifespan=agents.lifespan
)

# CORS Middleware (optional but recommended for frontend testing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this to specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(vector_stores.router, prefix="/vector_stores", tags=["Vector Stores"])
app.include_router(agents.router, prefix="/agents", tags=["Agents"])
app.add_api_websocket_route("/ws/agent/{agent_id}", agent_ws)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="debug")
