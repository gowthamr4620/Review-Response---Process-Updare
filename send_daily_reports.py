"""
Sends the Muthoot Finance Daily Review Report workbooks to the recipient
list configured for each Corporate scope (NEW / SOUTH / COMBINED).

Each scope gets only its own workbook as an attachment - recipients never
see another Corporate's report.

Config:
  recipients.json - maps scope -> list of recipient email addresses.
                     An empty list means "no send for that scope yet".

Credentials (env vars, not committed):
  GMAIL_ADDRESS       - the sending Gmail address
  GMAIL_APP_PASSWORD  - a Google App Password for that address
                        (Google Account > Security > App Passwords;
                        requires 2FA enabled on the account)

Usage:
  python send_daily_reports.py --date 2026-07-20 --reports-dir ./reports

  Looks in --reports-dir for files matching the naming convention:
    Muthoot Finance - Daily Review Report - {DD} {Mon}-{YYYY} - NEW.xlsx
    Muthoot Finance - Daily Review Report - {DD} {Mon}-{YYYY} - SOUTH.xlsx
    Muthoot Finance - Daily Review Report - {DD} {Mon}-{YYYY} - Combined.xlsx
"""

import argparse
import json
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

SCOPE_FILE_SUFFIX = {
    "NEW": "NEW",
    "SOUTH": "SOUTH",
    "COMBINED": "Combined",
}


def load_recipients(config_path: Path) -> dict:
    with open(config_path) as f:
        return json.load(f)


def find_report_file(reports_dir: Path, report_date: datetime, scope: str) -> Path | None:
    suffix = SCOPE_FILE_SUFFIX[scope]
    expected_name = (
        f"Muthoot Finance - Daily Review Report - "
        f"{report_date:%d %b}-{report_date:%Y} - {suffix}.xlsx"
    )
    candidate = reports_dir / expected_name
    if candidate.exists():
        return candidate

    # Fall back to a loose match in case of minor naming drift
    # (spaces/underscores, missing scope suffix on combined exports, etc.)
    date_token = f"{report_date:%d}"
    month_token = f"{report_date:%b}"
    for path in reports_dir.glob("*.xlsx"):
        name = path.name
        if date_token in name and month_token in name.replace("_", " "):
            if scope == "COMBINED" and "NEW" not in name and "SOUTH" not in name:
                return path
            if suffix in name:
                return path
    return None


def build_message(sender: str, recipients: list, scope: str, report_date: datetime, attachment: Path) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = (
        f"Muthoot Finance - Daily Review Report - {report_date:%d %b}-{report_date:%Y} - {scope.title()}"
    )
    msg.set_content(
        f"Hi,\n\n"
        f"Please find attached the Daily Review Report for Muthoot Finance "
        f"({scope.title()} scope) for {report_date:%d %b %Y}.\n\n"
        f"Regards,\nAutomated Reporting"
    )
    with open(attachment, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=attachment.name,
        )
    return msg


def send(sender: str, app_password: str, msg: EmailMessage) -> None:
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(sender, app_password)
        server.send_message(msg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send Muthoot daily review reports by Corporate scope")
    parser.add_argument("--date", required=True, help="Report date, YYYY-MM-DD")
    parser.add_argument("--reports-dir", required=True, help="Directory containing the generated workbooks")
    parser.add_argument("--recipients-config", default="recipients.json", help="Path to recipients.json")
    parser.add_argument("--dry-run", action="store_true", help="Resolve files/recipients but don't send")
    args = parser.parse_args()

    report_date = datetime.strptime(args.date, "%Y-%m-%d")
    reports_dir = Path(args.reports_dir)
    recipients_by_scope = load_recipients(Path(args.recipients_config))

    sender = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not args.dry_run and not (sender and app_password):
        raise SystemExit(
            "Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD env vars before sending "
            "(or pass --dry-run to test resolution without sending)."
        )

    for scope, recipients in recipients_by_scope.items():
        if not recipients:
            print(f"[skip] {scope}: no recipients configured")
            continue

        report_file = find_report_file(reports_dir, report_date, scope)
        if report_file is None:
            print(f"[error] {scope}: no report file found in {reports_dir} for {args.date}")
            continue

        print(f"[send] {scope}: {report_file.name} -> {', '.join(recipients)}")
        if args.dry_run:
            continue

        msg = build_message(sender, recipients, scope, report_date, report_file)
        send(sender, app_password, msg)


if __name__ == "__main__":
    main()
