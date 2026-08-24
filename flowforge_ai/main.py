from fastapi import FastAPI
from flowforge_ai.control_plane.auth.routes import router as auth_router

app = FastAPI(
    title="FlowForge AI Control Plane API",
    description="Minimal implementation-ready MVP backend foundation for FlowForge AI.",
    version="0.1.0"
)

# Mount Routers
app.include_router(auth_router)

@app.get("/")
def read_root():
    return {"message": "FlowForge AI Control Plane API is operational."}
