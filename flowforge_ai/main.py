from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from flowforge_ai.control_plane.auth.routes import router as auth_router
from flowforge_ai.control_plane.job_routes import router as job_router
from flowforge_ai.control_plane.worker_routes import router as worker_router

app = FastAPI(
    title="FlowForge AI Control Plane API",
    description="FlowForge AI — Distributed Job Scheduling Platform with AI Diagnostics.",
    version="0.2.0"
)

# Allow the local Vite dev server (frontend) to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(auth_router)
app.include_router(job_router)
app.include_router(worker_router)

@app.get("/")
def read_root():
    return {"message": "FlowForge AI Control Plane API is operational."}
