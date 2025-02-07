# OpenSenseMap Beekeeping API

A RESTful API service that interfaces with openSenseMap to help beekeepers monitor temperature conditions. This service includes Prometheus metrics for monitoring.

## Features

- Temperature monitoring from openSenseMap sensors
- Status classification (Too Cold/Good/Too Hot)
- Prometheus metrics integration
- Docker support
- Comprehensive test suite

## Prerequisites

- Python 3.9+
- Docker (optional)
- virtualenv (recommended)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd beekeeping-api
```

2. Create and activate virtual environment:
```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# On Linux/macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the Application

### Running Locally

1. Start the application:
```bash
python main.py
```

2. Access the API at `http://localhost:8000`

### Running with Docker

1. Build the Docker image:
```bash
docker build -t beekeeping-api .
```

2. Run the container:
```bash
docker run -p 8000:8000 beekeeping-api
```

## API Endpoints

- `GET /`: API information
- `GET /version`: Current API version
- `GET /temperature`: Current temperature data
- `GET /metrics`: Prometheus metrics

## Running Tests

1. Ensure you're in the virtual environment
2. Run the tests:
```bash
# Run all tests
pytest test_app.py -v

# Run tests with coverage report
pytest --cov=main test_app.py

# Generate HTML coverage report
pytest --cov=main test_app.py --cov-report=html
```

## Configuration

The application uses the following environment variables:
- `TARGET_ID`: SenseBox ID for temperature monitoring (default: "5eba5fbad46fb8001b799786")
- `APP_VERSION`: Application version (default: "0.0.1")

## Development

1. Update dependencies:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

2. Run tests before committing changes:
```bash
pytest test_app.py -v
```

## Contributing

1. Fork the repository
2. Create your feature branch
3. Make your changes
4. Run the tests
5. Submit a pull request

