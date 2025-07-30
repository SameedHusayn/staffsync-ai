tools = [
    {
        "type": "function",
        "name": "get_employee_balance",
        "description": "Return the remaining annual, sick, and casual leave days for the given employee.",
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
        "description": "Return basic directory information for an employee (name, email, lead).",
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
        "description": "Fetch leave‑request logs. If employee_id is omitted, all logs are returned.",
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
        "description": "Increment or decrement a particular type of leave balance for an employee.",
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
        "description": 'Create a new leave‑request entry (defaults to status "Pending").',
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
]
