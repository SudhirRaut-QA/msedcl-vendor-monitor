import sqlite3
import logging

DATABASE_FILE = "bot_database.db"
logger = logging.getLogger(__name__)

def initialize_database():
    """Creates the database and the users table if they don't exist."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            beneficiary_id TEXT UNIQUE,
            last_known_status TEXT DEFAULT 'Unknown',
            is_channel_member BOOLEAN DEFAULT 0,
            snoozed_until DATETIME
        )
        """)
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")

def add_or_update_user(chat_id: int, beneficiary_id: str) -> bool:
    """Adds a new user or updates an existing user's beneficiary ID."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO users (chat_id, beneficiary_id) VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET beneficiary_id = excluded.beneficiary_id
            """,
            (chat_id, beneficiary_id)
        )
        conn.commit()
        logger.info(f"Successfully added/updated user {chat_id} with beneficiary ID {beneficiary_id}")
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Attempt to add beneficiary ID {beneficiary_id} which is already in use.")
        return False
    except sqlite3.Error as e:
        logger.error(f"Database error while adding/updating user {chat_id}: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_all_users():
    """Fetches all users from the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # This allows accessing columns by name
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    conn.close()
    return users

def update_user_status(chat_id: int, new_status: str):
    """Updates the last_known_status for a specific user."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_known_status = ? WHERE chat_id = ?", (new_status, chat_id))
    conn.commit()
    conn.close()
    logger.info(f"Updated status for user {chat_id} to '{new_status}'")

if __name__ == '__main__':
    initialize_database()