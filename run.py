from app import app

if __name__ == '__main__':
    # Set debug to True for development
    app.run(debug=True, host='0.0.0.0', port=5000) 