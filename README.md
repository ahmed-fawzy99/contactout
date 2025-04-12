# ContactOut API Proxy

**EDUCATIONAL PURPOSES ONLY**

This project is a Flask-based API service that acts as a proxy for ContactOut's contact information retrieval service. It is designed to demonstrate secure API integration, authentication handling, and session management. The core functionality focuses on automated bypassing of sophisticated protection mechanisms.

## Features

- API endpoint for retrieving contact information based on LinkedIn profile IDs
- Advanced authentication bypass:
  - **Automated Cloudflare protection bypass**
  - **Headless browser automation to navigate login flows**
  - **Automatic email inbox monitoring for 2FA code retrieval**
  - **Session persistence and management across protection layers**
- Multiple authentication layers:
  - API Key authentication for clients
  - Session-based authentication with ContactOut
  - Automatic handling of 2FA (Two-Factor Authentication)
- Security measures:
  - Rate limiting
  - API key validation
  - Error handling and logging
  - Resource monitoring
- Dockerized deployment with Gunicorn WSGI server

## Technical Stack

- Python 3.9
- Flask
- Playwright
- Docker
- Gunicorn

## API Usage

Send requests to the `/co-get-contact` endpoint with:
- Required header: `X-API-KEY` with valid API key
- Request body: JSON with LinkedIn profile ID(s)

## Deployment

The application can be deployed using Docker:

```bash
docker-compose up -d
```

## Disclaimer

This project is intended for educational purposes only. Always respect privacy laws and terms of service when retrieving contact information.