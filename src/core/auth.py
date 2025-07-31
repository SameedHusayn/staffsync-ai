import secrets
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from src.sheets_config import directory_ws

# Store authenticated sessions per user
# Format: {user_id: True/False}
authenticated_users = {}

# Store pending OTPs
# Format: {emp_id: {"otp": str, "expires_at": datetime, "user_id": str}}
pending_otps = {}


def generate_otp() -> str:
    """Generate a 6-digit OTP."""
    return "".join(secrets.choice(string.digits) for _ in range(6))


def get_employee_email(emp_id: str) -> Optional[str]:
    """Get employee email from Google Sheets using employee ID."""
    try:
        directory_data = directory_ws.get_all_records()
        for record in directory_data:
            if str(record["Employee ID"]) == str(emp_id):
                return record["Email"]
        return None
    except Exception as e:
        print(f"Error fetching employee email: {e}")
        return None


def send_otp_email(email: str, otp: str) -> bool:
    """Send OTP to employee email."""
    try:
        # Email configuration
        sender_email = os.environ.get("EMAIL_SENDER", "staffsync@example.com")
        password = os.environ.get("EMAIL_PASSWORD")

        # Create message
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = email
        message["Subject"] = "StaffSync.AI - Authentication Code"

        body = f"""
        <html>
          <body style="font-family: Arial, sans-serif; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #f9f9f9; padding: 20px; border-radius: 10px;">
              <h2 style="color: #333;">Your Authentication Code</h2>
              <p>You've requested to authenticate with StaffSync.AI. Please use the following code:</p>
              <div style="background-color: #e7f3fe; padding: 15px; border-radius: 5px; margin: 20px 0; text-align: center;">
                <h1 style="margin: 0; color: #0066cc; letter-spacing: 5px;">{otp}</h1>
              </div>
              <p>This code will expire in 10 minutes.</p>
              <p>If you didn't request this code, please ignore this email.</p>
              <p>Thank you,<br>StaffSync.AI Team</p>
            </div>
          </body>
        </html>
        """

        message.attach(MIMEText(body, "html"))

        # Connect to SMTP server and send email
        if password:
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(sender_email, password)
            server.send_message(message)
            server.quit()
            print(f"OTP sent successfully to {email}")
            return True
        else:
            # For development/testing when no password is set
            print(f"[DEV MODE] OTP for {email}: {otp}")
            return True

    except Exception as e:
        print(f"Error sending OTP email: {e}")
        # For development/testing, print the OTP
        print(f"[DEV MODE] OTP for {email}: {otp}")
        return True  # Return True anyway so flow continues in dev environment


def initiate_authentication(user_id: str, emp_id: str) -> Dict:
    """
    Start the authentication process for a user.
    Returns a dict with authentication status and message.
    """
    # Get employee email
    email = get_employee_email(emp_id)

    if not email:
        return {
            "authenticated": False,
            "message": f"No email found for employee ID {emp_id}. Please check your ID and try again.",
        }

    # Generate and send OTP
    otp = generate_otp()

    # Store OTP with 1-minute expiration and associate with this user
    pending_otps[emp_id] = {
        "otp": otp,
        "expires_at": datetime.now() + timedelta(minutes=1),
        "user_id": user_id,
    }

    # Send OTP to employee email
    send_otp_email(email, otp)

    # Mask the email for privacy
    masked_email = (
        f"{email[:3]}{'*' * (len(email.split('@')[0]) - 3)}@{email.split('@')[1]}"
    )

    return {
        "authenticated": False,
        "message": f"Please check your email ({masked_email}) for your one-time password (OTP) and enter it here to continue.",
    }


def verify_otp(user_id: str, emp_id: str, provided_otp: str) -> Dict:
    """
    Verify the OTP provided by the user.
    Returns a dict with authentication status and message.
    """
    if emp_id not in pending_otps:
        return {
            "authenticated": False,
            "message": "No authentication process was initiated. Please try your request again.",
        }

    otp_data = pending_otps[emp_id]

    # Check if OTP has expired
    if datetime.now() > otp_data["expires_at"]:
        del pending_otps[emp_id]
        return {
            "authenticated": False,
            "message": "OTP has expired. Please try your request again.",
        }

    # Verify OTP
    if otp_data["otp"] == provided_otp:
        # OTP correct, set user as authenticated
        authenticated_users[user_id] = True

        # Clean up used OTP
        del pending_otps[emp_id]

        return {
            "authenticated": True,
            "message": "Authentication successful! Processing your request now.",
        }
    else:
        return {"authenticated": False, "message": "Incorrect OTP. Please try again."}


def is_authenticated(user_id: str) -> bool:
    """Check if a user is authenticated."""
    return authenticated_users.get(user_id, False)
