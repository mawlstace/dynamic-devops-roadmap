import pytest
import requests
from urllib.parse import urljoin

@pytest.fixture
def api_base_url():
    """Provides the base URL for the API."""
    return "http://localhost:8000"

@pytest.fixture
def api_client(api_base_url):
    """Creates a simple API client for testing."""
    class APIClient:
        def __init__(self, base_url):
            self.base_url = base_url
            
        def get(self, endpoint):
            url = urljoin(self.base_url, endpoint)
            return requests.get(url)
            
        def post(self, endpoint, json=None):
            url = urljoin(self.base_url, endpoint)
            return requests.post(url, json=json)
            
    return APIClient(api_base_url)
