from __future__ import print_function
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from decouple import config
# Configure API key
configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = config("BREVO_API_KEY")
# Create API instance for transactional emails
api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

# Define the email
send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
    to=[{"email": "hariharasudhansara@gmail.com", "name": "Recipient Name"}],
    sender={"name": "ComplianceTrained Support", "email": "support@compliancetrained.com"},
    subject="Test Email from DigitalOcean via Brevo API",
    html_content="<html><body><h1>Hello!</h1><p>This is a test email sent from DigitalOcean server via Brevo API.</p></body></html>"
)

# Send the email
try:
    api_response = api_instance.send_transac_email(send_smtp_email)
    print("Email sent successfully!")
    print(api_response)
except ApiException as e:
    print(f"Exception when calling TransactionalEmailsApi->send_transac_email: {e}\n")
