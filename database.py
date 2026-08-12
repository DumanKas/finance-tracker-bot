import sqlite3
from datetime import datetime
import gspread
import json
import os
from google.oauth2.service_account import Credentials


# ============================================================
# CONFIG
# ============================================================

DB_PATH = "/app/data/database.db"


# ============================================================
# GOOGLE SHEETS
# ============================================================

# GOOGLE_CREDS берётся из Railway Variables
creds_json = json.loads(os.environ["GOOGLE_CREDS"])

creds = Credentials.from_service_account_info(
    creds_json,
    scopes=[
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
)

gc = gspread.authorize(creds)
ws = gc.open("finanse-bot").sheet1


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    return sqlite3.connect(DB_PATH)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def database():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            category TEXT DEFAULT 'Другое',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            user_id INTEGER PRIMARY KEY
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vacancies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            url TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            user_id INTEGER PRIMARY KEY,
            daily_limit INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


# ============================================================
# CATEGORIES
# ============================================================

CATEGORIES = {
    "🍔 Еда": "Еда",
    "🛒 Продукты": "Продукты",
    "🚕 Транспорт": "Транспорт",
    "🏠 Дом": "Дом",
    "💳 Покупки": "Покупки",
    "🎮 Развлечения": "Развлечения",
    "📚 Образование": "Образование",
    "💊 Здоровье": "Здоровье",
    "💰 Другое": "Другое",
}


def get_categories():
    return list(CATEGORIES.values())


# ============================================================
# EXPENSES
# ============================================================

def add_expense(user_id, amount, category="Другое"):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO expenses (user_id, amount, category)
        VALUES (?, ?, ?)
        """,
        (user_id, amount, category)
    )

    conn.commit()
    conn.close()

    # Google Sheets оставляем как дополнительное хранилище
    try:
        ws.append_row([
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            user_id,
            amount,
            category
        ])
    except Exception as e:
        print(f"Ошибка Google Sheets: {e}")


# ============================================================
# OLD FUNCTION
# ============================================================

def add_expence(user_id, amount, category="Общее"):

    if category == "Общее":
        category = "Другое"

    add_expense(user_id, amount, category)


# ============================================================
# EXPENSE SEARCH
# ============================================================

def get_expenses_by_date(user_id, date):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, amount, category, created_at
        FROM expenses
        WHERE user_id = ?
        AND DATE(created_at, '+5 hours') = ?
        ORDER BY created_at DESC
        """,
        (user_id, date)
    )

    result = cursor.fetchall()

    conn.close()

    return result


def get_expenses_by_period(user_id, start_date, end_date):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, amount, category, created_at
        FROM expenses
        WHERE user_id = ?
        AND DATE(created_at, '+5 hours') BETWEEN ? AND ?
        ORDER BY created_at DESC
        """,
        (user_id, start_date, end_date)
    )

    result = cursor.fetchall()

    conn.close()

    return result


# ============================================================
# PERIOD TOTAL
# ============================================================

def get_total_by_period(user_id, start_date, end_date):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM expenses
        WHERE user_id = ?
        AND DATE(created_at, '+5 hours') BETWEEN ? AND ?
        """,
        (user_id, start_date, end_date)
    )

    result = cursor.fetchone()[0]

    conn.close()

    return result


# ============================================================
# TODAY
# ============================================================

def get_today_total(user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM expenses
        WHERE user_id = ?
        AND DATE(created_at, '+5 hours') =
            DATE('now', '+5 hours')
        """,
        (user_id,)
    )

    result = cursor.fetchone()[0]

    conn.close()

    return result


# ============================================================
# WEEK
# ============================================================

def get_weekly_total(user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM expenses
        WHERE user_id = ?
        AND DATE(created_at, '+5 hours') >=
            DATE('now', '+5 hours', '-6 days')
        """,
        (user_id,)
    )

    result = cursor.fetchone()[0]

    conn.close()

    return result


def get_weekly_stat(user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT category, SUM(amount)
        FROM expenses
        WHERE user_id = ?
        AND DATE(created_at, '+5 hours') >=
            DATE('now', '+5 hours', '-6 days')
        GROUP BY category
        ORDER BY SUM(amount) DESC
        """,
        (user_id,)
    )

    result = cursor.fetchall()

    conn.close()

    return result


# ============================================================
# MONTH
# ============================================================

def get_monthly_total(user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM expenses
        WHERE user_id = ?
        AND DATETIME(created_at, '+5 hours') >=
            DATETIME('now', '+5 hours', '-30 days')
        """,
        (user_id,)
    )

    result = cursor.fetchone()[0]

    conn.close()

    return result


# ============================================================
# CATEGORY STATISTICS
# ============================================================

def get_category_stats(user_id, start_date=None, end_date=None):

    conn = get_connection()
    cursor = conn.cursor()

    if start_date and end_date:

        cursor.execute(
            """
            SELECT category, SUM(amount)
            FROM expenses
            WHERE user_id = ?
            AND DATE(created_at, '+5 hours') BETWEEN ? AND ?
            GROUP BY category
            ORDER BY SUM(amount) DESC
            """,
            (user_id, start_date, end_date)
        )

    else:

        cursor.execute(
            """
            SELECT category, SUM(amount)
            FROM expenses
            WHERE user_id = ?
            GROUP BY category
            ORDER BY SUM(amount) DESC
            """,
            (user_id,)
        )

    result = cursor.fetchall()

    conn.close()

    return result


# ============================================================
# GOOGLE SHEETS REPORT
# ============================================================

def get_sheets(user_id):

    all_records = ws.get_all_records()

    totals = {}

    for row in all_records:

        try:

            if int(row["User ID"]) == user_id:

                category = row["Категория"]
                amount = row["Сумма"]

                totals[category] = (
                    totals.get(category, 0) + int(amount)
                )

        except (KeyError, ValueError, TypeError):
            continue

    return totals


# ============================================================
# SUBSCRIBERS
# ============================================================

def get_subscribers():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT user_id FROM subscribers"
    )

    result = [row[0] for row in cursor.fetchall()]

    conn.close()

    return result


def add_to_subscribers(user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO subscribers (user_id)
        VALUES (?)
        """,
        (user_id,)
    )

    conn.commit()
    conn.close()


# ============================================================
# VACANCIES
# ============================================================

def save_vacancy(title, url):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO vacancies(title, url)
        VALUES (?, ?)
        """,
        (title, url)
    )

    conn.commit()
    conn.close()


def get_new_vacancies(since_hours=6):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT title, url
        FROM vacancies
        WHERE created_at >=
            datetime('now', '-' || ? || ' hours')
        """,
        (since_hours,)
    )

    result = cursor.fetchall()

    conn.close()

    return result


# ============================================================
# SETTINGS
# ============================================================

def create_settings_table():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            user_id INTEGER PRIMARY KEY,
            daily_limit INTEGER DEFAULT 0
        )
        """
    )

    conn.commit()
    conn.close()


def set_daily_limit(user_id, limit):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO settings
        (user_id, daily_limit)
        VALUES (?, ?)
        """,
        (user_id, limit)
    )

    conn.commit()
    conn.close()


def get_limit(user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT daily_limit
        FROM settings
        WHERE user_id = ?
        """,
        (user_id,)
    )

    result = cursor.fetchone()

    conn.close()

    return result[0] if result else 0