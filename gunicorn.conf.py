import asyncio
import logging
import random
from playwright.async_api import async_playwright, Playwright
import os
import imaplib
import email
import re
import psutil
import gc
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    filename='logs/gunicorn_logs.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def monitor_resources():
    """Monitor system resources and log usage"""
    try:
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        cpu_percent = process.cpu_percent()

        logging.info(f"""
        Resource Usage:
        Memory: {mem_info.rss / 1024 / 1024:.2f} MB
        CPU: {cpu_percent}%
        Garbage objects: {len(gc.garbage)}
        """)
    except Exception as e:
        logging.error(f"Error monitoring resources: {e}")


async def get_verification_code():
    """Retrieve verification code from email"""
    imap_server = 'mail.getsnaptale.com'
    imap_port = 993
    email_address = os.getenv('email')
    password = os.getenv('smtp_password')
    mail = None

    try:
        mail = imaplib.IMAP4_SSL(imap_server, imap_port)
        mail.login(email_address, password)
        mail.select('inbox')

        _, message_numbers = mail.search(None, 'HEADER Subject "Your ContactOut verification code is:"')

        message_numbers = message_numbers[0].split()
        if not message_numbers:
            logging.warning("No verification emails found")
            return None

        latest_email_num = message_numbers[-1]
        _, msg_data = mail.fetch(latest_email_num, '(RFC822)')
        raw_email = msg_data[0][1]
        email_message = email.message_from_bytes(raw_email)

        subject = email_message['Subject']
        match = re.search(r'Your ContactOut verification code is: (\d+)', subject)

        if match:
            return match.group(1)
        else:
            logging.warning("Verification code not found in email")
            return None

    except Exception as e:
        logging.error(f"Error retrieving verification code: {e}")
        return None

    finally:
        if mail:
            try:
                mail.close()
                mail.logout()
            except Exception as e:
                logging.error(f"Error closing mail connection: {e}")


async def login(playwright: Playwright, max_retries: int = 3, retry_delay: int = 10):
    """Handle login process with retry mechanism"""
    browser = None
    context = None

    for attempt in range(max_retries):
        try:
            webkit = playwright.webkit
            browser = await webkit.launch()
            context = await browser.new_context()
            page = await context.new_page()

            # Navigation with timeout
            try:
                await page.goto("https://contactout.com/login", timeout=60000)
            except Exception as nav_error:
                logging.warning(f"Navigation attempt {attempt + 1} failed: {nav_error}")
                continue

            # Randomize mouse movement
            random_x = random.randint(0, 200)
            random_y = random.randint(0, 300)
            await page.mouse.move(random_x, random_y)
            await page.mouse.click(random_x, random_y)
            await asyncio.sleep(random.uniform(1, 3))

            # Login form
            await page.fill('input[name="email"]', os.getenv('email'))
            await page.fill('input[name="password"]', os.getenv('password'))
            await page.click('button[type="submit"]')
            logging.info("Login form submitted")

            await asyncio.sleep(3)

            # Handle verification
            is_verification_page = await page.query_selector('form[action="/device/verify"]')
            if is_verification_page:
                logging.info("Verification required")
                await asyncio.sleep(90)

                verification_code = await get_verification_code()
                if not verification_code:
                    logging.error("Failed to get verification code")
                    continue

                logging.info(f"Verification code: {verification_code}")
                code_inputs = await page.query_selector_all('.email-code')
                for i, digit in enumerate(verification_code):
                    await code_inputs[i].fill(digit)

                await page.click('#verify')
                await asyncio.sleep(5)

            # Get and save cookies
            cookies = await context.cookies()

            # Ensure we have all required cookies
            required_cookies = {
                'guid': None,
                'cf_clearance': None,
                'XSRF-TOKEN': None,
                'contactout_session': None
            }

            # Map cookies to their names
            cookie_map = {cookie['name']: cookie['value'] for cookie in cookies}

            # Verify all required cookies are present
            for cookie_name in required_cookies:
                if cookie_name not in cookie_map:
                    raise Exception(f"Missing required cookie: {cookie_name}")

            cookie = (
                f"landing_page=home; "
                f"guid={cookie_map.get('guid')}; "
                f"cf_clearance={cookie_map.get('cf_clearance')}; "
                f"XSRF-TOKEN={cookie_map.get('XSRF-TOKEN')}; "
                f"contactout_session={cookie_map.get('contactout_session')}"
            )

            csrfmiddlewaretoken = cookie_map.get('XSRF-TOKEN').replace("%3D", "")

            # Ensure directory exists
            os.makedirs("auth", exist_ok=True)

            try:
                for filename in ['auth/cookie.txt', 'auth/csrfmiddlewaretoken.txt']:
                    if os.path.exists(filename):
                        os.remove(filename)

                with open("auth/cookie.txt", "w", encoding='utf-8') as f:
                    f.write(cookie)
                with open("auth/csrfmiddlewaretoken.txt", "w", encoding='utf-8') as f:
                    f.write(csrfmiddlewaretoken)

                with open("auth/cookie.txt", "r", encoding='utf-8') as f:
                    written_cookie = f.read().strip()
                with open("auth/csrfmiddlewaretoken.txt", "r", encoding='utf-8') as f:
                    written_token = f.read().strip()

                if written_cookie != cookie or written_token != csrfmiddlewaretoken:
                    raise Exception("Cookie verification failed")

                logging.info("Login successful and cookies saved")

            except Exception as e:
                logging.error(f"Error writing cookie files: {e}")
                raise

            break

        except Exception as e:
            logging.error(f"Login attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                raise Exception("Failed to login to ContactOut")
            await asyncio.sleep(retry_delay)

        finally:
            if context:
                await context.close()
            if browser:
                await browser.close()


async def init_contact_out():
    """Initialize ContactOut session"""
    try:
        async with async_playwright() as playwright:
            await login(playwright)
    except Exception as e:
        logging.error(f"ContactOut initialization failed: {e}")
        raise


def on_starting(server):
    """Handler for server startup"""
    try:
        logging.info("Gunicorn starting up")
        monitor_resources()
        asyncio.run(init_contact_out())
        logging.info("ContactOut initialization complete")
    except Exception as e:
        logging.error(f"Startup error: {e}")
        raise


def post_fork(server, worker):
    """Handler for worker process creation"""
    try:
        logging.info(f"Worker {worker.pid} starting")
        monitor_resources()
    except Exception as e:
        logging.error(f"Post-fork error: {e}")


def worker_exit(server, worker):
    """Handler for worker exit"""
    try:
        logging.info(f"Worker {worker.pid} exiting")
        monitor_resources()
    except Exception as e:
        logging.error(f"Worker exit error: {e}")


def on_exit(server):
    """Handler for server shutdown"""
    try:
        logging.info("Gunicorn shutting down")
        monitor_resources()
        gc.collect()
    except Exception as e:
        logging.error(f"Shutdown error: {e}")


# Gunicorn configuration
bind = "0.0.0.0:8000"
workers = 1
worker_class = 'sync'
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
worker_tmp_dir = "/dev/shm"
preload_app = True
worker_connections = 1000
accesslog = 'logs/gunicorn_access.log'
errorlog = 'logs/gunicorn_logs.log'
loglevel = 'info'
access_log_format = '%({x-real-ip}i)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Memory management
def child_exit(server, worker):
    gc.collect()

def post_worker_init(worker):
    gc.enable()