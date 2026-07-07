from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.core.mail import get_connection
from django.conf import settings
from cryptography.fernet import Fernet
import secrets
import hashlib
import logging
import os

logger = logging.getLogger(__name__)

EMAIL_DELIVERY_CHOICES = [
    ('smtp', 'Direct SMTP'),
    ('sendgrid_api', 'SendGrid API'),
    ('mailgun_api', 'Mailgun API'),
    ('aws_ses_api', 'AWS SES API'),
    ('resend_api', 'Resend API'),
    ('postmark_api', 'Postmark API'),
    ('brevo_api', 'Brevo API'),
]

def platform_logo_upload_path(instance, filename):
    """
    Generate upload path: platforms/logos/{platform_id}_logo.{ext}
    This will be stored in: media/platforms/logos/compliance_trained_logo.png
    """
    ext = filename.split('.')[-1].lower()
    filename = f"{instance.platform_id}_logo.{ext}"
    return f"platforms/logos/{filename}"

def platform_favicon_upload_path(instance, filename):
    """
    Generate upload path: platforms/favicons/{platform_id}_favicon.{ext}
    This will be stored in: media/platforms/favicons/compliance_trained_favicon.ico
    """
    ext = filename.split('.')[-1].lower()
    filename = f"{instance.platform_id}_favicon.{ext}"
    return f"platforms/favicons/{filename}"

class Platform(models.Model):
    """Multi-tenant platform configuration with API key authentication"""
    
    platform_id = models.CharField(
        max_length=50, 
        unique=True, 
        db_index=True,
        help_text="Unique identifier (e.g., compliance_trained, people_skill_training)"
    )
    name = models.CharField(max_length=200)
    invoice_prefix = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        help_text="Invoice prefix (e.g., 'PSINV' for PeopleSkillTraining). Leave blank to auto-generate."
    )
    description = models.TextField(blank=True)
    
    # API KEY AUTHENTICATION
    api_key = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        editable=False,
        help_text="API key for platform authentication"
    )
    api_key_hash = models.CharField(
        max_length=128,
        unique=True,
        editable=False,
        help_text="Hashed version of API key for security"
    )
    
    domain = models.CharField(max_length=255, blank=True)
    allowed_origins = models.JSONField(default=list, blank=True)
    
    # Branding
    # logo = models.ImageField(upload_to='platforms/logos/', null=True, blank=True)
    # favicon = models.ImageField(upload_to='platforms/favicons/', null=True, blank=True)
    logo = models.ImageField(
        upload_to=platform_logo_upload_path,
        null=True, 
        blank=True
    )
    favicon = models.ImageField(
        upload_to=platform_favicon_upload_path,
        null=True, 
        blank=True
    )
    primary_color = models.CharField(max_length=7, default='#3B82F6')
    secondary_color = models.CharField(max_length=7, default='#8B5CF6')
    accent_color = models.CharField(max_length=7, default='#10B981')
    
    # Contact information
    support_email = models.EmailField(
        blank=True,
        help_text="Public support email for customer inquiries"
    )
    contact_email = models.EmailField(
        blank=True,
        help_text="Admin contact email for BCC notifications (payment confirmations, system alerts)"
    )
    contact_phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    
    # JSON fields
    social_links = models.JSONField(default=dict, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    features = models.JSONField(default=dict, blank=True)
    payment_settings = models.JSONField(default=dict, blank=True)
    email_delivery_method = models.CharField(
        max_length=20,
        choices=EMAIL_DELIVERY_CHOICES,
        default='smtp',
        help_text="Method for sending emails: Direct SMTP or API-based service"
    )
    email_settings = models.JSONField(
        default=dict, 
        blank=True,
        help_text="Encrypted email configuration including SMTP credentials"
    )
    analytics = models.JSONField(default=dict, blank=True)
    allowed_ip_addresses = models.JSONField(default=list, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    maintenance_mode = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    requires_email_verification = models.BooleanField(
        default=True,
        help_text="If True, users must verify email before login. If False, users are auto-verified on registration."
    )
    class Meta:
        db_table = 'platforms'
        verbose_name = 'Platform'
        verbose_name_plural = 'Platforms'
        ordering = ['name']
        indexes = [
            models.Index(fields=['api_key']),
            models.Index(fields=['platform_id']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.platform_id})"
    
    def save(self, *args, **kwargs):
        if not self.api_key:
            self.api_key = self.generate_api_key()
            self.api_key_hash = self.hash_api_key(self.api_key)
        
        if self.is_default:
            Platform.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        
        super().save(*args, **kwargs)
    
    # ============================================
    # API KEY METHODS
    # ============================================
    
    @staticmethod
    def generate_api_key():
        return f"pk_{secrets.token_urlsafe(32)}"
    
    @staticmethod
    def hash_api_key(api_key):
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    def regenerate_api_key(self):
        old_key = self.api_key
        self.api_key = self.generate_api_key()
        self.api_key_hash = self.hash_api_key(self.api_key)
        self.save()
        return self.api_key
    
    def verify_api_key(self, api_key):
        return self.api_key_hash == self.hash_api_key(api_key)
    
    # ============================================
    # EMAIL HELPER METHODS
    # ============================================
    
    def get_admin_emails_for_bcc(self):
        """
        Get list of admin emails for BCC notifications
        Returns list of emails in priority order:
        1. contact_email (dedicated admin email)
        2. support_email (fallback)
        """
        emails = []
        
        if self.contact_email:
            emails.append(self.contact_email)
        elif self.support_email:
            emails.append(self.support_email)
        
        return emails
    
    def get_notification_email(self):
        """Get primary email for system notifications"""
        return self.contact_email or self.support_email or settings.DEFAULT_FROM_EMAIL
    
    # ============================================
    # EMAIL ENCRYPTION/DECRYPTION METHODS
    # ============================================
    
    @staticmethod
    def _get_cipher():
        """Get Fernet cipher for encryption/decryption"""
        key = settings.FIELD_ENCRYPTION_KEY
        if isinstance(key, str):
            key = key.encode()
        return Fernet(key)
    
    @staticmethod
    def encrypt_value(value):
        """Encrypt a string value"""
        if not value:
            return value
        try:
            cipher = Platform._get_cipher()
            return cipher.encrypt(value.encode()).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise
    
    @staticmethod
    def decrypt_value(encrypted_value):
        """Decrypt an encrypted string"""
        if not encrypted_value:
            return encrypted_value
        try:
            cipher = Platform._get_cipher()
            return cipher.decrypt(encrypted_value.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return None
    
    # ============================================
    # EMAIL CONFIGURATION METHODS
    # ============================================
    
    def set_email_config(self, smtp_host, smtp_port, smtp_user, smtp_password, 
                        use_tls=True, use_ssl=False, from_email=None, 
                        from_name=None, provider='smtp'):
        """
        Set encrypted SMTP email configuration for this platform
        (Unified method that sets email_delivery_method)
        """
        encrypted_password = self.encrypt_value(smtp_password)
        
        self.email_delivery_method = 'smtp'
        self.email_settings = {
            'smtp_host': smtp_host,
            'smtp_port': smtp_port,
            'smtp_user': smtp_user,
            'smtp_password_encrypted': encrypted_password,
            'use_tls': use_tls,
            'use_ssl': use_ssl,
            'from_email': from_email or self.support_email,
            'from_name': from_name or self.name,
            'provider': provider,
            'timeout': 30,
            'configured_at': timezone.now().isoformat(),
        }
        self.save()
        logger.info(f"[{self.name}] SMTP config updated: {smtp_host}:{smtp_port}")
    
    def set_smtp_config(self, smtp_host, smtp_port, smtp_user, smtp_password,
                        use_tls=True, use_ssl=False, from_email=None, from_name=None):
        """Configure direct SMTP email delivery (alias for set_email_config)"""
        return self.set_email_config(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_password=smtp_password,
            use_tls=use_tls,
            use_ssl=use_ssl,
            from_email=from_email,
            from_name=from_name,
            provider='smtp'
        )
    
    def set_sendgrid_api_config(self, api_key, from_email=None, from_name=None):
        """Configure SendGrid API for email delivery"""
        encrypted_api_key = self.encrypt_value(api_key)
        
        self.email_delivery_method = 'sendgrid_api'
        self.email_settings = {
            'api_key_encrypted': encrypted_api_key,
            'from_email': from_email or self.support_email,
            'from_name': from_name or self.name,
            'configured_at': timezone.now().isoformat(),
        }
        self.save()
        logger.info(f"[{self.name}] SendGrid API configured")
    
    def set_mailgun_api_config(self, api_key, domain, from_email=None, from_name=None, region='us'):
        """Configure Mailgun API for email delivery"""
        encrypted_api_key = self.encrypt_value(api_key)
        
        self.email_delivery_method = 'mailgun_api'
        self.email_settings = {
            'api_key_encrypted': encrypted_api_key,
            'domain': domain,
            'region': region,
            'from_email': from_email or self.support_email,
            'from_name': from_name or self.name,
            'configured_at': timezone.now().isoformat(),
        }
        self.save()
        logger.info(f"[{self.name}] Mailgun API configured: {domain}")
    
    def set_brevo_api_config(self, api_key, from_email=None, from_name=None):
        """Configure Brevo (Sendinblue) API for email delivery"""
        encrypted_api_key = self.encrypt_value(api_key)
        
        self.email_delivery_method = 'brevo_api'
        self.email_settings = {
            'api_key_encrypted': encrypted_api_key,
            'from_email': from_email or self.support_email,
            'from_name': from_name or self.name,
            'configured_at': timezone.now().isoformat(),
        }
        self.save()
        logger.info(f"[{self.name}] Brevo API configured")
    
    # ============================================
    # EMAIL SENDING METHODS
    # ============================================
    
    def send_via_smtp(self, subject, body_text, body_html, to_emails, cc_emails, bcc_emails,
                      reply_to, attachments, headers):
        """Send email via SMTP"""
        from django.core.mail import EmailMultiAlternatives
        
        config = self.email_settings
        smtp_password = self.decrypt_value(config.get('smtp_password_encrypted'))
        
        if not smtp_password:
            return False, "Failed to decrypt SMTP password"
        
        connection = get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host=config.get('smtp_host'),
            port=config.get('smtp_port', 587),
            username=config.get('smtp_user'),
            password=smtp_password,
            use_tls=config.get('use_tls', True),
            use_ssl=config.get('use_ssl', False),
            timeout=config.get('timeout', 30),
            fail_silently=False,
        )
        
        from_name = config.get('from_name', self.name)
        from_email = config.get('from_email')
        
        msg = EmailMultiAlternatives(
            subject=subject,
            body=body_text,
            from_email=f"{from_name} <{from_email}>",
            to=to_emails if isinstance(to_emails, list) else [to_emails],
            cc=cc_emails,
            bcc=bcc_emails,
            reply_to=[reply_to] if reply_to else None,
            connection=connection,
            headers=headers or {}
        )
        
        if body_html:
            msg.attach_alternative(body_html, "text/html")
        
        if attachments:
            for attachment in attachments:
                msg.attach(
                    attachment['filename'],
                    attachment['content'],
                    attachment.get('mimetype', 'application/octet-stream')
                )
        
        msg.send()
        logger.info(f"[{self.name}] SMTP email sent to {to_emails}")
        return True, "Email sent via SMTP"
    
    def send_via_sendgrid(self, subject, body_text, body_html, to_emails, cc_emails, bcc_emails,
                          reply_to, attachments, headers):
        """Send email via SendGrid API"""
        import requests
        import base64
        
        config = self.email_settings
        api_key = self.decrypt_value(config.get('api_key_encrypted'))
        
        if not api_key:
            return False, "Failed to decrypt SendGrid API key"
        
        from_email = config.get('from_email')
        from_name = config.get('from_name', self.name)
        
        personalizations = [{
            'to': [{'email': email} for email in (to_emails if isinstance(to_emails, list) else [to_emails])]
        }]
        
        if cc_emails:
            personalizations[0]['cc'] = [{'email': email} for email in cc_emails]
        if bcc_emails:
            personalizations[0]['bcc'] = [{'email': email} for email in bcc_emails]
        
        payload = {
            'personalizations': personalizations,
            'from': {'email': from_email, 'name': from_name},
            'subject': subject,
            'content': [{'type': 'text/plain', 'value': body_text}]
        }
        
        if body_html:
            payload['content'].append({'type': 'text/html', 'value': body_html})
        
        if reply_to:
            payload['reply_to'] = {'email': reply_to}
        
        if attachments:
            payload['attachments'] = []
            for attachment in attachments:
                payload['attachments'].append({
                    'content': base64.b64encode(attachment['content']).decode(),
                    'filename': attachment['filename'],
                    'type': attachment.get('mimetype', 'application/octet-stream')
                })
        
        response = requests.post(
            'https://api.sendgrid.com/v3/mail/send',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            json=payload,
            timeout=30
        )
        
        if response.status_code in (200, 202):
            logger.info(f"[{self.name}] SendGrid email sent to {to_emails}")
            return True, "Email sent via SendGrid API"
        else:
            logger.error(f"[{self.name}] SendGrid failed: {response.text}")
            return False, f"SendGrid API error: {response.text}"
    
    def send_via_mailgun(self, subject, body_text, body_html, to_emails, cc_emails, bcc_emails,
                         reply_to, attachments, headers):
        """Send email via Mailgun API"""
        import requests
        
        config = self.email_settings
        api_key = self.decrypt_value(config.get('api_key_encrypted'))
        domain = config.get('domain')
        region = config.get('region', 'us')
        
        if not api_key or not domain:
            return False, "Missing Mailgun API key or domain"
        
        base_url = 'https://api.mailgun.net' if region == 'us' else 'https://api.eu.mailgun.net'
        url = f'{base_url}/v3/{domain}/messages'
        
        from_email = config.get('from_email')
        from_name = config.get('from_name', self.name)
        
        data = {
            'from': f'{from_name} <{from_email}>',
            'to': to_emails if isinstance(to_emails, list) else [to_emails],
            'subject': subject,
            'text': body_text,
        }
        
        if body_html:
            data['html'] = body_html
        if cc_emails:
            data['cc'] = cc_emails
        if bcc_emails:
            data['bcc'] = bcc_emails
        if reply_to:
            data['h:Reply-To'] = reply_to
        
        files = []
        if attachments:
            for attachment in attachments:
                files.append(('attachment', (attachment['filename'], attachment['content'])))
        
        response = requests.post(
            url,
            auth=('api', api_key),
            data=data,
            files=files if files else None,
            timeout=30
        )
        
        if response.status_code == 200:
            logger.info(f"[{self.name}] Mailgun email sent to {to_emails}")
            return True, "Email sent via Mailgun API"
        else:
            logger.error(f"[{self.name}] Mailgun failed: {response.text}")
            return False, f"Mailgun API error: {response.text}"
    
    def send_via_brevo(self, subject, body_text, body_html, to_emails, cc_emails, bcc_emails,
                       reply_to, attachments, headers):
        """Send email via Brevo API"""
        import requests
        import base64
        
        config = self.email_settings
        api_key = self.decrypt_value(config.get('api_key_encrypted'))
        
        if not api_key:
            return False, "Failed to decrypt Brevo API key"
        
        from_email = config.get('from_email')
        from_name = config.get('from_name', self.name)
        
        payload = {
            'sender': {'name': from_name, 'email': from_email},
            'to': [{'email': email} for email in (to_emails if isinstance(to_emails, list) else [to_emails])],
            'subject': subject,
            'textContent': body_text,
        }
        
        if body_html:
            payload['htmlContent'] = body_html
        if cc_emails:
            payload['cc'] = [{'email': email} for email in cc_emails]
        if bcc_emails:
            payload['bcc'] = [{'email': email} for email in bcc_emails]
        if reply_to:
            payload['replyTo'] = {'email': reply_to}
        if attachments:
            payload['attachment'] = []
            for attachment in attachments:
                payload['attachment'].append({
                    'name': attachment['filename'],
                    'content': base64.b64encode(attachment['content']).decode('utf-8')
                })
        
        try:
            response = requests.post(
                'https://api.brevo.com/v3/smtp/email',
                headers={
                    'accept': 'application/json',
                    'api-key': api_key,
                    'content-type': 'application/json'
                },
                json=payload,
                timeout=30
            )
            
            if response.status_code in (200, 201):
                result = response.json()
                message_id = result.get('messageId', 'unknown')
                logger.info(f"[{self.name}] Brevo email sent to {to_emails} (MessageId: {message_id})")
                return True, f"Email sent via Brevo API (MessageId: {message_id})"
            else:
                error_data = response.json() if 'application/json' in response.headers.get('content-type', '') else response.text
                logger.error(f"[{self.name}] Brevo failed: {error_data}")
                return False, f"Brevo API error: {error_data}"
        except Exception as e:
            logger.error(f"[{self.name}] Brevo request failed: {e}")
            return False, f"Brevo API request failed: {str(e)}"
    
    def send_email(self, subject, body_text, body_html, to_emails, cc_emails=None,
                   bcc_emails=None, reply_to=None, attachments=None, headers=None):
        """
        Unified email sending interface - works with both SMTP and API methods
        
        Returns:
            (success: bool, message: str)
        """
        try:
            method = self.email_delivery_method or 'smtp'
            
            if method == 'smtp':
                return self.send_via_smtp(subject, body_text, body_html, to_emails,
                                         cc_emails, bcc_emails, reply_to, attachments, headers)
            elif method == 'sendgrid_api':
                return self.send_via_sendgrid(subject, body_text, body_html, to_emails,
                                             cc_emails, bcc_emails, reply_to, attachments, headers)
            elif method == 'mailgun_api':
                return self.send_via_mailgun(subject, body_text, body_html, to_emails,
                                            cc_emails, bcc_emails, reply_to, attachments, headers)
            elif method == 'brevo_api':
                return self.send_via_brevo(subject, body_text, body_html, to_emails,
                                          cc_emails, bcc_emails, reply_to, attachments, headers)
            else:
                return False, f"Unsupported email delivery method: {method}"
        except Exception as e:
            logger.error(f"[{self.name}] Email send failed: {e}", exc_info=True)
            return False, str(e)
    
    # ============================================
    # LEGACY/HELPER METHODS
    # ============================================
    
    def get_smtp_password(self):
        """Get decrypted SMTP password"""
        if not self.email_settings:
            return None
        
        encrypted_password = self.email_settings.get('smtp_password_encrypted')
        if not encrypted_password:
            return None
        
        return self.decrypt_value(encrypted_password)
    
    def get_email_connection(self):
        """Get platform-specific SMTP connection with decrypted credentials"""
        try:
            email_config = self.email_settings or {}
            
            if not email_config.get('smtp_host'):
                logger.warning(f"[{self.name}] No SMTP config, using Django default")
                return None
            
            smtp_password = self.get_smtp_password()
            
            if not smtp_password:
                logger.error(f"[{self.name}] Failed to decrypt SMTP password")
                return None
            
            use_ssl = email_config.get('use_ssl', False)
            use_tls = email_config.get('use_tls', True)
            
            connection = get_connection(
                backend='django.core.mail.backends.smtp.EmailBackend',
                host=email_config.get('smtp_host'),
                port=email_config.get('smtp_port', 587),
                username=email_config.get('smtp_user'),
                password=smtp_password,
                use_tls=False if use_ssl else use_tls,
                use_ssl=use_ssl,
                timeout=email_config.get('timeout', 30),
                fail_silently=False,
            )
            
            logger.info(
                f"[{self.name}] Email connection created: {email_config.get('smtp_host')} "
                f"(SSL={use_ssl}, TLS={use_tls})"
            )
            return connection
            
        except Exception as e:
            logger.error(f"[{self.name}] Email connection failed: {e}", exc_info=True)
            return None
    
    def get_from_email(self):
        """Get platform-specific from email with fallback"""
        email_config = self.email_settings or {}
        return (
            email_config.get('from_email') or 
            self.support_email or 
            settings.DEFAULT_FROM_EMAIL
        )
    
    def get_from_name(self):
        """Get platform-specific sender name"""
        email_config = self.email_settings or {}
        return email_config.get('from_name', self.name)
    
    def test_email_connection(self):
        """Test platform's email configuration"""
        try:
            if not self.email_settings:
                return False, "❌ No email configuration found"
            
            method = self.email_delivery_method or 'smtp'
            
            if method == 'smtp':
                if not self.email_settings.get('smtp_host'):
                    return False, "❌ No SMTP configuration found"
                
                connection = self.get_email_connection()
                if not connection:
                    return False, "❌ Failed to create email connection"
                
                connection.open()
                connection.close()
                
                smtp_host = self.email_settings.get('smtp_host')
                smtp_port = self.email_settings.get('smtp_port')
                return True, f"✅ Connected to SMTP ({smtp_host}:{smtp_port})"
            
            else:
                # For API methods, just check if API key exists
                if self.email_settings.get('api_key_encrypted'):
                    return True, f"✅ {method.upper()} API key configured"
                else:
                    return False, f"❌ {method.upper()} API key not found"
            
        except Exception as e:
            return False, f"❌ Connection failed: {str(e)}"
    
    def get_email_config_summary(self):
        """Get non-sensitive email configuration summary for display"""
        if not self.email_settings:
            return {"configured": False}
        
        config = self.email_settings
        return {
            'provider': config.get('provider', 'custom'),
            'smtp_host': config.get('smtp_host'),
            'smtp_port': config.get('smtp_port'),
            'smtp_user': config.get('smtp_user'),
            'from_email': config.get('from_email'),
            'use_tls': config.get('use_tls'),
            'use_ssl': config.get('use_ssl'),
            'configured_at': config.get('configured_at'),
            'password_encrypted': bool(config.get('smtp_password_encrypted')),
        }
    
    # ============================================
    # PROPERTIES
    # ============================================
    
    @property
    def logo_url(self):
        if self.logo:
            return self.logo.url
        return None
    
    @property
    def user_count(self):
        return self.users.count()
    
    @property
    def active_user_count(self):
        return self.users.filter(is_active=True).count()
    
    @property
    def has_email_config(self):
        """Check if platform has email configuration"""
        if not self.email_settings:
            return False
        
        method = self.email_delivery_method or 'smtp'
        
        # Check based on delivery method
        if method == 'smtp':
            return bool(self.email_settings.get('smtp_host'))
        elif method in ['brevo_api', 'sendgrid_api', 'mailgun_api', 'aws_ses_api', 'resend_api', 'postmark_api']:
            return bool(self.email_settings.get('api_key_encrypted'))
        
        return False
    
    # def get_active_payment_gateways(self, currency=None):
    #     """
    #     Get all active payment gateways for this platform
    #     Optionally filter by currency support
    #     """
    #     gateways = self.payment_gateways.filter(is_active=True).order_by('display_order')
        
    #     if currency:
    #         # Filter gateways that support the currency
    #         gateways = [g for g in gateways if g.supports_currency(currency)]
        
    #     return gateways
    
    # def get_gateway_by_id(self, gateway_id, is_test_mode=None):
    #     """Get specific payment gateway for this platform"""
    #     filters = {
    #         'gateway_id': gateway_id,
    #         'is_active': True
    #     }
    #     if is_test_mode is not None:
    #         filters['is_test_mode'] = is_test_mode
        
    #     return self.payment_gateways.filter(**filters).first()
   
    def get_active_payment_gateways(self, currency=None):
        """
        Get all active payment gateways for this platform
        Includes both platform-specific AND global gateways
        """
        from apps.payments.models import PaymentGateway
        
        # Get platform-specific gateways OR global gateways (platform=None)
        gateways = PaymentGateway.objects.filter(
            models.Q(platform=self) | models.Q(platform__isnull=True),
            is_active=True
        ).order_by('display_order')
        
        if currency:
            # Filter gateways that support the currency
            gateways = [g for g in gateways if currency in g.supported_currencies]
        
        return gateways
    
    def get_gateway_by_id(self, gateway_id, is_test_mode=None):
        """
        Get specific payment gateway for this platform
        Prioritizes platform-specific, falls back to global
        """
        from apps.payments.models import PaymentGateway
        
        filters = {
            'gateway_id': gateway_id,
            'is_active': True
        }
        if is_test_mode is not None:
            filters['is_test_mode'] = is_test_mode
        
        # First try platform-specific gateway
        gateway = PaymentGateway.objects.filter(
            platform=self,
            **filters
        ).first()
        
        # Fallback to global gateway
        if not gateway:
            gateway = PaymentGateway.objects.filter(
                platform__isnull=True,
                **filters
            ).first()
        
        return gateway

    def has_payment_gateway(self, gateway_id):
        """Check if platform has specific gateway configured and active"""
        return self.payment_gateways.filter(
            gateway_id=gateway_id,
            is_active=True
        ).exists()
    
    def get_default_payment_gateway(self):
        """Get the first active payment gateway (by display_order)"""
        return self.payment_gateways.filter(
            is_active=True
        ).order_by('display_order').first()
    
    def get_payment_gateways_summary(self):
        """Get summary of payment gateways for this platform"""
        total = self.payment_gateways.count()
        active = self.payment_gateways.filter(is_active=True).count()
        configured = sum(1 for g in self.payment_gateways.all() if g.is_configured)
        
        return {
            'total': total,
            'active': active,
            'configured': configured,
            'inactive': total - active
        }

class PlatformStats(models.Model):
    """Statistics for each platform"""
    
    platform = models.OneToOneField(
        Platform,
        on_delete=models.CASCADE,
        related_name='stats'
    )
    
    total_users = models.IntegerField(default=0)
    active_users = models.IntegerField(default=0)
    total_instructors = models.IntegerField(default=0)
    total_attendees = models.IntegerField(default=0)
    
    total_webinars = models.IntegerField(default=0)
    live_webinars = models.IntegerField(default=0)
    recorded_webinars = models.IntegerField(default=0)
    
    total_enrollments = models.IntegerField(default=0)
    active_enrollments = models.IntegerField(default=0)
    
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    this_month_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    last_calculated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'platform_stats'
        verbose_name = 'Platform Statistics'
        verbose_name_plural = 'Platform Statistics'
    
    def __str__(self):
        return f"Stats for {self.platform.name}"


class PlatformAPILog(models.Model):
    """Log API requests for each platform"""
    
    platform = models.ForeignKey(
        Platform,
        on_delete=models.CASCADE,
        related_name='api_logs'
    )
    
    # Request details
    endpoint = models.CharField(max_length=500)
    method = models.CharField(max_length=10)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    
    # Response details
    status_code = models.IntegerField()
    response_time_ms = models.IntegerField(help_text="Response time in milliseconds")
    
    authenticated_user = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='platform_api_logs'
    )
    
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'platform_api_logs'
        verbose_name = 'Platform API Log'
        verbose_name_plural = 'Platform API Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['platform', 'created_at']),
            models.Index(fields=['platform', 'endpoint']),
            models.Index(fields=['authenticated_user']),
        ]
    
    def __str__(self):
        return f"{self.platform.name} - {self.method} {self.endpoint}"


# ============================================
# SIGNALS
# ============================================

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=Platform)
def create_platform_stats(sender, instance, created, **kwargs):
    """Create PlatformStats when a new Platform is created"""
    if created:
        PlatformStats.objects.create(platform=instance)
