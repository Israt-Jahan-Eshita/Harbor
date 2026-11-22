"""Integration test configuration using harbor_test PostgreSQL database."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

# Ensure integration tests run against TEST_DATABASE_URL rather than harbor_dev
from app.config import get_settings
from app.db import build_engine, get_db
from app.main import app

_settings = get_settings()
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or _settings.test_database_url
if not TEST_DB_URL:
    raise RuntimeError("TEST_DATABASE_URL must be configured for integration tests.")

test_engine = build_engine(TEST_DB_URL)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine, class_=Session)


def override_get_db() -> Generator[Session, None, None]:
    """Yield a session bound to harbor_test."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Provide a database session connected to harbor_test."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """FastAPI TestClient wired to harbor_test."""
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
