import os
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- CONFIGURATION ---
load_dotenv() # Load variables from .env file

# Reads credentials from environment variables.
# For local testing, it will use the values from the .env file.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- Verification Step ---
print("--- Verifying Environment Variables ---")
if TELEGRAM_BOT_TOKEN and "AAG" in TELEGRAM_BOT_TOKEN: # Basic check for a valid-looking token
    print("TELEGRAM_BOT_TOKEN loaded successfully.")
else:
    print("WARNING: TELEGRAM_BOT_TOKEN not found or looks invalid.")
    
if TELEGRAM_CHAT_ID:
    print(f"TELEGRAM_CHAT_ID loaded: {TELEGRAM_CHAT_ID}")
else:
    print("WARNING: TELEGRAM_CHAT_ID not found.")
print("------------------------------------")

# --- BENEFICIARY DETAILS ---
BENEFICIARY_ID = "MT4420500385456"
URL = "https://offgridmtsup.mahadiscom.in/AGSolarPumpMTS/PMKusumCons?uiActionName=trackA1FormStatus"

def send_telegram_notification(message):
    """Sends a message to the configured Telegram group."""
    print(f"Sending notification: {message}")
    # Make sure the token and chat ID are filled out
    if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN" or TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_GROUP_CHAT_ID":
        print("ERROR: Please fill in your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in the script.")
        return

    # Construct the API URL
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # Prepare the payload
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    try:
        response = requests.post(api_url, json=payload)
        if response.status_code == 200:
            print("Notification sent successfully!")
        else:
            print(f"Failed to send notification. Status Code: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"An error occurred while sending the notification: {e}")

def check_vendor_status():
    """
    Launches a browser, navigates to the website, and checks the vendor status
    for the specified beneficiary ID.
    """
    with sync_playwright() as p:
        print("Launching browser...")
        # Use headless=False for debugging, True for production/automation
        browser = p.chromium.launch(headless=False) 
        page = browser.new_page()
        
        # State variable to track if the specific "quota exceeded" message is found
        quota_exceeded_found = False
        
        # This handler will check the message of any alert that appears
        def handle_dialog(dialog):
            nonlocal quota_exceeded_found
            print(f"Alert dialog appeared with message: '{dialog.message}'")
            if "All Empanelled Vendors Quota Exceeded" in dialog.message:
                print("Quota exceeded message found in alert.")
                quota_exceeded_found = True
            dialog.accept()
        
        page.on("dialog", handle_dialog)

        try:
            print(f"Navigating to URL: {URL}")
            page.goto(URL, timeout=60000)
            
            print(f"Searching for beneficiary ID: {BENEFICIARY_ID}")
            beneficiary_input = page.locator("#beneficiaryId")
            beneficiary_input.fill(BENEFICIARY_ID)
            
            print("Clicking the initial search button...")
            page.locator("button:has-text('Search')").first.click()
            
            print("Waiting for the 'Search Vendor' button to be ready...")
            search_vendor_button = page.locator("#searchVendorBtn")
            search_vendor_button.wait_for(state="visible", timeout=30000) # Wait up to 30s

            print("Clicking the 'Search Vendor' button...")
            search_vendor_button.click()

            # The dialog handler will catch any pop-up alerts.
            # Now, we check for the specific message on the page using the provided locator.
            print("Checking for 'Quota Exceeded' message in the specific element...")
            
            try:
                # Wait for the specific element with id 'quotaMsg' to be visible
                quota_msg_element = page.locator("//td[@id='quotaMsg']")
                quota_msg_element.wait_for(state="visible", timeout=5000)
                
                # If the element is found, check if its text contains the desired message
                element_text = quota_msg_element.inner_text()
                print(f"Found element with text: '{element_text}'")
                if "All Empanelled Vendors Quota Exceeded" in element_text:
                    print("Quota exceeded message confirmed in the target element.")
                    quota_exceeded_found = True

            except TimeoutError:
                # This block will execute if the 'quotaMsg' element is not found after 5 seconds.
                print("The specific 'quotaMsg' element was not found on the page.")

            # --- Final Decision Logic ---
            if quota_exceeded_found:
                message = f"✅ Status at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: 'All Empanelled Vendors Quota Exceeded'. No action needed."
                print(message)
                # send_telegram_notification(message)
            else:
                message = f"🚨 ACTION REQUIRED at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Vendor status requires manual review. The 'Quota Exceeded' message was NOT found."
                print(message)
                send_telegram_notification(message)

        except Exception as e:
            print(f"An error occurred during the automation process: {e}")
            error_message = f"⚠️ An error occurred in the script for beneficiary `{BENEFICIARY_ID}`. Error: {e}"
            send_telegram_notification(error_message)
            
        finally:
            print("Pausing for 5 seconds before closing browser to see the result.")
            page.wait_for_timeout(5000)
            print("Closing browser.")
            browser.close()

if __name__ == "__main__":
    print("--- Starting Vendor Monitor Script ---")
    check_vendor_status()
    print("--- Script Finished ---")
