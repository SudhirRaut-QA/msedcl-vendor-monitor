import os
import requests
import time
import json
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

# Load environment variables from .env file
load_dotenv()

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- BENEFICIARY DETAILS ---
BENEFICIARY_ID = "MT4420500385456"
URL = "https://offgridmtsup.mahadiscom.in/AGSolarPumpMTS/PMKusumCons?uiActionName=trackA1FormStatus"

def send_telegram_notification(message):
    """Sends a message to the configured Telegram group."""
    print(f"Sending notification: {message}")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Telegram credentials not found in environment variables.")
        return

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
    
    try:
        # The verify=False is important for corporate networks
        response = requests.post(api_url, json=payload, verify=False)
        if response.status_code == 200:
            print("Notification sent successfully!")
        else:
            print(f"Failed to send notification. Status Code: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"An error occurred while sending the notification: {e}")

def send_photo_notification(message, photo_path):
    """Sends a photo with a caption and interactive buttons to Telegram."""
    print(f"Sending photo notification: {message}")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Telegram credentials not found in environment variables.")
        return

    # --- Define the interactive buttons ---
    # Construct a URL that attempts to pre-fill the beneficiary ID. Note: This cannot click the search button.
    enhanced_url = f"{URL}&beneficiaryId={BENEFICIARY_ID}"
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "View Website", "url": enhanced_url},
            ]
        ]
    }
    reply_markup = json.dumps(keyboard)
    # ------------------------------------

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'caption': message,
        'parse_mode': 'HTML',
        'reply_markup': reply_markup
    }
    
    try:
        with open(photo_path, 'rb') as photo_file:
            files = {'photo': photo_file}
            # The verify=False is important for corporate networks
            response = requests.post(api_url, data=payload, files=files, verify=False)
        
        if response.status_code == 200:
            print("Photo notification sent successfully!")
        else:
            print(f"Failed to send photo notification. Status Code: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"An error occurred while sending the photo notification: {e}")
    finally:
        # Clean up the screenshot file after sending
        if os.path.exists(photo_path):
            os.remove(photo_path)
            print(f"Removed screenshot file: {photo_path}")

def check_vendor_status(page, status):
    """Navigates, interacts, and checks the vendor status on the given page."""
    try:
        print(f"--- New Check at {datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%H:%M:%S')} ---")
        
        # Reset the dialog-based flag for this specific check
        status['quota_exceeded_found'] = False

        print(f"Navigating to URL: {URL}")
        page.goto(URL, timeout=60000, wait_until="domcontentloaded")
        
        print(f"Searching for beneficiary ID: {BENEFICIARY_ID}")
        page.locator("#beneficiaryId").fill(BENEFICIARY_ID)
        
        print("Clicking the initial search button...")
        page.locator("button:has-text('Search')").first.click()
        
        print("Waiting for the 'Search Vendor' button to be ready...")
        search_vendor_button = page.locator("#searchVendorBtn")
        search_vendor_button.wait_for(state="visible", timeout=30000)

        print("Clicking the 'Search Vendor' button...")
        search_vendor_button.click()

        # This flag is for the message found on the page itself
        page_quota_found = False
        print("Checking for 'Quota Exceeded' message on page...")
        try:
            quota_msg_element = page.locator("//td[@id='quotaMsg']")
            quota_msg_element.wait_for(state="visible", timeout=5000)
            element_text = quota_msg_element.inner_text()
            print(f"Found element with text: '{element_text}'")
            if "All Empanelled Vendors Quota Exceeded" in element_text:
                print("Quota exceeded message confirmed in the target element.")
                page_quota_found = True
        except TimeoutError:
            
            print("The specific 'quotaMsg' element was not found on the page.")

        ist_time = datetime.now(ZoneInfo("Asia/Kolkata"))
        timestamp = ist_time.strftime('%Y-%m-%d %H:%M:%S %Z')

        # Check both the dialog flag (from the listener) and the on-page element flag
        if status['quota_exceeded_found'] or page_quota_found:
            message = f"<b>❌</b> Status at {timestamp}: 'All Empanelled Vendors Quota Exceeded'. \nकोणताही विक्रेता उपलब्ध नाही"
            print(message)
            #send_telegram_notification(message) # This was commented out in your last version
        else:
            message = f"🚨 ACTION REQUIRED at {timestamp}:<b>********** विक्रेता उपलब्ध आहे. \n कृपया तपासा आणि अर्ज करा.**********</b>"
            print(message)
            
            # --- Force dropdown to be visible for screenshot ---
            try:
                vendor_dropdown = page.locator("#VendorCode")
                vendor_dropdown.wait_for(state="visible", timeout=5000)
                
                # Count the options to set the size attribute
                option_count = vendor_dropdown.locator("option").count()
                
                if option_count > 1:
                    # Use JavaScript to change the select element to a listbox, making all options visible
                    vendor_dropdown.evaluate(f"(element) => element.size = {option_count}")
                    print(f"Expanded dropdown to show all {option_count} options for screenshot.")
                    # Give the browser a moment to redraw the page
                    page.wait_for_timeout(1000)
                else:
                    print("Dropdown found, but no vendor options were available to expand.")

            except Exception as dropdown_error:
                print(f"Could not find or interact with vendor dropdown: {dropdown_error}")
            # ----------------------------------------------------
            
            # Take a screenshot and send a photo notification
            screenshot_path = "vendor_available.png"
            page.screenshot(path=screenshot_path)
            send_photo_notification(message, screenshot_path)

    except Exception as e:
        print(f"An error occurred during the check: {e}")
        error_message = f"⚠️ An error occurred in the script for beneficiary `{BENEFICIARY_ID}`. Error: {e}"
        # Take a screenshot on error and send it
        error_screenshot_path = "error_screenshot.png"
        try:
            page.screenshot(path=error_screenshot_path)
            send_photo_notification(error_message, error_screenshot_path)
        except Exception as screenshot_error:
            print(f"Could not take or send screenshot on error: {screenshot_error}")
            send_telegram_notification(error_message) # Fallback to text

def main():
    """Main function to run the monitoring loop."""
    # --- Verifying Environment Variables ---
    print("--- Verifying Environment Variables ---")
    if os.environ.get("TELEGRAM_BOT_TOKEN") and "AAG" in os.environ.get("TELEGRAM_BOT_TOKEN"):
        print("TELEGRAM_BOT_TOKEN loaded successfully.")
    else:
        print("WARNING: TELEGRAM_BOT_TOKEN not found or looks invalid.")
    if os.environ.get("TELEGRAM_CHAT_ID"):
        print(f"TELEGRAM_CHAT_ID loaded: {os.environ.get('TELEGRAM_CHAT_ID')}")
    else:
        print("WARNING: TELEGRAM_CHAT_ID not found.")
    print("------------------------------------")

    # Use an environment variable to determine if we are in a long-running CI job
    is_ci_job = os.environ.get("GITHUB_ACTIONS") == "true"
    
    if is_ci_job:
        run_duration = timedelta(hours=5, minutes=50)
        end_time = datetime.now() + run_duration
        print(f"--- Starting Vendor Monitor Script in CI mode ---")
        print(f"Monitoring will run until {end_time.strftime('%Y-%m-%d %H:%M:%S')}.")
    else:
        print("--- Starting Vendor Monitor Script for a single local run ---")

    with sync_playwright() as p:
        browser = None
        try:
            print("Launching browser for the session...")
            # Headless must be True for GitHub Actions, can be False for local debugging
            browser = p.chromium.launch(headless=False) 
            page = browser.new_page()

            # --- Set up the listener once, outside the loop ---
            status = {'quota_exceeded_found': False}
            def handle_dialog(dialog):
                print(f"Alert dialog appeared with message: '{dialog.message}'")
                if "All Empanelled Vendors Quota Exceeded" in dialog.message:
                    print("Quota exceeded message found in alert.")
                    status['quota_exceeded_found'] = True
                dialog.accept()
            page.on("dialog", handle_dialog)
            # ------------------------------------------------

            if is_ci_job:
                while datetime.now() < end_time:
                    check_vendor_status(page, status)
                    
                    if datetime.now() >= end_time:
                        print("--- Monitoring duration finished. ---")
                        break

                    print(f"--- Waiting for 3 minutes. Next check at {(datetime.now() + timedelta(minutes=3)).strftime('%H:%M:%S')} ---")
                    time.sleep(180) # 3 minutes
            else:
                # For local runs, just check once
                check_vendor_status(page, status)

        except Exception as e:
            print(f"A critical error occurred in the main loop: {e}")
            error_message = f"💥 The monitoring script has crashed. Error: {e}"
            # Cannot take a screenshot here as the browser may have crashed
            send_telegram_notification(error_message)
        finally:
            if browser:
                print("Closing browser at the end of the session.")
                browser.close()
    
    print("--- Script Finished ---")

if __name__ == "__main__":
    main()