from typing import Generator

import pytest
from boto3.session import Session


@pytest.fixture
def mock_aws_session(monkeypatch) -> Generator[Session, None, None]:
    import os

    import boto3
    import moto

    monkeypatch.setenv("MOTO_ALLOW_NONEXISTENT_REGION", "true")
    monkeypatch.setenv("MOTO_ALLOW_NONEXISTENT_ACCOUNT", "true")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    if "AWS_PROFILE" in os.environ:
        monkeypatch.delenv("AWS_PROFILE")

    with moto.mock_aws():
        session = boto3.Session()
        yield session
