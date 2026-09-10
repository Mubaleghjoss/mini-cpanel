import logging
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.base import User
from app.core.security import get_password_hash
from app.api.auth import router as auth_router
from app.api.system import router as system_router
from app.api.files import router as files_router
from app.api.projects import router as projects_router
from app.api.backups import router as backups_router
from app.api.notifications import router as notifications_router
from app.api.databases import (
    disabled_query_router,
    router as databases_router,
)
from app.api.marketplace import router as marketplace_router
from app.api.terminal import router as terminal_router
from app.api.users import router as users_router
from app.api.docker import router as docker_router
from app.api.ingress import router as ingress_router
from app.api.applications import router as applications_router
from app.core.scheduler import start_scheduler



logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cpanel_lite")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        user_count = db.query(User).count()
        if user_count == 0:
            logger.warning("No users found in database. Seeding default admin user...")
            default_username = "admin"
            default_password = secrets.token_urlsafe(16)
            
            hashed_password = get_password_hash(default_password)
            default_user = User(
                username=default_username,
                password_hash=hashed_password
            )
            db.add(default_user)
            db.commit()
            logger.info(f"Default admin user created successfully. Username: {default_username}")
            logger.info(f"Default admin password: {default_password}")
            logger.warning("IMPORTANT: Change this password immediately after first login!")
    except Exception as e:
        logger.error(f"Error seeding database: {e}")
    finally:
        db.close()
        
    start_scheduler()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan
)

origins = [origin.strip() for origin in settings.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Include API Routers
app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["Authentication"])
app.include_router(system_router, prefix=f"{settings.API_V1_STR}/system", tags=["System Metrics"])
app.include_router(files_router, prefix=f"{settings.API_V1_STR}/files", tags=["File Manager"])
app.include_router(projects_router, prefix=f"{settings.API_V1_STR}/projects", tags=["Project Manager"])
app.include_router(backups_router, prefix=f"{settings.API_V1_STR}/backups", tags=["Backup Manager"])
app.include_router(notifications_router, prefix=f"{settings.API_V1_STR}/notifications", tags=["Notification Manager"])
# Register the terminal 410 route first so it short-circuits the protected database router.
app.include_router(disabled_query_router, prefix=f"{settings.API_V1_STR}/databases", tags=["Database Administrator"])
app.include_router(databases_router, prefix=f"{settings.API_V1_STR}/databases", tags=["Database Administrator"])
app.include_router(marketplace_router, prefix=f"{settings.API_V1_STR}/marketplace", tags=["App Store Marketplace"])
app.include_router(terminal_router, prefix=f"{settings.API_V1_STR}/system/terminal", tags=["Terminal Console"])
app.include_router(users_router, prefix=f"{settings.API_V1_STR}/users", tags=["User Management"])
app.include_router(docker_router, prefix=f"{settings.API_V1_STR}/docker", tags=["Docker Administrator"])
app.include_router(ingress_router, prefix=f"{settings.API_V1_STR}/ingress", tags=["Ingress Proxy Router"])
app.include_router(applications_router, prefix=f"{settings.API_V1_STR}/applications", tags=["Applications Inventory"])


@app.get("/health")
def health_check():
    return {"status": "ok", "project": settings.PROJECT_NAME}
