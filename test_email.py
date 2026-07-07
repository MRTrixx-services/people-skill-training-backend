import smtplib
from email.message import EmailMessage

# Your Namecheap Private Email details
sender_email = 'support@compliancetrained.com'
receiver_email = 'hariharasudhansara@gmail.com'  # Send to your own email to test
smtp_server = 'mail.privateemail.com'
port = 26
login = 'support@compliancetrained.com'  # Same as sender_email
password = 'S@r04294839'  # NOT Namecheap account password

# Create message
message = EmailMessage()
message["Subject"] = "Test Email from DigitalOcean"
message["From"] = f"Your Name <{sender_email}>"
message["To"] = receiver_email
message.set_content("Hello! This is a test email sent from DigitalOcean server via Namecheap Private Email.")

# Send email
server = smtplib.SMTP_SSL(smtp_server, port)
server.login(login, password)
server.send_message(message)
server.quit()

print("Test email sent successfully!")
