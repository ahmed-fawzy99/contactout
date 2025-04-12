import logging
import requests
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
from dotenv import load_dotenv
from functools import lru_cache
import psutil
import gc
from contextlib import contextmanager

load_dotenv()

app = Flask(__name__)

# Configure logging
logging.basicConfig(filename='logs/access.log',
                   level=logging.INFO,
                   format='%(asctime)s - %(levelname)s - %(message)s')

# API configuration
API_KEY = os.getenv('api_key')
CONTACTOUT_URL = 'https://contactout.com/dashboard/search/reveal_profile'

# Limiter configuration with memory limits
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["5 per minute", "100 per hour"],
    storage_uri="memory://",
    storage_options={"max_keys": 1000}  # Limit the number of stored keys
)

@contextmanager
def get_session():
    """Context manager for handling request sessions"""
    session = requests.Session()
    try:
        yield session
    finally:
        session.close()

def monitor_resources():
    """Monitor memory usage and garbage collection"""
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    gc.collect()
    logging.info(f"""
    Memory usage: {mem_info.rss / 1024 / 1024:.2f} MB
    Garbage objects: {len(gc.garbage)}
    """)

@app.before_request
def before_request():
    """Execute before each request"""
    monitor_resources()

# Add cache for reading files with size limit
@lru_cache(maxsize=128)
def read_auth_files():
    """Read authentication files with caching"""
    try:
        with open("auth/cookie.txt", "r") as f:
            cookie = f.read().strip()
        with open("auth/csrfmiddlewaretoken.txt", "r") as f:
            csrfmiddlewaretoken = f.read().strip()
        return cookie, csrfmiddlewaretoken
    except Exception as e:
        logging.error(f"Error reading auth files: {e}")
        return None, None

@app.route('/co-get-contact', methods=['POST'])
@limiter.limit("5 per minute")
def reveal_profile():
    """Main endpoint for revealing contact profiles"""
    # Validate API key
    provided_api_key = request.headers.get('X-API-KEY')
    if not provided_api_key or provided_api_key != API_KEY:
        logging.warning(f"Unauthorized access attempt with key: {provided_api_key}")
        return jsonify({"error": "Unauthorized"}), 401

    # Get liVanity from headers
    li_vanity = request.headers.get('X-LI-VANITY')
    if not li_vanity:
        logging.error("No LinkedIn vanity URL provided")
        return jsonify({"error": "LinkedIn vanity URL is required"}), 400

    # Read authentication details
    cookie, csrfmiddlewaretoken = read_auth_files()

    if not cookie or not csrfmiddlewaretoken:
        logging.error("Failed to read cookie credentials")
        return jsonify({"error": "Internal cookie configuration error"}), 500

    # Prepare headers
    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-US,en;q=0.9,ar;q=0.8',
        'content-type': 'application/json',
        'cookie': cookie,
        'dnt': '1',
        'origin': 'https://contactout.com',
        'priority': 'u=1, i',
        'referer': 'https://contactout.com/dashboard/search?login=success&nm=bill%20gates&page=1',
        'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Linux"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'x-reveal-source': '1',
        'x-xsrf-token': csrfmiddlewaretoken
    }

    # Prepare payload
    payload = {
        "liVanity": li_vanity
    }

    with get_session() as session:
        try:
            # Make the request
            response = session.post(CONTACTOUT_URL, headers=headers, json=payload)

            # Log the request details
            logging.info(f"Request for {li_vanity} - Status: {response.status_code}")

            # Handle different response scenarios
            if response.status_code == 200:
                return jsonify(response.json()), 200
            elif response.status_code == 429:
                logging.warning("Rate limit exceeded")
                return jsonify({"error": "Rate limit exceeded from ContactOut Side"}), 429
            elif response.status_code == 423:
                logging.warning("Plan Not Covered")
                return jsonify({"error": "Your Plan does not support this profile"}), 423
            elif response.status_code == 403:
                logging.error("Authentication failed")
                return jsonify({"error": "Authentication failed"}), 403
            else:
                logging.error(f"Unexpected response: {response.status_code} - {response.text}")
                return jsonify({"error": "An unexpected error occurred"}), response.status_code

        except requests.exceptions.RequestException as e:
            logging.error(f"Request failed: {e}")
            return jsonify({"error": "Network error"}), 500
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            return jsonify({"error": "Internal server error"}), 500

@app.teardown_appcontext
def cleanup(exc):
    """Cleanup resources when the application context ends"""
    gc.collect()
    logging.info("Cleaning up resources")

# Error handlers
@app.errorhandler(429)
def ratelimit_handler(e):
    logging.warning(f"Rate limit exceeded: {e}")
    return jsonify({"error": "Rate limit exceeded"}), 429

@app.errorhandler(500)
def internal_error(e):
    logging.error(f"Internal server error: {e}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(debug=False, port=5000)