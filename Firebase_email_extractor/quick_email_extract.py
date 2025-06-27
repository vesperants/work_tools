import firebase_admin
from firebase_admin import credentials, firestore
import os
import json
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables explicitly
# This makes sure the script finds the .env file in the project root.
dotenv_path = Path('.') / '.env'
load_dotenv(dotenv_path=dotenv_path)

# Initialize Firebase using a path from .env
# Storing the full JSON in an env var can corrupt the private key's newlines.
# It's safer to store the file path instead.
service_account_path = os.getenv('FIRE_SERVICE_ACCOUNT_PATH')
if not service_account_path or not os.path.exists(service_account_path):
    raise ValueError(
        "Please create a .env file and set FIRE_SERVICE_ACCOUNT_PATH to the valid path of your Firebase service account JSON file."
    )

cred = credentials.Certificate(service_account_path)
firebase_admin.initialize_app(cred)
db = firestore.client()

# Quick email extraction
users_ref = db.collection('users')
docs = users_ref.stream()

emails = []
for doc in docs:
    data = doc.to_dict()
    if 'email' in data and data['email']:
        emails.append(data['email'])

# Print comma-separated list (ready to copy-paste)
print("Copy this for your email client:")
print('; '.join(emails))

print(f"\nTotal emails: {len(emails)}")