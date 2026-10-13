import asyncio
import logging
from typing import List, Optional
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from backend.app.core.safe_paths import safe_request_path

from backend.app.core.config import settings
from backend.app.api import auth, students, hostels, devices, attendance, punches, dashboard, reports, system, users, recovery, live, student_details

logger = logging.getLogger("FastAPI")
logging.basicConfig(level=logging.INFO)

# Base directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")
FRONTEND_ASSETS = os.path.join(FRONTEND_DIST, "assets")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-grade Hostel Attendance Management System Backend API",
    version="1.0.0",
    docs_url=None if settings.APP_ENV == 'production' else '/docs',
    redoc_url=None if settings.APP_ENV == 'production' else '/redoc',
    openapi_url=None if settings.APP_ENV == 'production' else '/openapi.json'
)

# HTTP Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    if not safe_request_path(request.scope.get('path', '')):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': 'Invalid path'}, status_code=404)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if settings.APP_ENV == 'production':
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response

# CORS Configuration with Explicit Allowed Origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Next-Cursor"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[h.strip() for h in settings.ALLOWED_HOSTS.split(',') if h.strip()])

# Include Routers
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(students.router, prefix="/api")
app.include_router(student_details.router, prefix="/api")
app.include_router(hostels.router, prefix="/api")
app.include_router(devices.router, prefix="/api")
app.include_router(attendance.router, prefix="/api")
app.include_router(punches.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(recovery.router, prefix="/api")
app.include_router(live.router, prefix="/api")

# Static assets mounting for React frontend
if os.path.exists(FRONTEND_ASSETS):
    app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS), name="assets")

# Authenticated WebSocket invalidations refresh the same scoped HTTP endpoints.

@app.get("/logo.jpg", include_in_schema=False)
async def serve_logo():
    logo_path = os.path.join(FRONTEND_DIST, "logo.jpg")
    if os.path.exists(logo_path):
        return FileResponse(logo_path)
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Logo not found")

@app.get("/", include_in_schema=False)
async def serve_root():
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "project": settings.PROJECT_NAME,
        "status": "ONLINE",
        "docs_url": "/docs",
        "env": settings.APP_ENV
    }

@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str):
    if not safe_request_path(full_path):
        raise HTTPException(404, 'File not found')
    # Prevent catching unknown API endpoints
    if full_path.startswith("api/") or full_path == "api":
        raise HTTPException(status_code=404, detail="API endpoint not found")

    # Check if a static file exists in dist
    # Resolve Windows separators and reject paths escaping the frontend root.
    file_path = os.path.realpath(os.path.join(FRONTEND_DIST, full_path))
    frontend_root = os.path.realpath(FRONTEND_DIST)
    try:
        if os.path.commonpath([frontend_root, file_path]).casefold() != frontend_root.casefold():
            raise HTTPException(status_code=404, detail='File not found')
    except ValueError:
        raise HTTPException(status_code=404, detail='File not found')
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)

    # Fallback to index.html for client-side React routing (e.g. /dashboard, /attendance, /login)
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)

    return {
        "project": settings.PROJECT_NAME,
        "status": "ONLINE",
        "docs_url": "/docs",
        "env": settings.APP_ENV
    }
