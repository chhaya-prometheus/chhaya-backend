import json
import threading
import time

import boto3

from src.core.config import settings
from src.core.logger import configLogger

logger = configLogger(__file__)

CITIES_FILE = "cities.json"
LEGACY_FILE = "cells.geojson"

# filename -> {"data", "body", "etag", "loaded_at", plus "by_h3" / "by_ward" for cells files}
_files = {}


class DataLoadError(RuntimeError):
    """Raised when the data cannot be loaded from S3 at startup."""


def _key(name):
    return f"{settings.S3_PREFIX}/{name}"


def _s3_client():
    # Credentials come from the environment, the AWS CLI profile, or the EC2 role
    return boto3.client("s3", region_name=settings.AWS_REGION)


def _build_wards(features):
    """Group cells by ward_id. Cells with a null ward_id (demo cities) are skipped."""
    wards = {}
    for f in features:
        p = f["properties"]
        ward_id = p.get("ward_id")
        if ward_id is None:
            continue
        w = wards.setdefault(str(ward_id), {
            "ward_id": ward_id,
            "ward_name": p.get("ward"),
            "n_cells": 0,
            "population_sum": 0,
            "_priority_sum": 0.0,
            "cell_ids": [],
            "_points": [],
        })
        w["n_cells"] += 1
        w["population_sum"] += p.get("population") or 0
        w["_priority_sum"] += p.get("priority") or 0
        w["cell_ids"].append(p["h3_index"])
        w["_points"].extend(f["geometry"]["coordinates"][0])

    # rank 1 = highest average priority
    ranked = sorted(wards.values(), key=lambda w: w["_priority_sum"] / w["n_cells"], reverse=True)
    for rank, w in enumerate(ranked, start=1):
        points = w.pop("_points")
        w["avg_priority"] = round(w.pop("_priority_sum") / w["n_cells"], 4)
        w["ward_rank"] = rank
        w["bbox"] = [
            min(p[0] for p in points),
            min(p[1] for p in points),
            max(p[0] for p in points),
            max(p[1] for p in points),
        ]
    return wards


def _install(name, data, etag):
    """Build the complete entry first, then store it with one assignment.
    If building raises (e.g. NaN in the file, or a cell without h3_index),
    the old copy of this file stays in place."""
    entry = {
        "data": data,
        "body": json.dumps(data, allow_nan=False).encode("utf-8"),
        "etag": etag,
        "loaded_at": time.time(),
    }
    if name.endswith("_cells.geojson"):
        entry["by_h3"] = {f["properties"]["h3_index"]: f for f in data["features"]}
        entry["by_ward"] = _build_wards(data["features"])
    _files[name] = entry


def _load_file(name):
    start = time.perf_counter()
    obj = _s3_client().get_object(Bucket=settings.S3_BUCKET, Key=_key(name))
    data = json.loads(obj["Body"].read().decode("utf-8"))

    if name.endswith("cells.geojson") and not data.get("features"):
        raise ValueError("cells file contains no features")

    _install(name, data, obj["ETag"])
    ms = round((time.perf_counter() - start) * 1000)
    logger.info(f"Loaded {name} in {ms} ms")


def get_file(name):
    """Cache entry for one S3 file, or None if it is not loaded."""
    return _files.get(name)


def get_cities():
    entry = _files.get(CITIES_FILE)
    if entry is None:
        raise DataLoadError("cities.json has not been loaded")
    return entry["data"]


def get_city(slug):
    """The city with this slug, or None. Routes use this to reject unknown slugs."""
    return next((c for c in get_cities() if c["slug"] == slug), None)


def _all_names():
    names = [LEGACY_FILE]
    for city in get_cities():
        slug = city["slug"]
        names += [f"{slug}_cells.geojson", f"{slug}_status.json"]
    return names


def load_data():
    """Startup load. cities.json is required; a broken city file is skipped, not fatal."""
    if not settings.S3_BUCKET:
        message = "S3_BUCKET is not set. Add it to your .env file."
        logger.error(message)
        raise DataLoadError(message)

    try:
        _load_file(CITIES_FILE)
    except Exception as e:
        logger.error("Could not load cities.json", exc_info=True)
        raise DataLoadError(
            f"Could not load s3://{settings.S3_BUCKET}/{_key(CITIES_FILE)}: "
            f"{type(e).__name__}: {e}"
        ) from e

    for name in _all_names():
        try:
            _load_file(name)
        except Exception as e:
            logger.error(f"Could not load {name}, skipping it: {type(e).__name__}: {e}")

    if not any(name.endswith("_cells.geojson") for name in _files):
        raise DataLoadError("No city cells file could be loaded")


def _refresh_file(name):
    """Re-download one file only if it is new, or if it never loaded successfully."""
    head = _s3_client().head_object(Bucket=settings.S3_BUCKET, Key=_key(name))
    current = _files.get(name)
    if current is None or head["ETag"] != current["etag"]:
        logger.info(f"{name}: new version in S3, loading")
        _load_file(name)
    else:
        logger.debug(f"{name}: unchanged")


def _refresh_loop():
    while True:
        time.sleep(settings.REFRESH_SECONDS)
        try:
            _refresh_file(CITIES_FILE)  # picks up newly added cities
        except Exception as e:
            logger.error(f"Refresh of cities.json failed: {type(e).__name__}: {e}")
        for name in _all_names():
            try:
                _refresh_file(name)
            except Exception as e:
                logger.error(f"Refresh of {name} failed, keeping last good copy: {type(e).__name__}: {e}")


def start_background_refresh():
    threading.Thread(target=_refresh_loop, daemon=True).start()
    logger.info(f"Background refresh started (every {settings.REFRESH_SECONDS}s)")