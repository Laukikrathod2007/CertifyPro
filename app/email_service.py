import os
from email.message import EmailMessage
from pathlib import Path

import smtplib
import ssl


def send_certificate_email(
    display_name: str,
    recipient_email: str,
    pdf_path: str,
    certificate_name: str,
    subject: str = None,
    message_body: str = None,
) -> None:
    """
    Send a rich HTML email with the certificate attached.

    All configurable text (subject, body, sender name) comes from the caller
    or environment — nothing is hardcoded.
    """
    sender_email = os.getenv("SENDER_EMAIL")
    app_password = os.getenv("APP_PASSWORD")
    sender_name = os.getenv("SENDER_NAME", "Certificate Team")

    if not sender_email or not app_password:
        raise RuntimeError(
            "Email credentials not configured. "
            "Set SENDER_EMAIL and APP_PASSWORD in .env"
        )

    if not subject:
        subject = "Your Certificate"

    if not message_body:
        message_body = "We are pleased to share your certificate. Please find it attached."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = recipient_email

    plain_body = (
        f"Dear {display_name},\n\n"
        f"{message_body}\n\n"
        f"Your certificate ({certificate_name}) is attached as a PDF.\n\n"
        f"Best regards,\n{sender_name}"
    )
    msg.set_content(plain_body)

    html_message = message_body.replace('\n', '<br/>')

    html_body = f"""
    <html>
      <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background-color:#F8F9FA; padding:24px;">
        <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:10px;border:1px solid #E0E0E0;box-shadow:0 2px 12px rgba(0,0,0,0.08);padding:24px;">
          <h2 style="margin-top:0;color:#1A1A2E;font-weight:600;">{subject}</h2>
          <p style="color:#2B2D42;font-size:15px;">Dear {display_name},</p>
          <p style="color:#2B2D42;font-size:15px;line-height:1.6;">
            {html_message}
          </p>
          <div style="margin:18px 0;padding:16px;border-radius:8px;background:#F8F9FA;border:1px solid #E0E0E0;">
            <div style="font-size:13px;text-transform:uppercase;letter-spacing:0.08em;color:#6c757d;margin-bottom:4px;">
              Certificate Holder
            </div>
            <div style="font-size:18px;font-weight:600;color:#1A1A2E;">
              {certificate_name}
            </div>
          </div>
          <p style="color:#2B2D42;font-size:15px;line-height:1.6;">
            Your PDF certificate is attached. You can download and keep it for your records.
          </p>
          <p style="color:#2B2D42;font-size:15px;line-height:1.6;">
            Warm regards,<br/>
            <strong>{sender_name}</strong>
          </p>
        </div>
      </body>
    </html>
    """
    msg.add_alternative(html_body, subtype="html")

    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"Certificate PDF not found at {pdf_file}")

    with pdf_file.open("rb") as f:
        pdf_data = f.read()

    msg.add_attachment(
        pdf_data,
        maintype="application",
        subtype="pdf",
        filename=pdf_file.name,
    )

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender_email, app_password)
        server.send_message(msg)
