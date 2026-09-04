"""
Tests for app/engine/currency.py (Module 8 — INR secondary display) and
the GET /api/v1/exchange-rate endpoint it backs.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.engine.currency import USD_TO_INR_RATE, as_dict, usd_to_inr
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_usd_to_inr_multiplies_by_the_cited_rate():
    assert usd_to_inr(100.0) == pytest.approx(100.0 * USD_TO_INR_RATE)


def test_usd_to_inr_zero_is_zero():
    assert usd_to_inr(0.0) == 0.0


def test_as_dict_shape():
    d = as_dict()
    assert d["usd_to_inr_rate"] == USD_TO_INR_RATE
    assert d["source"]
    assert d["source_url"].startswith("http")
    assert d["source_date"]


def test_exchange_rate_endpoint(client):
    r = client.get("/api/v1/exchange-rate")
    assert r.status_code == 200
    body = r.json()
    assert body["usd_to_inr_rate"] == USD_TO_INR_RATE
    assert body == as_dict()
