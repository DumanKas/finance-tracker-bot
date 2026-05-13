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
    conn.commit()
    conn.close()

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
