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
        "S3_CELLS_KEY": "features/cells.geojson",
    })

import boto3
import pytest
from moto import mock_aws

MOCK_CELLS = Path(__file__).resolve().parents[1] / "contract" / "mock_cells.geojson"


@pytest.fixture(scope="session", autouse=True)
def fake_s3():
    if USE_REAL_S3:
        yield
        return

    with mock_aws():
        s3 = boto3.client("s3", region_name="ap-south-1")
        s3.create_bucket(
            Bucket="chhaya-delhi",
            CreateBucketConfiguration={"LocationConstraint": "ap-south-1"},
        )
        s3.put_object(
            Bucket="chhaya-delhi",
            Key="features/cells.geojson",
            Body=MOCK_CELLS.read_bytes(),
        )
        yield