from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.core.logger import configLogger
from src.services.s3_service import get_cities, get_city, get_file

logger = configLogger(__file__)

router = APIRouter()

CACHE_5_MIN = {"Cache-Control": "public, max-age=300"}


class WhatIf(BaseModel):
    h3_index: str
    canopy_ha: float = Field(ge=0)


def _city_or_404(slug):
    city = get_city(slug)
    if city is None:
        raise HTTPException(status_code=404, detail=f"Unknown city: {slug}")
    return city


def _file_or_503(name):
    entry = get_file(name)
    if entry is None:
        raise HTTPException(status_code=503, detail=f"{name} is not loaded")
    return entry


def _wards_city_or_404(slug):
    city = _city_or_404(slug)
    if not city.get("has_wards"):
        raise HTTPException(status_code=404, detail=f"{slug} has no wards")
    return city


def _ward_list(slug):
    wards = _file_or_503(f"{slug}_cells.geojson")["by_ward"]
    keys = ("ward_id", "ward_name", "n_cells", "population_sum", "avg_priority", "ward_rank")
    result = [{k: w[k] for k in keys} for w in wards.values()]
    result.sort(key=lambda w: w["ward_rank"])
    return result


def run_whatif(slug, body):
    """Heuristic cooling estimate. Keep identical to the frontend fallback."""
    _city_or_404(slug)
    by_h3 = _file_or_503(f"{slug}_cells.geojson")["by_h3"]
    cell = by_h3.get(body.h3_index)
    if cell is None:
        raise HTTPException(status_code=404, detail=f"Cell {body.h3_index} not found in {slug}")

    props = cell["properties"]
    ndvi = props.get("ndvi")
    if ndvi is None:
        ndvi = 0.2
    population = props.get("population") or 0
    ha = body.canopy_ha

    cooling_c = 0.5 * ha * (0.4 + (1 - ndvi)) / (1 + 0.2 * ha)
    people = round(population * min(1, ha / 4) * 0.6)
    return {"delta_c": -cooling_c, "people_benefited": people}


def city_status(slug):
    _city_or_404(slug)
    return JSONResponse(_file_or_503(f"{slug}_status.json")["data"])


@router.get("/cities")
def list_cities():
    return get_cities()


@router.get("/cities/{slug}/cells")
def city_cells(slug: str):
    _city_or_404(slug)
    entry = _file_or_503(f"{slug}_cells.geojson")
    return Response(content=entry["body"], media_type="application/json", headers=CACHE_5_MIN)


@router.get("/cities/{slug}/status")
def city_status_route(slug: str):
    return city_status(slug)


@router.get("/cities/{slug}/wards")
def city_wards(slug: str):
    city = _city_or_404(slug)
    if not city.get("has_wards"):
        return []
    return _ward_list(slug)


@router.get("/cities/{slug}/wards/{ward_id}")
def city_ward(slug: str, ward_id: str):
    _wards_city_or_404(slug)
    wards = _file_or_503(f"{slug}_cells.geojson")["by_ward"]
    ward = wards.get(ward_id)
    if ward is None:
        raise HTTPException(status_code=404, detail=f"Ward {ward_id} not found in {slug}")
    return ward


@router.get("/cities/{slug}/top")
def city_top(
    slug: str,
    level: Literal["cell", "ward"] = "cell",
    n: int = Query(10, ge=1, le=100),
):
    city = _city_or_404(slug)

    if level == "ward":
        if not city.get("has_wards"):
            raise HTTPException(status_code=400, detail=f"{slug} has no wards")
        return _ward_list(slug)[:n]

    features = _file_or_503(f"{slug}_cells.geojson")["data"]["features"]
    best = sorted(features, key=lambda f: f["properties"]["priority"], reverse=True)[:n]
    return [f["properties"] for f in best]


@router.post("/cities/{slug}/whatif")
def city_whatif(slug: str, body: WhatIf):
    return run_whatif(slug, body)