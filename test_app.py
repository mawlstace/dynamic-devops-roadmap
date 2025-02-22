"""
Unit Tests for OpenSenseMap Beekeeping API
"""
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest
import requests
from flask import Flask
from main import app, get_temperature_status, redis_client, minio_client

# Mock Redis and MinIO clients
@pytest.fixture(autouse=True)
def mock_redis():
    """Mock Redis client for testing."""
    with patch('main.redis_client') as mock:
        mock.get.return_value = None
        yield mock

@pytest.fixture(autouse=True)
def mock_minio():
    """Mock MinIO client for testing."""
    with patch('main.minio_client') as mock:
        yield mock

@pytest.fixture
def client():
    """
    Fixture that creates a test client for our Flask application.
    """
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def mock_sensor_data():
    """
    Fixture that provides mock sensor data for testing.
    """
    return {
        "sensors": [
            {
                "title": "Temperatur",
                "lastMeasurement": {
                    "value": "25.5",
                    "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                }
            }
        ]
    }

def test_index_endpoint(client):
    """Test the index endpoint returns correct API information."""
    response = client.get('/')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "name" in data
    assert "version" in data
    assert "endpoints" in data
    assert isinstance(data["endpoints"], list)

def test_version_endpoint(client):
    """Test the version endpoint returns correct version string."""
    response = client.get('/version')
    assert response.status_code == 200
    assert response.data.decode('utf-8') == "0.0.2"  # Updated version number

@pytest.mark.parametrize("temperature,expected_status", [
    (5, "Too Cold"),
    (25, "Good"),
    (40, "Too Hot"),
    (10, "Too Cold"),
    (36, "Good"),
    (37, "Too Hot")
])
def test_get_temperature_status(temperature, expected_status):
    """Test temperature status determination."""
    assert get_temperature_status(temperature) == expected_status

@patch('requests.get')
def test_temperature_endpoint_success(mock_get, client, mock_sensor_data):
    """Test successful temperature endpoint response."""
    mock_response = MagicMock()
    mock_response.json.return_value = mock_sensor_data
    mock_get.return_value = mock_response
    
    response = client.get('/temperature')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "temperature" in data
    assert "status" in data
    assert "timestamp" in data

@patch('requests.get')
def test_temperature_endpoint_old_data(mock_get, client, mock_sensor_data):
    """Test temperature endpoint with outdated sensor data."""
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    mock_sensor_data["sensors"][0]["lastMeasurement"]["createdAt"] = \
        old_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    
    mock_response = MagicMock()
    mock_response.json.return_value = mock_sensor_data
    mock_get.return_value = mock_response
    
    response = client.get('/temperature')
    assert response.status_code == 404
    assert b"Data exceeds 1 hour threshold" in response.data

@patch('requests.get')
def test_temperature_endpoint_api_error(mock_get, client):
    """Test temperature endpoint handling of API errors."""
    mock_get.side_effect = requests.exceptions.RequestException("API Error")
    
    response = client.get('/temperature')
    assert response.status_code == 503
    assert b"Error fetching sensor data" in response.data

def test_metrics_endpoint(client):
    """Test the metrics endpoint returns Prometheus metrics."""
    response = client.get('/metrics')
    assert response.status_code == 200
    assert b"beekeeping_api_request_count" in response.data
    assert b"beekeeping_api_last_temperature" in response.data

@patch('requests.get')
def test_temperature_endpoint_missing_sensor(mock_get, client):
    """Test temperature endpoint handling of missing sensor data."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"sensors": []}
    mock_get.return_value = mock_response
    
    response = client.get('/temperature')
    assert response.status_code == 404
    assert b"Temperature sensor not found" in response.data

@patch('requests.get')
def test_temperature_endpoint_invalid_data(mock_get, client):
    """Test temperature endpoint handling of invalid sensor data."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "sensors": [{
            "title": "Temperatur",
            "lastMeasurement": None
        }]
    }
    mock_get.return_value = mock_response
    
    response = client.get('/temperature')
    assert response.status_code == 404
    assert b"No temperature measurements available" in response.data