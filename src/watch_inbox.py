import time
import imaplib, email, re, os
from src.utils import update_leave_log_status, first_visible_line, infer_imap

IMAP_USER = os.environ["EMAIL_SENDER"]
IMAP_PASS = os.environ["EMAIL_PASSWORD"]
IMAP_HOST, IMAP_PORT = infer_imap(IMAP_USER)  # keep both host & port

PATTERN = re.compile(r"Leave Request #(\d+)", re.I)

POLL_SECONDS = 5  # how often to check


def _process_unseen_messages(imap):
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
            update_leave_log_status(request_id, "Approved", approved_by=lead_email)
        elif reply == "n":
            update_leave_log_status(request_id, "Rejected", approved_by=lead_email)

        imap.store(num, "+FLAGS", "\\Seen")  # mark processed


def watch_inbox():
    while True:
        try:
            with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
                imap.login(IMAP_USER, IMAP_PASS)
                imap.select("INBOX")
                _process_unseen_messages(imap)
        except Exception as e:
            # log the exception here; if you use logging, replace print
            print("Inbox watcher error:", e)

        time.sleep(POLL_SECONDS)  # wait before next cycle
