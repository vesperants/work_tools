import firebase_admin
from firebase_admin import credentials, auth
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
dotenv_path = Path('.') / '.env'
load_dotenv(dotenv_path=dotenv_path)

# Initialize Firebase
service_account_path = os.getenv('FIRE_SERVICE_ACCOUNT_PATH')
if not service_account_path or not os.path.exists(service_account_path):
    raise ValueError(
        "Please ensure your .env file has a valid FIRE_SERVICE_ACCOUNT_PATH."
    )

cred = credentials.Certificate(service_account_path)
firebase_admin.initialize_app(cred)

# Get emails from Firebase Authentication
emails = []
try:
    # Iterate through all users
    for user in auth.list_users().iterate_all():
        if user.email:
            emails.append(user.email)

    # Print comma-separated list
    print("Copy this for your email client:")
    print('; '.join(emails))
    print(f"\nTotal emails: {len(emails)}")

except Exception as e:
    print(f"An error occurred: {e}")
    print("Please ensure your service account has the 'Firebase Authentication Admin' role in IAM.") 