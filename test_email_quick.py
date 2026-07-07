import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Email account credentials
sender_email = "support@peopleskilltraining.com"
password = "^zD$Hvuv-WIt"

# Receiver email
receiver_email = "hariharasudhansara@gmail.com"  # 👈 change to the target email

# Create the email
message = MIMEMultipart("alternative")
message["Subject"] = "Test Email from peopleskilltraining.com"
message["From"] = sender_email
message["To"] = receiver_email

# Email body (both plain text and HTML)
text = """\
Hello,

This is a test email sent from peopleskilltraining.com business email setup.

Best,
People Skill Training
"""
html = """\
<html>
  <body>
    <p>Hello,<br><br>
       This is a <b>test email</b> sent from <b>peopleskilltraining.com</b> business email setup.<br><br>
       Best,<br>
       <i>People Skill Training</i>
    </p>
  </body>
</html>
"""

# Attach both versions
message.attach(MIMEText(text, "plain"))
message.attach(MIMEText(html, "html"))

# SMTP configuration
smtp_server = "businessemail.webeyesoft.com"
port = 465  # SSL port

# Send the email
context = ssl.create_default_context()
with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
    server.login(sender_email, password)
    server.sendmail(sender_email, receiver_email, message.as_string())

print("✅ Email sent successfully!")
