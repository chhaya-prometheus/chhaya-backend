# Chhaya Backend

Backend service for the Chhaya climate planning platform. This project exposes a FastAPI API that serves city and ward geospatial data, climate-planning summaries, and what-if impact calculations for Delhi and other supported cities.

The API loads GeoJSON and metadata from an S3-backed data source, refreshes it in the background, and keeps the frontend served with lightweight, cache-friendly responses.

## Overview

Chhaya is a climate planning and urban resilience platform that helps users explore city-level and ward-level planning data. The backend acts as the data access layer between upstream spatial datasets in S3 and the frontend interface.

This repository currently provides:

- A FastAPI application serving city data and planning endpoints.
- GeoJSON cell and ward data loading from AWS S3.
- Background refresh of datasets to keep responses current.
- Legacy compatibility routes for the earlier Delhi frontend.
- Health checks and observability for operational monitoring.
- Docker-based deployment and reverse-proxy setup.

## Architecture

The application follows a simple layered structure:

- `src/main.py` initializes the FastAPI app, middleware, and lifecycle hooks.
- `src/api/` contains route definitions for cities, cells, and legacy endpoints.
- `src/services/s3_service.py` handles S3 retrieval, caching, and background refresh logic.
- `src/core/config.py` centralizes environment configuration.
- `src/core/logger.py` configures structured logging.
- `contract/` contains JSON schema and example GeoJSON payloads used by the data pipeline.
- `tests/` validates S3-backed dataset behavior and service expectations.

## Key Features

### City and Cell APIs

The API exposes endpoints such as:

- `/health` — Service and dataset health.
- `/cities` — List configured cities.
- `/cities/{slug}/cells` — Return a city's GeoJSON cell dataset.
- `/cities/{slug}/status` — Fetch city status information.
- `/cities/{slug}/wards` — Retrieve ward summaries.
- `/cities/{slug}/wards/{ward_id}` — Retrieve a specific ward summary.
- `/cities/{slug}/top` — Retrieve the highest-priority cells or wards.
- `/cities/{slug}/whatif` — Estimate planning scenarios.

There are also legacy routes kept for compatibility:

- `/cells`
- `/cells/{h3}`
- `/wards`
- `/status`
- `/whatif`

### S3-Driven Data Pipeline

The backend does not store geospatial data locally. Instead, it expects JSON files in an S3 bucket, such as:

- `cities.json`
- `{city_slug}_cells.geojson`
- `{city_slug}_status.json`

At startup, it downloads and validates the configured files, then keeps a cache in memory and refreshes it periodically based on a configurable interval.

### Background Refresh

The app starts a daemon thread that periodically checks S3 object ETags and re-downloads files when they change. This allows the backend to keep serving the latest data without restarting the service.

## Repository Layout

```text
.
├── .dockerignore
├── .env.example
├── .github/
├── .gitignore
├── Caddyfile
├── Dockerfile
├── README.md
├── LICENSE
├── contract/
│   ├── cell.schema.json
│   └── mock_cells.geojson
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── scripts/
├── src/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── cells.py
│   │   └── cities.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── logger.py
│   ├── main.py
│   ├── models/
│   └── services/
│       └── s3_service.py
└── tests/
    ├── conftest.py
    └── test_s3_data.py
```

## Tech Stack

- **Python 3.11** — Programming language.
- **FastAPI** — API routing and request handling.
- **Pydantic and pydantic-settings** — Settings validation.
- **boto3** — AWS S3 integration.
- **GeoJSON** — City and cell spatial data representation.
- **Docker and Docker Compose** — Containerized deployment.
- **Caddy** — Reverse proxy and static asset frontend host.

## Prerequisites

Before running the project, ensure you have:

- Python 3.11 or later.
- pip.
- Access to an AWS S3 bucket containing the city datasets.
- A configured `.env` file with the required settings.
- Docker and Docker Compose (optional, for containerized deployment).

## Configuration

Copy the sample environment file:

```bash
cp .env.example .env
```

The repository ships with the following configuration defaults:

| Variable | Default Value | Description |
|---|---|---|
| `API_PORT` | `8000` | API server port. |
| `CORS_ORIGINS` | `*` | Allowed cross-origin request origins. |
| `LOG_LEVEL` | `INFO` | Logging level. |
| `LOG_TO_FILE` | `false` | Whether to write logs to a file. |
| `AWS_REGION` | `ap-south-1` | AWS region. |
| `S3_BUCKET` | Empty | S3 bucket containing the datasets. |
| `S3_PREFIX` | `features` | S3 object prefix. |
| `REFRESH_SECONDS` | `300` | Dataset refresh interval in seconds. |
| `POSTGRES_USER` | `postgres` | PostgreSQL username. |
| `POSTGRES_PASSWORD` | Empty | PostgreSQL password. |
| `POSTGRES_DB` | `chhaya_db` | PostgreSQL database name. |
| `ROOT_PATH` | Empty | Root path for the application. |

**Important notes:**

- `S3_BUCKET` is required for startup data loading.
- AWS credentials can come from environment variables, an AWS CLI profile, or an IAM role.
- When running locally without an existing AWS credentials configuration, you can optionally set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in `.env`.

## Local Development

### 1. Create a Virtual Environment

```bash
python -m venv .venv
```

### 2. Activate the Virtual Environment

**Linux/macOS:**

```bash
source .venv/bin/activate
```

**Windows (Command Prompt):**

```cmd
.venv\Scripts\activate.bat
```

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the API

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Access the API

- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

## Docker

### Build and Run with Docker

```bash
docker build -t chhaya-backend .
docker run --rm -p 8000:8000 --env-file .env chhaya-backend
```

### Run with Docker Compose

```bash
docker compose up --build
```

This brings up:

- `api` — The FastAPI backend.
- `caddy` — A reverse proxy for frontend routing and TLS termination.

## Production Notes

The provided `Caddyfile` routes requests under `/api/*` to the backend service, while other routes are served as static frontend content. This is useful for deployments where the frontend and backend are served from the same host.

The service is designed to operate in a containerized environment and supports environment-based configuration for the AWS region, S3 bucket, ports, and CORS.

## Testing

The repository includes tests focused on S3-backed data loading and service responses.

Run the test suite with:

```bash
pytest
```

The test suite validates dataset loading behavior and ensures the API can work correctly with sample city data.

## Data Contracts

The `contract/` directory contains schema and example files used to validate the structure of cell and city geospatial data.

These files are useful when preparing inputs for the backend or developing against consistent data formats.

## Contributing

Contributions are welcome. If you would like to improve the API, add new endpoints, or expand support for more cities or planning metrics, please open an issue or submit a pull request with a clear description of the change.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Contact

For questions about the project, deployment, or dataset integration, reach out through the repository issues or the project's maintainers.
