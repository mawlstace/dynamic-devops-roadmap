from datetime import datetime, timedelta, timezone
import sys
from typing import Dict, Union, Optional, List, Tuple
import logging
import json
from apscheduler.schedulers.background import BackgroundScheduler
from io import BytesIO



# Flask imports for web application
from flask import Flask, jsonify, Response
import requests

# Prometheus imports for metrics
from prometheus_client import CollectorRegistry, Counter, Gauge, make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware

# Redis imports for caching
import redis

# MinIO imports for storage
from minio import Minio
from minio.error import S3Error

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Application Constants
APP_VERSION = "0.0.2"
TARGET_ID = "5eba5fbad46fb8001b799786"
OPENSENSEMAP_API_BASE = "https://api.opensensemap.org/boxes"
TEMPERATURE_THRESHOLDS = {
    "cold": 10,
    "hot": 36
}

# Redis Configuration
REDIS_HOST = "redis"
REDIS_PORT = 6379
CACHE_TTL = 300  # Cache TTL in seconds (5 minutes)

# MinIO Configuration
MINIO_ENDPOINT = "minio:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
MINIO_BUCKET = "temperature-data"
MINIO_SECURE = False

# Initialize Flask application
app = Flask(__name__)

# Initialize Redis client
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True
)

# Initialize MinIO client
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE
)

# Create metrics registry
REGISTRY = CollectorRegistry()

# Existing metrics
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

# New metrics
storage_operations = Counter(
    "beekeeping_api_storage_operations_total",
    "Total number of storage operations performed",
    ['operation_type'],
    registry=REGISTRY
)
sensebox_availability = Gauge(
    "beekeeping_api_sensebox_availability",
    "Percentage of senseBoxes that are currently accessible",
    registry=REGISTRY
)
cache_age = Gauge(
    "beekeeping_api_cache_age_seconds",
    "Age of the cached data in seconds",
    registry=REGISTRY
)

def ensure_minio_bucket():
    """Create MinIO bucket if it doesn't exist."""
    try:
        if not minio_client.bucket_exists(MINIO_BUCKET):
            minio_client.make_bucket(MINIO_BUCKET)
            logger.info(f"Created MinIO bucket: {MINIO_BUCKET}")
            storage_operations.labels(operation_type="bucket_creation").inc()
    except S3Error as e:
        logger.error(f"Error ensuring MinIO bucket exists: {e}")

def store_temperature_data(data: Dict) -> bool:
    """Store temperature data in MinIO."""
    try:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        object_name = f"temperature_{timestamp}.json"
        
        # Convert data to JSON bytes
        json_data = json.dumps(data).encode('utf-8')
        
        # Create BytesIO object from JSON bytes
        data_stream = BytesIO(json_data)
        
        minio_client.put_object(
            MINIO_BUCKET,
            object_name,
            data_stream,
            length=len(json_data),
            content_type='application/json'
        )
        logger.info(f"Stored temperature data in MinIO: {object_name}")
        storage_operations.labels(operation_type="data_storage").inc()
        return True
    except S3Error as e:
        logger.error(f"Error storing data in MinIO: {e}")
        return False




def get_temperature_status(temperature: float) -> str:
    """Determine temperature status based on predefined thresholds."""
    if temperature <= TEMPERATURE_THRESHOLDS["cold"]:
        return "Too Cold"
    elif temperature <= TEMPERATURE_THRESHOLDS["hot"]:
        return "Good"
    else:
        return "Too Hot"

def fetch_sensor_data(box_id: str) -> Optional[Dict]:
    """Fetch sensor data from OpenSenseMap API with Redis caching."""
    cache_key = f"sensor_data_{box_id}"
    cached_data = redis_client.get(cache_key)
    
    if cached_data:
        logger.info("Retrieved sensor data from cache")
        # Update cache age metric
        cache_time = json.loads(cached_data).get("cache_timestamp")
        if cache_time:
            age = (datetime.now(timezone.utc) - datetime.fromtimestamp(cache_time, timezone.utc)).total_seconds()
            cache_age.set(age)
        return json.loads(cached_data)
    
    try:
        response = requests.get(
            f"{OPENSENSEMAP_API_BASE}/{box_id}",
            params={"format": "json"},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        # Add cache timestamp to data
        data["cache_timestamp"] = datetime.now(timezone.utc).timestamp()
        
        redis_client.setex(
            cache_key,
            CACHE_TTL,
            json.dumps(data)
        )
        
        cache_age.set(0)  # Reset cache age for fresh data
        return data
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching sensor data: {e}")
        return None

def check_senseboxes_health() -> Tuple[int, int]:
    """Check the health of all configured senseBoxes."""
    total_boxes = 1  # Currently only one box, but could be extended
    accessible_boxes = 0
    
    data = fetch_sensor_data(TARGET_ID)
    if data:
        accessible_boxes += 1
    
    availability_percentage = (accessible_boxes / total_boxes) * 100
    sensebox_availability.set(availability_percentage)
    
    return accessible_boxes, total_boxes

@app.route("/")
def index() -> Response:
    """Root endpoint returning API information."""
    return jsonify({
        "name": "OpenSenseMap Beekeeping API",
        "version": APP_VERSION,
        "endpoints": ["/version", "/temperature", "/metrics", "/store", "/readyz"]
    })

@app.route("/version")
def version() -> Response:
    """Return the current API version."""
    return Response(APP_VERSION, mimetype='text/plain')

@app.route("/store", methods=['GET'])
def store() -> Response:
    """
    Manually trigger immediate data storage to MinIO.
    This is separate from the automatic 5-minute periodic storage.
    """
    try:
        data = fetch_sensor_data(TARGET_ID)
        if not data:
            return jsonify({
                "status": "error",
                "message": "Failed to fetch sensor data"
            }), 503
        
        if store_temperature_data(data):
            return jsonify({
                "status": "success", 
                "message": "Data stored successfully",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        else:
            return jsonify({
                "status": "error", 
                "message": "Failed to store data in MinIO"
            }), 500
            
    except Exception as e:
        logger.error(f"Unexpected error during immediate storage: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route("/readyz")
def readyz() -> Response:
    """Health check endpoint."""
    accessible_boxes, total_boxes = check_senseboxes_health()
    
    # Check if more than 50% of boxes are inaccessible
    boxes_threshold = (total_boxes // 2) + 1
    boxes_healthy = accessible_boxes >= boxes_threshold
    
    # Check cache age
    cached_data = redis_client.get(f"sensor_data_{TARGET_ID}")
    cache_healthy = True
    
    if cached_data:
        data = json.loads(cached_data)
        cache_time = data.get("cache_timestamp")
        if cache_time:
            age = (datetime.now(timezone.utc) - datetime.fromtimestamp(cache_time, timezone.utc)).total_seconds()
            cache_healthy = age <= CACHE_TTL
    
    if not boxes_healthy and not cache_healthy:
        return jsonify({
            "status": "unhealthy",
            "boxes_accessible": accessible_boxes,
            "total_boxes": total_boxes,
            "cache_status": "stale" if not cache_healthy else "fresh"
        }), 503
    
    return jsonify({
        "status": "healthy",
        "boxes_accessible": accessible_boxes,
        "total_boxes": total_boxes,
        "cache_status": "fresh" if cache_healthy else "stale"
    })

@app.route("/temperature")
def temperature() -> Union[Response, str]:
    """Fetch and return the current temperature data with status."""
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

                try:
                    measurement_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
                    measurement_time = measurement_time.replace(tzinfo=timezone.utc)
                    
                    if datetime.now(timezone.utc) - measurement_time > timedelta(hours=1):
                        return "Data exceeds 1 hour threshold", 404
                    
                    temp_float = float(temp_value)
                    response_data = {
                        "temperature": temp_value,
                        "status": get_temperature_status(temp_float),
                        "timestamp": timestamp
                    }
                    
                    request_count.inc()
                    last_temperature.set(temp_float)
                    
                    return jsonify(response_data)
                except ValueError as e:
                    logger.error(f"Error parsing timestamp: {e}")
                    return "Invalid timestamp format", 500

        return "Temperature sensor not found", 404
    except Exception as e:
        logger.error(f"Unexpected error in temperature endpoint: {e}")
        return "Internal server error", 500

def store_periodic_data():
    """Periodic task to store temperature data in MinIO."""
    try:
        data = fetch_sensor_data(TARGET_ID)
        if data:
            store_temperature_data(data)
    except Exception as e:
        logger.error(f"Error in periodic data storage: {e}")

# Add metrics endpoint
app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
    '/metrics': make_wsgi_app(REGISTRY)
})

def main():
    """Main entry point for the application."""
    if len(sys.argv) > 1 and sys.argv[1] == "--version":
        print(f"OpenSenseMap Beekeeping API v{APP_VERSION}")
        sys.exit(0)
    
    ensure_minio_bucket()
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        store_periodic_data,
        'interval',
        minutes=5,
        timezone=timezone.utc
    )
    scheduler.start()
    
    app.run(host='0.0.0.0', port=8000, debug=False)

if __name__ == "__main__":
    main()