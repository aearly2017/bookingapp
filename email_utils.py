import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# -------- Gmail SMTP config --------
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_ADDRESS = "logansbeachlookout@gmail.com"        # <-- Your new Gmail address
EMAIL_PASSWORD = "foru ucev gyty gizi"              # <-- Your Gmail App Password
NOTIFY_EMAIL_TO = "logansbeachlookout@gmail.com"       # <-- Where notifications should go
# -----------------------------------

def send_booking_notification(name, email, check_in, check_out, notes):
    subject = "New Booking Request Received"
    body = f"""
    New booking request received:

    Name: {name}
    Email: {email}
    Check-in: {check_in}
    Check-out: {check_out}
    Notes: {notes}

    Please log in to the admin page to approve or decline this booking.
    """

    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = NOTIFY_EMAIL_TO
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("Notification email sent successfully.")
    except Exception as e:
        print(f"Error sending email: {e}")
