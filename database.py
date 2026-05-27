import sqlite3

def database():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    category TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)
    ''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS subscribers (
        user_id INTEGER PRIMARY KEY)''')
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS vacancies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                url TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
    conn.commit()
    conn.close()

def save_vacancy(title, url):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO vacancies(title, url) VALUES (?, ?)", (title, url))
    conn.commit()
    conn.close()


def get_new_vacancies(since_hours = 6):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT title, url FROM vacancies WHERE created_at >= datetime('now', '-' || ? || ' hours')", (since_hours,))
    vacancies = cursor.fetchall()
    conn.close()
    return vacancies
def get_subscribers():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    # ИСПРАВЛЕНО: Добавлен SELECT запрос
    cursor.execute('SELECT user_id FROM subscribers')
    result = [row[0] for row in cursor.fetchall()]
    conn.close()
    return result


def add_to_subscribers(user_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO subscribers (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()
def get_weekly_stat(user_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT category, SUM(amount) FROM expenses WHERE user_id = ? AND created_at >= DATE('now', '-7 days')
    GROUP BY category
    ORDER BY SUM(amount) DESC''', (user_id,))
    result = cursor.fetchall()
    conn.close()
    return result
def add_expence(user_id, amount, category = "Общее"):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO expenses (user_id, amount, category) VALUES (?, ?, ?)", (user_id,amount,category))
    conn.commit()
    conn.close()

def get_today_total(user_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT SUM(amount) FROM expenses 
        WHERE user_id = ? 
        AND DATE(created_at, '+5 hours') = DATE('now', '+5 hours')
    ''', (user_id, ))
    result = cursor.fetchone()[0]
    conn.close()
    return result if result else 0

def get_weekly_total(user_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''SELECT SUM(amount) FROM expenses WHERE user_id = ? AND created_at >= DATE('now', '-7 days')''', (user_id, ))
    result = cursor.fetchone()[0]
    conn.close()
    return result if result else 0

def get_monthly_total(user_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''SELECT SUM(amount) FROM expenses WHERE user_id = ? AND created_at >= DATETIME('now', '+5 hours' , '-30 days')''', (user_id, ))
    result = cursor.fetchone()[0]
    conn.close()
    return result if result else 0

def create_settings_table():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS settings (
    user_id INTEGER PRIMARY KEY,
    daily_limit INTEGER DEFAULT 0)""")
    conn.commit()
    conn.close()

def set_daily_limit(user_id, limit):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (user_id, daily_limit) VALUES (?, ?)", (user_id, limit))
    conn.commit()
    conn.close()

def get_limit(user_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''SELECT daily_limit FROM settings WHERE user_id = ?''', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0
