import imaplib, email, re, datetime, os
from src.utils import (
    update_leave_log_status,
    get_employee_info,
    first_visible_line,
    infer_imap,
)
from .core.auth import send_mail

IMAP_USER = os.environ["EMAIL_SENDER"]
IMAP_PASS = os.environ["EMAIL_PASSWORD"]
IMAP_HOST, IMAP_PORT = infer_imap(IMAP_USER)

imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)

PATTERN = re.compile(r"Leave Request #(\d+)", re.I)


def process_reply(request_id: int, lead_email: str, verb: str) -> None:
    """
    Update the sheet and notify the employee based on the lead's reply.
    verb = "Approved" or "Rejected"
    """
    ok = update_leave_log_status(request_id, verb, approved_by=lead_email)
    if not ok:
        print(f"⚠️  Request {request_id} not found in sheet")
        return

    # Fetch employee's own address for confirmation
    employee = get_employee_info_by_request_id(request_id)  # implement or look up
    body = f"""
    Hi {employee['name']},

    Your leave request #{request_id} has been <b>{verb.lower()}</b> by {lead_email}.

    — StaffSync.AI
    """
    send_mail(
        employee["email"],
        f"Leave Request #{request_id} {verb} {'✅' if verb=='Approved' else '❌'}",
        body,
        otp=False,
    )
    print(f"✅ Request {request_id} {verb.lower()} by {lead_email}")


def watch_inbox():
    imap = imaplib.IMAP4_SSL(IMAP_HOST)
    imap.login(IMAP_USER, IMAP_PASS)
    imap.select("INBOX")
    typ, data = imap.search(None, '(UNSEEN SUBJECT "Leave Request #")')
    for num in data[0].split():
        typ, raw = imap.fetch(num, "(RFC822)")
        msg = email.message_from_bytes(raw[0][1])

        m = PATTERN.search(msg["Subject"] or "")
        if not m:
            continue
        request_id = int(m.group(1))
        lead_email = email.utils.parseaddr(msg["From"])[1].lower()

        reply = first_visible_line(msg).strip().lower()
        if reply == "y":
            process_reply(request_id, lead_email, "Approved")
        elif reply == "n":
            process_reply(request_id, lead_email, "Rejected")

        # mark processed so we don't touch it again
        imap.store(num, "+FLAGS", "\\Seen")

    imap.close()
    imap.logout()
