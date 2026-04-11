# main.py - SHOPS EKLENMİŞ
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from sqlalchemy import select, func  # ← BUNU EKLE!
from database.database import get_db
from models.user import User, UserRole, AuthProvider 
from config.config import settings  # settings import et!
from database.database import db_manager
from fastapi.staticfiles import StaticFiles
import os
import httpx
from fastapi.responses import Response


# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# main.py'ye EN BAŞA ekle:
import os
os.environ["DEBUG"] = "true"
os.environ["ENVIRONMENT"] = "development"
logger = logging.getLogger("craftora")

# Create FastAPI app
app = FastAPI(
    title="Craftora API",
    description="No-Code E-Commerce Platform", 
    version="1.0.0",
    docs_url="/docs",  # ✅ HER ZAMAN AÇIK
    redoc_url="/redoc",  # ✅ HER ZAMAN AÇIK
    openapi_url="/openapi.json",  # ✅ HER ZAMAN AÇIk
    debug=True
)

# ==================== MINIO PROXY ====================

# ==================== MINIO PROXY ====================
@app.get("/craftora-uploads/{path:path}")
async def proxy_minio(path: str):
    """MinIO'ya proxy yap - Görselleri serve et"""
    try:
        # DİKKAT: path ZATEN craftora-uploads içermiyor!
        minio_url = f"http://localhost:9000/craftora-uploads/{path}"
        print(f"🔍 Proxy: {minio_url}")
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(minio_url)
            
            if resp.status_code == 200:
                return Response(
                    content=resp.content,
                    media_type=resp.headers.get("content-type", "image/jpeg")
                )
            else:
                print(f"❌ MinIO'dan {resp.status_code} döndü")
                return Response(
                    content="Görsel bulunamadı",
                    status_code=404
                )
    except Exception as e:
        print(f"❌ Hata: {e}")
        return Response(
            content=f"Hata: {str(e)}",
            status_code=500
        )

go_uploads_path = os.path.join(os.path.dirname(__file__), "../go-backend/uploads")
os.makedirs(go_uploads_path, exist_ok=True)
app.mount("/go-uploads", StaticFiles(directory=go_uploads_path), name="go-uploads")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",           # Next.js için
        "https://craftora.vercel.app",      # ✅ FRONTEND VERCEL
        "https://craftora-z524.vercel.app", # ✅ SENİN SİTEN
        "https://craftora-seven.vercel.app", # ✅ DİĞER
        "https://craftora-python.vercel.app", # Backend'in kendisi
        "https://craftora-go.vercel.app",     # Go backend
        "https://crafotra.netlify.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

@app.options("/{path:path}")
async def options_handler(request: Request):
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": request.headers.get("origin", ""),
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Allow-Credentials": "true",
        }
    )

# ==================== HEALTH CHECK ====================

@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "message": " Craftora API is running!",
        "version": "1.0.0",
        "endpoints": {
            "auth": "/auth",
            "users": "/users", 
            "shops": "/shops",
            "docs": "/docs",
            "redoc": "/redoc"
        }
    }

# auth.py veya users.py dosyasına ekle:
@app.get("/me/test")
async def get_my_profile_test():
    """
    TEST endpoint - No auth required.
    """
    return {
        "id": "test-user-id",
        "email": "test@craftora.com",
        "full_name": "Test User",
        "avatar_url": None,
        "role": "user",
        "is_seller": False,
        "is_verified": True,
        "is_active": True,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
    }    

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": "2024-01-01T00:00:00Z",
        "services": {
            "api": "running",
            "database": "connected",
            "authentication": "ready"
        }
    }





@app.get("/db/stats")
async def get_database_stats(db: AsyncSession = Depends(get_db)):
    """
    Get database statistics.
    """
    try:
        # User counts
        total_users = await db.scalar(select(func.count(User.id)))
        active_users = await db.scalar(
            select(func.count(User.id)).where(User.is_active == True)
        )
        sellers = await db.scalar(
            select(func.count(User.id)).where(User.role == "seller")
        )
        admins = await db.scalar(
            select(func.count(User.id)).where(User.role == "admin")
        )
        
        # Recent users (last 7 days)
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_users = await db.scalar(
            select(func.count(User.id)).where(User.created_at >= week_ago)
        )
        
        # Auth providers
        google_users = await db.scalar(
            select(func.count(User.id)).where(User.auth_provider == "google")
        )
        apple_users = await db.scalar(
            select(func.count(User.id)).where(User.auth_provider == "apple")
        )
        email_users = await db.scalar(
            select(func.count(User.id)).where(User.auth_provider == "email")
        )
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "database": "craftora",
            "statistics": {
                "users": {
                    "total": total_users,
                    "active": active_users,
                    "inactive": total_users - active_users,
                    "sellers": sellers,
                    "admins": admins,
                    "regular": total_users - sellers - admins
                },
                "growth": {
                    "last_7_days": recent_users,
                    "active_percentage": round((active_users / total_users * 100), 2) if total_users > 0 else 0
                },
                "auth_providers": {
                    "google": google_users,
                    "apple": apple_users,
                    "email": email_users,
                    "unknown": total_users - google_users - apple_users - email_users
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Database stats error: {e}")
        return {
            "error": str(e),
            "message": "Could not retrieve database statistics"
        }

# ==================== ROUTERS IMPORT ====================

# Auth router
try:
    from api.auth import router as auth_router
    app.include_router(auth_router, prefix=settings.API_PREFIX)
    logger.info(" Auth router loaded successfully")
except ImportError as e:
    logger.error(f" Failed to import auth router: {e}")
except Exception as e:
    logger.error(f" Error loading auth router: {e}")

# Users router  
# Users router  
try:
    from api.users import router as users_router
    app.include_router(users_router, prefix=settings.API_PREFIX)  # ✅
    logger.info(" Users router loaded successfully")
except ImportError as e:
    logger.error(f" Failed to import users router: {e}")

# SHOPS router
try:
    from api.shops import router as shops_router
    app.include_router(shops_router, prefix=settings.API_PREFIX)  # ✅
    logger.info(" Shops router loaded successfully")
except ImportError as e:
    logger.error(f" Failed to import shops router: {e}")

# Products router
try:
    from api.products import router as products_router
    app.include_router(products_router, prefix=settings.API_PREFIX)  # ✅
    logger.info(" Products router loaded successfully")
except ImportError as e:
    logger.error(f" Failed to import products router: {e}")

# Orders router
try:
    from api.orders import router as orders_router
    app.include_router(orders_router, prefix=settings.API_PREFIX)  # ✅
    logger.info(" Orders router loaded successfully")
except ImportError as e:
    logger.error(f" Failed to import orders router: {e}")

# Carts router
try:
    from api.carts import router as carts_router
    app.include_router(carts_router, prefix=settings.API_PREFIX)  # ✅
    logger.info(" Carts router loaded successfully")
except ImportError as e:
    logger.error(f" Failed to import carts router: {e}")
    
# main.py'ye ekle (diğer router'ların yanına)
# main.py - router import'larının olduğu yere (diğer router'larla birlikte)
try:
    from api.cj import router as cj_router
    app.include_router(cj_router, prefix=settings.API_PREFIX)
    logger.info("✅ CJ Dropshipping router loaded successfully")
except ImportError as e:
    logger.error(f"❌ Failed to import CJ router: {e}")
except Exception as e:
    logger.error(f"❌ Error loading CJ router: {e}")
    
# main.py - diğer router'larla birlikte
try:
    from api.aliexpress import router as aliexpress_router
    app.include_router(aliexpress_router, prefix=settings.API_PREFIX)
    logger.info("✅ AliExpress router loaded successfully")
except ImportError as e:
    logger.error(f"❌ Failed to import AliExpress router: {e}")

# ==================== STARTUP EVENT ====================

# startup_event fonksiyonuna ekle
# startup_event fonksiyonuna ekle
@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info(" Craftora API starting up...")
    
    # ✅ DATABASE İNİTIALIZE ET!
    try:
        from database.database import db_manager
        await db_manager.initialize()
        logger.info(" Database initialized successfully")
    except Exception as e:
        logger.error(f" Database initialization failed: {e}")
        raise
    
    # Log loaded routes
    routes = []
    for route in app.routes:
        if hasattr(route, "methods"):
            routes.append({
                "path": route.path,
                "methods": list(route.methods),
                "name": route.name
            })
    
    logger.info(f" Loaded {len(routes)} routes")
    
    # Log loaded endpoints by category
    auth_endpoints = [r for r in routes if r["path"].startswith("/auth")]
    user_endpoints = [r for r in routes if r["path"].startswith("/users")]
    shop_endpoints = [r for r in routes if r["path"].startswith("/shops")]
    product_endpoints = [r for r in routes if r["path"].startswith("/products")]
    order_endpoints = [r for r in routes if r["path"].startswith("/orders")]
    cart_endpoints = [r for r in routes if r["path"].startswith("/carts")]
    
    logger.info(f" Auth endpoints: {len(auth_endpoints)}")
    logger.info(f" User endpoints: {len(user_endpoints)}")
    logger.info(f" Shop endpoints: {len(shop_endpoints)}")
    logger.info(f" Product endpoints: {len(product_endpoints)}")
    logger.info(f" Order endpoints: {len(order_endpoints)}")
    logger.info(f" Cart endpoints: {len(cart_endpoints)}")
    
    # List all routes
    logger.info(" All available routes:")
    for route in sorted(routes, key=lambda x: x["path"]):
        methods = ", ".join(sorted(route["methods"]))
        logger.info(f"  {methods:10} {route['path']}")
    
    logger.info(" Startup complete")

# ==================== RUN APPLICATION ====================

if __name__ == "__main__":
    import uvicorn
    
    logger.info(" Starting Craftora API server...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9004,
        reload=True,
        log_level="info"
    )