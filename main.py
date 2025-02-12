import undetected_chromedriver as uc
from selenium.common import WebDriverException
from selenium.webdriver.common.by import By
import time
import requests
import logging
import urllib.parse
import signal
import sys
import pickle
from urllib.parse import urlparse
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Path to store cookies
COOKIE_FILE = "cookies.pkl"

# 最大重启次数
MAX_RESTARTS = 999

# 重启间隔（秒）
RESTART_DELAY = 5


def send_bark_notification(message: str, device_key: str, level: str = "timeSensitive"):
    """
    Send a notification via Bark by embedding the message in the URL path.

    Parameters:
    - message (str): The message to send.
    - device_key (str): Your unique Bark device key.
    - level (str): Notification level (default is "timeSensitive").
    """
    try:
        # URL-encode the message to safely include it in the URL path
        encoded_message = urllib.parse.quote(message)

        # Construct the Bark URL with the encoded message
        bark_url = f"https://api.day.app/{device_key}/{encoded_message}?level={level}"

        response = requests.get(bark_url)
        if response.status_code == 200:
            logging.info("Bark notification sent successfully.")
        else:
            logging.warning(f"Bark notification failed with status code: {response.status_code}")
    except requests.RequestException as e:
        logging.error(f"Failed to send Bark notification: {e}")


def save_cookies(driver, path):
    """
    Save cookies from the current browser session to a file.

    Parameters:
    - driver: The Selenium WebDriver instance.
    - path (str): The file path to save cookies.
    """
    try:
        cookies = driver.get_cookies()
        with open(path, 'wb') as file:
            pickle.dump(cookies, file)
        logging.info(f"Cookies have been saved to {path}.")
    except Exception as e:
        logging.error(f"Failed to save cookies: {e}")


def load_cookies(driver, path, base_url):
    """
    Load cookies from a file into the browser session.

    Parameters:
    - driver: The Selenium WebDriver instance.
    - path (str): The file path from which to load cookies.
    - base_url (str): The base URL to navigate to before adding cookies.
    """
    if not os.path.exists(path):
        logging.info("No cookies file found. Proceeding without loading cookies.")
        return

    try:
        with open(path, 'rb') as file:
            cookies = pickle.load(file)
        driver.get(base_url)  # Navigate to base URL to set cookies
        for cookie in cookies:
            # Selenium requires the domain to match when adding cookies
            if 'sameSite' in cookie:
                if cookie['sameSite'] == 'None':
                    cookie['sameSite'] = 'Strict'  # Adjust if necessary
            driver.add_cookie(cookie)
        logging.info(f"Cookies have been loaded from {path}.")
        driver.refresh()  # Refresh to apply cookies
    except Exception as e:
        logging.error(f"Failed to load cookies: {e}")


def wait_for_manual_login():
    """
    Prompt the user to manually log in and wait for user confirmation.

    This function pauses the script execution until the user confirms that they've
    successfully logged in by pressing Enter.
    """
    logging.info("Please manually log in to your account in the opened browser.")
    input("After logging in, press Enter to continue...")


def check_product_availability(driver):
    """
    Check if the product is available for purchase.

    Parameters:
    - driver: The Selenium WebDriver instance.

    Returns:
    - bool: True if the product is available and added to cart, False otherwise.
    """
    try:
        # Check for "Sold Out" button
        sold_out = driver.find_elements(By.XPATH, "//button[contains(text(), 'Sold Out')]")
        if sold_out:
            logging.info("Product is sold out.")
            return False

        # Check for "Add to Cart" button
        add_to_cart = driver.find_elements(By.XPATH, "//button[contains(text(), 'Add to Cart')]")
        if add_to_cart:
            logging.info("Product is available. Attempting to add to cart.")
            add_to_cart[0].click()
            return True

        logging.info("Product status unknown. Retrying...")
        return False

    except Exception as e:
        logging.error(f"Error checking product availability: {e}")
        return False


def initialize_driver():
    """
    Initialize the WebDriver with desired options.

    Returns:
    - driver: The initialized Selenium WebDriver instance.
    """
    options = uc.ChromeOptions()
    options.add_argument("--incognito")
    options.add_argument("--disable-blink-features=AutomationControlled")

    # Enable headless mode with new option
    # options.add_argument("--headless=new")

    # Additional arguments for stability
    options.add_argument("--disable-gpu")  # Disable GPU acceleration
    options.add_argument("--no-sandbox")  # Bypass OS security model
    options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
    options.add_argument("--window-size=1920,1080")  # Set window size to standard dimensions

    # Optional: Reduce detection
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--mute-audio")

    driver = uc.Chrome(options=options)
    return driver


def graceful_exit(signum, frame):
    """
    Handle graceful exit on signal interrupt.

    Parameters:
    - signum: Signal number.
    - frame: Current stack frame.
    """
    logging.info("Interrupt received. Exiting gracefully...")
    sys.exit(0)


def get_base_url(url):
    """
    Extract the base URL from a full URL.

    Parameters:
    - url (str): The full URL.

    Returns:
    - str: The base URL.
    """
    parsed_url = urlparse(url)
    return f"{parsed_url.scheme}://{parsed_url.netloc}"


def check_and_buy(url: str, device_key: str, refresh_interval: int = 30):
    """
    Monitor the product page and attempt to purchase when available.

    Parameters:
    - url (str): The URL of the product page to monitor.
    - device_key (str): Your unique Bark device key.
    - refresh_interval (int): Time to wait between refreshes (in seconds).
    """
    restarts = 0
    base_url = get_base_url(url)

    while restarts <= MAX_RESTARTS:
        driver = None
        try:
            driver = initialize_driver()
            logging.info("Browser has been initialized.")

            # 尝试加载 Cookie
            driver.get(base_url)
            load_cookies(driver, COOKIE_FILE, base_url)

            # 导航到产品页面
            driver.get(url)

            # 检查是否已登录（可选：根据具体网站实现）
            # 如果需要手动登录，取消下面的注释
            # wait_for_manual_login()

            # 如果需要手动登录，且用户已经登录，保存 Cookie
            # save_cookies(driver, COOKIE_FILE)

            while True:
                try:
                    if check_product_availability(driver):
                        time.sleep(3)  # 等待购物车更新
                        send_bark_notification("Product successfully added to cart!", device_key)
                        logging.info("Product successfully added to cart!")
                        break  # 退出循环以保持浏览器打开

                except WebDriverException as wde:
                    logging.error(f"WebDriver Error: {wde}")
                    raise wde  # 触发外层异常处理以重启

                except Exception as e:
                    logging.error(f"Unexpected error: {e}")

                logging.info(f"Refreshing page in {refresh_interval} seconds...")
                time.sleep(refresh_interval)
                driver.refresh()

            # 添加到购物车后，保持浏览器打开
            logging.info("Browser will remain open to complete purchase.")
            while True:
                time.sleep(1)  # 保持脚本运行以保持浏览器打开

        except WebDriverException as wde:
            logging.error(f"Detected WebDriver error: {wde}")
            if driver:
                driver.quit()
            restarts += 1
            logging.info(f"Restarting browser... (Restart {restarts}/{MAX_RESTARTS})")
            time.sleep(RESTART_DELAY)
            continue  # 重新启动循环

        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            if driver:
                driver.quit()
            restarts += 1
            logging.info(f"Restarting browser... (Restart {restarts}/{MAX_RESTARTS})")
            time.sleep(RESTART_DELAY)
            continue  # 重新启动循环

        finally:
            if driver:
                driver.quit()

    logging.error("Maximum restart limit reached. Exiting...")


if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, graceful_exit)  # Handle Ctrl+C
    signal.signal(signal.SIGTERM, graceful_exit)  # Handle termination

    # Configuration
    PRODUCT_URL = "https://www.bestbuy.com/site/nvidia-geforce-rtx-5090-32gb-gddr7-graphics-card-dark-gun-metal/6614151.p?skuId=6614151"  # Replace with the actual product URL
    BARK_DEVICE_KEY = ""  # Replace with your actual Bark device key

    check_and_buy(PRODUCT_URL, BARK_DEVICE_KEY)
