# Document Processing Application

A Flask-based web application for document processing with automated text extraction and Google Sheets integration.

## Features

- User authentication (login page)
- Document selection (Passport, Cheque, Invoice)
- Upload images from local system or NAS
- Parallel processing of document images
- Review and correction of extracted data
- Integration with Google Sheets for data storage

## Requirements

- Python 3.8+
- Flask and other packages listed in requirements.txt
- Google Sheets API credentials

## Setup

1. Clone the repository
2. Install required packages:
   ```
   pip install -r requirements.txt
   ```
3. Set up Google Sheets API:
   - Create a project in Google Cloud Console
   - Enable Google Sheets API
   - Create a service account and download credentials
   - Rename the credentials file to `google_credentials.json` and place it in the project root
   - Create a Google Sheet named "Document_Processing_App_Logs" and share it with the service account email
   - Create worksheets: "Login_Logs", "Passport_Data", "Check_Data", "Invoice_Data"

4. Run the application:
   ```
   python app.py
   ```

## Usage

1. **Login Page**: 
   - Enter email and password credentials
   - Submits to Google Sheets for logging

2. **Document Selection Page**:
   - Choose document type (Passport, Cheque, Invoice)
   - Upload images from local system or NAS
   - Click "Process" to begin extraction

3. **Review Page**:
   - View processed documents in the sidebar
   - Review and correct extracted data
   - Save data to Google Sheets
   - Navigate between processed documents

## Technical Details

The application uses:
- Flask for the web framework
- Transformer models for document text extraction (via MAIN.py)
- Google Sheets API for data storage
- Multi-threading for parallel image processing

## File Structure

- `app.py` - Main Flask application
- `MAIN.py` - Document processing module with transformer models
- `templates/` - HTML templates
- `static/` - CSS, JS, and image assets
- `uploads/` - Directory for uploaded files (created at runtime)
- `google_credentials.json` - Google Sheets API credentials


 
 
