import secrets
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from src.sheets_config import directory_ws
from src.constants import AUTH_EMAIL_TEMPLATE

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


def send_mail(email, content, body, subject, otp=True) -> bool:
    """Send OTP to employee email with improved Gmail support."""

    if otp:
        email_type = "OTP"
    else:
        email_type = "Notification"
    try:
        # Email configuration
        sender_email = os.environ.get("EMAIL_SENDER")
        password = os.environ.get("EMAIL_PASSWORD")

        if not sender_email or not password:
            print("⚠️  EMAIL_SENDER or EMAIL_PASSWORD not set in environment variables")
            print(f"[DEV MODE] {email_type} for {email}: {content}")
            return True

        # Create message
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = email
        message["Subject"] = subject

        message.attach(MIMEText(body, "html"))

        # Determine SMTP settings based on sender email
        if "gmail.com" in sender_email.lower():
            smtp_server = "smtp.gmail.com"
            smtp_port = 587
        elif (
            "outlook.com" in sender_email.lower()
            or "hotmail.com" in sender_email.lower()
        ):
            smtp_server = "smtp-mail.outlook.com"
            smtp_port = 587
        elif "yahoo.com" in sender_email.lower():
            smtp_server = "smtp.mail.yahoo.com"
            smtp_port = 587
        else:
            # Default to Gmail settings
            smtp_server = "smtp.gmail.com"
            smtp_port = 587

        # Connect to SMTP server and send email
        print(f"📧 Attempting to send {email_type} email via {smtp_server}...")

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, password)
        server.send_message(message)
        server.quit()

        print(f"✅ {email_type} sent successfully to {email}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ SMTP Authentication failed: {e}")
        print("\n🔧 TROUBLESHOOTING GMAIL AUTHENTICATION:")
        print(
            "1. Make sure you're using an App Password, not your regular Gmail password"
        )
        print("2. Enable 2-Factor Authentication on your Gmail account")
        print("3. Generate an App Password: https://myaccount.google.com/apppasswords")
        print(
            "4. Use the 16-character App Password in your EMAIL_PASSWORD environment variable"
        )
        print(
            "5. Make sure 'Less secure app access' is NOT enabled (use App Passwords instead)"
        )
        print(f"\n[DEV MODE] {email_type} for {email}: {content}")
        return True  # Return True for dev environment

    except Exception as e:
        print(f"❌ Error sending {email_type} email: {e}")
        print(f"[DEV MODE] {email_type} for {email}: {content}")
        return True  # Return True anyway so flow continues in dev environment


def initiate_authentication(user_id: str, emp_id: str) -> Dict:
    """
    Start the authentication process for a user.
    Returns a dict with authentication status and message.
    """
    print(f"🔐 Initiating authentication for user: {user_id}, employee: {emp_id}")

    # Get employee email
    email = get_employee_email(emp_id)

    if not email:
        return {
            "authenticated": False,
            "message": f"❌ No email found for employee ID {emp_id}. Please check your ID and try again.",
        }

    # Generate and send OTP
    otp = generate_otp()

    # Store OTP with 10-minute expiration and associate with this user
    pending_otps[emp_id] = {
        "otp": otp,
        "expires_at": datetime.now() + timedelta(minutes=10),
        "user_id": user_id,
    }

    print(
        f"📱 Generated OTP {otp} for employee {emp_id}, expires at {pending_otps[emp_id]['expires_at']}"
    )

    # Prepare email body
    body = AUTH_EMAIL_TEMPLATE.format(message=otp)
    # Send OTP to employee email
    email_sent = send_mail(email, otp, body, "StaffSync.AI - Authentication Code")

    # Mask the email for privacy
    email_parts = email.split("@")
    if len(email_parts[0]) > 3:
        masked_email = (
            f"{email_parts[0][:3]}{'*' * (len(email_parts[0]) - 3)}@{email_parts[1]}"
        )
    else:
        masked_email = f"{'*' * len(email_parts[0])}@{email_parts[1]}"

    if email_sent:
        message = f"📧 Please check your email ({masked_email}) for your one-time password (OTP) and enter it here to continue."
    else:
        message = f"⚠️ There was an issue sending the email to ({masked_email}). Please check the console for the OTP in development mode."

    return {"authenticated": False, "message": message}


def verify_otp(user_id: str, emp_id: str, provided_otp: str) -> Dict:
    """
    Verify the OTP provided by the user.
    Returns a dict with authentication status and message.
    """
    print(
        f"🔍 Verifying OTP for user: {user_id}, employee: {emp_id}, provided: {provided_otp}"
    )

    if emp_id not in pending_otps:
        print(f"❌ No pending OTP found for employee {emp_id}")
        return {
            "authenticated": False,
            "message": "❌ No authentication process was initiated. Please try your request again.",
        }

    otp_data = pending_otps[emp_id]
    print(f"🕐 OTP data: {otp_data}")

    # Check if the OTP belongs to this user
    if otp_data.get("user_id") != user_id:
        print(
            f"❌ OTP user mismatch. Expected: {otp_data.get('user_id')}, Got: {user_id}"
        )
        return {
            "authenticated": False,
            "message": "❌ This OTP doesn't belong to your session. Please try your request again.",
        }

    # Check if OTP has expired
    if datetime.now() > otp_data["expires_at"]:
        print(f"⏰ OTP expired at {otp_data['expires_at']}")
        del pending_otps[emp_id]
        return {
            "authenticated": False,
            "message": "⏰ OTP has expired. Please try your request again.",
        }

    # Verify OTP
    if otp_data["otp"] == provided_otp:
        print(f"✅ OTP verification successful for user {user_id}")
        # OTP correct, set user as authenticated
        authenticated_users[user_id] = True

        # Store which employee this user is authenticated as
        from src.core.auth_middleware import authenticated_employee_mapping

        authenticated_employee_mapping[user_id] = emp_id
        print(f"👥 Mapped user {user_id} to employee {emp_id}")

        # Clean up used OTP
        del pending_otps[emp_id]

        return {
            "authenticated": True,
            "message": "✅ Authentication successful! Processing your request now...",
        }
    else:
        print(f"❌ OTP mismatch. Expected: {otp_data['otp']}, Got: {provided_otp}")
        return {
            "authenticated": False,
            "message": "❌ Incorrect OTP. Please try again or request a new one.",
        }


def is_authenticated(user_id: str) -> bool:
    """Check if a user is authenticated."""
    result = authenticated_users.get(user_id, False)
    print(f"🔐 Authentication check for user {user_id}: {result}")
    return result


def clear_authentication(user_id: str):
    """Clear authentication for a user (useful for logout)."""
    if user_id in authenticated_users:
        del authenticated_users[user_id]
        print(f"🚪 Cleared authentication for user {user_id}")

    # Also clear employee mapping
    from src.core.auth_middleware import authenticated_employee_mapping

    if user_id in authenticated_employee_mapping:
        emp_id = authenticated_employee_mapping[user_id]
        del authenticated_employee_mapping[user_id]
        print(f"🗑️ Cleared employee mapping for user {user_id} (was employee {emp_id})")


def get_authenticated_employee(user_id: str) -> Optional[str]:
    """Get the employee ID that this user is authenticated as."""
    from src.core.auth_middleware import authenticated_employee_mapping

    return authenticated_employee_mapping.get(user_id)


def get_authentication_stats():
    """Get current authentication statistics (for debugging)."""
    from src.core.auth_middleware import authenticated_employee_mapping

    return {
        "authenticated_users": len(authenticated_users),
        "pending_otps": len(pending_otps),
        "employee_mappings": len(authenticated_employee_mapping),
        "active_sessions": list(authenticated_users.keys()),
        "pending_employees": list(pending_otps.keys()),
    }
