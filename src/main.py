import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from src.api import cells, cities
from src.core.config import settings
from src.core.logger import configLogger
from src.services.s3_service import get_cities, get_file, load_data, start_background_refresh

logger = configLogger(__file__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.PROJECT_NAME} (log level {settings.LOG_LEVEL})")
    load_data()
    start_background_refresh()
    logger.info(f"Startup complete: {len(get_cities())} cities listed in cities.json")
    yield
    logger.info("Shutting down")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API for Delhi Climate Planning Engine",
    lifespan=lifespan,
    root_path=settings.ROOT_PATH,
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    ms = round((time.perf_counter() - start) * 1000)
    level = logging.DEBUG if request.url.path == "/health" else logging.INFO
    logger.log(level, f"{request.method} {request.url.path} -> {response.status_code} ({ms} ms)")
    return response

@app.get("/health")
def health_check():
    report = {}
    for city in get_cities():
        entry = get_file(f"{city['slug']}_cells.geojson")
        report[city["slug"]] = {
            "cell_count": len(entry["data"]["features"]) if entry else 0,
            "loaded_at": entry["loaded_at"] if entry else None,
            "etag": entry["etag"] if entry else None,
        }
    return {"status": "ok", "cities": report}

app.include_router(cells.router)
app.include_router(cities.router)