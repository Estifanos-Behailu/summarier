from flask import Flask, request, render_template
import PyPDF2
import os
import openai
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

app = Flask(__name__)

openai.api_key = "sk-k3zyHHs9XvVbuAUtGDUoi2khs90H0ZJSvWL1URRNVKT3BlbkFJmUYRkzNevySXzwfKNqt7n-hKu-cU1lngdUhL9kueUA"

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
            pdf_file_path = os.path.join('uploads', file.filename)
            file.save(pdf_file_path)

            # Read the PDF file and count the tokens
            pdf_reader = PyPDF2.PdfReader(pdf_file_path)
            total_tokens = 0
            pdf_text = ""

            for page_num in range(len(pdf_reader.pages)):
                page_text = pdf_reader.pages[page_num].extract_text()
                total_tokens += len(page_text.split())
                pdf_text += page_text.lower()

            # Check token limit
            if total_tokens > TOKEN_LIMIT:
                os.remove(pdf_file_path)
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

            # Save the summary to the database
            new_summary = Summary(filename=file.filename, summary=summary)
            session.add(new_summary)
            session.commit()

            return render_template('index.html', summary=summary)

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=False,host='0.0.0.0')
