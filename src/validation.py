from typing import Annotated, Literal, Union, Optional, List, Dict, Any
from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)
import re, json, textwrap, time
from datetime import datetime, timedelta


#  Constrained types and validators
def validate_employee_id(v: str) -> str:
    """Validate employee ID is not a placeholder."""
    v = v.strip()
    # Check if it's a placeholder or generic text
    placeholders = [
        "your_employee_id",
        "employee_id",
        "your employee id",
        "employee id",
    ]
    if v.lower() in placeholders:
        raise ValueError("Please provide an actual employee ID, not a placeholder.")

    # Allow any non-empty string that's not a placeholder
    # This is more lenient to accept IDs like "1"
    if not v:
        raise ValueError("Employee ID cannot be empty.")

    return v


EmployeeID = Annotated[str, Field(strip_whitespace=True)]
DateYMD = Annotated[str, StringConstraints(pattern=r"\d{4}-\d{2}-\d{2}")]
PositiveDays = Annotated[int, Field(gt=0)]


#  Argument models
class GetEmployeeBalanceArgs(BaseModel):
    employee_id: EmployeeID

    @field_validator("employee_id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        return validate_employee_id(v)


class AddLeaveLogArgs(BaseModel):
    employee_id: EmployeeID
    leave_type: Literal["Annual Leave", "Sick Leave", "Casual Leave"]
    days: PositiveDays
    start_date: DateYMD
    end_date: DateYMD
    status: Literal["Pending", "Approved", "Rejected"] = "Pending"

    @field_validator("employee_id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        return validate_employee_id(v)


class FileSearchArgs(BaseModel):
    query_text: Annotated[str, Field(min_length=3, strip_whitespace=True)]


class ToolCall(BaseModel):
    name: Literal["get_employee_balance", "add_leave_log", "file_search"]
    parameters: Union[
        GetEmployeeBalanceArgs,
        AddLeaveLogArgs,
        FileSearchArgs,
    ]


def first_json_block(text: str) -> str | None:
    """
    Return the first {...} block that json.loads() can parse.
    """
    stack = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if stack == 0:
                start = i
            stack += 1
        elif ch == "}":
            stack -= 1
            if stack == 0 and start is not None:
                candidate = text[start : i + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    continue
    return None


MAX_REPAIR_TRIES = 3  # stop after this many self-fix attempts


# def extract_response(raw_reply):
#     """
#     Extract the text response or tool call from the raw reply.
#     Returns a tuple of (is_tool_call, content)
#     """
#     # Always check for valid JSON block first, regardless of tokens
#     json_blob = first_json_block(raw_reply)
#     if json_blob:
#         try:
#             # Check if it's a valid tool call
#             json_obj = json.loads(json_blob)
#             if "name" in json_obj and "parameters" in json_obj:
#                 return True, json_blob
#         except json.JSONDecodeError:
#             pass

#     # Find the position of special tokens
#     eot_pos = raw_reply.find("<|eot_id|>")
#     eom_pos = raw_reply.find("<|eom_id|>")

#     # Determine which token appears first (if any)
#     if eot_pos >= 0 and (eom_pos < 0 or eot_pos < eom_pos):
#         # Text response ends with eot_id
#         return False, raw_reply[:eot_pos].strip()
#     elif eom_pos >= 0:
#         # Tool call ends with eom_id
#         content = raw_reply[:eom_pos].strip()
#         json_blob = first_json_block(content)
#         if json_blob:
#             return True, json_blob

#     # If we get here, no special tokens or JSON found, treat as regular text
#     return False, raw_reply.strip()


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 3:
            # take the middle block
            s = parts[1 if parts[0] == "" else 2]
    return s.strip()


def _last_json_block(text: str) -> str | None:
    stack, start = 0, None
    last = None
    for i, ch in enumerate(text):
        if ch == "{":
            if stack == 0:
                start = i
            stack += 1
        elif ch == "}":
            stack -= 1
            if stack == 0 and start is not None:
                cand = text[start : i + 1]
                try:
                    json.loads(cand)
                    last = cand  # keep the last valid one
                except json.JSONDecodeError:
                    pass
    return last


def extract_response(raw_reply: str):
    def first_pos(s, token):
        p = s.find(token)
        return p if p >= 0 else None

    # Find first control token (if any)
    eot = first_pos(raw_reply, "<|eot_id|>")
    eom = first_pos(raw_reply, "<|eom_id|>")
    first = min([p for p in [eot, eom] if p is not None], default=None)
    head = raw_reply if first is None else raw_reply[:first]

    # Try JSON in the head (prefer last valid block if you want)
    blob = first_json_block(head)
    if blob:
        try:
            obj = json.loads(blob)
            if "name" in obj and "parameters" in obj:
                return True, blob
        except json.JSONDecodeError:
            pass

    # If the first control token was EOM but no JSON parsed → malformed tool call
    if first is not None and first == eom:
        return True, None  # ← triggers your repair path

    # If first token was EOT → plain text
    if first is not None and first == eot:
        return False, head.strip()

    # No control tokens at all → plain text (or stray JSON not matching schema)
    return False, raw_reply.strip()
