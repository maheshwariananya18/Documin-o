import sqlite3
import bcrypt
import os
from config import Config

def init_database():
    # Ensure data directory exists
    data_dir = os.path.dirname(Config.USER_DB_PATH)
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    # Connect to database
    conn = sqlite3.connect(Config.USER_DB_PATH)
    cursor = conn.cursor()

    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            full_name TEXT,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            annotation_mode TEXT DEFAULT 'manual',
            verification_mode INTEGER DEFAULT 0
        )
    ''')

    # Create initial users
    initial_users = [
        {
            'username': 'admin@example.com',
            'password': 'admin123',
            'role': 'admin',
            'full_name': 'Admin User',
            'email': 'admin@example.com'
        },
        {
            'username': 'user@example.com',
            'password': 'user123',
            'role': 'annotator',
            'full_name': 'Regular User',
            'email': 'user@example.com'
        }
    ]

    # Insert users
    for user in initial_users:
        # Check if user already exists
        cursor.execute("SELECT username FROM users WHERE username = ?", (user['username'],))
        if cursor.fetchone() is None:
            # Hash the password
            password_hash = bcrypt.hashpw(user['password'].encode('utf-8'), bcrypt.gensalt())
            
            # Insert the user
            cursor.execute('''
                INSERT INTO users (username, password_hash, role, full_name, email)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                user['username'],
                password_hash,
                user['role'],
                user['full_name'],
                user['email']
            ))
            print(f"Created user: {user['username']}")

    # Commit changes and close connection
    conn.commit()
    conn.close()
    print("Database initialization completed successfully!")

if __name__ == "__main__":
    init_database() 