"""
OpenSenseMap Beekeeping API
--------------------------
A RESTful API service that interfaces with openSenseMap to help beekeepers monitor
temperature conditions. This service includes prometheus metrics for monitoring.

Author: [Your Name]
Version: 0.0.1
"""

from datetime import datetime, timedelta, timezone
import sys
from typing import Dict, Union, Optional
import logging

from flask import Flask, jsonify, Response
import requests
from prometheus_client import CollectorRegistry, Counter, Gauge, make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Application Constants
APP_VERSION = "0.0.1"
TARGET_ID = "5eba5fbad46fb8001b799786"
OPENSENSEMAP_API_BASE = "https://api.opensensemap.org/boxes"
TEMPERATURE_THRESHOLDS = {
    "cold": 10,
    "hot": 36
}

# Initialize Flask application
app = Flask(__name__)

# Create metrics registry
REGISTRY = CollectorRegistry()
request_count = Counter(
    "beekeeping_api_request_count", 
    "Total number of requests served", 
    registry=REGISTRY
)
last_temperature = Gauge(
    "beekeeping_api_last_temperature", 
    "Last measured temperature", 
    registry=REGISTRY
)
api_latency = Gauge(
    "beekeeping_api_latency_seconds",
    "Time taken to process API requests",
    registry=REGISTRY
)

def get_temperature_status(temperature: float) -> str:
    """
    Determine temperature status based on predefined thresholds.
    
    Args:
        temperature (float): The measured temperature
        
    Returns:
        str: Status description ("Too Cold", "Good", or "Too Hot")
    """
    if temperature <= TEMPERATURE_THRESHOLDS["cold"]:
        return "Too Cold"
    elif temperature <= TEMPERATURE_THRESHOLDS["hot"]:
        return "Good"
    else:
        return "Too Hot"

def fetch_sensor_data(box_id: str) -> Optional[Dict]:
    """
    Fetch sensor data from OpenSenseMap API.
    
    Args:
        box_id (str): The senseBox ID to query
        
    Returns:
        Optional[Dict]: JSON response from API or None if request fails
    """
    try:
        response = requests.get(
            f"{OPENSENSEMAP_API_BASE}/{box_id}",
            params={"format": "json"},
            timeout=10  # Reduced timeout from 600s to 10s
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching sensor data: {e}")
        return None

@app.route("/")
def index() -> Response:
    """Root endpoint returning API information."""
    return jsonify({
        "name": "OpenSenseMap Beekeeping API",
        "version": APP_VERSION,
        "endpoints": ["/version", "/temperature", "/metrics"]
    })

@app.route("/version")
def version() -> str:
    """Return the current API version."""
    return APP_VERSION

@app.route("/temperature")
def temperature() -> Union[Response, str]:
    """
    Fetch and return the current temperature data with status.
    
    Returns:
        Union[Response, str]: JSON response with temperature data or error message
    """
    try:
        data = fetch_sensor_data(TARGET_ID)
        if not data:
            return "Error fetching sensor data", 503

        for sensor in data.get("sensors", []):
            if sensor["title"] == "Temperatur":
                measurement = sensor.get("lastMeasurement", {})
                if not measurement:
                    return "No temperature measurements available", 404

                temp_value = measurement.get("value")
                timestamp = measurement.get("createdAt")
                
                if not all([temp_value, timestamp]):
                    return "Invalid measurement data", 500

                # Parse and validate timestamp
                try:
                    # Make the parsed datetime timezone-aware
                    measurement_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
                    measurement_time = measurement_time.replace(tzinfo=timezone.utc)
                    
                    if datetime.now(timezone.utc) - measurement_time > timedelta(hours=1):
                        return "Data exceeds 1 hour threshold", 404
                    
                    # Update metrics
                    temp_float = float(temp_value)
                    request_count.inc()
                    last_temperature.set(temp_float)
                    
                    return jsonify({
                        "temperature": temp_value,
                        "status": get_temperature_status(temp_float),
                        "timestamp": timestamp
                    })
                except ValueError as e:
                    logger.error(f"Error parsing timestamp: {e}")
                    return "Invalid timestamp format", 500

        return "Temperature sensor not found", 404
    except Exception as e:
        logger.error(f"Unexpected error in temperature endpoint: {e}")
        return "Internal server error", 500

# Add metrics endpoint using middleware
app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
    '/metrics': make_wsgi_app(REGISTRY)
})

def main():
    """Main entry point for the application."""
    if len(sys.argv) > 1 and sys.argv[1] == "--version":
        print(f"OpenSenseMap Beekeeping API v{APP_VERSION}")
        sys.exit(0)
    
    app.run(host='0.0.0.0', port=8000, debug=False)

if __name__ == "__main__":
    main()
