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

# Store which employee ID each user is authenticated as
# Format: {user_id: employee_id}
authenticated_employee_mapping = {}


def extract_otp_from_message(message: str) -> Optional[str]:
    """Extract a 6-digit OTP from a message."""
    # Look for exactly 6 consecutive digits
    match = re.search(r"\b\d{6}\b", message)
    if match:
        return match.group(0)
    return None


def find_pending_emp_id_for_user(user_id: str) -> Optional[str]:
    """Find the employee ID associated with a pending OTP verification for this user."""
    print(f"🔍 Looking for pending OTP for user: {user_id}")
    print(f"📋 Current pending_otps: {pending_otps}")

    for emp_id, otp_data in pending_otps.items():
        if otp_data.get("user_id") == user_id:
            print(f"✅ Found pending OTP for employee {emp_id}")
            return emp_id

    print(f"❌ No pending OTP found for user {user_id}")
    return None


def authenticate_function_call(
    user_id: str, message: str, func_name: str, func_args: Dict
):
    """
    Middleware that handles authentication before allowing function calls.

    Returns:
        None if authentication is successful or not required
        str if authentication is required or in progress
    """
    print(f"🛡️ Authentication check for user: {user_id}, function: {func_name}")

    # Functions that don't require authentication
    non_auth_functions = {
        # Add any functions that don't need authentication
        # For now, all HR functions require authentication
        "file_search",
    }

    if func_name in non_auth_functions:
        print(f"✅ Function {func_name} doesn't require authentication")
        return None

    # Get the employee ID being requested
    requested_emp_id = func_args.get("employee_id")
    if not requested_emp_id:
        return "🆔 Please provide your employee ID to proceed with this request."

    # Check if user is already authenticated
    if is_authenticated(user_id):
        print(f"✅ User {user_id} is authenticated")

        # Check if they're authorized to access this specific employee's data
        # For now, users can only access their own data
        if user_id in authenticated_employee_mapping:
            authenticated_emp_id = authenticated_employee_mapping[user_id]
            if str(authenticated_emp_id) == str(requested_emp_id):
                print(f"✅ User authorized to access employee {requested_emp_id} data")
                return None
            else:
                print(
                    f"❌ User authenticated as employee {authenticated_emp_id} but trying to access employee {requested_emp_id}"
                )
                return f"🚫 Access denied. You can only access your own employee data. You are authenticated as employee {authenticated_emp_id}."
        else:
            print(f"❌ User {user_id} authenticated but no employee mapping found")
            return "🔐 Authentication mapping error. Please re-authenticate."

    print(f"🔐 User {user_id} needs authentication for {func_name}")

    # User needs authentication - save the function call for later
    pending_function_calls[user_id] = {
        "func_name": func_name,
        "func_args": func_args,
        "emp_id": requested_emp_id,
    }

    print(
        f"💾 Stored pending function call for user {user_id}: {pending_function_calls[user_id]}"
    )

    # Start authentication process
    auth_result = initiate_authentication(user_id, requested_emp_id)
    return auth_result["message"]


def clear_pending_call(user_id: str):
    """Clear any pending function call for a user."""
    if user_id in pending_function_calls:
        del pending_function_calls[user_id]
        print(f"🗑️ Cleared pending function call for user {user_id}")


def get_pending_call(user_id: str) -> Optional[Dict]:
    """Get the pending function call for a user."""
    return pending_function_calls.get(user_id)


def get_authenticated_employee_id(user_id: str) -> Optional[str]:
    """Get the employee ID that this user is authenticated as."""
    return authenticated_employee_mapping.get(user_id)


def debug_auth_state():
    """Print current authentication state for debugging."""
    print("\n📊 AUTHENTICATION DEBUG STATE:")
    print(f"🔐 Authenticated users: {len(authenticated_employee_mapping)}")
    print(f"📱 Pending OTPs: {len(pending_otps)}")
    print(f"⏳ Pending function calls: {len(pending_function_calls)}")

    if authenticated_employee_mapping:
        print("👥 Employee mappings:")
        for user_id, emp_id in authenticated_employee_mapping.items():
            print(f"  - User {user_id[:8]}... → Employee {emp_id}")

    if pending_otps:
        print("📋 Pending OTP details:")
        for emp_id, data in pending_otps.items():
            print(
                f"  - Employee {emp_id}: User {data.get('user_id', 'N/A')[:8]}..., expires {data.get('expires_at')}"
            )

    if pending_function_calls:
        print("🔄 Pending function calls:")
        for user_id, call_data in pending_function_calls.items():
            print(
                f"  - User {user_id[:8]}...: {call_data.get('func_name')} for employee {call_data.get('emp_id')}"
            )

    print("=" * 50)


# Enhanced message processing
def process_auth_message(user_id: str, message: str) -> Optional[Dict]:
    """
    Process a message that might contain authentication information.

    Returns:
        None if no authentication action needed
        Dict with auth result if authentication was processed
    """
    # Check if message contains OTP
    otp = extract_otp_from_message(message)

    if otp:
        print(f"🔢 Extracted OTP: {otp} from message: '{message}'")

        # Find associated employee ID
        emp_id = find_pending_emp_id_for_user(user_id)

        if emp_id:
            # Verify the OTP
            result = verify_otp(user_id, emp_id, otp)

            if result["authenticated"]:
                print(f"✅ OTP verification successful for user {user_id}")

                # Check if there's a pending function call
                pending_call = get_pending_call(user_id)

                return {
                    "authenticated": True,
                    "message": result["message"],
                    "pending_call": pending_call,
                }
            else:
                print(
                    f"❌ OTP verification failed for user {user_id}: {result['message']}"
                )
                return {
                    "authenticated": False,
                    "message": result["message"],
                    "pending_call": None,
                }
        else:
            print(f"❌ No pending authentication found for user {user_id}")
            return {
                "authenticated": False,
                "message": "❌ No authentication process was initiated. Please make a request that requires authentication first.",
                "pending_call": None,
            }

    return None


# Utility functions for session management
def cleanup_expired_sessions():
    """Clean up expired OTP sessions and stale function calls."""
    from datetime import datetime

    # Clean up expired OTPs
    expired_otps = []
    for emp_id, otp_data in pending_otps.items():
        if datetime.now() > otp_data["expires_at"]:
            expired_otps.append(emp_id)

    for emp_id in expired_otps:
        user_id = pending_otps[emp_id]["user_id"]
        del pending_otps[emp_id]
        # Also clear associated pending function call
        clear_pending_call(user_id)
        print(f"🧹 Cleaned up expired OTP for employee {emp_id}, user {user_id}")


def get_auth_stats() -> Dict:
    """Get current authentication statistics."""
    return {
        "pending_otps": len(pending_otps),
        "pending_calls": len(pending_function_calls),
        "authenticated_employees": len(authenticated_employee_mapping),
        "otp_employees": list(pending_otps.keys()),
        "pending_users": list(pending_function_calls.keys()),
        "employee_mappings": dict(authenticated_employee_mapping),
    }
