system_call = """You are Avy, an HR assistant for StaffSync.AI. You help employees with leave requests, balance inquiries, and HR policy questions. You can also search HR policy documents for relevant information. Today's date is {date}."""

tools = [
    {
        "type": "function",
        "name": "get_employee_balance",
        "description": "Return the remaining annual, sick, and casual leave days for the given employee. Make sure user has provided required parameters.",
        "parameters": {
            "type": "object",
            "properties": {
                "employee_id": {
                    "type": "string",
                    "description": 'The employee’s unique ID (e.g. "113654").',
                }
            },
            "required": ["employee_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_employee_info",
        "description": "Return basic directory information for an employee (name, email, lead).  Make sure user has provided required parameters.",
        "parameters": {
            "type": "object",
            "properties": {
                "employee_id": {
                    "type": "string",
                    "description": "The employee’s unique ID.",
                }
            },
            "required": ["employee_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_employee_logs",
        "description": "Fetch leave‑request logs. If employee_id is omitted, all logs are returned. ",
        "parameters": {
            "type": "object",
            "properties": {
                "employee_id": {
                    "type": "string",
                    "description": "The employee’s unique ID (optional).",
                }
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "update_leave_balance",
        "description": "Increment or decrement a particular type of leave balance for an employee.  Make sure user has provided required parameters.",
        "parameters": {
            "type": "object",
            "properties": {
                "employee_id": {
                    "type": "string",
                    "description": "The employee’s unique ID.",
                },
                "leave_type": {
                    "type": "string",
                    "enum": ["Annual Leave", "Sick Leave", "Casual Leave"],
                    "description": "Type of leave to adjust.",
                },
                "days_change": {
                    "type": "number",
                    "description": "Days to add (positive) or subtract (negative).",
                },
            },
            "required": ["employee_id", "leave_type", "days_change"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "add_leave_log",
        "description": 'Create a new leave‑request entry (defaults to status "Pending").  Make sure user has provided required parameters.',
        "parameters": {
            "type": "object",
            "properties": {
                "employee_id": {
                    "type": "string",
                    "description": "The employee’s unique ID.",
                },
                "leave_type": {
                    "type": "string",
                    "enum": ["Annual Leave", "Sick Leave", "Casual Leave"],
                    "description": "Type of leave being requested.",
                },
                "days": {
                    "type": "number",
                    "description": "Total leave days requested.",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date of leave (YYYY‑MM‑DD).",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date of leave (YYYY‑MM‑DD).",
                },
                "status": {
                    "type": "string",
                    "enum": ["Pending", "Approved", "Rejected"],
                    "description": "Initial status of the request (optional).",
                },
            },
            "required": ["employee_id", "leave_type", "days", "start_date", "end_date"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "update_leave_log_status",
        "description": "Change the status of an existing leave request and optionally record the approver.",
        "parameters": {
            "type": "object",
            "properties": {
                "request_id": {
                    "type": "integer",
                    "description": "The numeric ID of the leave request.",
                },
                "new_status": {
                    "type": "string",
                    "enum": ["Approved", "Rejected", "Pending", "Cancelled"],
                    "description": "The status to apply.",
                },
                "approved_by": {
                    "type": "string",
                    "description": "Name or identifier of the approver/rejecter (optional).",
                },
            },
            "required": ["request_id", "new_status"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "file_search",
        "description": "Search HR policy documents for relevant information. If you think user has asked a question about company policies, use this tool to find relevant documents.",
        "parameters": {
            "type": "object",
            "properties": {
                "query_text": {
                    "type": "string",
                    "description": "The text to search for in policy documents.",
                }
            },
            "required": ["query_text"],
            "additionalProperties": False,
        },
    },
]

LEAVE_REQUEST_TEMPLATE = """
<html>
  <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f5f5f5;">
    <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
      <!-- Header -->
      <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="color: #333; margin: 0;">📅 StaffSync.AI</h1>
        <h2 style="color: #666; font-weight: normal; margin: 10px 0;">New Leave Request</h2>
      </div>

      <!-- Greeting -->
      <p style="color: #555; font-size: 16px; line-height: 1.5;">
        Hi,
      </p>
      <p style="color: #555; font-size: 16px; line-height: 1.5;">
        <strong>{employee_name}</strong> has submitted a leave request. Below are the details:
      </p>

      <!-- Leave Details Box -->
      <div style="background: #fafafa; padding: 20px; border-radius: 8px; border: 1px solid #e0e0e0; margin: 25px 0;">
        <table style="width: 100%; font-size: 15px;">
          <tr>
            <td style="padding: 8px 0;"><strong>Request&nbsp;ID:</strong></td>
            <td style="padding: 8px 0;">{request_id}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0;"><strong>Leave&nbsp;Type:</strong></td>
            <td style="padding: 8px 0;">{leave_type}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0;"><strong>Duration:</strong></td>
            <td style="padding: 8px 0;">{days} day(s)</td>
          </tr>
          <tr>
            <td style="padding: 8px 0;"><strong>Start&nbsp;Date:</strong></td>
            <td style="padding: 8px 0;">{start_date}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0;"><strong>End&nbsp;Date:</strong></td>
            <td style="padding: 8px 0;">{end_date}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0;"><strong>Submitted&nbsp;At:</strong></td>
            <td style="padding: 8px 0;">{submitted_at}</td>
          </tr>
        </table>
      </div>

      <p style="color: #555; font-size: 14px; line-height: 1.5; margin-top: 0;">
        <strong>To approve</strong> this request, reply with Y on the first line.<br>
        <strong>To reject</strong> it, reply with N on the first line.
      </p>

      <!-- Footer -->
      <hr style="border: none; border-top: 1px solid #eee; margin: 25px 0;">
      <p style="color: #999; font-size: 12px; text-align: center; margin: 0;">
        Thank you,<br>
        <strong>StaffSync.AI Team</strong>
      </p>
    </div>
  </body>
</html>
"""

AUTH_EMAIL_TEMPLATE = """
<html>
    <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f5f5f5;">
    <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
        <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="color: #333; margin: 0;">🔐 StaffSync.AI</h1>
        <h2 style="color: #666; font-weight: normal; margin: 10px 0;">Authentication Code</h2>
        </div>
        
        <p style="color: #555; font-size: 16px; line-height: 1.5;">
        You've requested to authenticate with StaffSync.AI. Please use the following verification code:
        </p>
        
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 25px; border-radius: 8px; margin: 25px 0; text-align: center;">
        <div style="background-color: white; display: inline-block; padding: 15px 25px; border-radius: 6px;">
            <h1 style="margin: 0; color: #333; letter-spacing: 8px; font-family: 'Courier New', monospace;">{message}</h1>
        </div>
        </div>
        
        <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 6px; margin: 20px 0;">
        <p style="margin: 0; color: #856404; font-size: 14px;">
            ⏰ This code will expire in <strong>10 minutes</strong>
        </p>
        </div>
        
        <p style="color: #666; font-size: 14px; line-height: 1.5;">
        If you didn't request this code, please ignore this email. For security reasons, never share this code with anyone.
        </p>
        
        <hr style="border: none; border-top: 1px solid #eee; margin: 25px 0;">
        
        <p style="color: #999; font-size: 12px; text-align: center; margin: 0;">
        Thank you,<br>
        <strong>StaffSync.AI Team</strong>
        </p>
    </div>
    </body>
</html>
"""
