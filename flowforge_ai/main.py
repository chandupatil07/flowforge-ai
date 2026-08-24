from fastapi import FastAPI
from flowforge_ai.control_plane.auth.routes import router as auth_router
from flowforge_ai.control_plane.job_routes import router as job_router
from flowforge_ai.control_plane.worker_routes import router as worker_router

app = FastAPI(
    title="FlowForge AI Control Plane API",
    description="FlowForge AI — Distributed Job Scheduling Platform with AI Diagnostics.",
    version="0.2.0"
)

# Mount Routers
app.include_router(auth_router)
app.include_router(job_router)
app.include_router(worker_router)

@app.get("/")
def read_root():
    return {"message": "FlowForge AI Control Plane API is operational."}
