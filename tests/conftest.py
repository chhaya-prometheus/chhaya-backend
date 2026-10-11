import json
import os
from pathlib import Path

USE_REAL_S3 = os.environ.get("CHHAYA_REAL_S3") == "1"

if not USE_REAL_S3:
    # This runs before any src.* import, because settings are read at import time.
    # These are dummy values for the fake S3, not real credentials.
    os.environ.pop("AWS_PROFILE", None)
    os.environ.update({
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "ap-south-1",
        "AWS_REGION": "ap-south-1",
        "S3_BUCKET": "chhaya-delhi",
        "S3_PREFIX": "features",
    })

import boto3
import pytest
from moto import mock_aws

BUCKET = "chhaya-delhi"
LEGACY_CELLS = Path(__file__).resolve().parents[1] / "contract" / "mock_cells.geojson"

CITIES = [
    {
        "slug": "delhi", "name": "Delhi", "bbox": [77.0, 28.4, 77.4, 28.9],
        "center": [77.2, 28.6], "zoom": 10, "data_mode": "real", "has_wards": True,
    },
    {
        "slug": "mumbai", "name": "Mumbai", "bbox": [72.8, 18.9, 73.0, 19.3],
        "center": [72.9, 19.1], "zoom": 10, "data_mode": "demo", "has_wards": False,
    },
]


def _cell(h3, lng, lat, priority, rank, ward_id=None, ward=None, area=None,
          ndvi=0.3, population=1000):
    d = 0.01
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [lng, lat], [lng + d, lat], [lng + d, lat + d], [lng, lat + d], [lng, lat],
            ]],
        },
        "properties": {
            "h3_index": h3, "ndvi": ndvi, "lst_c": 38.0, "population": population,
            "built_frac": 0.5, "dust_idx": 0.4, "school_count": 1,
            "priority": priority, "priority_rank": rank,
            "ward": ward, "ward_id": ward_id, "area_name": area,
        },
    }


def _collection(features):
    return {"type": "FeatureCollection", "features": features}


def _delhi_cells():
    # 3 wards with average priorities 0.85 / 0.55 / 0.25, plus one cell with no ward.
    # d3 has a null ndvi so the null handling is exercised.
    return _collection([
        _cell("d1", 77.20, 28.60, 0.9, 1, 1, "Ward A", "Area 1"),
        _cell("d2", 77.21, 28.60, 0.8, 2, 1, "Ward A", "Area 1"),
        _cell("d3", 77.22, 28.60, 0.6, 3, 2, "Ward B", "Area 2", ndvi=None),
        _cell("d4", 77.23, 28.60, 0.5, 4, 2, "Ward B", "Area 2"),
        _cell("d5", 77.24, 28.60, 0.3, 5, 3, "Ward C", "Area 3"),
        _cell("d6", 77.25, 28.60, 0.2, 6, 3, "Ward C", "Area 3"),
        _cell("d7", 77.26, 28.60, 0.1, 7),
    ])


def _mumbai_cells():
    # Demo city: ward columns are present but null.
    return _collection([
        _cell("m1", 72.90, 19.10, 0.7, 1),
        _cell("m2", 72.91, 19.10, 0.5, 2),
        _cell("m3", 72.92, 19.10, 0.3, 3),
    ])


def _status(slug):
    return {"city": slug, "status": "ok"}


@pytest.fixture(scope="session", autouse=True)
def fake_s3():
    if USE_REAL_S3:
        yield
        return

    with mock_aws():
        s3 = boto3.client("s3", region_name="ap-south-1")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-south-1"},
        )

        def put(name, body):
            s3.put_object(Bucket=BUCKET, Key=f"features/{name}", Body=body)

        put("cities.json", json.dumps(CITIES).encode())
        put("delhi_cells.geojson", json.dumps(_delhi_cells()).encode())
        put("delhi_status.json", json.dumps(_status("delhi")).encode())
        put("mumbai_cells.geojson", json.dumps(_mumbai_cells()).encode())
        put("mumbai_status.json", json.dumps(_status("mumbai")).encode())
        put("cells.geojson", LEGACY_CELLS.read_bytes())  # legacy file for /cells and /wards
        yield