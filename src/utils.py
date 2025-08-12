import datetime
import os
import json
from .core.auth_middleware import authenticate_function_call, pending_function_calls
from .core.auth import send_mail
from .sheets_config import balance_ws, directory_ws, logs_ws
from .constants import LEAVE_REQUEST_TEMPLATE, LEAVE_STATUS_EMAIL_TEMPLATE
from .hr_policy_vault import (
    search_policy,
    load_policies,
    get_or_create_policy_collection,
)

hr_docs = get_or_create_policy_collection()
load_policies(hr_docs)


def get_employee_balance(employee_id):
    """
    Get leave balances for a specific employee.

    Args:
        employee_id: The employee's ID

    Returns:
        dict: Employee's leave balances or None if employee not found
    """
    print("Called get_employee_balance with employee_id:", employee_id)
    balance_data = balance_ws.get_all_records()
    print("Fetched balance data:", balance_data)
    for record in balance_data:
        if str(record["Employee ID"]) == str(employee_id):
            return {
                "Annual Leave": record["Annual Leave"],
                "Sick Leave": record["Sick Leave"],
                "Casual Leave": record["Casual Leave"],
                "Message": "You currently have {} Annual Leave(s), {} Sick Leave(s), and {} Casual Leave(s).".format(
                    record["Annual Leave"],
                    record["Sick Leave"],
                    record["Casual Leave"],
                ),
            }

    return None  # Employee not found


def get_employee_info(employee_id):
    """
    Get employee information including their lead.

    Args:
        employee_id: The employee's ID

    Returns:
        dict: Employee's information or None if employee not found
    """
    directory_data = directory_ws.get_all_records()

    for record in directory_data:
        if str(record["Employee ID"]) == str(employee_id):
            return {
                "name": record["Name"],
                "email": record["Email"],
                "lead": record["Lead"],
            }

    return None  # Employee not found


def get_employee_logs(employee_id=None):
    """
    Get leave logs for a specific employee or all logs if employee_id is None.

    Args:
        employee_id: The employee's ID (optional)

    Returns:
        list: Employee's leave logs
    """
    logs_data = logs_ws.get_all_records()

    if employee_id:
        return [log for log in logs_data if str(log["Employee ID"]) == str(employee_id)]
    else:
        return logs_data


def update_leave_balance(employee_id, leave_type, days_change):
    """
    Update an employee's leave balance.

    Args:
        employee_id: The employee's ID
        leave_type: Type of leave ("Annual Leave", "Sick Leave", or "Casual Leave")
        days_change: Number of days to add (positive) or subtract (negative)

    Returns:
        bool: True if successful, False if employee not found
    """
    # Find the employee row
    all_balances = balance_ws.get_all_records()
    employee_row = None

    for i, record in enumerate(all_balances):
        if str(record["Employee ID"]) == str(employee_id):
            # Add 2 for header row and zero-indexing
            employee_row = i + 2
            current_balance = record[leave_type]
            break

    if not employee_row:
        return "Employee Not Found"  # Employee not found

    # Update the balance
    new_balance = current_balance + days_change

    # Find the column index
    headers = balance_ws.row_values(1)
    col_index = headers.index(leave_type) + 1

    # Update the cell
    balance_ws.update_cell(employee_row, col_index, new_balance)
    return "Leave balance updated successfully"


def add_leave_log(
    employee_id, leave_type, days, start_date, end_date, status="Pending"
):
    """
    Add a new leave request log.

    Args:
        employee_id: The employee's ID
        leave_type: Type of leave
        days: Number of days requested
        start_date: Start date of leave
        end_date: End date of leave
        status: Status of the request (default "Pending")

    Returns:
        int: The new request ID
    """

    leaves_balance = get_employee_balance(employee_id)
    if not leaves_balance:
        print(f"Employee ID {employee_id} not found or has no leave balance.")
        return {
            "Message": f"Employee ID {employee_id} not found or has no leave balance."
        }

    if leaves_balance[leave_type] < days:
        print(
            f"Insufficient {leave_type} balance for employee ID {employee_id}. Available: {leaves_balance[leave_type]}, Requested: {days}."
        )
        return {
            "Message": f"Insufficient {leave_type} balance for employee ID {employee_id}. Available: {leaves_balance[leave_type]}, Requested: {days}."
        }

    employee_info = get_employee_info(employee_id)
    employee_name = employee_info["name"]
    # Generate a new request ID
    logs_data = logs_ws.get_all_records()
    if logs_data:
        new_request_id = max([int(log.get("Request ID", 0)) for log in logs_data]) + 1
    else:
        new_request_id = 1

    # Create the new log entry
    submitted_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_row = [
        new_request_id,
        employee_id,
        employee_name,
        leave_type,
        days,
        start_date,
        end_date,
        status,
        submitted_at,
        "",  # Approved By (empty for new requests)
        "",  # Approval Date (empty for new requests)
    ]

    # Append to the sheet
    logs_ws.append_row(new_row)

    email_body = LEAVE_REQUEST_TEMPLATE.format(
        employee_name=employee_name,
        request_id=new_request_id,
        leave_type=leave_type,
        days=days,
        start_date=start_date,
        end_date=end_date,
        submitted_at=submitted_at,
    )

    email_sent = send_mail(
        employee_info["lead"],
        f"New Leave Request #{new_request_id}",
        email_body,
        f"StaffSync.AI - New Leave Request #{new_request_id}",
        otp=False,
    )

    if email_sent:
        print(
            f"✅ Email sent to LEAD: {employee_info['lead']} for new leave request #{new_request_id}"
        )
        return {
            "Message": f"{new_request_id} - Leave request added successfully and email sent to employee's lead."
        }
    else:
        print(f"⚠️ Failed to send email for new leave request #{new_request_id}")
        return {
            "Message": f"{new_request_id} - Leave request added successfully, but email notification failed."
        }


def update_leave_log_status(request_id, new_status, approved_by=None):
    """
    Update the status of a leave request.

    Args:
        request_id: The request ID to update
        new_status: New status ("Approved", "Rejected", etc.)
        approved_by: Name of the person who approved/rejected

    Returns:
        bool: True if successful, False if request not found
    """
    logs_data = logs_ws.get_all_records()

    # Find the request
    for i, log in enumerate(logs_data):
        if int(log["Request ID"]) == int(request_id):
            row_num = i + 2  # Adjust for header and zero-indexing

            employee_name = log["Employee Name"]
            employee_id = log["Employee ID"]
            # Update status
            logs_ws.update_cell(row_num, 8, new_status)

            # Update approver info if provided
            if approved_by:
                logs_ws.update_cell(row_num, 10, approved_by)  # Approved By
                approval_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logs_ws.update_cell(row_num, 11, approval_date)  # Approval Date

            if new_status.lower() == "approved":
                # Update leave balance
                leave_type = log["Leave Type"]
                days = log["Days"]
                update_leave_balance(employee_id, leave_type, -days)
            elif new_status.lower() == "rejected":
                # No balance update needed for rejection
                pass
            print(f"✅ Request {request_id} updated to {new_status}")

            try:
                email_body = LEAVE_STATUS_EMAIL_TEMPLATE.format(
                    employee_name=employee_name,
                    request_id=request_id,
                    new_status=new_status.lower(),
                    approved_by=approved_by,
                )
                employee_info = get_employee_info(employee_id)

                to_addr = employee_info["email"]  # ← match the real key
                subject = f"Leave status {new_status} - Request #{request_id}"
                # Send email notification
                email_sent = send_mail(
                    to_addr,
                    subject,
                    email_body,
                    f"StaffSync.AI - {subject}",
                    otp=False,
                )
                if email_sent:
                    print(
                        f"✅ Email sent to employee: {to_addr} for request #{request_id}"
                    )
                    return True
                else:
                    print(f"⚠️ Failed to send email for request #{request_id}")
                    return False
            except Exception as e:
                print(
                    f"⚠️ Error updating leave log status for request #{request_id}: {e}"
                )

    return False  # Request not found


def file_search(query_text):
    contextful_message = search_policy(
        query_text, n_results=3, collection=hr_docs, extract_relevant=True
    )

    if contextful_message:
        context_text = "\n".join(
            [f"{doc} (from {meta['source']})" for doc, meta in contextful_message]
        )
        user_message_with_context = f"{query_text}\n\nContext:\n{context_text}"
    else:
        user_message_with_context = query_text
    return user_message_with_context


def infer_imap(host_email: str) -> tuple[str, int]:
    host_email = host_email.lower()
    if host_email.endswith("@gmail.com") or host_email.endswith("@googlemail.com"):
        return "imap.gmail.com", 993
    elif host_email.endswith(("@outlook.com", "@hotmail.com", "@live.com")):
        return "outlook.office365.com", 993  # modern Outlook IMAP
    elif host_email.endswith("@yahoo.com"):
        return "imap.mail.yahoo.com", 993
    else:  # fallback: let user supply
        env_host = os.getenv("EMAIL_IMAP_SERVER")
        return env_host or "imap.gmail.com", int(os.getenv("EMAIL_IMAP_PORT", 993))


def first_visible_line(msg) -> str:
    """Return the first non-quoted, non-blank line (plain-text > HTML). This function is utilized for watching the inbox."""
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            body = part.get_payload(decode=True).decode(
                part.get_content_charset() or "utf-8", "ignore"
            )
            break
        if part.get_content_type() == "text/html":
            import bs4, html

            html_body = part.get_payload(decode=True).decode(
                part.get_content_charset() or "utf-8", "ignore"
            )
            body = bs4.BeautifulSoup(html_body, "html.parser").get_text()
            break
    else:
        return ""

    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith((">", "|")):
            return line
    return ""


function_map = {
    "get_employee_balance": get_employee_balance,
    "add_leave_log": add_leave_log,
    "file_search": file_search,
}


def call_function(name, raw_args, user_id):
    """Call a function with authentication check."""
    try:
        args = json.loads(raw_args)
        func = function_map.get(name)

        # Check if authentication is required
        auth_message = authenticate_function_call(user_id, "", name, args)
        if auth_message:
            # Authentication required or in progress - return the message instead of calling function
            return {"message": auth_message, "auth_required": True}

        # User is authenticated or function doesn't require authentication
        if func:
            result = func(**args)
            message = result["Message"]
            # If there's a pending function call for this user, clear it
            if user_id in pending_function_calls:
                del pending_function_calls[user_id]

            return message
    except Exception as e:
        print(f"Error calling function {name}: {e}")
        return {
            "message": f"❌ Error calling function '{name}': {str(e)}",
            "auth_required": False,
        }
