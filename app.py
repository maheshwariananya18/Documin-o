import os
import json
import threading
import queue
import time
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_file
from werkzeug.utils import secure_filename
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from functools import wraps
import pandas as pd
import MAIN as doc_processor
from io import StringIO, BytesIO
import csv
import shutil
from gspread_pandas import Spread
from user_auth import UserAuth

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)
user_auth = UserAuth()  # Create UserAuth instance

# App Configuration
app.config.update(
    UPLOAD_FOLDER='uploads',
    ALLOWED_EXTENSIONS={'png', 'jpg', 'jpeg', 'pdf'},
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 MB limit
    CLEANUP_AFTER_PROCESSING=True,  # Enable automatic cleanup
    CLEANUP_INTERVAL=3600  # Cleanup old files every hour (in seconds)
)

# Create upload folder if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Global variables
process_queue = queue.Queue()
results_dict = {}

###################
# UTILITY FUNCTIONS
###################

def delete_file(file_path):
    """Deletes a file at the given path and returns success status"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Deleted temporary file: {file_path}")
            return True
        return False
    except Exception as e:
        print(f"Error deleting file {file_path}: {str(e)}")
        return False

def get_file_extension(path):
    """Extract file extension from path"""
    if path.lower().endswith('.jpg') or path.lower().endswith('.jpeg'):
        return '.jpg', 'image/jpeg'
    elif path.lower().endswith('.png'):
        return '.png', 'image/png'
    elif path.lower().endswith('.pdf'):
        return '.pdf', 'application/pdf'
    else:
        return '.png', 'image/png'  # Default

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def cleanup_uploads_folder():
    """Removes files from the uploads folder that are older than 24 hours"""
    while True:
        try:
            print("Starting scheduled cleanup of uploads folder...")
            now = time.time()
            count = 0
            
            # Get all files in the upload folder
            for file_name in os.listdir(app.config['UPLOAD_FOLDER']):
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)
                
                # Check if it's a file (not a directory)
                if os.path.isfile(file_path):
                    # Check if file is older than 24 hours
                    if now - os.path.getmtime(file_path) > 86400:  # 24 hours in seconds
                        if delete_file(file_path):
                            count += 1
            
            print(f"Cleanup complete. Deleted {count} old files.")
        except Exception as e:
            print(f"Error during scheduled cleanup: {str(e)}")
        
        # Sleep for the configured interval
        time.sleep(app.config['CLEANUP_INTERVAL'])

def parse_extracted_text(text, document_type):
    """Parse extracted text into structured data dictionary"""
    data = {}
    if text:
        lines = text.strip().split('\n')
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                data[key.strip()] = value.strip()
    return data

# Start the cleanup thread
cleanup_thread = threading.Thread(target=cleanup_uploads_folder, daemon=True)
cleanup_thread.start()

#####################
# GOOGLE SHEETS INTEGRATION
#####################

def setup_google_sheets():
    """Initialize Google Sheets client"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name('google_credentials.json', scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        print(f"Error setting up Google Sheets: {str(e)}")
        return None

def log_user_login(email):
    """Log user login information to Google Sheets"""
    try:
        client = setup_google_sheets()
        if client:
            sheet = client.open("Document_Processing_App_Logs").worksheet("Login_Logs")
            sheet.append_row([email, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
            return True
    except Exception as e:
        print(f"Error logging to Google Sheets: {str(e)}")
    return False

def save_document_data(email, document_type, data, corrections=None):
    """Save processed document data to Google Sheets"""
    try:
        client = setup_google_sheets()
        if client:
            # Open the spreadsheet
            sheet = client.open("Document_Processing_App_Logs").worksheet(f"{document_type.capitalize()}_Data")
            
            # Prepare row data
            row_data = [email, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), document_type]
            
            # Parse the extracted data based on document type
            if document_type == "check":
                row_data.extend([
                    " ",  # Link to The file
                    " ",  # Pic Date
                    " ",  # Download Date
                    " ",  # Check Type
                    data.get("Bank Name", ""),
                    data.get("1st Payor First Name", data.get("Payor Name", "")),
                    " ",  # 1st Payor Family Name
                    " ",  # 2nd Payor First Name
                    " ",  # 2nd Payor Family Name
                    data.get("Payor Street Address", data.get("Payor Address", "")),
                    " ",  # Payor City
                    " ",  # Payor State
                    " ",  # Payor Zip code
                    data.get("Check Amount", data.get("Amount", "")),
                    " ",  # Account Number
                    " ",  # Routing Number
                    " ",  # Payee Type
                    data.get("1st Payee First Name", data.get("Payee Name", "")),
                    " ",  # 1st Payee Family Name
                    " ",  # 2nd Payee First Name
                    " ",  # 2nd Payee Family Name
                    data.get("Check Number", ""),
                    data.get("Payee Street Address", data.get("Payee Address", "")),
                    " ",  # Payee City
                    " ",  # Payee State
                    " ",  # Payee Zip Code
                    " "   # Market
                ])
            elif document_type == "passport":
                row_data.extend([
                    data.get("Passport Country Code", "Not found"),
                    data.get("Passport Number", "Not found"),
                    data.get("First Name", "Not found"),
                    data.get("Family Name", "Not found"),
                    data.get("Date of Birth", "Not found"),
                    data.get("Gender", "Not found")
                ])
            elif document_type == "invoice":
                row_data.extend([
                    data.get("Invoice Number", "Not found"),
                    data.get("Invoice Date", "Not found"),
                    data.get("Vendor/Seller", "Not found"),
                    data.get("Total Amount", "Not found")
                ])
            
            # Add corrections info if available
            if corrections:
                row_data.append(json.dumps(corrections))
            
            # Append data to sheet
            sheet.append_row(row_data)
            return True
    except Exception as e:
        print(f"Error saving to Google Sheets: {str(e)}")
    return False

# Authentication decorator
def login_required(f):
    """Decorator to require login for protected routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_email' not in session:
            return redirect(url_for('login'))
        
        # Verify user still exists and is active
        user = user_auth.get_user(session['user_email'])
        if not user or not user['is_active']:
            session.clear()
            flash("Your account has been deactivated or deleted")
            return redirect(url_for('login'))
            
        return f(*args, **kwargs)
    return decorated_function

#####################
# DOCUMENT PROCESSING
#####################

def background_processor():
    """Background thread function to process documents from the queue"""
    while True:
        try:
            # Get item from queue
            task = process_queue.get()
            if task is None:  # Sentinel to end the thread
                break

            image_path, document_type, image_id, in_memory = task
            temp_file_path = None

            try:
                # Handle in-memory files (BytesIO objects)
                if in_memory:
                    # Get file extension and create temp file
                    file_extension, _ = get_file_extension(results_dict[image_id]['path'])
                    
                    import tempfile
                    temp_fd, temp_file_path = tempfile.mkstemp(suffix=file_extension)
                    os.close(temp_fd)
                    
                    # Write BytesIO to temp file
                    try:
                        with open(temp_file_path, 'wb') as f:
                            f.write(image_path.getvalue())
                        image_path = temp_file_path
                    except Exception as e:
                        print(f"Error writing to temporary file: {str(e)}")
                        results_dict[image_id]['status'] = 'error'
                        results_dict[image_id]['error'] = f"Could not create temporary file: {str(e)}"
                        process_queue.task_done()
                        continue
                else:
                    # Check if file exists or needs to be created from memory
                    if not os.path.exists(image_path):
                        if 'image_data' in results_dict[image_id]:
                            # Create temp file from image_data
                            file_extension, _ = get_file_extension(image_path)
                            
                            import tempfile
                            temp_fd, temp_file_path = tempfile.mkstemp(suffix=file_extension)
                            os.close(temp_fd)
                            
                            try:
                                with open(temp_file_path, 'wb') as f:
                                    f.write(results_dict[image_id]['image_data'])
                                image_path = temp_file_path
                                in_memory = True
                            except Exception as e:
                                print(f"Error writing to temporary file from image data: {str(e)}")
                                results_dict[image_id]['status'] = 'error'
                                results_dict[image_id]['error'] = f"Could not create temporary file: {str(e)}"
                                process_queue.task_done()
                                continue
                        else:
                            results_dict[image_id]['status'] = 'error'
                            results_dict[image_id]['error'] = 'File not found'
                            process_queue.task_done()
                            continue

                # Process document with model
                tokenizer, model = doc_processor.load_model()
                extracted_data = doc_processor.process_document_image(
                    image_path, document_type, tokenizer, model
                )

                # Update results with preserving existing data
                existing_data = results_dict[image_id].copy() if image_id in results_dict else {}
                results_dict[image_id] = {
                    'status': 'completed',
                    'data': extracted_data,
                    'path': existing_data.get('path', image_path)
                }
                
                # Preserve other metadata
                for key, value in existing_data.items():
                    if key not in results_dict[image_id]:
                        results_dict[image_id][key] = value

                # Process document-specific content
                process_extracted_data_by_type(image_id, document_type, extracted_data)

            finally:
                # Clean up temporary file if created
                if temp_file_path and os.path.exists(temp_file_path):
                    delete_file(temp_file_path)
                
                # Clean up original file if needed and not in-memory
                if not in_memory and app.config['CLEANUP_AFTER_PROCESSING'] and 'path' in results_dict[image_id]:
                    original_path = results_dict[image_id]['path']
                    if 'image_data' in results_dict[image_id] and os.path.exists(original_path):
                        delete_file(original_path)

                # Mark task as done
                process_queue.task_done()

        except Exception as e:
            import traceback
            traceback_str = traceback.format_exc()
            print(f"Error in background processor: {str(e)}")
            print(f"Traceback: {traceback_str}")
            
            if 'image_id' in locals():
                results_dict[image_id] = {
                    'status': 'error',
                    'error': str(e),
                    'path': image_path if 'image_path' in locals() else None
                }
                
                # Preserve image_data if it exists
                if image_id in results_dict and 'image_data' in results_dict[image_id]:
                    results_dict[image_id]['image_data'] = results_dict[image_id]['image_data']
                    
            process_queue.task_done()
            
            # Clean up temporary file if created
            if 'temp_file_path' in locals() and temp_file_path and os.path.exists(temp_file_path):
                delete_file(temp_file_path)

def process_extracted_data_by_type(image_id, document_type, extracted_data):
    """Process extracted data according to document type"""
    # Initialize txt_content variable with a default value
    txt_content = ""
    
    if document_type == 'check':
        # Convert to dictionary if it's a string
        extracted_data_dict = {}
        if isinstance(extracted_data, str):
            lines = extracted_data.strip().split('\n')
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    extracted_data_dict[key.strip()] = value.strip()
        elif isinstance(extracted_data, dict):
            extracted_data_dict = extracted_data
        else:
            # If neither string nor dict, convert to string then parse
            str_data = str(extracted_data)
            lines = str_data.strip().split('\n')
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    extracted_data_dict[key.strip()] = value.strip()

        # Generate formatted text content
        txt_content = "\n\n".join([
            f"File: {os.path.basename(results_dict[image_id]['path'])}\n"
            f"Link to The file: \n"
            f"Pic Date: NA\n"
            f"Download Date: \n"
            f"Check Type: NA\n"
            f"Bank Name: {extracted_data_dict.get('Bank Name', 'NA')}\n"
            f"1st Payor First Name: {extracted_data_dict.get('Payor Name', extracted_data_dict.get('1st Payor First Name', 'NA'))}\n"
            f"1st Payor Family Name: \n"
            f"2nd Payor First Name: \n"
            f"2nd Payor Family Name: \n"
            f"Payor Street Address: {extracted_data_dict.get('Payor Address', extracted_data_dict.get('Payor Street Address', 'NA'))}\n"
            f"Payor City: \n"
            f"Payor State: \n"
            f"Payor Zip code: \n"
            f"Check Amount: {extracted_data_dict.get('Amount', extracted_data_dict.get('Check Amount', 'NA'))}\n"
            f"Account Number: \n"
            f"Routing Number: \n"
            f"Payee Type: \n"
            f"1st Payee First Name: {extracted_data_dict.get('Payee Name', extracted_data_dict.get('1st Payee First Name', 'NA'))}\n"
            f"1st Payee Family Name: \n"
            f"2nd Payee First Name: \n"
            f"2nd Payee Family Name: \n"
            f"Check Number: {extracted_data_dict.get('Check Number', 'NA')}\n"
            f"Payee Street Address: {extracted_data_dict.get('Payee Address', extracted_data_dict.get('Payee Street Address', 'NA'))}\n"
            f"Payee City: \n"
            f"Payee State: \n"
            f"Payee Zip Code: \n"
            f"Market: \n"
            f"{'-'*50}"
        ])

    elif document_type == 'passport':
        # ... existing code ...
        pass
    elif document_type == 'invoice':
        # ... existing code ...
        pass
    elif document_type == 'text':
        txt_content = extracted_data  # This was likely missing in some code paths
    else:
        # ... existing code ...
        pass

    results_dict[image_id]['txt_content'] = txt_content
    results_dict[image_id]['parsed_data'] = extracted_data_dict

    # Generate CSV content
    all_results = [{
        'filename': os.path.basename(results_dict[image_id]['path']),
        'extraction_data': extracted_data_dict
    }]
    csv_content = convert_to_csv_content(all_results, document_type)
    results_dict[image_id]['csv_content'] = csv_content

# Start background processing thread
processor_thread = threading.Thread(target=background_processor, daemon=True)
processor_thread.start()

#####################
# DATA EXPORT FUNCTIONS
#####################

def convert_to_csv_content(all_results, document_type=None):
    """Convert text extraction results to TSV format with proper document type handling"""
    output = StringIO()
    writer = csv.writer(output, delimiter='\t')
    
    # Use passed document_type instead of reading from session
    doc_type = document_type or 'unknown'
    
    # Define headers and data extraction based on document type
    if doc_type == 'check':
        headers = [
            'Filename',
            'Link to The file',
            'Pic Date',
            'Download Date',
            'Check Type',
            'Bank Name',
            '1st Payor First Name',
            '1st Payor Family Name',
            '2nd Payor First Name',
            '2nd Payor Family Name',
            'Payor Street Address',
            'Payor City',
            'Payor State',
            'Payor Zip code',
            'Check Amount',
            'Account Number',
            'Routing Number',
            'Payee Type',
            '1st Payee First Name',
            '1st Payee Family Name',
            '2nd Payee First Name',
            '2nd Payee Family Name',
            'Check Number',
            'Payee Street Address',
            'Payee City',
            'Payee State',
            'Payee Zip Code',
            'Market'
        ]
        
        def extract_check_data(filename, extraction_text):
            # Parse the raw extraction text to get check-specific data
            data = {}
            if isinstance(extraction_text, str):
                lines = extraction_text.split('\n')
                for line in lines:
                    if ':' in line:
                        key, value = [x.strip() for x in line.split(':', 1)]
                        data[key] = value if value else 'NA'
            else:
                # If it's already a dictionary
                data = extraction_text
            
            return [
                filename,
                'Not found',  # Link to The file
                'Not found',  # Pic Date
                'Not found',  # Download Date
                'Not found',  # Check Type
                data.get('Bank Name', 'Not found'),
                data.get('Payor Name', 'Not found'),  # 1st Payor First Name
                'Not found',  # 1st Payor Family Name
                'Not found',  # 2nd Payor First Name
                'Not found',  # 2nd Payor Family Name
                data.get('Payor Address', 'Not found'),
                'Not found',  # Payor City
                'Not found',  # Payor State
                'Not found',  # Payor Zip code
                data.get('Amount', 'Not found'),
                'Not found',  # Account Number
                'Not found',  # Routing Number
                'Not found',  # Payee Type
                data.get('Payee Name', 'Not found'),  # 1st Payee First Name
                'Not found',  # 1st Payee Family Name
                'Not found',  # 2nd Payee First Name
                'Not found',  # 2nd Payee Family Name
                data.get('Check Number', 'Not found'),
                data.get('Payee Address', 'Not found'),
                'Not found',  # Payee City
                'Not found',  # Payee State
                'Not found',  # Payee Zip Code
                'Not found'   # Market
            ]
        
        # Write headers
        writer.writerow(headers)
        
        # Process each result
        for result in all_results:
            filename = result['filename']
            row = extract_check_data(filename, result['extraction_data'])
            writer.writerow(row)
            
    elif doc_type == 'passport':
        headers = [
            'Filename',
            'Passport Country Code',
            'Passport Type',
            'Passport Number',
            'First Name',
            'Family Name',
            'Date of Birth Day',
            'Date of Birth Month',
            'Date of Birth Year',
            'Place of Birth',
            'Gender',
            'Date of Issue Day',
            'Date of Issue Month',
            'Date of Issue Year',
            'Date of Expiration Day',
            'Date of Expiration Month',
            'Date of Expiration Year',
            'Authority'
        ]
        
        def extract_passport_data(filename, data):
            if isinstance(data, str):
                # Parse the data string into a dictionary
                data_dict = {}
                lines = data.split('\n')
                for line in lines:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        data_dict[key.strip()] = value.strip()
                data = data_dict
                
            return [
                filename,
                data.get('Passport Country Code', 'NA'),
                data.get('Passport Type', 'NA'),
                data.get('Passport Number', 'NA'),
                data.get('First Name', 'NA'),
                data.get('Family Name', 'NA'),
                data.get('Date of Birth Day', 'NA'),
                data.get('Date of Birth Month', 'NA'),
                data.get('Date of Birth Year', 'NA'),
                data.get('Place of Birth', 'NA'),
                data.get('Gender', 'NA'),
                data.get('Date of Issue Day', 'NA'),
                data.get('Date of Issue Month', 'NA'),
                data.get('Date of Issue Year', 'NA'),
                data.get('Date of Expiration Day', 'NA'),
                data.get('Date of Expiration Month', 'NA'),
                data.get('Date of Expiration Year', 'NA'),
                data.get('Authority', 'NA')
            ]
        
        # Write headers
        writer.writerow(headers)
        
        # Process each result
        for result in all_results:
            filename = result['filename']
            row = extract_passport_data(filename, result['extraction_data'])
            writer.writerow(row)
        
    elif doc_type == 'invoice':
        headers = [
            'Filename',
            'Invoice Number',
            'Date',
            'Due Date',
            'Total Amount',
            'Vendor Name',
            'Customer Name',
            'Payment Terms'
        ]
        
        def extract_invoice_data(filename, data):
            if isinstance(data, str):
                # Parse the data string into a dictionary
                data_dict = {}
                lines = data.split('\n')
                for line in lines:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        data_dict[key.strip()] = value.strip()
                data = data_dict
                
            return [
                filename,
                data.get('Invoice Number', 'NA'),
                data.get('Date', 'NA'),
                data.get('Due Date', 'NA'),
                data.get('Total Amount', 'NA'),
                data.get('Vendor Name', 'NA'),
                data.get('Customer Name', 'NA'),
                data.get('Payment Terms', 'NA')
            ]
        
        # Write headers
        writer.writerow(headers)
        
        # Process each result
        for result in all_results:
            filename = result['filename']
            row = extract_invoice_data(filename, result['extraction_data'])
            writer.writerow(row)
    
    else:
        headers = ['Filename', 'Extraction Data']
        writer.writerow(headers)
        
        for result in all_results:
            filename = result['filename']
            writer.writerow([filename, str(result['extraction_data'])])
    
    return output.getvalue()

#####################
# ROUTE HANDLERS
#####################

@app.route('/')
def login():
    """Render the login page"""
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def process_login():
    """Process user login using UserAuth"""
    email = request.form.get('email')
    password = request.form.get('password')
    
    if not email or not password:
        flash("Please enter both email and password")
        return redirect(url_for('login'))
    
    # Authenticate user
    success, result = user_auth.authenticate_user(email, password)
    
    if success:
        # Set session variables
        session['user_email'] = email
        session['user_role'] = result['role']
        session['user_id'] = result['id']
        
        # Log to Google Sheets
        log_user_login(email)
        
        return redirect(url_for('document_selection'))
    else:
        # Show specific error message
        error_message = result if isinstance(result, str) else "Invalid username or password"
        flash(error_message)
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    """Log user out and clear session"""
    session.clear()
    return redirect(url_for('login'))

@app.route('/document-selection')
@login_required
def document_selection():
    """Show document type selection page"""
    return render_template('document_selection.html')

@app.route('/fetch-data')
@login_required
def fetch_data():
    """Show fetch data interface"""
    try:
        return render_template('fetch_data.html')
    except Exception as e:
        print(f"Error rendering fetch_data.html: {str(e)}")
        flash("Error loading fetch data page")
        return redirect(url_for('document_selection'))

@app.route('/process-data')
@login_required
def process_data():
    """Show document type selection for processing"""
    try:
        return render_template('process_data.html')
    except Exception as e:
        print(f"Error rendering process_data.html: {str(e)}")
        flash("Error loading process data page")
        return redirect(url_for('document_selection'))

@app.route('/upload', methods=['POST'])
@login_required
def upload_documents():
    """Handle document uploads and queue for processing"""
    document_type = request.form.get('document_type')
    if not document_type or document_type not in ['passport', 'check', 'invoice']:
        return jsonify({'error': 'Invalid document type'}), 400

    if 'files[]' not in request.files:
        return jsonify({'error': 'No files selected'}), 400

    files = request.files.getlist('files[]')
    if not files or files[0].filename == '':
        return jsonify({'error': 'No files selected'}), 400
        
    if len(files) > 10:
        return jsonify({'error': 'You can only upload up to 10 files at a time'}), 400

    processed_files = []
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            unique_filename = f"{timestamp}_{filename}"
            image_id = f"{timestamp}_{filename}"
            
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            
            file_data = file.read()
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            
            if file_size < 1024 * 1024 and app.config['CLEANUP_AFTER_PROCESSING']:
                results_dict[image_id] = {
                    'status': 'processing',
                    'path': file_path,
                    'image_data': file_data
                }
                file_buffer = BytesIO(file_data)
                process_queue.put((file_buffer, document_type, image_id, True))
            else:
                with open(file_path, 'wb') as f:
                    f.write(file_data)

                results_dict[image_id] = {
                    'status': 'processing', 
                    'path': file_path,
                    'image_data': file_data
                }
                process_queue.put((file_path, document_type, image_id, False))

            processed_files.append({
                'id': image_id,
                'name': filename,
                'path': file_path
            })

    session['document_type'] = document_type
    session['processing_files'] = processed_files

    return jsonify({
        'success': True,
        'redirect': url_for('review_documents'),
        'message': f'{len(processed_files)} files uploaded and being processed'
    })

@app.route('/review')
@login_required
def review_documents():
    """Show document review page"""
    if 'document_type' not in session or 'processing_files' not in session:
        flash('No documents selected for processing')
        return redirect(url_for('document_selection'))
        
    return render_template(
        'review.html',
        document_type=session['document_type'],
        files=session['processing_files']
    )

@app.route('/api/check-status/<image_id>')
@login_required
def check_status(image_id):
    """Check processing status of a document"""
    if image_id in results_dict:
        result = results_dict[image_id]
        if result['status'] == 'completed':
            # Parse the extracted text into structured data
            extracted_data = parse_extracted_text(result['data'], session['document_type'])
            return jsonify({
                'status': 'completed',
                'data': extracted_data
            })
        elif result['status'] == 'error':
            return jsonify({
                'status': 'error',
                'error': result.get('error', 'An unknown error occurred')
            })
        else:
            return jsonify({'status': 'processing'})
    else:
        return jsonify({'status': 'not_found'})

@app.route('/document-image/<image_id>')
@login_required
def serve_document_image(image_id):
    """Serve document image from memory or disk"""
    if image_id in results_dict:
        result = results_dict[image_id]
        
        # Check if we have in-memory image data
        if 'image_data' in result:
            _, mimetype = get_file_extension(result['path'])
            
            # Create BytesIO object from image data
            img_io = BytesIO(result['image_data'])
            img_io.seek(0)
            
            return send_file(img_io, mimetype=mimetype)
        
        # If image data not in memory, get the file path
        file_path = result['path']
        
        # Check if file exists
        if os.path.exists(file_path):
            _, mimetype = get_file_extension(file_path)
            return send_file(file_path, mimetype=mimetype)

    # If image not found or file doesn't exist
    return jsonify({'error': 'Image not found'}), 404

@app.route('/api/save-document', methods=['POST'])
@login_required
def save_document():
    """Save document data with user corrections"""
    data = request.json
    image_id = data.get('image_id')
    corrected_data = data.get('data')
    corrections = data.get('corrections')
    verified = data.get('verified', True)  # Default to true since we removed the checkbox
    
    if not image_id or not corrected_data:
        return jsonify({'success': False, 'error': 'Missing required data'}), 400
    
    document_type = session.get('document_type')
    if not document_type:
        return jsonify({'success': False, 'error': 'Document type not found in session'}), 400
    
    # Mark as completed in our results dictionary regardless of saving to sheets
    if image_id in results_dict:
        results_dict[image_id]['is_saved'] = True
        
        # Store the updated data
        if 'parsed_data' in results_dict[image_id]:
            results_dict[image_id]['parsed_data'].update(corrected_data)
        
        # Clean up the file if it's not already cleaned up but ensure we keep image_data
        if app.config['CLEANUP_AFTER_PROCESSING'] and 'path' in results_dict[image_id]:
            file_path = results_dict[image_id]['path']
            # Ensure we have image data in memory before deleting the file
            if 'image_data' not in results_dict[image_id] and os.path.exists(file_path):
                try:
                    # Read the image file into memory
                    with open(file_path, 'rb') as f:
                        image_data = f.read()
                    results_dict[image_id]['image_data'] = image_data
                    # Now we can delete the file
                    delete_file(file_path)
                except Exception as e:
                    print(f"Error reading image data before cleanup: {str(e)}")
            elif os.path.exists(file_path):
                # We already have image data, just delete the file
                delete_file(file_path)
        
    # Only save to Google Sheets if verified
    if verified:
        # Save to Google Sheets
        save_success = save_document_data(
            session.get('user_email'),
            document_type,
            corrected_data,
            corrections
        )
        
        if not save_success:
            return jsonify({'success': False, 'error': 'Failed to save data to Google Sheets'}), 500
            
    return jsonify({'success': True})

@app.route('/download_csv/<image_id>')
@login_required
def download_csv(image_id):
    """Generate and download CSV for processed document"""
    if image_id not in results_dict or results_dict[image_id]['status'] != 'completed':
        flash('No processed results found for this file', 'error')
        return redirect(url_for('review_documents'))
    
    result = results_dict[image_id]
    document_type = session.get('document_type', 'document')
    filename = os.path.basename(result['path'])
    
    # Check if we have CSV content already or need to generate it
    if 'csv_content' not in result:
        # Generate CSV content
        all_results = [{
            'filename': filename,
            'extraction_data': result['data']
        }]
        csv_content = convert_to_csv_content(all_results, document_type)
    else:
        csv_content = result['csv_content']
    
    # Convert the TSV content to actual CSV content with commas
    csv_lines = []
    for line in csv_content.split('\n'):
        if line.strip():
            # Convert tab-separated values to comma-separated values
            values = line.split('\t')
            # Properly escape values containing commas by enclosing them in quotes
            escaped_values = [f'"{value}"' if ',' in value else value for value in values]
            csv_lines.append(','.join(escaped_values))
    
    csv_content = '\n'.join(csv_lines)
    
    # Create a memory file
    mem_file = BytesIO()
    mem_file.write(csv_content.encode('utf-8'))
    mem_file.seek(0)
    
    # Generate a timestamp for the filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    return send_file(
        mem_file,
        as_attachment=True,
        download_name=f"{document_type}_{filename}_{timestamp}.csv",
        mimetype='text/csv'
    )

@app.route('/download_txt/<image_id>')
@login_required
def download_txt(image_id):
    """Generate and download TXT for processed document"""
    if image_id not in results_dict or results_dict[image_id]['status'] != 'completed':
        flash('No processed results found for this file', 'error')
        return redirect(url_for('review_documents'))
    
    result = results_dict[image_id]
    document_type = session.get('document_type', 'document')
    filename = os.path.basename(result['path'])
    
    # Check if we have TXT content already or need to generate it
    if 'txt_content' not in result:
        # Generate TXT content based on document type
        txt_content = result['data']
    else:
        txt_content = result['txt_content']
    
    # Create a memory file
    mem_file = BytesIO()
    mem_file.write(txt_content.encode('utf-8'))
    mem_file.seek(0)
    
    # Generate a timestamp for the filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    return send_file(
        mem_file,
        as_attachment=True,
        download_name=f"{document_type}_{filename}_{timestamp}.txt",
        mimetype='text/plain'
    )

# Add a registration route (optional)
@app.route('/register', methods=['POST'])
def register():
    """Register a new user"""
    email = request.form.get('email')
    password = request.form.get('password')
    full_name = request.form.get('full_name', '')
    role = request.form.get('role', 'annotator')
    
    if email and password:
        success, message = user_auth.register_user(
            username=email,
            password=password,
            role=role,
            full_name=full_name,
            email=email
        )
        
        if success:
            flash("Registration successful. Please login.")
            return redirect(url_for('login'))
        else:
            flash(message)
            return redirect(url_for('register'))
    else:
        flash("Please enter both email and password")
        return redirect(url_for('register'))

# Run the application
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 