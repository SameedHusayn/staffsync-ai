import os
from dotenv import load_dotenv          
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

load_dotenv()

creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if not creds_path:
    raise RuntimeError(
        "GOOGLE_APPLICATION_CREDENTIALS is not set. "
        "Copy .env.example → .env and put the full path to your JSON key."
    )

creds = Credentials.from_service_account_file(
    creds_path,
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ],
)

gc = gspread.authorize(creds)

balance_wb   = gc.open("StaffSync.AI - Leaves Balance")
directory_wb = gc.open("StaffSync.AI - Employee Directory")
logs_wb      = gc.open("StaffSync.AI - Leaves Logs")

balance_ws   = balance_wb.sheet1
directory_ws = directory_wb.sheet1
logs_ws      = logs_wb.sheet1

print("Connected to Google Sheets successfully!")
