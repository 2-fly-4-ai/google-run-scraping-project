import os
import re
import time
import base64
import json
import threading
from dotenv import load_dotenv
from flask import Flask, request, jsonify
# from seleniumwire import webdriver
import seleniumwire.undetected_chromedriver as webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth

load_dotenv()
app = Flask(__name__)


apiKey = os.getenv('SPM_APIKEY')
# Proxy configuration
proxy_options = {
    'proxy': {
        'http': 'http://{apiKey}:@api.zyte.com:8011',
        'https': 'http://{apiKey}:@api.zyte.com:8011',
        'no_proxy': 'localhost,127.0.0.1'
    }
}

def wait_for_download_link(driver, timeout=60):
    end_time = time.time() + timeout
    while time.time() < end_time:
        for req in driver.requests:
            if req.response and 'download?' in req.url.lower() and req.response.status_code == 200:
                return req.url
        time.sleep(1)
    return None

def get_driver():
    chrome_options = Options()
    # chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--headless') 
    chrome_options.add_argument('--disable-dev-shm-usage')
    capabilities = chrome_options.to_capabilities()         #cap
    capabilities['acceptInsecureCerts'] = True              #cap
    
    driver = webdriver.Chrome(
        options=chrome_options,
        desired_capabilities=capabilities,
        seleniumwire_options=proxy_options,
    )
    
    # Apply stealth settings
    stealth(driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    
    return driver

def cf_manual_solver(driver) -> None:
    captcha_frame_regex = re.compile(r'cf-chl-widget-.{3,6}')
    try:
        # Find all elements that might contain the CAPTCHA
        matching_elements = driver.find_elements(By.XPATH, "//*[contains(@id, 'cf-chl-widget-')]")
        cf_captcha_frame = None

        for element in matching_elements:
            element_id = element.get_attribute("id")
            accessible_name = element.get_attribute("aria-label") or ""
            if captcha_frame_regex.match(element_id) and 'Cloudflare security challenge' in accessible_name:
                cf_captcha_frame = element
                break

        if cf_captcha_frame:
            # Switch to the CAPTCHA iframe
            WebDriverWait(driver, 15.0).until(EC.frame_to_be_available_and_switch_to_it(cf_captcha_frame))
            # Locate and click the CAPTCHA checkbox
            captcha_checkbox = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CLASS_NAME, 'ctp-checkbox-label'))
            )
            captcha_checkbox.click()
            # Switch back to the default content
            driver.switch_to.default_content()
            print("CAPTCHA solved successfully.")
        else:
            print("No Cloudflare CAPTCHA detected.")
    except Exception as err:
        print(f'Failed to solve CAPTCHA: {err}')

@app.route('/download_mp3', methods=['POST'])
def download_mp3():
    youtube_url = request.form.get('youtube_url')
    if not youtube_url:
        return jsonify({"error": "YouTube URL is required"}), 400

    driver = None
    start_screenshot_base64 = None  # Initialize variable here for scope access in error handling
    try:
        driver = get_driver()
        # Access the MP3 conversion site
        driver.get("https://ezmp3.cc")
        
        # Capture a screenshot at the start of the session
        start_screenshot = driver.get_screenshot_as_png()
        start_screenshot_base64 = base64.b64encode(start_screenshot).decode('utf-8')
        
        # Attempt to solve CAPTCHA if present
      
        
        # Proceed with the normal workflow after attempting CAPTCHA solving
        # Wait for the input element to be present
        input_element = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="url"]'))
        )
        input_element.send_keys(youtube_url)
        
        # Wait for the submit button to be present and clickable
        submit_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]'))
        )
        submit_button.click()



        cf_manual_solver(driver)

        # Wait for the download link to be present
        download_button_present = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//button[text()='Download MP3']"))
        )
        if download_button_present:
            download_button_present.click()
            print("Clicked Download MP3 button")

        download_link = wait_for_download_link(driver)
        if download_link:
            driver.get(download_link)
            screenshot = driver.get_screenshot_as_png()
            screenshot_base64 = base64.b64encode(screenshot).decode('utf-8')
            return jsonify({
                "screenshot": screenshot_base64, 
                "download_url": download_link, 
                "start_screenshot": start_screenshot_base64
            }), 200
        else:
            print("Download link not found. Taking screenshot.")
            screenshot = driver.get_screenshot_as_png()
            screenshot_base64 = base64.b64encode(screenshot).decode('utf-8')
            return jsonify({
                "screenshot": screenshot_base64, 
                "message": "Download link not found", 
                "start_screenshot": start_screenshot_base64
            }), 200
    except Exception as e:
        print(f"Error during processing: {e}")
        if driver and start_screenshot_base64:
            try:
                screenshot = driver.get_screenshot_as_png()
                screenshot_base64 = base64.b64encode(screenshot).decode('utf-8')
                return jsonify({
                    "screenshot": screenshot_base64, 
                    "error": str(e), 
                    "start_screenshot": start_screenshot_base64
                }), 500
            except Exception as screenshot_error:
                print(f"Failed to capture screenshot: {screenshot_error}")
                return jsonify({
                    "error": str(e), 
                    "start_screenshot": start_screenshot_base64
                }), 500
        else:
            return jsonify({"error": str(e)}), 500
    finally:
        if driver:
            driver.quit()

if __name__ == '__main__':
    server_port = os.environ.get('PORT', '8080')
    app.run(debug=False, port=server_port, host='0.0.0.0')