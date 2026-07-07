from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from django.contrib.auth import get_user_model
from celery import shared_task
import logging
from sib_api_v3_sdk import ApiClient, Configuration, TransactionalEmailsApi, SendSmtpEmail
from sib_api_v3_sdk.rest import ApiException


logger = logging.getLogger(__name__)
User = get_user_model()


class EmailService:
    """
    Multi-platform email service with platform-specific branding and SMTP
    Supports multiple platforms with custom colors, logos, settings, and email providers
    """
    # @staticmethod
    # def get_brevo_client(platform=None):
    #     """
    #     Get Brevo API client with platform-specific API key
        
    #     Args:
    #         platform: Platform object with brevo_api_key in email_settings
        
    #     Returns:
    #         TransactionalEmailsApi: Brevo API client
    #     """
    #     # Get API key from platform or default
        
    #     if platform and hasattr(platform, 'email_settings') and platform.email_settings:
    #         api_key = platform.email_settings.get('brevo_api_key')
        
    #     # Fallback to settings
    #     if not api_key:
        
    #     if not api_key:
    #         logger.error("No Brevo API key configured")
    #         raise ValueError("Brevo API key not configured for platform or in settings")
        
    #     # Configure Brevo client
    #     configuration = Configuration()
    #     configuration.api_key['api-key'] = api_key
        
    #     return TransactionalEmailsApi(ApiClient(configuration))
      
    @staticmethod
    def get_base_url(request=None, platform=None):
        """Get platform-specific or fallback base URL"""
        # Priority 1: Platform-specific domain
        if platform and hasattr(platform, 'domain') and platform.domain:
            protocol = 'http' if platform.domain.startswith(('localhost', '127.0.0.1')) else 'https'
            return f"{protocol}://{platform.domain}"
        
        # Priority 2: Request-based URL
        if request:
            return f"{request.scheme}://{request.get_host()}"
        
        # Priority 3: Settings fallback
        return getattr(settings, 'FRONTEND_URL', 'http://localhost:4028')
    
    
    # @staticmethod
    # def get_base_url(request=None, platform=None):
    #     """Get platform-specific or fallback base URL"""
    #     # Priority 1: Platform-specific domain
    #     if platform and hasattr(platform, 'domain') and platform.domain:
    #         protocol = 'http' if platform.domain.startswith(('localhost', '127.0.0.1')) else 'https'
    #         return f"{protocol}://{platform.domain}"
        
    #     # Priority 2: Request-based URL
    #     if request:
    #         return f"{request.scheme}://{request.get_host()}"
        
    #     # Priority 3: Settings fallback
    #     return getattr(settings, 'FRONTEND_URL', 'http://localhost:4028')
    
    # @staticmethod
    # def get_platform_colors(platform=None):
    #     """Get platform-specific color scheme"""
    #     if platform:
    #         return {
    #             'primary': getattr(platform, 'primary_color', '#667eea'),
    #             'secondary': getattr(platform, 'secondary_color', '#764ba2'),
    #             'accent': getattr(platform, 'accent_color', '#10B981'),
    #         }
        
    #     # Default colors
    #     return {
    #         'primary': '#667eea',
    #         'secondary': '#764ba2',
    #         'accent': '#10B981',
    #     }
    
    # @staticmethod
    # def get_platform_settings(platform=None):
    #     """Get platform-specific email settings or defaults"""
    #     default_settings = getattr(settings, 'EMAIL_TEMPLATE_SETTINGS', {})
        
    #     if platform:
    #         return {
    #             'company_name': platform.name,
    #             'company_logo': getattr(platform, 'logo_url', None) or default_settings.get('COMPANY_LOGO', ''),
    #             'support_email': getattr(platform, 'support_email', None) or default_settings.get('SUPPORT_EMAIL', 'support@peopleskilltraining.com'),
    #             'company_address': getattr(platform, 'address', None) or default_settings.get('COMPANY_ADDRESS', ''),
    #             'company_phone': getattr(platform, 'contact_phone', None) or default_settings.get('COMPANY_PHONE', ''),
    #             'from_email': getattr(platform, 'support_email', None) or settings.DEFAULT_FROM_EMAIL,
    #         }
        
    #     # Default fallback settings
    #     return {
    #         'company_name': default_settings.get('COMPANY_NAME', 'PeopleSkillTraining'),
    #         'company_logo': default_settings.get('COMPANY_LOGO', ''),
    #         'support_email': default_settings.get('SUPPORT_EMAIL', 'support@peopleskilltraining.com'),
    #         'company_address': default_settings.get('COMPANY_ADDRESS', '2313 East Venango St Ste 4B PMB 1026, Philadelphia, PA 19134, United States'),
    #         'company_phone': default_settings.get('COMPANY_PHONE', '+1 (555) 123-4567'),
    #         'from_email': settings.DEFAULT_FROM_EMAIL,
    #     }
    @staticmethod
    def get_platform_colors(platform=None):
        """Get platform-specific color scheme"""
        if platform:
            return {
                'primary': getattr(platform, 'primary_color', '#667eea'),
                'secondary': getattr(platform, 'secondary_color', '#764ba2'),
                'accent': getattr(platform, 'accent_color', '#10B981'),
            }
        
        return {
            'primary': '#667eea',
            'secondary': '#764ba2',
            'accent': '#10B981',
        }
    
    @staticmethod
    def get_platform_settings(platform=None):
        """Get platform-specific email settings or defaults"""
        default_settings = getattr(settings, 'EMAIL_TEMPLATE_SETTINGS', {})
        
        if platform:
            return {
                'company_name': platform.name,
                'company_logo': getattr(platform, 'logo_url', None) or default_settings.get('COMPANY_LOGO', ''),
                'support_email': getattr(platform, 'support_email', None) or default_settings.get('SUPPORT_EMAIL', 'support@peopleskilltraining.com'),
                'company_address': getattr(platform, 'address', None) or default_settings.get('COMPANY_ADDRESS', ''),
                'company_phone': getattr(platform, 'contact_phone', None) or default_settings.get('COMPANY_PHONE', ''),
                'from_email': getattr(platform, 'support_email', None) or settings.DEFAULT_FROM_EMAIL,
                'from_name': platform.name,
            }
        
        return {
            'company_name': default_settings.get('COMPANY_NAME', 'PeopleSkillTraining'),
            'company_logo': default_settings.get('COMPANY_LOGO', ''),
            'support_email': default_settings.get('SUPPORT_EMAIL', 'support@peopleskilltraining.com'),
            'company_address': default_settings.get('COMPANY_ADDRESS', '2313 East Venango St Ste 4B PMB 1026, Philadelphia, PA 19134, United States'),
            'company_phone': default_settings.get('COMPANY_PHONE', '+1 (555) 123-4567'),
            'from_email': settings.DEFAULT_FROM_EMAIL,
            'from_name': default_settings.get('COMPANY_NAME', 'PeopleSkillTraining'),
        }
    @classmethod
    def get_email_context(cls, user=None, request=None, platform=None, **kwargs):
        """
        Build comprehensive email context with platform branding
        
        Args:
            user: User object
            request: HTTP request object
            platform: Platform object
            **kwargs: Additional context variables
        
        Returns:
            dict: Complete email context
        """
        # Get platform from user if not explicitly provided
        if not platform and user and hasattr(user, 'platform'):
            platform = user.platform
        
        # Get platform-specific settings and colors
        platform_settings = cls.get_platform_settings(platform)
        colors = cls.get_platform_colors(platform)
        
        # Build base context
        context = {
            **platform_settings,
            'colors': colors,
            'website_url': cls.get_base_url(request, platform),
            'platform': platform,
            'platform_name': platform.name if platform else platform_settings['company_name'],
            'current_year': 2025,
        }
        
        # Add user-specific context
        if user:
            context.update({
                'user': user,
                'user_name': getattr(user, 'first_name', '') or getattr(user, 'email', '').split('@')[0],
                'user_full_name': f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip() or getattr(user, 'email', ''),
            })
        
        # Merge additional kwargs
        context.update(kwargs)
        
        return context
    # @classmethod
    # def get_email_context(cls, user=None, request=None, platform=None, **kwargs):
    #     """
    #     Build comprehensive email context with platform branding
        
    #     Args:
    #         user: User object
    #         request: HTTP request object
    #         platform: Platform object
    #         **kwargs: Additional context variables
        
    #     Returns:
    #         dict: Complete email context
    #     """
    #     # Get platform from user if not explicitly provided
    #     if not platform and user and hasattr(user, 'platform'):
    #         platform = user.platform
        
    #     # Get platform-specific settings and colors
    #     platform_settings = cls.get_platform_settings(platform)
    #     colors = cls.get_platform_colors(platform)
        
    #     # Build base context
    #     context = {
    #         **platform_settings,
    #         'colors': colors,
    #         'website_url': cls.get_base_url(request, platform),
    #         'platform': platform,
    #         'platform_name': platform.name if platform else platform_settings['company_name'],
    #         'current_year': 2025,  # Can use datetime.now().year in production
    #     }
        
    #     # Add user-specific context
    #     if user:
    #         context.update({
    #             'user': user,
    #             'user_name': getattr(user, 'first_name', '') or getattr(user, 'email', '').split('@')[0],
    #             'user_full_name': f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip() or getattr(user, 'email', ''),
    #         })
        
    #     # Merge additional kwargs
    #     context.update(kwargs)
        
    #     return context
    
    
    
    # @classmethod
    # def send_email(cls, subject, template_name, context, recipient_list, from_email=None, platform=None, attachments=None):
    #     """
    #     Send platform-branded HTML email via Brevo Transactional API
        
    #     Args:
    #         subject: Email subject line
    #         template_name: Template filename (without .html extension)
    #         context: Email template context
    #         recipient_list: List of recipient email addresses
    #         from_email: Sender email (optional, uses platform default)
    #         platform: Platform object for branding and API config
    #         attachments: List of file attachments (optional)
        
    #     Returns:
    #         dict: Brevo API response
    #     """
    #     try:
    #         # Get platform settings
    #         platform_settings = cls.get_platform_settings(platform)
            
    #         # Get sender info
    #         if from_email is None:
    #             from_email = platform_settings['from_email']
            
    #         from_name = platform_settings['from_name']
            
    #         # Render HTML content
    #         html_content = render_to_string(f'emails/{template_name}.html', context)
    #         text_content = strip_tags(html_content)
            
    #         # ✅ Get Brevo API client
    #         api_instance = cls.get_brevo_client(platform)
            
    #         # ✅ Build recipient list for Brevo
    #         brevo_recipients = [
    #             {"email": email, "name": email.split('@')[0]}
    #             for email in recipient_list
    #         ]
            
    #         # ✅ Create SendSmtpEmail object
    #         send_smtp_email = SendSmtpEmail(
    #             to=brevo_recipients,
    #             sender={"name": from_name, "email": from_email},
    #             subject=subject,
    #             html_content=html_content,
    #             text_content=text_content,
    #         )
            
    #         # ✅ Add attachments if provided
    #         if attachments:
    #             brevo_attachments = []
    #             for attachment in attachments:
    #                 if isinstance(attachment, dict):
    #                     import base64
    #                     brevo_attachments.append({
    #                         'name': attachment.get('filename'),
    #                         'content': base64.b64encode(attachment.get('content')).decode('utf-8'),
    #                     })
    #             send_smtp_email.attachment = brevo_attachments
            
    #         # ✅ Send email via Brevo API
    #         response = api_instance.send_transac_email(send_smtp_email)
            
    #         # Log success
    #         platform_name = platform.name if platform else 'System'
    #         logger.info(
    #             f"[{platform_name}] ✅ Email sent via Brevo API | "
    #             f"Message ID: {response.message_id} | "
    #             f"To: {recipient_list} | Subject: {subject}"
    #         )
            
    #         return {
    #             'success': True,
    #             'message_id': response.message_id,
    #             'recipients': recipient_list
    #         }
            
    #     except ApiException as e:
    #         platform_name = platform.name if platform else 'System'
    #         logger.error(
    #             f"[{platform_name}] ❌ Brevo API error | "
    #             f"Status: {e.status} | Body: {e.body} | "
    #             f"To: {recipient_list}", 
    #             exc_info=True
    #         )
    #         raise
            
    #     except Exception as e:
    #         platform_name = platform.name if platform else 'System'
    #         logger.error(
    #             f"[{platform_name}] ❌ Email failed | "
    #             f"To: {recipient_list} | Error: {str(e)}", 
    #             exc_info=True
    #         )
    #         raise
    
    # ============================================
# API-BASED EMAIL SERVICE CONFIGURATION
# ============================================

        
    def set_smtp_config(self, smtp_host, smtp_port, smtp_user, smtp_password, 
                        use_tls=True, use_ssl=False, from_email=None, from_name=None):
        """Configure direct SMTP email delivery"""
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
            'timeout': 30,
            'configured_at': timezone.now().isoformat(),
        }
        self.save()
        logger.info(f"[{self.name}] SMTP configured: {smtp_host}:{smtp_port}")
    
    
    
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
    # EMAIL SENDING IMPLEMENTATIONS
    # ============================================

    
    def _send_via_smtp(self, subject, body_text, body_html, to_emails,
                    cc_emails, bcc_emails, reply_to, attachments, headers):
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


    
    def _send_via_sendgrid(self, subject, body_text, body_html, to_emails,
                        cc_emails, bcc_emails, reply_to, attachments, headers):
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
            "to": [{"email": email} for email in (to_emails if isinstance(to_emails, list) else [to_emails])],
        }]
        
        if cc_emails:
            personalizations[0]["cc"] = [{"email": email} for email in cc_emails]
        if bcc_emails:
            personalizations[0]["bcc"] = [{"email": email} for email in bcc_emails]
        
        payload = {
            "personalizations": personalizations,
            "from": {"email": from_email, "name": from_name},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body_text}]
        }
        
        if body_html:
            payload["content"].append({"type": "text/html", "value": body_html})
        
        if reply_to:
            payload["reply_to"] = {"email": reply_to}
        
        if attachments:
            payload["attachments"] = []
            for attachment in attachments:
                payload["attachments"].append({
                    "content": base64.b64encode(attachment['content']).decode(),
                    "filename": attachment['filename'],
                    "type": attachment.get('mimetype', 'application/octet-stream'),
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
        
        if response.status_code in [200, 202]:
            logger.info(f"[{self.name}] SendGrid email sent to {to_emails}")
            return True, "Email sent via SendGrid API"
        else:
            logger.error(f"[{self.name}] SendGrid failed: {response.text}")
            return False, f"SendGrid API error: {response.text}"
            
    
    def _send_via_mailgun(self, subject, body_text, body_html, to_emails,
                        cc_emails, bcc_emails, reply_to, attachments, headers):
        """Send email via Mailgun API"""
        import requests
        
        config = self.email_settings
        api_key = self.decrypt_value(config.get('api_key_encrypted'))
        domain = config.get('domain')
        region = config.get('region', 'us')
        
        if not api_key or not domain:
            return False, "Missing Mailgun API key or domain"
        
        base_url = 'https://api.mailgun.net' if region == 'us' else 'https://api.eu.mailgun.net'
        url = f"{base_url}/v3/{domain}/messages"
        
        from_email = config.get('from_email')
        from_name = config.get('from_name', self.name)
        
        data = {
            'from': f"{from_name} <{from_email}>",
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
    
    def _send_via_brevo(self, subject, body_text, body_html, to_emails,
                        cc_emails, bcc_emails, reply_to, attachments, headers):
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
            "sender": {"name": from_name, "email": from_email},
            "to": [{"email": email} for email in (to_emails if isinstance(to_emails, list) else [to_emails])],
            "subject": subject,
            "textContent": body_text,
        }
        
        if body_html:
            payload["htmlContent"] = body_html
        if cc_emails:
            payload["cc"] = [{"email": email} for email in cc_emails]
        if bcc_emails:
            payload["bcc"] = [{"email": email} for email in bcc_emails]
        if reply_to:
            payload["replyTo"] = {"email": reply_to}
        
        if attachments:
            payload["attachment"] = []
            for attachment in attachments:
                payload["attachment"].append({
                    "name": attachment['filename'],
                    "content": base64.b64encode(attachment['content']).decode('utf-8')
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
            
            if response.status_code in [200, 201]:
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

# ============================================
# UNIFIED EMAIL SENDING INTERFACE
# ============================================

    
    def send_email(self, subject, body_text, body_html, to_emails, 
                cc_emails=None, bcc_emails=None, reply_to=None, 
                attachments=None, headers=None):
        """
        Unified email sending interface - works with both SMTP and API methods
        
        Returns:
            (success: bool, message: str)
        """
        try:
            method = self.email_delivery_method or 'smtp'
            
            if method == 'smtp':
                return self._send_via_smtp(
                    subject, body_text, body_html, to_emails,
                    cc_emails, bcc_emails, reply_to, attachments, headers
                )
            elif method == 'sendgrid_api':
                return self._send_via_sendgrid(
                    subject, body_text, body_html, to_emails,
                    cc_emails, bcc_emails, reply_to, attachments, headers
                )
            elif method == 'mailgun_api':
                return self._send_via_mailgun(
                    subject, body_text, body_html, to_emails,
                    cc_emails, bcc_emails, reply_to, attachments, headers
                )
            elif method == 'brevo_api':
                return self._send_via_brevo(
                    subject, body_text, body_html, to_emails,
                    cc_emails, bcc_emails, reply_to, attachments, headers
                )
            else:
                return False, f"Unsupported email delivery method: {method}"
                
        except Exception as e:
            logger.error(f"[{self.name}] Email send failed: {e}", exc_info=True)
            return False, str(e)

    # @classmethod
    # def send_email(cls, subject, template_name, context, recipient_list, from_email=None, platform=None, attachments=None, bcc=None):
    #     """
    #     Send platform-branded HTML email via Brevo Transactional API
        
    #     Args:
    #         subject: Email subject line
    #         template_name: Template filename (without .html extension)
    #         context: Email template context
    #         recipient_list: List of recipient email addresses
    #         from_email: Sender email (optional, uses platform default)
    #         platform: Platform object for branding and API config
    #         attachments: List of file attachments (optional)
    #         bcc: List of BCC email addresses (optional) - ✅ NEW
        
    #     Returns:
    #         dict: Brevo API response
    #     """
    #     try:
    #         # Get platform settings
    #         platform_settings = cls.get_platform_settings(platform)
            
    #         # Get sender info
    #         if from_email is None:
    #             from_email = platform_settings['from_email']
            
    #         from_name = platform_settings['from_name']
            
    #         # Render HTML content
    #         html_content = render_to_string(f'emails/{template_name}.html', context)
    #         text_content = strip_tags(html_content)
            
    #         # ✅ Get Brevo API client
    #         api_instance = cls.get_brevo_client(platform)
            
    #         # ✅ Build recipient list for Brevo
    #         brevo_recipients = [
    #             {"email": email, "name": email.split('@')[0]}
    #             for email in recipient_list
    #         ]
            
    #         # ✅ Build BCC list for Brevo
    #         brevo_bcc = []
    #         if bcc:
    #             brevo_bcc = [
    #                 {"email": email, "name": email.split('@')[0]}
    #                 for email in bcc
    #             ]
            
    #         # ✅ Create SendSmtpEmail object
    #         send_smtp_email = SendSmtpEmail(
    #             to=brevo_recipients,
    #             sender={"name": from_name, "email": from_email},
    #             subject=subject,
    #             html_content=html_content,
    #             text_content=text_content,
    #             bcc=brevo_bcc if brevo_bcc else None  # ✅ Add BCC support
    #         )
            
    #         # ✅ Add attachments if provided
    #         if attachments:
    #             brevo_attachments = []
    #             for attachment in attachments:
    #                 if isinstance(attachment, dict):
    #                     import base64
    #                     brevo_attachments.append({
    #                         'name': attachment.get('filename'),
    #                         'content': base64.b64encode(attachment.get('content')).decode('utf-8'),
    #                     })
    #             send_smtp_email.attachment = brevo_attachments
            
    #         # ✅ Send email via Brevo API
    #         response = api_instance.send_transac_email(send_smtp_email)
            
    #         # Log success
    #         platform_name = platform.name if platform else 'System'
    #         bcc_info = f" | BCC: {bcc}" if bcc else ""
    #         logger.info(
    #             f"[{platform_name}] ✅ Email sent via Brevo API | "
    #             f"Message ID: {response.message_id} | "
    #             f"To: {recipient_list}{bcc_info} | Subject: {subject}"
    #         )
            
    #         return {
    #             'success': True,
    #             'message_id': response.message_id,
    #             'recipients': recipient_list,
    #             'bcc': bcc if bcc else []
    #         }
            
    #     except ApiException as e:
    #         platform_name = platform.name if platform else 'System'
    #         logger.error(
    #             f"[{platform_name}] ❌ Brevo API error | "
    #             f"Status: {e.status} | Body: {e.body} | "
    #             f"To: {recipient_list}", 
    #             exc_info=True
    #         )
    #         raise
            
    #     except Exception as e:
    #         platform_name = platform.name if platform else 'System'
    #         logger.error(
    #             f"[{platform_name}] ❌ Email failed | "
    #             f"To: {recipient_list} | Error: {str(e)}", 
    #             exc_info=True
    #         )
    #         raise

    
    
    
    # @classmethod
    # def send_email(cls, subject, template_name, context, recipient_list, from_email=None, platform=None, attachments=None):
    #     """
    #     Send platform-branded HTML email with platform-specific SMTP connection
        
    #     Args:
    #         subject: Email subject line
    #         template_name: Template filename (without .html extension)
    #         context: Email template context
    #         recipient_list: List of recipient email addresses
    #         from_email: Sender email (optional, uses platform default)
    #         platform: Platform object for branding and SMTP config
    #         attachments: List of file attachments (optional)
        
    #     Returns:
    #         int: Number of emails sent
    #     """
    #     try:
    #         # ✅ Get platform-specific SMTP connection
    #         connection = None
    #         smtp_info = "default SMTP"
            
    #         if platform:
    #             connection = platform.get_email_connection()
    #             smtp_info = platform.email_settings.get('smtp_host', 'default') if platform.email_settings else 'default'
                
    #             # Use platform's from_email if not provided
    #             if from_email is None:
    #                 from_email = platform.get_from_email()
    #                 from_name = platform.get_from_name()
    #                 # Format as "Name <email@domain.com>"
    #                 from_email = f"{from_name} <{from_email}>"
    #         else:
    #             from_email = from_email or settings.DEFAULT_FROM_EMAIL
            
    #         # Render HTML and text versions
    #         html_content = render_to_string(f'emails/{template_name}.html', context)
    #         text_content = strip_tags(html_content)
            
    #         # Create email message with platform-specific connection
    #         msg = EmailMultiAlternatives(
    #             subject=subject,
    #             body=text_content,
    #             from_email=from_email,
    #             to=recipient_list,
    #             connection=connection  # ✅ Platform-specific SMTP connection
    #         )
            
    #         # Attach HTML alternative
    #         msg.attach_alternative(html_content, "text/html")
            
    #         # Add attachments if provided
    #         if attachments:
    #             for attachment in attachments:
    #                 if isinstance(attachment, dict):
    #                     msg.attach(
    #                         attachment.get('filename'),
    #                         attachment.get('content'),
    #                         attachment.get('mimetype', 'application/octet-stream')
    #                     )
    #                 else:
    #                     msg.attach_file(attachment)
            
    #         # Send email
    #         result = msg.send()
            
    #         # Log success with SMTP info
    #         platform_name = platform.name if platform else 'System'
    #         logger.info(
    #             f"[{platform_name}] ✅ Email sent via {smtp_info} | "
    #             f"To: {recipient_list} | Subject: {subject}"
    #         )
            
    #         return result
            
    #     except Exception as e:
    #         platform_name = platform.name if platform else 'System'
    #         logger.error(
    #             f"[{platform_name}] ❌ Email failed via {smtp_info} | "
    #             f"To: {recipient_list} | Error: {str(e)}", 
    #             exc_info=True
    #         )
    #         raise
    
    # ============================================
    # VERIFICATION EMAILS
    # ============================================
    # In EmailService class
    @classmethod
    def send_verification_email(cls, user, verification_token, request=None, platform=None):
        """Send email verification with platform branding"""
        platform = platform or getattr(user, 'platform', None)
        base_url = cls.get_base_url(request, platform)
        verification_url = f"{base_url}/verify-email?token={verification_token}&email={user.email}"
        
        context = cls.get_email_context(
            user=user,
            request=request,
            platform=platform,
            verification_url=verification_url,
            verification_token=verification_token,
            subject="Verify Your Email Address"
        )
        
        company_name = platform.name if platform else 'PeopleSkillTraining'
        
        # Render email content
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags
        
        html_content = render_to_string('emails/verify_email.html', context)
        text_content = strip_tags(html_content)
        
        # ✅ USE PLATFORM'S send_email() METHOD
        if platform:
            return platform.send_email(
                subject=f"🔐 Verify Your {company_name} Account",
                body_text=text_content,
                body_html=html_content,
                to_emails=[user.email]
            )
        else:
            # Fallback to Django default email
            from django.core.mail import send_mail
            return send_mail(
                subject=f"🔐 Verify Your {company_name} Account",
                message=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_content
            )

    # @classmethod
    # def send_verification_email(cls, user, verification_token, request=None, platform=None):
    #     """Send email verification with platform branding"""
    #     platform = platform or getattr(user, 'platform', None)
    #     base_url = cls.get_base_url(request, platform)
    #     verification_url = f"{base_url}/verify-email?token={verification_token}&email={user.email}"
        
    #     context = cls.get_email_context(
    #         user=user,
    #         request=request,
    #         platform=platform,
    #         verification_url=verification_url,
    #         verification_token=verification_token,
    #         subject="Verify Your Email Address"
    #     )
        
    #     company_name = platform.name if platform else 'PeopleSkillTraining'
        
    #     return cls.send_email(
    #         subject=f"🔐 Verify Your {company_name} Account",
    #         template_name="verify_email",
    #         context=context,
    #         recipient_list=[user.email],
    #         platform=platform
    #     )
    
    # @classmethod
    # def send_verification_email(cls, user, verification_token, request=None, platform=None):
    #     """Send email verification with platform branding"""
    #     platform = platform or getattr(user, 'platform', None)
    #     base_url = cls.get_base_url(request, platform)
    #     verification_url = f"{base_url}/verify-email?token={verification_token}&email={user.email}"
        
    #     context = cls.get_email_context(
    #         user=user,
    #         request=request,
    #         platform=platform,
    #         verification_url=verification_url,
    #         verification_token=verification_token,
    #         subject="Verify Your Email Address"
    #     )
        
    #     company_name = platform.name if platform else 'PeopleSkillTraining'
        
    #     return cls.send_email(
    #         subject=f"🔐 Verify Your {company_name} Account",
    #         template_name="verify_email",
    #         context=context,
    #         recipient_list=[user.email],
    #         platform=platform
    #     )
    @classmethod
    def send_resend_verification_email(cls, user, verification_token, request=None, platform=None):
        """Resend verification email"""
        platform = platform or getattr(user, 'platform', None)
        base_url = cls.get_base_url(request, platform)
        verification_url = f"{base_url}/verify-email?token={verification_token}&email={user.email}"
        
        context = cls.get_email_context(
            user=user,
            request=request,
            platform=platform,
            verification_url=verification_url,
            verification_token=verification_token,
            subject="Verify Your Email Address",
            is_resend=True
        )
        
        company_name = platform.name if platform else 'PeopleSkillTraining'
        
        return cls.send_email(
            subject=f"🔄 Email Verification - {company_name}",
            template_name="verify_email",
            context=context,
            recipient_list=[user.email],
            platform=platform
        )
    
    # @classmethod
    # def send_resend_verification_email(cls, user, verification_token, request=None, platform=None):
    #     """Resend verification email"""
    #     platform = platform or getattr(user, 'platform', None)
    #     base_url = cls.get_base_url(request, platform)
    #     verification_url = f"{base_url}/verify-email?token={verification_token}&email={user.email}"
        
    #     context = cls.get_email_context(
    #         user=user,
    #         request=request,
    #         platform=platform,
    #         verification_url=verification_url,
    #         verification_token=verification_token,
    #         subject="Verify Your Email Address",
    #         is_resend=True
    #     )
        
    #     company_name = platform.name if platform else 'PeopleSkillTraining'
        
    #     return cls.send_email(
    #         subject=f"🔄 Email Verification - {company_name}",
    #         template_name="verify_email",
    #         context=context,
        #     recipient_list=[user.email],
        #     platform=platform
        # )
    @classmethod
    def send_verification_success_email(cls, user, request=None, platform=None):
        """Send verification success confirmation"""
        platform = platform or getattr(user, 'platform', None)
        base_url = cls.get_base_url(request, platform)
        login_url = f"{base_url}/login"
        dashboard_url = f"{base_url}/{user.role}"
        
        context = cls.get_email_context(
            user=user,
            request=request,
            platform=platform,
            login_url=login_url,
            dashboard_url=dashboard_url,
            subject="Email Verified Successfully!"
        )
        
        company_name = platform.name if platform else 'PeopleSkillTraining'
        
        return cls.send_email(
            subject=f"✅ Welcome to {company_name}!",
            template_name="verification_success",
            context=context,
            recipient_list=[user.email],
            platform=platform
        )
    
    # @classmethod
    # def send_verification_success_email(cls, user, request=None, platform=None):
    #     """Send verification success confirmation"""
    #     platform = platform or getattr(user, 'platform', None)
    #     base_url = cls.get_base_url(request, platform)
    #     login_url = f"{base_url}/login"
    #     dashboard_url = f"{base_url}/{user.role}"
        
    #     context = cls.get_email_context(
    #         user=user,
    #         request=request,
    #         platform=platform,
    #         login_url=login_url,
    #         dashboard_url=dashboard_url,
    #         subject="Email Verified Successfully!"
    #     )
        
    #     company_name = platform.name if platform else 'PeopleSkillTraining'
        
    #     return cls.send_email(
    #         subject=f"✅ Welcome to {company_name}!",
    #         template_name="verification_success",
    #         context=context,
    #         recipient_list=[user.email],
    #         platform=platform
    #     )
    
    # ============================================
    # INSTRUCTOR EMAILS
    # ============================================
    
    @classmethod
    def send_instructor_approval_email(cls, user, request=None, platform=None):
        """Send instructor approval notification"""
        platform = platform or getattr(user, 'platform', None)
        base_url = cls.get_base_url(request, platform)
        dashboard_url = f"{base_url}/instructor/dashboard"
        help_url = f"{base_url}/help/instructor-guide"
        
        # Get platform settings for support email
        platform_settings = cls.get_platform_settings(platform)
        
        context = cls.get_email_context(
            user=user,
            request=request,
            platform=platform,
            dashboard_url=dashboard_url,
            help_url=help_url,
            support_email=platform_settings.get('support_email', 'support@peopleskilltraining.com'),
            subject="Instructor Application Approved!"
        )
        
        company_name = platform.name if platform else 'PeopleSkillTraining'
        
        return cls.send_email(
            subject=f"🎉 Welcome to {company_name} Instructors!",
            template_name="instructor_approved",
            context=context,
            recipient_list=[user.email],
            platform=platform
        )
    
    # ============================================
    # PASSWORD RESET
    # ============================================
    
    @classmethod
    def send_password_reset_email(cls, user, reset_token, request=None, platform=None):
        """Send password reset link"""
        platform = platform or getattr(user, 'platform', None)
        base_url = cls.get_base_url(request, platform)
        reset_url = f"{base_url}/reset-password?token={reset_token}&email={user.email}"
        
        context = cls.get_email_context(
            user=user,
            request=request,
            platform=platform,
            reset_url=reset_url,
            reset_token=reset_token,
            subject="Reset Your Password"
        )
        
        company_name = platform.name if platform else 'PeopleSkillTraining'
        
        return cls.send_email(
            subject=f"🔑 Reset Your {company_name} Password",
            template_name="password_reset",
            context=context,
            recipient_list=[user.email],
            platform=platform
        )
    
    # ============================================
    # WEBINAR EMAILS
    # ============================================
    
    @classmethod
    def send_webinar_reminder(cls, user, webinar, time_until_start, request=None, platform=None):
        """Send webinar reminder notification"""
        platform = platform or getattr(user, 'platform', None)
        base_url = cls.get_base_url(request, platform)
        join_url = f"{base_url}/webinars/{webinar.webinar_id}/join"
        cancel_url = f"{base_url}/enrollments/cancel/{webinar.id}"
        reschedule_url = f"{base_url}/webinars"
        
        context = cls.get_email_context(
            user=user,
            request=request,
            platform=platform,
            webinar=webinar,
            time_until_start=time_until_start,
            join_url=join_url,
            cancel_url=cancel_url,
            reschedule_url=reschedule_url,
            subject=f"Reminder: {webinar.title}"
        )
        
        return cls.send_email(
            subject=f"⏰ Reminder: {webinar.title} starts in {time_until_start}!",
            template_name="webinar_reminder",
            context=context,
            recipient_list=[user.email],
            platform=platform
        )
    
    # ============================================
    # PAYMENT EMAILS
    # ============================================
    
    @classmethod
    def send_payment_confirmation_email(cls, user, order, request=None, platform=None):
        """Send payment confirmation with order details"""
        platform = platform or getattr(user, 'platform', None) or getattr(order, 'platform', None)
        base_url = cls.get_base_url(request, platform)
        dashboard_url = f"{base_url}/attendee/orders"
        invoice_url = f"{base_url}/invoices/{order.order_id}"
        
        # Build webinar list from order items
        webinar_list = []
        for item in order.items.all():
            webinar_list.append({
                'title': item.webinar.title,
                'instructor': item.webinar.speaker.user.get_full_name() if item.webinar.speaker else 'TBD',
                'scheduled_date': item.webinar.scheduled_date.strftime('%B %d, %Y at %I:%M %p') if item.webinar.scheduled_date else 'On Demand',
                'duration': f"{item.webinar.duration} minutes" if item.webinar.duration else 'Self-paced',
                'webinar_url': f"{base_url}/webinars/{item.webinar.webinar_id}"
            })
        
        context = cls.get_email_context(
            user=user,
            request=request,
            platform=platform,
            order=order,
            webinars=webinar_list,
            total_amount=f"{order.total_amount:.2f}",
            currency=order.currency,
            transaction_id=order.transaction_id,
            payment_method=order.payment_method.title() if hasattr(order, 'payment_method') else 'N/A',
            payment_date=order.created_at.strftime('%B %d, %Y at %I:%M %p'),
            dashboard_url=dashboard_url,
            invoice_url=invoice_url,
            subject="Payment Confirmation"
        )
        
        return cls.send_email(
            subject=f"✅ Payment Confirmed - Order #{order.order_id}",
            template_name="payment_confirmation",
            context=context,
            recipient_list=[user.email],
            platform=platform
        )


# ============================================
# CELERY TASKS - ASYNC EMAIL SENDING
# ============================================


@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,))
def send_verification_email_task(self, user_id, verification_token):
    """Async: Send verification email"""
    try:
        user = User.objects.select_related('platform').get(id=user_id)
        EmailService.send_verification_email(user, verification_token, platform=user.platform)
        logger.info(f"[{user.platform.name if user.platform else 'System'}] Verification email sent to {user.email}")
    except Exception as exc:
        logger.error(f"Failed to send verification email: {exc}")
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,))
def send_resend_verification_email_task(self, user_id, verification_token):
    """Async: Resend verification email"""
    try:
        user = User.objects.select_related('platform').get(id=user_id)
        EmailService.send_resend_verification_email(user, verification_token, platform=user.platform)
        logger.info(f"[{user.platform.name if user.platform else 'System'}] Resend verification to {user.email}")
    except Exception as exc:
        logger.error(f"Failed to resend verification: {exc}")
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,))
def send_verification_success_email_task(self, user_id):
    """Async: Send verification success email"""
    try:
        user = User.objects.select_related('platform').get(id=user_id)
        EmailService.send_verification_success_email(user, platform=user.platform)
        logger.info(f"[{user.platform.name if user.platform else 'System'}] Success email sent to {user.email}")
    except Exception as exc:
        logger.error(f"Failed to send success email: {exc}")
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,))
def send_instructor_approval_email_task(self, user_id):
    """Async: Send instructor approval email"""
    try:
        user = User.objects.select_related('platform').get(id=user_id)
        EmailService.send_instructor_approval_email(user, platform=user.platform)
        logger.info(f"[{user.platform.name if user.platform else 'System'}] Instructor approval sent to {user.email}")
    except Exception as exc:
        logger.error(f"Failed to send instructor approval: {exc}")
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,))
def send_password_reset_email_task(self, user_id, reset_token):
    """Async: Send password reset email"""
    try:
        user = User.objects.select_related('platform').get(id=user_id)
        EmailService.send_password_reset_email(user, reset_token, platform=user.platform)
        logger.info(f"[{user.platform.name if user.platform else 'System'}] Password reset sent to {user.email}")
    except Exception as exc:
        logger.error(f"Failed to send password reset: {exc}")
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,))
def send_webinar_reminder_task(self, user_id, webinar_id, time_until_start):
    """Async: Send webinar reminder"""
    try:
        user = User.objects.select_related('platform').get(id=user_id)
        from apps.webinars.models import Webinar
        webinar = Webinar.objects.select_related('speaker__user').get(id=webinar_id)
        EmailService.send_webinar_reminder(user, webinar, time_until_start, platform=user.platform)
        logger.info(f"[{user.platform.name if user.platform else 'System'}] Webinar reminder sent to {user.email}")
    except Exception as exc:
        logger.error(f"Failed to send webinar reminder: {exc}")
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,))
def send_payment_confirmation_email_task(self, user_id, order_id):
    """Async: Send payment confirmation email"""
    try:
        user = User.objects.select_related('platform').get(id=user_id)
        from apps.orders.models import Order
        order = Order.objects.select_related('platform').prefetch_related('items__webinar__speaker__user').get(id=order_id)
        
        EmailService.send_payment_confirmation_email(user, order, platform=order.platform)
        logger.info(f"[{order.platform.name if order.platform else 'System'}] Payment confirmation sent to {user.email}")
    except Exception as exc:
        logger.error(f"Failed to send payment confirmation: {exc}")
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
