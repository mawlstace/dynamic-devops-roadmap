import pytest

def test_version_endpoint(api_client):
    """Test the /version endpoint returns correct response."""
    response = api_client.get("/version")
    assert response.status_code == 200
    # Expect plain text version number
    assert response.text == "0.0.1"

def test_metrics_endpoint(api_client):
    """Test the /metrics endpoint for Prometheus metrics."""
    response = api_client.get("/metrics")
    assert response.status_code == 200
    # Check for actual metrics that exist in your API
    assert "beekeeping_api_request_count_total" in response.text
    assert "beekeeping_api_latency_seconds" in response.text

def test_invalid_endpoint(api_client):
    """Test response for non-existent endpoint."""
    response = api_client.get("/nonexistent")
    assert response.status_code == 404
