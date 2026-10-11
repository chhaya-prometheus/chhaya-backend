import json

import boto3

BUCKET = "chhaya-delhi"
s3 = boto3.client("s3")


def read(name):
    return json.loads(s3.get_object(Bucket=BUCKET, Key=f"features/{name}")["Body"].read())


cities = read("cities.json")
print("cities.json:", json.dumps(cities, indent=1))

for city in cities:
    slug = city["slug"]
    features = read(f"{slug}_cells.geojson")["features"]
    props = [f["properties"] for f in features]
    with_ward = [p for p in props if p.get("ward_id") is not None]
    wards = {p["ward_id"] for p in with_ward}
    print(
        f"{slug}: {len(props)} cells, {len(with_ward)} with ward_id, {len(wards)} distinct wards, "
        f"has_wards={city['has_wards']}, keys={sorted(props[0].keys())}"
    )
    if with_ward:
        print("  sample ward cell:", {k: with_ward[0].get(k) for k in ("ward", "ward_id", "area_name")})