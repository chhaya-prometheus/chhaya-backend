from fastapi import APIRouter, HTTPException, Response

from src.api.cities import WhatIf, city_status, run_whatif
from src.core.logger import configLogger
from src.services.s3_service import LEGACY_FILE, get_file

logger = configLogger(__file__)

router = APIRouter()


def _legacy_entry():
    entry = get_file(LEGACY_FILE)
    if entry is None:
        raise HTTPException(status_code=503, detail=f"{LEGACY_FILE} is not loaded")
    return entry


@router.get("/cells")
def get_cells():
    """Legacy: the old Delhi file, so the deployed site keeps working."""
    return Response(content=_legacy_entry()["body"], media_type="application/json")


@router.get("/cells/{h3}")
def get_cell_by_h3(h3: str):
    for feature in _legacy_entry()["data"].get("features", []):
        if feature.get("properties", {}).get("h3") == h3:
            return feature

    logger.warning(f"Cell not found: {h3}")
    raise HTTPException(status_code=404, detail=f"Cell with H3 {h3} not found")


@router.get("/wards")
def get_ward_summaries():
    """Legacy: per-ward summary computed from the old Delhi file."""
    wards = {}

    for feature in _legacy_entry()["data"].get("features", []):
        props = feature.get("properties", {})
        ward_name = props.get("ward", "Unknown")

        if ward_name not in wards:
            wards[ward_name] = {
                "ward": ward_name,
                "cell_count": 0,
                "total_population": 0,
                "avg_priority": 0.0,
                "_priority_sum": 0.0,
            }

        wards[ward_name]["cell_count"] += 1
        wards[ward_name]["total_population"] += props.get("population", 0)
        wards[ward_name]["_priority_sum"] += props.get("priority", 0.0)

    result = []
    for w_data in wards.values():
        if w_data["cell_count"] > 0:
            w_data["avg_priority"] = round(w_data["_priority_sum"] / w_data["cell_count"], 4)
        del w_data["_priority_sum"]
        result.append(w_data)

    return result


@router.get("/status")
def legacy_status():
    """Legacy alias for /cities/delhi/status."""
    return city_status("delhi")


@router.post("/whatif")
def legacy_whatif(body: WhatIf):
    """Legacy alias for /cities/delhi/whatif."""
    return run_whatif("delhi", body)