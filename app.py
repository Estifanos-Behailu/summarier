from flask import Flask, request, render_template
import PyPDF2
import os
import openai
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io
import time
from sqlalchemy.exc import OperationalError, PendingRollbackError

SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'service_account.json'
PARENT_FOLDER_ID = "1P1I2RBsj48aaPiSJsg8c6HWxkdjd5MNF"

def authenticate():
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return creds

def upload_file(file_path):
    creds = authenticate()
    service = build('drive', 'v3', credentials=creds)
    file_metadata = {
        'name': os.path.basename(file_path),
        'parents': [PARENT_FOLDER_ID]
    }
    media = MediaFileUpload(file_path, mimetype='application/pdf')
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return file.get('id')  # Return the file ID after upload

def download_file(file_id):
    creds = authenticate()
    service = build('drive', 'v3', credentials=creds)
    
    # Create a request to download the file
    request = service.files().get_media(fileId=file_id)
    file_data = io.BytesIO()  # Use BytesIO to handle the file in memory
    downloader = MediaIoBaseDownload(file_data, request)
    
    done = False
    while not done:
        status, done = downloader.next_chunk()
    
    file_data.seek(0)  # Move to the beginning of the file stream
    return file_data

app = Flask(__name__)

openai.api_key = "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"

# Database configuration
DATABASE_URL = "postgresql://StudySphere_owner:0mxFNCK2OTpP@ep-gentle-sound-a2sptgrr.eu-central-1.aws.neon.tech/StudySphere?sslmode=require"

# Set up SQLAlchemy
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

Base = declarative_base()

# Define a model for summaries
class Summary(Base):
    __tablename__ = 'summaries'
    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    summary = Column(Text, nullable=False)

# Create tables if they don't exist
Base.metadata.create_all(engine)

# Token limit
TOKEN_LIMIT = 7000

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        file = request.files['file']
        if file:
            try:
                # Save file locally temporarily to upload to Google Drive
                pdf_file_path = os.path.join('uploads', file.filename)
                file.save(pdf_file_path)

                # Upload file to Google Drive
                google_drive_file_id = upload_file(pdf_file_path)

                # Delete the local file after upload
                os.remove(pdf_file_path)

                # Download the file from Google Drive
                file_data = download_file(google_drive_file_id)

                # Use PyPDF2 to read the file from memory
                pdf_reader = PyPDF2.PdfReader(file_data)
                total_tokens = 0
                pdf_text = ""

                for page_num in range(len(pdf_reader.pages)):
                    page_text = pdf_reader.pages[page_num].extract_text()
                    total_tokens += len(page_text.split())
                    pdf_text += page_text.lower()

                # Check token limit
                if total_tokens > TOKEN_LIMIT:
                    return render_template('index.html', error="File is too large")

                # Call OpenAI API to summarize text
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You are a helpful research assistant."},
                        {"role": "user", "content": f"Summarize this: {pdf_text}"},
                    ],
                )

                summary = response["choices"][0]["message"]["content"]

                # Save the summary to the database with error handling
                retries = 3
                while retries > 0:
                    try:
                        new_summary = Summary(filename=file.filename, summary=summary)
                        session.add(new_summary)
                        session.commit()
                        break
                    except OperationalError as e:
                        session.rollback()
                        retries -= 1
                        time.sleep(2)  # Wait and retry
                        if retries == 0:
                            raise e  # Reraise the exception if all retries failed

                return render_template('index.html', summary=summary, drive_file_id=google_drive_file_id)

            except Exception as e:
                session.rollback()  # Ensure rollback on any unhandled exception
                return render_template('index.html', error=f"An error occurred: {str(e)}")

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0')