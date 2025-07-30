import datetime
from sheets_config import balance_ws, directory_ws, logs_ws
from openai import OpenAI
import os
from dotenv import load_dotenv
import json
from constants import tools

load_dotenv()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY is not set. "
        "Copy .env.example → .env and put your OpenAI API key."
    )

client = OpenAI(api_key=OPENAI_API_KEY)


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
                "annual_leave": record["Annual Leave"],
                "sick_leave": record["Sick Leave"],
                "casual_leave": record["Casual Leave"],
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
        return False  # Employee not found

    # Update the balance
    new_balance = current_balance + days_change

    # Find the column index
    headers = balance_ws.row_values(1)
    col_index = headers.index(leave_type) + 1

    # Update the cell
    balance_ws.update_cell(employee_row, col_index, new_balance)
    return True


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

    return new_request_id


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

            # Update status
            logs_ws.update_cell(row_num, 7, new_status)

            # Update approver info if provided
            if approved_by:
                logs_ws.update_cell(row_num, 9, approved_by)  # Approved By
                approval_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logs_ws.update_cell(row_num, 10, approval_date)  # Approval Date

            return True

    return False  # Request not found


function_map = {
    "get_employee_balance": get_employee_balance,
    "get_employee_info": get_employee_info,
    "get_employee_logs": get_employee_logs,
    "update_leave_balance": update_leave_balance,
    "add_leave_log": add_leave_log,
    "update_leave_log_status": update_leave_log_status,
}


def call_function(name, raw_args):
    args = json.loads(raw_args)
    func = function_map.get(name)
    if func:
        return func(**args)
    raise ValueError(f"Function '{name}' not recognized.")


def generate_response(input_messages, tools=tools):
    response = client.responses.create(
        model="gpt-4.1", input=input_messages, tools=tools
    )
    return response
