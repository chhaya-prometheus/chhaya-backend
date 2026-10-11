import pytest
from fastapi.testclient import TestClient

from src.core.config import settings
from src.main import app
from src.services.s3_service import DataLoadError, load_data

import src.services.s3_service as s3_service

CELL_FIELDS = [
    "h3_index", "ndvi", "lst_c", "population", "built_frac", "dust_idx",
    "school_count", "priority", "priority_rank", "ward", "ward_id", "area_name",
]
CITY_FIELDS = ["slug", "name", "bbox", "center", "zoom", "data_mode", "has_wards"]
WARD_FIELDS = ["ward_id", "ward_name", "n_cells", "population_sum", "avg_priority", "ward_rank"]


@pytest.fixture(scope="module")
def client():
    # Using "with" runs the app's startup, which loads the data from S3
    with TestClient(app) as c:
        yield c


def test_health_reports_every_city(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["cities"]["delhi"]["cell_count"] > 0


def test_cities_have_contract_fields(client):
    cities = client.get("/cities").json()
    assert len(cities) >= 2
    for city in cities:
        for key in CITY_FIELDS:
            assert key in city, f"city {city.get('slug')} is missing {key}"
    delhi = next(c for c in cities if c["slug"] == "delhi")
    assert delhi["data_mode"] == "real"
    assert delhi["has_wards"] is True


def test_every_city_serves_cells_with_cache_header(client):
    for city in client.get("/cities").json():
        response = client.get(f"/cities/{city['slug']}/cells")
        assert response.status_code == 200, city["slug"]
        assert response.json()["type"] == "FeatureCollection"
        assert "max-age=300" in response.headers["cache-control"]


def test_unknown_city_returns_404(client):
    assert client.get("/cities/atlantis/cells").status_code == 404
    assert client.get("/cities/atlantis/status").status_code == 404
    assert client.get("/cities/atlantis/wards").status_code == 404


def test_every_city_has_all_contract_fields(client):
    for city in client.get("/cities").json():
        features = client.get(f"/cities/{city['slug']}/cells").json()["features"]
        for f in features:
            for key in CELL_FIELDS:
                assert key in f["properties"], f"{city['slug']}: cell is missing {key}"


def test_status_files_load(client):
    for city in client.get("/cities").json():
        assert client.get(f"/cities/{city['slug']}/status").status_code == 200, city["slug"]


def test_delhi_cells_have_ward_values(client):
    features = client.get("/cities/delhi/cells").json()["features"]
    with_ward = [f for f in features if f["properties"]["ward_id"] is not None]
    assert len(with_ward) > 0
    assert all(f["properties"]["ward"] is not None for f in with_ward)


def test_demo_cities_have_null_ward_columns(client):
    demo = [c for c in client.get("/cities").json() if not c["has_wards"]]
    if not demo:
        pytest.skip("no demo city in cities.json")
    for city in demo:
        features = client.get(f"/cities/{city['slug']}/cells").json()["features"]
        for f in features:
            assert f["properties"]["ward_id"] is None
            assert f["properties"]["ward"] is None


def test_delhi_wards_list_and_detail(client):
    wards = client.get("/cities/delhi/wards").json()
    assert len(wards) > 0
    for key in WARD_FIELDS:
        assert key in wards[0]
    assert [w["ward_rank"] for w in wards] == list(range(1, len(wards) + 1))

    ward_id = wards[0]["ward_id"]
    detail = client.get(f"/cities/delhi/wards/{ward_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["cell_ids"]) == body["n_cells"]
    assert len(body["bbox"]) == 4

    assert client.get("/cities/delhi/wards/no-such-ward").status_code == 404


def test_ward_totals_match_the_cells(client):
    features = client.get("/cities/delhi/cells").json()["features"]
    with_ward = [f["properties"] for f in features if f["properties"]["ward_id"] is not None]
    wards = client.get("/cities/delhi/wards").json()
    assert sum(w["n_cells"] for w in wards) == len(with_ward)
    expected_population = sum(p["population"] or 0 for p in with_ward)
    assert sum(w["population_sum"] for w in wards) == pytest.approx(expected_population)


def test_demo_city_has_no_wards(client):
    demo = [c for c in client.get("/cities").json() if not c["has_wards"]]
    if not demo:
        pytest.skip("no demo city in cities.json")
    slug = demo[0]["slug"]
    assert client.get(f"/cities/{slug}/wards").json() == []
    assert client.get(f"/cities/{slug}/wards/1").status_code == 404
    assert client.get(f"/cities/{slug}/top", params={"level": "ward"}).status_code == 400


def test_top_cells_are_sorted_by_priority(client):
    top = client.get("/cities/delhi/top", params={"level": "cell", "n": 3}).json()
    assert len(top) == 3
    priorities = [c["priority"] for c in top]
    assert priorities == sorted(priorities, reverse=True)


def test_top_wards_are_sorted_by_rank(client):
    top = client.get("/cities/delhi/top", params={"level": "ward", "n": 3}).json()
    ranks = [w["ward_rank"] for w in top]
    assert ranks == sorted(ranks)
    assert ranks[0] == 1


def test_whatif_matches_the_heuristic(client):
    cell = client.get("/cities/delhi/cells").json()["features"][0]["properties"]
    ha = 2.0
    ndvi = 0.2 if cell["ndvi"] is None else cell["ndvi"]
    expected_delta = -(0.5 * ha * (0.4 + (1 - ndvi)) / (1 + 0.2 * ha))
    expected_people = round((cell["population"] or 0) * min(1, ha / 4) * 0.6)

    response = client.post(
        "/cities/delhi/whatif", json={"h3_index": cell["h3_index"], "canopy_ha": ha}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["delta_c"] == pytest.approx(expected_delta)
    assert body["people_benefited"] == expected_people


def test_whatif_unknown_cell_returns_404(client):
    response = client.post("/cities/delhi/whatif", json={"h3_index": "nope", "canopy_ha": 1})
    assert response.status_code == 404


def test_legacy_routes_still_work(client):
    assert client.get("/cells").json()["type"] == "FeatureCollection"
    assert client.get("/status").status_code == 200
    assert client.get("/wards").status_code == 200

    cell = client.get("/cities/delhi/cells").json()["features"][0]["properties"]
    payload = {"h3_index": cell["h3_index"], "canopy_ha": 1.5}
    assert client.post("/whatif", json=payload).json() == client.post(
        "/cities/delhi/whatif", json=payload
    ).json()


def test_cors_allows_post_preflight(client):
    response = client.options(
        "/cities/delhi/whatif",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers


def test_empty_bucket_raises(monkeypatch):
    monkeypatch.setattr(settings, "S3_BUCKET", "")
    with pytest.raises(DataLoadError):
        load_data()


def test_nonexistent_bucket_raises(monkeypatch):
    monkeypatch.setattr(settings, "S3_BUCKET", "chhaya-bucket-that-does-not-exist-123")
    with pytest.raises(DataLoadError):
        load_data()


def test_one_broken_city_does_not_take_down_the_others(client, monkeypatch):
    cities = client.get("/cities").json()
    victim = next(c["slug"] for c in cities if c["slug"] != "delhi")

    real_load = s3_service._load_file

    def flaky(name):
        if name.startswith(f"{victim}_"):
            raise RuntimeError("simulated broken file")
        real_load(name)

    monkeypatch.setattr(s3_service, "_files", {})
    monkeypatch.setattr(s3_service, "_load_file", flaky)

    with TestClient(app) as c:
        health = c.get("/health").json()
        assert health["status"] == "ok"
        assert health["cities"][victim]["cell_count"] == 0
        assert health["cities"]["delhi"]["cell_count"] > 0
        assert c.get(f"/cities/{victim}/cells").status_code == 503
        assert c.get("/cities/delhi/cells").status_code == 200