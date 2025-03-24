import sqlite3
import bcrypt
import logging
import os
from config import Config

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("user_auth.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class UserAuth:
    """
    User authentication class that handles user registration, login, and password management
    using SQLite and bcrypt for password hashing.
    """
    
    def __init__(self, db_path=None):
        """
        Initialize the UserAuth class with the database path
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path or Config.USER_DB_PATH
        self._init_db()
    
    def _init_db(self):
        """
        Initialize the database by creating the users table if it doesn't exist
        """
        try:
            # Create the database directory if it doesn't exist
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            
            # Connect to the database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create the users table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    full_name TEXT,
                    email TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    annotation_mode TEXT DEFAULT 'manual',
                    verification_mode INTEGER DEFAULT 0
                )
            ''')
            
            # Check if the annotation_mode column exists, add it if it doesn't
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'annotation_mode' not in columns:
                logger.info("Adding annotation_mode column to users table")
                cursor.execute("ALTER TABLE users ADD COLUMN annotation_mode TEXT DEFAULT 'manual'")
                
            if 'verification_mode' not in columns:
                logger.info("Adding verification_mode column to users table")
                cursor.execute("ALTER TABLE users ADD COLUMN verification_mode INTEGER DEFAULT 0")
            
            # Commit the changes and close the connection
            conn.commit()
            conn.close()
            
            # Import existing users from config.py if the table is empty
            self._import_existing_users()
            
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}")
    
    def _import_existing_users(self):
        """
        Import existing users from config.py if the table is empty
        """
        try:
            # Connect to the database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if the users table is empty
            cursor.execute("SELECT COUNT(*) FROM users")
            count = cursor.fetchone()[0]
            
            if count == 0:
                logger.info("Importing existing users from config.py")
                
                # Import existing users from config.py
                try:
                    from config import USERS
                    for username, user_data in USERS.items():
                        try:
                            # Hash the password
                            password_hash = bcrypt.hashpw(user_data['password'].encode('utf-8'), bcrypt.gensalt())
                            
                            # Insert the user into the database
                            cursor.execute(
                                "INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, ?, ?)",
                                (username, password_hash, user_data['role'], user_data.get('full_name', ''))
                            )
                        except Exception as e:
                            logger.error(f"Error importing user {username}: {str(e)}")
                
                    # Commit the changes
                    conn.commit()
                    logger.info(f"Imported default users")
                except ImportError:
                    # Create default admin user if USERS is not available
                    logger.info("Creating default admin user")
                    admin_password = bcrypt.hashpw('admin123'.encode('utf-8'), bcrypt.gensalt())
                    cursor.execute(
                        "INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, ?, ?)",
                        ('admin@example.com', admin_password, 'admin', 'Admin User')
                    )
                    conn.commit()
                    logger.info("Created default admin user")
            
            # Close the connection
            conn.close()
        except Exception as e:
            logger.error(f"Error importing existing users: {str(e)}")
    
    def register_user(self, username, password, role='annotator', full_name='', email='', annotation_mode='manual', verification_mode=False):
        """
        Register a new user
        
        Args:
            username: Username for the new user
            password: Password for the new user
            full_name: Full name of the user
            email: Email address of the user
            annotation_mode: Annotation mode for the user (default: manual)
            verification_mode: Verification mode for the user (default: False)
            
        Returns:
            tuple: (success, message)
        """
        try:
            # Connect to the database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if the username already exists
            cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
            if cursor.fetchone():
                conn.close()
                return False, "Username already exists"
            
            # Hash the password
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            
            # Insert the new user
            cursor.execute(
                "INSERT INTO users (username, password_hash, role, full_name, email, annotation_mode, verification_mode) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (username, password_hash, role, full_name, email, annotation_mode, 1 if verification_mode else 0)
            )
            
            # Commit the changes and close the connection
            conn.commit()
            conn.close()
            
            logger.info(f"User {username} registered successfully")
            return True, "User registered successfully"
        except Exception as e:
            logger.error(f"Error registering user {username}: {str(e)}")
            return False, f"Error registering user: {str(e)}"
    
    def authenticate_user(self, username, password):
        """
        Authenticate a user
        
        Args:
            username: Username to authenticate
            password: Password to authenticate
            
        Returns:
            tuple: (success, user_data or error_message)
        """
        try:
            # Connect to the database
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Return rows as dictionaries
            cursor = conn.cursor()
            
            # Get the user from the database
            cursor.execute(
                "SELECT id, username, password_hash, role, full_name, email, is_active, annotation_mode, verification_mode FROM users WHERE username = ?",
                (username,)
            )
            user = cursor.fetchone()
            
            # Check if the user exists
            if not user:
                conn.close()
                return False, "Invalid username or password"
            
            # Check if the user is active
            if not user['is_active']:
                conn.close()
                return False, "User account is inactive"
            
            # Check if the password is correct
            if bcrypt.checkpw(password.encode('utf-8'), user['password_hash']):
                # Update last login timestamp
                cursor.execute(
                    "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                    (user['id'],)
                )
                conn.commit()
                
                # Convert user row to dictionary
                user_dict = dict(user)
                
                # Close the connection
                conn.close()
                
                logger.info(f"User {username} authenticated successfully")
                return True, user_dict
            else:
                conn.close()
                logger.warning(f"Failed authentication attempt for user {username}")
                return False, "Invalid username or password"
        except Exception as e:
            logger.error(f"Error authenticating user {username}: {str(e)}")
            return False, f"Error authenticating user: {str(e)}"
    
    def change_password(self, username, current_password, new_password):
        """
        Change a user's password
        
        Args:
            username: Username of the user
            current_password: Current password of the user
            new_password: New password for the user
            
        Returns:
            tuple: (success, message)
        """
        try:
            # First authenticate the user with the current password
            success, result = self.authenticate_user(username, current_password)
            
            if not success:
                return False, "Current password is incorrect"
            
            # Connect to the database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Hash the new password
            new_password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
            
            # Update the password
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (new_password_hash, username)
            )
            
            # Commit the changes and close the connection
            conn.commit()
            conn.close()
            
            logger.info(f"Password changed successfully for user {username}")
            return True, "Password changed successfully"
        except Exception as e:
            logger.error(f"Error changing password for user {username}: {str(e)}")
            return False, f"Error changing password: {str(e)}"
    
    def get_user(self, username):
        """
        Get a user by username
        
        Args:
            username: Username to get
            
        Returns:
            dict: User data or None if not found
        """
        try:
            # Connect to the database
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Return rows as dictionaries
            cursor = conn.cursor()
            
            # Get the user from the database
            cursor.execute(
                "SELECT id, username, role, full_name, email, is_active, annotation_mode, verification_mode FROM users WHERE username = ?",
                (username,)
            )
            user = cursor.fetchone()
            
            # Close the connection
            conn.close()
            
            if user:
                return dict(user)
            else:
                return None
        except Exception as e:
            logger.error(f"Error getting user {username}: {str(e)}")
            return None
    
    def get_user_by_id(self, user_id):
        """
        Get a user by ID
        
        Args:
            user_id: User ID to get
            
        Returns:
            dict: User data or None if not found
        """
        try:
            # Connect to the database
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Return rows as dictionaries
            cursor = conn.cursor()
            
            # Get the user from the database
            cursor.execute(
                "SELECT id, username, role, full_name, email, is_active, annotation_mode, verification_mode FROM users WHERE id = ?",
                (user_id,)
            )
            user = cursor.fetchone()
            
            # Close the connection
            conn.close()
            
            if user:
                return dict(user)
            else:
                return None
        except Exception as e:
            logger.error(f"Error getting user by ID {user_id}: {str(e)}")
            return None
    
    def get_all_users(self):
        """
        Get all users
        
        Returns:
            list: List of user dictionaries
        """
        try:
            # Connect to the database
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Return rows as dictionaries
            cursor = conn.cursor()
            
            # Get all users from the database
            cursor.execute(
                "SELECT id, username, role, full_name, email, created_at, last_login, is_active, annotation_mode, verification_mode FROM users"
            )
            users = cursor.fetchall()
            
            # Close the connection
            conn.close()
            
            # Convert rows to dictionaries
            return [dict(user) for user in users]
        except Exception as e:
            logger.error(f"Error getting all users: {str(e)}")
            return []
    
    def update_user(self, username, role=None, full_name=None, email=None, is_active=None, annotation_mode=None, verification_mode=None):
        """
        Update user information
        
        Args:
            username: Username of the user to update
            role: New role for the user (optional)
            full_name: New full name for the user (optional)
            email: New email for the user (optional)
            is_active: New active status for the user (optional)
            annotation_mode: New annotation mode for the user (optional)
            verification_mode: New verification mode for the user (optional)
            
        Returns:
            tuple: (success, message)
        """
        try:
            # Connect to the database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if the user exists
            cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
            if not cursor.fetchone():
                conn.close()
                return False, "User does not exist"
            
            # Build the update query
            update_fields = []
            params = []
            
            if role is not None:
                update_fields.append("role = ?")
                params.append(role)
            
            if full_name is not None:
                update_fields.append("full_name = ?")
                params.append(full_name)
            
            if email is not None:
                update_fields.append("email = ?")
                params.append(email)
            
            if is_active is not None:
                update_fields.append("is_active = ?")
                params.append(1 if is_active else 0)
                
            if annotation_mode is not None:
                update_fields.append("annotation_mode = ?")
                params.append(annotation_mode)
                
            if verification_mode is not None:
                update_fields.append("verification_mode = ?")
                params.append(1 if verification_mode else 0)
            
            if not update_fields:
                conn.close()
                return False, "No fields to update"
            
            # Add the username to the parameters
            params.append(username)
            
            # Execute the update query
            cursor.execute(
                f"UPDATE users SET {', '.join(update_fields)} WHERE username = ?",
                params
            )
            
            # Commit the changes and close the connection
            conn.commit()
            conn.close()
            
            logger.info(f"User {username} updated successfully")
            return True, "User updated successfully"
        except Exception as e:
            logger.error(f"Error updating user {username}: {str(e)}")
            return False, f"Error updating user: {str(e)}"
    
    def delete_user(self, username):
        """
        Delete a user
        
        Args:
            username: Username of the user to delete
            
        Returns:
            tuple: (success, message)
        """
        try:
            # Connect to the database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if the user exists
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            
            if not user:
                conn.close()
                return False, "User not found"
            
            # Delete the user
            cursor.execute("DELETE FROM users WHERE username = ?", (username,))
            
            # Commit the changes and close the connection
            conn.commit()
            conn.close()
            
            logger.info(f"User {username} deleted successfully")
            return True, "User deleted successfully"
        except Exception as e:
            logger.error(f"Error deleting user {username}: {str(e)}")
            return False, f"Error deleting user: {str(e)}"
    
    def suspend_user(self, username):
        """
        Suspend a user by setting their is_active status to 0
        
        Args:
            username: Username of the user to suspend
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Connect to the database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if the user exists
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            
            if not user:
                conn.close()
                logger.warning(f"Failed to suspend user {username}: User not found")
                return False
            
            # Suspend the user by setting is_active to 0
            cursor.execute("UPDATE users SET is_active = 0 WHERE username = ?", (username,))
            
            # Commit the changes and close the connection
            conn.commit()
            conn.close()
            
            logger.info(f"User {username} suspended successfully")
            return True
        except Exception as e:
            logger.error(f"Error suspending user {username}: {str(e)}")
            return False
    
    def unsuspend_user(self, username):
        """
        Unsuspend a user by setting their is_active status to 1
        
        Args:
            username: Username of the user to unsuspend
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Connect to the database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if the user exists
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            
            if not user:
                conn.close()
                logger.warning(f"Failed to unsuspend user {username}: User not found")
                return False
            
            # Unsuspend the user by setting is_active to 1
            cursor.execute("UPDATE users SET is_active = 1 WHERE username = ?", (username,))
            
            # Commit the changes and close the connection
            conn.commit()
            conn.close()
            
            logger.info(f"User {username} unsuspended successfully")
            return True
        except Exception as e:
            logger.error(f"Error unsuspending user {username}: {str(e)}")
            return False

# Create a singleton instance
user_auth = UserAuth() 