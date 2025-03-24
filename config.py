import os

class Config:
    # Database configuration
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    USER_DB_PATH = os.path.join(BASE_DIR, 'data', 'users.db')
    
    # Add other configuration settings as needed
    DEBUG = True
    SECRET_KEY = 'your-secret-key-here'  # Change this in production!

# Default users dictionary (used for initial setup)
USERS = {
    'admin@example.com': {
        'password': 'admin123',
        'role': 'admin',
        'full_name': 'Admin User'
    },
    'user@example.com': {
        'password': 'user123',
        'role': 'annotator',
        'full_name': 'Regular User'
    }
} 