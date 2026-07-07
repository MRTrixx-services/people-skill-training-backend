from django.core.management.base import BaseCommand
from apps.platforms.models import Platform


class Command(BaseCommand):
    help = 'Send test email from a platform (supports SMTP and Brevo API)'

    def add_arguments(self, parser):
        parser.add_argument('platform_id', type=str, help='Platform ID')
        parser.add_argument('recipient', type=str, help='Recipient email address')

    def handle(self, *args, **options):
        platform_id = options['platform_id']
        recipient = options['recipient']
        
        try:
            platform = Platform.objects.get(platform_id=platform_id)
            
            self.stdout.write(f'\n📧 Testing email for: {platform.name}')
            self.stdout.write(f'Recipient: {recipient}\n')
            
            # Check if email is configured
            if not platform.has_email_config:
                self.stdout.write(self.style.ERROR('❌ No email configuration found!'))
                self.stdout.write('Configure email in Django admin first.')
                return
            
            # Display email method
            method = platform.email_delivery_method or 'smtp'
            self.stdout.write(f'📊 Email Method: {method.upper()}')
            
            # Test connection (SMTP only)
            if method == 'smtp':
                self.stdout.write('🧪 Testing SMTP connection...')
                success, message = platform.test_email_connection()
                self.stdout.write(message)
                
                if not success:
                    return
            else:
                self.stdout.write(f'🔑 Using {method.upper()} API')
            
            # Send test email
            self.stdout.write('\n📨 Sending test email...')
            
            # Prepare email content
            subject = f"✅ Test Email from {platform.name}"
            
            body_text = f"""
Hello Test User,

This is a test email from {platform.name}.

If you received this, your email configuration is working correctly!

Platform: {platform.name}
Method: {method.upper()}
From: {platform.get_from_email()}

Best regards,
{platform.name} Team
            """.strip()
            
            body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, {platform.primary_color}, {platform.secondary_color}); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
        .content {{ background: white; padding: 30px; border: 1px solid #ddd; }}
        .success-box {{ background: #d4edda; border-left: 4px solid #28a745; padding: 15px; margin: 20px 0; border-radius: 4px; }}
        .info-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        .info-table td {{ padding: 10px; border-bottom: 1px solid #eee; }}
        .info-table td:first-child {{ font-weight: bold; width: 40%; color: #666; }}
        .footer {{ background: #f5f5f5; padding: 20px; text-align: center; border-radius: 0 0 8px 8px; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0;">🧪 Test Email</h1>
        </div>
        <div class="content">
            <h2>Hello Test User,</h2>
            <p>This is a test email from <strong>{platform.name}</strong>.</p>
            
            <div class="success-box">
                <p style="margin: 0; color: #155724;">
                    <strong>✅ Success!</strong> Your email configuration is working correctly.
                </p>
            </div>
            
            <h3>Configuration Details:</h3>
            <table class="info-table">
                <tr>
                    <td>Platform:</td>
                    <td>{platform.name}</td>
                </tr>
                <tr>
                    <td>Delivery Method:</td>
                    <td><span style="background: {platform.primary_color}; color: white; padding: 3px 10px; border-radius: 3px; font-size: 11px;">{method.upper()}</span></td>
                </tr>
                <tr>
                    <td>From Email:</td>
                    <td>{platform.get_from_email()}</td>
                </tr>
            </table>
            
            <p style="color: #999; font-size: 14px; margin-top: 30px;">
                This is an automated test email.
            </p>
        </div>
        <div class="footer">
            <p style="margin: 0;">Best regards,<br><strong>{platform.name}</strong> Team</p>
            {f'<p style="margin-top: 10px;">{platform.support_email}</p>' if platform.support_email else ''}
        </div>
    </div>
</body>
</html>
            """
            
            # Get BCC emails
            bcc_emails = platform.get_admin_emails_for_bcc()
            
            # Send via platform's send_email method
            success, message = platform.send_email(
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                to_emails=[recipient],
                bcc_emails=bcc_emails if bcc_emails else None
            )
            
            if success:
                config = platform.get_email_config_summary()
                
                bcc_info = f'\nBCC: {", ".join(bcc_emails)}' if bcc_emails else ''
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n✅ Email sent successfully!\n'
                        f'Method: {method.upper()}\n'
                        f'From: {platform.get_from_email()}'
                        f'{bcc_info}\n'
                        f'Status: {message}'
                    )
                )
                
                self.stdout.write(f'\n💡 Check inbox: {recipient}')
                if bcc_emails:
                    self.stdout.write(f'💡 Check BCC: {", ".join(bcc_emails)}')
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f'\n❌ Email failed!\n'
                        f'Error: {message}'
                    )
                )
            
        except Platform.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ Platform not found: {platform_id}'))
            self.stdout.write('\n💡 Available platforms:')
            for p in Platform.objects.all():
                self.stdout.write(f'   • {p.platform_id} ({p.name})')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Failed: {str(e)}'))
            import traceback
            self.stdout.write(traceback.format_exc())
