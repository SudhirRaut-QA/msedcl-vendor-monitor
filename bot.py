import os
import logging
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright, TimeoutError
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
import database

# --- CONFIGURATION ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
URL = "https://offgridmtsup.mahadiscom.in/AGSolarPumpMTS/PMKusumCons?uiActionName=trackA1FormStatus"

# --- LOGGING SETUP ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CORE VENDOR CHECK LOGIC ---
async def check_vendor_status(beneficiary_id: str):
    """
    Performs the Playwright check for a single beneficiary ID.
    Returns a tuple: (status_string, screenshot_path_or_none)
    """
    status = "Unknown"
    screenshot_path = None
    dialog_found = False

    async def handle_dialog(dialog):
        nonlocal dialog_found
        logger.info(f"Dialog appeared for {beneficiary_id}: '{dialog.message}'")
        if "All Empanelled Vendors Quota Exceeded" in dialog.message:
            dialog_found = True
        await dialog.accept()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.on("dialog", handle_dialog) # Set up the dialog listener

        try:
            await page.goto(URL, timeout=60000)
            await page.locator("#beneficiaryId").fill(beneficiary_id)
            await page.locator("button:has-text('Search')").first.click()
            
            search_vendor_button = page.locator("#searchVendorBtn")
            await search_vendor_button.wait_for(state="visible", timeout=30000)
            await search_vendor_button.click()

            # Give a moment for any dialogs to appear after the click
            await page.wait_for_timeout(2000)

            if dialog_found:
                status = "Not Available"
            else:
                # If no dialog appeared, check for the vendor dropdown as confirmation
                try:
                    vendor_dropdown = page.locator("#VendorCode")
                    await vendor_dropdown.wait_for(state="visible", timeout=5000)
                    
                    option_count = await vendor_dropdown.locator("option").count()
                    if option_count > 1:
                        status = "Available"
                        await page.evaluate(f"document.getElementById('VendorCode').size = {option_count};")
                        await page.wait_for_timeout(500) # Wait for redraw
                        screenshot_path = f"screenshot_{beneficiary_id}.png"
                        await page.screenshot(path=screenshot_path)
                    else:
                        # Dropdown is there but empty, so not available
                        status = "Not Available"
                except TimeoutError:
                    # If no dialog and no dropdown, something is wrong, but vendors are not available
                    logger.warning(f"No dialog and no vendor dropdown found for {beneficiary_id}.")
                    status = "Not Available"

        except Exception as e:
            logger.error(f"Error checking {beneficiary_id}: {e}")
            status = f"Error: {e}"
            try:
                screenshot_path = f"error_{beneficiary_id}.png"
                await page.screenshot(path=screenshot_path)
            except Exception as screenshot_error:
                logger.error(f"Could not even take an error screenshot: {screenshot_error}")
        finally:
            await browser.close()
    return status, screenshot_path

# --- TELEGRAM BOT JOB ---
async def run_monitor_job(context: ContextTypes.DEFAULT_TYPE):
    """The main job that runs every 3 minutes."""
    logger.info("Running scheduled monitor job for all users...")
    users = database.get_all_users()
    if not users:
        logger.info("No users in database. Skipping job.")
        return

    for user in users:
        chat_id = user['chat_id']
        beneficiary_id = user['beneficiary_id']
        last_status = user['last_known_status']
        
        logger.info(f"Checking status for user {chat_id} ({beneficiary_id})...")
        current_status, screenshot = await check_vendor_status(beneficiary_id)

        # Only notify if the status has changed
        if current_status != last_status:
            logger.info(f"Status changed for {beneficiary_id} from '{last_status}' to '{current_status}'. Sending notification.")
            database.update_user_status(chat_id, current_status)
            
            ist_time = datetime.now(ZoneInfo("Asia/Kolkata")).strftime('%Y-%m-%d %H:%M:%S %Z')
            message = ""
            if current_status == "Available":
                message = f"✅ Status for <code>{beneficiary_id}</code> at {ist_time}: <b>VENDOR AVAILABLE!</b>"
            elif current_status == "Not Available":
                 message = f"❌ Status for <code>{beneficiary_id}</code> at {ist_time}: Vendor Not Available."
            else: # Error case
                message = f"⚠️ Error checking <code>{beneficiary_id}</code> at {ist_time}: {current_status}"

            # Prepare keyboard
            keyboard = [[InlineKeyboardButton("View Website", url=f"{URL}&beneficiaryId={beneficiary_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send photo or text
            if screenshot:
                await context.bot.send_photo(
                    chat_id=chat_id, 
                    photo=open(screenshot, 'rb'), 
                    caption=message, 
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
                os.remove(screenshot) # Clean up
            else:
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=message, 
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
        else:
            logger.info(f"Status for {beneficiary_id} has not changed ('{current_status}'). No notification sent.")

# --- COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    welcome_message = (
        "Welcome to the MSEDCL Vendor Monitor Bot!\n\n"
        "To start monitoring, please use the command:\n"
        "/add <YOUR_BENEFICIARY_ID>\n\n"
        "Example: /add MT4420500385456"
    )
    await update.message.reply_text(welcome_message)

async def add_beneficiary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /add command to add/update a beneficiary ID."""
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Please provide a Beneficiary ID. Example: /add MT4420500385456")
        return

    beneficiary_id = context.args[0].strip().upper()
    if not beneficiary_id.startswith("MT") or len(beneficiary_id) != 15:
        await update.message.reply_text("Invalid Beneficiary ID format. It should start with 'MT' and be 15 characters long.")
        return

    success = database.add_or_update_user(chat_id, beneficiary_id)
    if success:
        await update.message.reply_text(
            f"✅ Success! I will now monitor the Beneficiary ID: <code>{beneficiary_id}</code>\n\n"
            "I will notify you only when the vendor status changes. Performing an initial check now...",
            parse_mode='HTML'
        )
        # Schedule an immediate one-time check for this new user
        context.job_queue.run_once(run_monitor_job, when=1, chat_id=chat_id, name=f"initial_check_{chat_id}")
    else:
        await update.message.reply_text("⚠️ This Beneficiary ID is already being monitored by another user.")

# --- MAIN APPLICATION ---
def main():
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found. Exiting.")
        return

    database.initialize_database()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_beneficiary))

    # Schedule the recurring job
    job_queue = application.job_queue
    job_queue.run_repeating(run_monitor_job, interval=180, first=10) # Runs every 3 minutes

    logger.info("Bot is running... Press Ctrl-C to stop.")
    application.run_polling()

if __name__ == "__main__":
    main()