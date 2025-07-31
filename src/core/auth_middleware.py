import re
from typing import Any, Callable, Dict, Optional

from src.core.auth import (
    is_authenticated,
    initiate_authentication,
    verify_otp,
    pending_otps,
)

# Store pending function calls while waiting for OTP
# Format: {user_id: {"func_name": str, "func_args": dict, "emp_id": str}}
pending_function_calls = {}


def extract_otp_from_message(message: str) -> Optional[str]:
    """Extract a 6-digit OTP from a message."""
    match = re.search(r"\b\d{6}\b", message)
    if match:
        return match.group(0)
    return None


def find_pending_emp_id_for_user(user_id: str) -> Optional[str]:
    """Find the employee ID associated with a pending OTP verification for this user."""
    for emp_id, otp_data in pending_otps.items():
        if otp_data.get("user_id") == user_id:
            return emp_id
    return None


def authenticate_function_call(
    user_id: str, message: str, func_name: str, func_args: Dict
):
    """
    Middleware that handles authentication before allowing function calls.
    """
    # Check if user is already authenticated
    if is_authenticated(user_id):
        # Already authenticated, allow function call
        return None

    # Check if there's a pending OTP verification for this user
    otp = extract_otp_from_message(message)
    if otp:
        # User is providing OTP, try to verify it
        emp_id = find_pending_emp_id_for_user(user_id)
        if emp_id:
            result = verify_otp(user_id, emp_id, otp)
            if result["authenticated"]:
                # Authentication successful
                return result["message"]
            else:
                # Failed verification, return error
                return result["message"]

    # No OTP in message or no pending verification, we need to initiate authentication
    # Save the function call for later
    emp_id = func_args.get("employee_id")

    if not emp_id:
        return "Please provide your employee ID to proceed."

    # Store pending function call
    pending_function_calls[user_id] = {
        "func_name": func_name,
        "func_args": func_args,
        "emp_id": emp_id,
    }

    # Start authentication process
    auth_result = initiate_authentication(user_id, emp_id)
    return auth_result["message"]
