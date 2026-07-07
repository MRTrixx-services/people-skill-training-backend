from django.contrib import admin
from django import forms
from django.utils.html import format_html
from django.contrib import messages
from .models import Platform, PlatformStats, PlatformAPILog


class PlatformEmailConfigForm(forms.ModelForm):
    """
    Email configuration form supporting both Direct SMTP and Brevo API
    """
    
    # ============================================
    # SMTP CONFIGURATION FIELDS
    # ============================================
    
    smtp_host = forms.CharField(
        required=False,
        label="SMTP Host",
        help_text="e.g., smtp.gmail.com or businessemail.webeyesoft.com",
        widget=forms.TextInput(attrs={
            'placeholder': 'smtp.example.com',
            'size': 60
        })
    )
    
    smtp_port = forms.IntegerField(
        required=False,
        initial=587,
        label="SMTP Port",
        help_text="Usually 587 (TLS) or 465 (SSL)",
        widget=forms.NumberInput(attrs={
            'style': 'width: 120px;'
        })
    )
    
    smtp_user = forms.CharField(
        required=False,
        label="SMTP Username",
        help_text="Usually your email address",
        widget=forms.TextInput(attrs={
            'placeholder': 'your-email@domain.com',
            'size': 60
        })
    )
    
    smtp_password = forms.CharField(
        required=False,
        label="SMTP Password",
        help_text="⚠️ Will be encrypted before storage. Leave blank to keep existing password.",
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Enter password',
            'autocomplete': 'new-password',
            'size': 60
        })
    )
    
    use_tls = forms.BooleanField(
        required=False,
        initial=True,
        label="Use TLS",
        help_text="Enable for port 587"
    )
    
    use_ssl = forms.BooleanField(
        required=False,
        initial=False,
        label="Use SSL",
        help_text="Enable for port 465"
    )
    
    # ============================================
    # BREVO API CONFIGURATION
    # ============================================
    
    brevo_api_key = forms.CharField(
        required=False,
        label="Brevo API Key",
        help_text="Your Brevo (Sendinblue) API key (will be encrypted)",
        widget=forms.PasswordInput(attrs={
            'placeholder': 'xkeysib-xxxxxxxxxxxxx',
            'size': 60,
            'autocomplete': 'new-password'
        })
    )
    
    # ============================================
    # COMMON FIELDS
    # ============================================
    
    from_email = forms.EmailField(
        required=False,
        label="From Email",
        help_text="Email address shown as sender (must be verified in Brevo for API method)",
        widget=forms.EmailInput(attrs={
            'placeholder': 'noreply@yourdomain.com',
            'size': 60
        })
    )
    
    from_name = forms.CharField(
        required=False,
        label="From Name",
        help_text="Name shown as sender",
        widget=forms.TextInput(attrs={
            'placeholder': 'Your Platform Name',
            'size': 60
        })
    )
    
    class Meta:
        model = Platform
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate fields if platform exists and has configuration
        if self.instance.pk and self.instance.email_settings:
            config = self.instance.email_settings
            method = self.instance.email_delivery_method
            
            # SMTP fields
            if method == 'smtp':
                self.fields['smtp_host'].initial = config.get('smtp_host')
                self.fields['smtp_port'].initial = config.get('smtp_port', 587)
                self.fields['smtp_user'].initial = config.get('smtp_user')
                self.fields['use_tls'].initial = config.get('use_tls', True)
                self.fields['use_ssl'].initial = config.get('use_ssl', False)
            
            # Common fields (for both methods)
            self.fields['from_email'].initial = config.get('from_email')
            self.fields['from_name'].initial = config.get('from_name')
    
    def clean(self):
        cleaned_data = super().clean()
        email_delivery_method = cleaned_data.get('email_delivery_method')
        
        # Validation based on selected method
        if email_delivery_method == 'smtp':
            smtp_host = cleaned_data.get('smtp_host')
            smtp_password = cleaned_data.get('smtp_password')
            use_tls = cleaned_data.get('use_tls')
            use_ssl = cleaned_data.get('use_ssl')
            
            # Validate TLS/SSL
            if use_tls and use_ssl:
                raise forms.ValidationError(
                    "Cannot use both TLS and SSL. Choose one: TLS (port 587) or SSL (port 465)"
                )
            
            # Check if SMTP is being configured for the first time
            if not self.instance.pk or not self.instance.has_email_config:
                if smtp_host and not smtp_password:
                    raise forms.ValidationError(
                        "SMTP password is required when configuring SMTP for the first time"
                    )
        
        elif email_delivery_method == 'brevo_api':
            brevo_api_key = cleaned_data.get('brevo_api_key')
            
            # Check if Brevo is being configured for the first time
            if not self.instance.pk or not self.instance.has_email_config:
                if not brevo_api_key:
                    raise forms.ValidationError(
                        "Brevo API key is required when configuring Brevo email for the first time"
                    )
        
        return cleaned_data


@admin.register(Platform)
class PlatformAdmin(admin.ModelAdmin):
    form = PlatformEmailConfigForm
    
    list_display = [
        'platform_id', 'name', 'email_status_badge', 'verification_status_badge',
        'bcc_status_badge', 'is_active', 'is_default', 'invoice_prefix', 
        'maintenance_mode', 'user_count', 'created_at', 'last_used_at'
    ]
    
    list_filter = [
        'is_active', 'is_default', 'maintenance_mode', 
        'email_delivery_method', 'requires_email_verification', 'created_at'
    ]
    search_fields = ['platform_id', 'name', 'domain', 'support_email', 'contact_email']
    
    readonly_fields = [
        'api_key', 'api_key_hash', 'created_at', 'updated_at', 'last_used_at',
        'email_config_display', 'bcc_recipients_display', 'email_help_links',
        'verification_workflow_display'
    ]
    
    actions = ['send_test_emails', 'enable_verification', 'disable_verification']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('platform_id', 'name', 'description', 'invoice_prefix')
        }),
        
        ('Authentication', {
            'fields': ('api_key', 'api_key_hash'),
            'classes': ('collapse',)
        }),
        
        ('Domain & CORS', {
            'fields': ('domain', 'allowed_origins')
        }),
        
        ('✉️ Email Verification Settings', {
            'fields': (
                'requires_email_verification',
                'verification_workflow_display',
            ),
            'description': (
                '<div style="background: #fff3e0; padding: 15px; border-left: 4px solid #ff9800; margin-bottom: 15px;">'
                '<strong>📋 Email Verification Workflow:</strong><br><br>'
                
                '<strong>✅ Enabled (Default):</strong><br>'
                '• User registers → Receives verification email<br>'
                '• User must click verification link → Account activated<br>'
                '• User can then login<br>'
                '• Best for: Public platforms, customer-facing applications<br><br>'
                
                '<strong>⚡ Disabled (Auto-Verify):</strong><br>'
                '• User registers → Immediately verified<br>'
                '• Receives welcome email instead of verification email<br>'
                '• Can login immediately after registration<br>'
                '• Best for: Internal platforms, trusted environments, B2B systems<br><br>'
                
                '<strong>💡 Use Cases:</strong><br>'
                '• <strong>PeopleSkillTraining</strong> (Internal): Disable verification<br>'
                '• <strong>PeopleSkillTraining</strong> (Public): Enable verification<br>'
                '• <strong>DailyRespond</strong> (Client Portal): Based on your preference'
                '</div>'
            )
        }),
        
        ('📧 Email Configuration', {
            'fields': (
                'support_email',
                'contact_email',
                'email_delivery_method',
                
                # SMTP Fields
                'smtp_host',
                'smtp_port',
                'smtp_user',
                'smtp_password',
                'use_tls',
                'use_ssl',
                
                # Brevo Fields
                'brevo_api_key',
                
                # Common Fields
                'from_email',
                'from_name',
                
                # Status displays
                'email_config_display',
                'bcc_recipients_display',
                'email_help_links',
            ),
            'description': (
                '<div style="background: #e3f2fd; padding: 15px; border-left: 4px solid #2196f3; margin-bottom: 15px;">'
                '<strong>📧 Email Configuration Guide:</strong><br><br>'
                
                '<strong>1️⃣ Select Email Delivery Method:</strong><br>'
                '• <strong>Direct SMTP:</strong> Use your own email server or Gmail/Outlook<br>'
                '• <strong>Brevo API:</strong> Use Brevo\'s transactional email service<br><br>'
                
                '<strong>2️⃣ Configure Based on Method:</strong><br><br>'
                
                '<strong>For Direct SMTP:</strong><br>'
                '• Fill in SMTP Host, Port, Username, Password<br>'
                '• Choose TLS (port 587) or SSL (port 465)<br>'
                '• Example: Gmail uses smtp.gmail.com:587 with TLS<br><br>'
                
                '<strong>For Brevo API:</strong><br>'
                '• Get API key from: <a href="https://app.brevo.com/settings/keys/api" target="_blank">Brevo Dashboard</a><br>'
                '• Verify your sender email in Brevo<br><br>'
                
                '<strong>3️⃣ Common Settings (Both Methods):</strong><br>'
                '• <strong>Support Email:</strong> Public customer support email<br>'
                '• <strong>Contact Email:</strong> Admin email for BCC notifications<br>'
                '• <strong>From Email:</strong> Sender email address<br>'
                '• <strong>From Name:</strong> Sender display name<br><br>'
                
                '<strong>🔒 Security:</strong> All passwords and API keys are encrypted using Fernet before database storage.'
                '</div>'
            )
        }),
        
        ('Branding', {
            'fields': ('logo', 'favicon', 'primary_color', 'secondary_color', 'accent_color')
        }),
        
        ('Contact', {
            'fields': ('contact_phone', 'address', 'social_links')
        }),
        
        ('Configuration', {
            'fields': ('settings', 'features', 'payment_settings', 'analytics'),
            'classes': ('collapse',)
        }),
        
        ('Security', {
            'fields': ('allowed_ip_addresses',),
            'classes': ('collapse',)
        }),
        
        ('Status', {
            'fields': ('is_active', 'is_default', 'maintenance_mode')
        }),
        
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'last_used_at'),
            'classes': ('collapse',)
        }),
    )
    
    # ============================================
    # CUSTOM DISPLAY METHODS
    # ============================================
    
    def verification_status_badge(self, obj):
        """Display email verification requirement status"""
        if obj.requires_email_verification:
            return format_html(
                '<span style="background-color: #ff9800; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-size: 11px; font-weight: bold;" '
                'title="Users must verify email before login">✉️ REQUIRED</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #4caf50; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-size: 11px; font-weight: bold;" '
                'title="Users are auto-verified on registration">⚡ AUTO</span>'
            )
    verification_status_badge.short_description = 'Verification'
    
    def verification_workflow_display(self, obj):
        """Display current verification workflow configuration"""
        if not obj.pk:
            return format_html(
                '<div style="padding: 12px; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px;">'
                '💡 Save the platform first to see workflow details'
                '</div>'
            )
        
        if obj.requires_email_verification:
            return format_html(
                '<div style="padding: 15px; background: #fff3e0; border-left: 4px solid #ff9800; border-radius: 4px;">'
                '<strong style="color: #e65100;">✉️ Email Verification REQUIRED</strong><br><br>'
                
                '<strong>Registration Flow:</strong><br>'
                '<ol style="margin: 10px 0; padding-left: 20px; color: #bf360c;">'
                '<li>User submits registration form</li>'
                '<li>Account created with <code>is_verified=False</code></li>'
                '<li><strong>Verification email sent</strong> with unique token</li>'
                '<li>User clicks verification link</li>'
                '<li>Account activated (<code>is_verified=True</code>)</li>'
                '<li>Welcome email sent</li>'
                '<li>User can now login</li>'
                '</ol>'
                
                '<div style="background: #ffecb3; padding: 10px; border-radius: 4px; margin-top: 10px;">'
                '<strong>📧 Emails Sent:</strong><br>'
                '• Registration → Verification Email<br>'
                '• After Verification → Welcome Email'
                '</div>'
                '</div>'
            )
        else:
            return format_html(
                '<div style="padding: 15px; background: #e8f5e9; border-left: 4px solid #4caf50; border-radius: 4px;">'
                '<strong style="color: #1b5e20;">⚡ Auto-Verification ENABLED</strong><br><br>'
                
                '<strong>Registration Flow:</strong><br>'
                '<ol style="margin: 10px 0; padding-left: 20px; color: #2e7d32;">'
                '<li>User submits registration form</li>'
                '<li>Account created with <code>is_verified=True</code></li>'
                '<li><strong>Auto-login tokens generated</strong></li>'
                '<li>Welcome email sent immediately</li>'
                '<li>User logged in and redirected to dashboard</li>'
                '</ol>'
                
                '<div style="background: #c8e6c9; padding: 10px; border-radius: 4px; margin-top: 10px;">'
                '<strong>📧 Email Sent:</strong><br>'
                '• Registration → Welcome Email (no verification needed)'
                '</div>'
                
                '<div style="background: #fff9c4; padding: 10px; border-radius: 4px; margin-top: 10px; border-left: 3px solid #fbc02d;">'
                '<strong>⚠️ Security Notice:</strong><br>'
                'Auto-verification is recommended only for:<br>'
                '• Internal company platforms<br>'
                '• Trusted B2B environments<br>'
                '• Systems with other authentication layers'
                '</div>'
                '</div>'
            )
    verification_workflow_display.short_description = 'Current Workflow'
    
    def email_status_badge(self, obj):
        """Display email configuration status"""
        if obj.has_email_config:
            method = obj.email_delivery_method or 'smtp'
            method_display = dict(obj._meta.get_field('email_delivery_method').choices).get(
                method, method
            ).upper()
            
            color = '#0084ff' if method == 'brevo_api' else '#28a745'
            
            return format_html(
                '<span style="background-color: {}; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-size: 11px; font-weight: bold;">✅ {}</span>',
                color,
                method_display
            )
        elif obj.email_delivery_method:
            method_display = dict(obj._meta.get_field('email_delivery_method').choices).get(
                obj.email_delivery_method,
                obj.email_delivery_method
            )
            return format_html(
                '<span style="background-color: #ffc107; color: black; padding: 3px 10px; '
                'border-radius: 3px; font-size: 11px; font-weight: bold;">⚙️ {}</span>',
                method_display
            )
        return format_html(
            '<span style="background-color: #dc3545; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">❌ NOT SET</span>'
        )
    email_status_badge.short_description = 'Email'
    
    def bcc_status_badge(self, obj):
        """Display BCC configuration status"""
        bcc_emails = obj.get_admin_emails_for_bcc()
        
        if bcc_emails:
            email_count = len(bcc_emails)
            return format_html(
                '<span style="background-color: #17a2b8; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-size: 11px; font-weight: bold;" '
                'title="{}">📧 {} BCC</span>',
                ', '.join(bcc_emails),
                email_count
            )
        return format_html(
            '<span style="background-color: #6c757d; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">⚠️ NO BCC</span>'
        )
    bcc_status_badge.short_description = 'BCC'
    
    def bcc_recipients_display(self, obj):
        """Display BCC recipients for email notifications"""
        if not obj.pk:
            return format_html(
                '<div style="padding: 12px; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px;">'
                '💡 Save the platform first to configure BCC recipients.'
                '</div>'
            )
        
        bcc_emails = obj.get_admin_emails_for_bcc()
        
        if bcc_emails:
            email_list = '<br>'.join([
                f'<span style="color: #28a745; font-weight: bold;">✓ {email}</span>'
                for email in bcc_emails
            ])
            
            return format_html(
                '<div style="padding: 12px; background: #d4edda; border-left: 4px solid #28a745; border-radius: 4px;">'
                '<strong style="color: #155724;">📧 BCC Recipients (Payment Notifications)</strong><br><br>'
                '{}<br><br>'
                '<small style="color: #155724;">ℹ️ All payment confirmation emails will be BCC\'d to these addresses</small>'
                '</div>',
                email_list
            )
        else:
            return format_html(
                '<div style="padding: 12px; background: #fff3cd; border-left: 4px solid #ffc107; border-radius: 4px;">'
                '<strong style="color: #856404;">⚠️ No BCC Recipients Configured</strong><br><br>'
                'To receive BCC copies of payment confirmations:<br>'
                '• Set <strong>Contact Email</strong> for admin notifications, or<br>'
                '• Set <strong>Support Email</strong> as fallback<br><br>'
                '<small>Priority: Contact Email → Support Email</small>'
                '</div>'
            )
    bcc_recipients_display.short_description = 'BCC Recipients'
    
    def email_help_links(self, obj):
        """Display helpful links based on email delivery method"""
        if not obj.pk:
            return "—"
        
        method = obj.email_delivery_method
        
        if method == 'brevo_api':
            return format_html(
                '<div style="padding: 10px; background: #e3f2fd; border: 1px solid #2196f3; border-radius: 4px;">'
                '<strong>🔗 Brevo Quick Links:</strong><br><br>'
                '• <a href="https://app.brevo.com/settings/keys/api" target="_blank" style="color: #1976d2; font-weight: bold;">📋 API Keys</a><br>'
                '• <a href="https://app.brevo.com/senders" target="_blank" style="color: #1976d2; font-weight: bold;">✉️ Verify Senders</a><br>'
                '• <a href="https://app.brevo.com/statistics/email" target="_blank" style="color: #1976d2; font-weight: bold;">📊 Email Statistics</a><br>'
                '• <a href="https://app.brevo.com/logs" target="_blank" style="color: #1976d2; font-weight: bold;">📜 Email Logs</a>'
                '</div>'
            )
        elif method == 'smtp':
            return format_html(
                '<div style="padding: 10px; background: #e8f5e9; border: 1px solid #4caf50; border-radius: 4px;">'
                '<strong>🔗 SMTP Setup Guides:</strong><br><br>'
                '• <a href="https://support.google.com/mail/answer/7126229" target="_blank" style="color: #2e7d32; font-weight: bold;">📧 Gmail SMTP Setup</a><br>'
                '• <a href="https://support.microsoft.com/en-us/office/pop-imap-and-smtp-settings-8361e398-8af4-4e97-b147-6c6c4ac95353" target="_blank" style="color: #2e7d32; font-weight: bold;">📧 Outlook SMTP Setup</a><br>'
                '• <strong>Gmail:</strong> smtp.gmail.com:587 (TLS) or :465 (SSL)<br>'
                '• <strong>Outlook:</strong> smtp.office365.com:587 (TLS)'
                '</div>'
            )
        else:
            return format_html(
                '<div style="padding: 10px; background: #fff3e0; border: 1px solid #ff9800; border-radius: 4px;">'
                '⚠️ Select an email delivery method above to see relevant help links'
                '</div>'
            )
    email_help_links.short_description = 'Help & Resources'
    
    def email_config_display(self, obj):
        """Display current email configuration summary"""
        if not obj.pk:
            return format_html(
                '<div style="padding: 12px; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px;">'
                '💡 Save the platform first to view configuration'
                '</div>'
            )
        
        if not obj.email_delivery_method:
            return format_html(
                '<div style="padding: 12px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px;">'
                '⚠️ No email delivery method selected'
                '</div>'
            )
        
        if not obj.has_email_config:
            method_display = dict(obj._meta.get_field('email_delivery_method').choices).get(
                obj.email_delivery_method,
                obj.email_delivery_method
            )
            return format_html(
                '<div style="padding: 12px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px;">'
                '⚠️ Email delivery method set to <strong>{}</strong> but not configured yet<br><br>'
                'Please fill in the required fields above and save.'
                '</div>',
                method_display
            )
        
        config = obj.get_email_config_summary()
        method = obj.email_delivery_method
        
        if method == 'smtp':
            ssl_tls = 'TLS' if config.get('use_tls') else ('SSL' if config.get('use_ssl') else 'None')
            
            return format_html(
                '<div style="padding: 12px; background: #e8f5e9; border: 1px solid #4caf50; border-radius: 4px;">'
                '<strong>📊 SMTP Configuration</strong><br><br>'
                '<table style="width: 100%;">'
                '<tr><td style="padding: 4px; width: 35%;"><strong>Method:</strong></td>'
                '<td><span style="background: #28a745; color: white; padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: bold;">DIRECT SMTP</span></td></tr>'
                '<tr><td style="padding: 4px;"><strong>SMTP Host:</strong></td><td><code>{}</code></td></tr>'
                '<tr><td style="padding: 4px;"><strong>Port:</strong></td><td><code>{}</code></td></tr>'
                '<tr><td style="padding: 4px;"><strong>Username:</strong></td><td>{}</td></tr>'
                '<tr><td style="padding: 4px;"><strong>Encryption:</strong></td><td><span style="background: #2196f3; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{}</span></td></tr>'
                '<tr><td style="padding: 4px;"><strong>From Email:</strong></td><td>{}</td></tr>'
                '<tr><td style="padding: 4px;"><strong>From Name:</strong></td><td>{}</td></tr>'
                '<tr><td style="padding: 4px;"><strong>Password:</strong></td><td>🔒 <span style="color: #28a745;">Encrypted</span></td></tr>'
                '<tr><td style="padding: 4px;"><strong>Configured:</strong></td><td>{}</td></tr>'
                '</table>'
                '</div>',
                config.get('smtp_host', 'N/A'),
                config.get('smtp_port', 'N/A'),
                config.get('smtp_user', 'N/A'),
                ssl_tls,
                config.get('from_email', 'N/A'),
                obj.get_from_name(),
                config.get('configured_at', 'Unknown')[:19] if config.get('configured_at') else 'Unknown'
            )
        
        elif method == 'brevo_api':
            return format_html(
                '<div style="padding: 12px; background: #e3f2fd; border: 1px solid #2196f3; border-radius: 4px;">'
                '<strong>📊 Brevo Configuration</strong><br><br>'
                '<table style="width: 100%;">'
                '<tr><td style="padding: 4px; width: 35%;"><strong>Method:</strong></td>'
                '<td><span style="background: #0084ff; color: white; padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: bold;">BREVO API</span></td></tr>'
                '<tr><td style="padding: 4px;"><strong>From Email:</strong></td><td>{}</td></tr>'
                '<tr><td style="padding: 4px;"><strong>From Name:</strong></td><td>{}</td></tr>'
                '<tr><td style="padding: 4px;"><strong>API Key:</strong></td><td>🔒 <span style="color: #28a745;">Encrypted</span></td></tr>'
                '<tr><td style="padding: 4px;"><strong>Configured:</strong></td><td>{}</td></tr>'
                '</table>'
                '</div>',
                config.get('from_email', 'N/A'),
                obj.get_from_name(),
                config.get('configured_at', 'Unknown')[:19] if config.get('configured_at') else 'Unknown'
            )
        
        return "Configuration details not available"
    email_config_display.short_description = 'Configuration Summary'
    
    # ============================================
    # SAVE MODEL
    # ============================================
    
    def save_model(self, request, obj, form, change):
        """Save platform and update email configuration based on selected method"""
        
        email_delivery_method = form.cleaned_data.get('email_delivery_method')
        
        try:
            if email_delivery_method == 'smtp':
                smtp_host = form.cleaned_data.get('smtp_host')
                smtp_password = form.cleaned_data.get('smtp_password')
                
                # Get existing password if not provided
                if not smtp_password and obj.pk:
                    smtp_password = obj.get_smtp_password()
                
                if smtp_host and smtp_password:
                    obj.set_email_config(
                        smtp_host=smtp_host,
                        smtp_port=form.cleaned_data.get('smtp_port', 587),
                        smtp_user=form.cleaned_data.get('smtp_user', ''),
                        smtp_password=smtp_password,
                        use_tls=form.cleaned_data.get('use_tls', True),
                        use_ssl=form.cleaned_data.get('use_ssl', False),
                        from_email=form.cleaned_data.get('from_email', obj.support_email),
                        from_name=form.cleaned_data.get('from_name', obj.name),
                        provider='smtp'
                    )
                    
                    messages.success(
                        request,
                        f'✅ SMTP configuration saved for {obj.name}'
                    )
            
            elif email_delivery_method == 'brevo_api':
                brevo_api_key = form.cleaned_data.get('brevo_api_key')
                
                # Get existing API key if not provided
                if not brevo_api_key and obj.pk and obj.email_settings:
                    encrypted_key = obj.email_settings.get('api_key_encrypted')
                    if encrypted_key:
                        brevo_api_key = obj.decrypt_value(encrypted_key)
                
                if brevo_api_key:
                    obj.set_brevo_api_config(
                        api_key=brevo_api_key,
                        from_email=form.cleaned_data.get('from_email', obj.support_email),
                        from_name=form.cleaned_data.get('from_name', obj.name)
                    )
                    
                    messages.success(
                        request,
                        f'✅ Brevo API configured for {obj.name}. Make sure "{obj.get_from_email()}" is verified in Brevo!'
                    )
        
        except Exception as e:
            messages.error(
                request,
                f'❌ Failed to save email configuration: {str(e)}'
            )
        
        super().save_model(request, obj, form, change)
    
    # ============================================
    # ADMIN ACTIONS
    # ============================================
    
    @admin.action(description='✉️ Enable email verification')
    def enable_verification(self, request, queryset):
        """Enable email verification requirement for selected platforms"""
        updated = queryset.update(requires_email_verification=True)
        self.message_user(
            request,
            f'✅ Email verification enabled for {updated} platform(s)',
            level=messages.SUCCESS
        )
    
    @admin.action(description='⚡ Disable email verification (auto-verify)')
    def disable_verification(self, request, queryset):
        """Disable email verification (auto-verify) for selected platforms"""
        updated = queryset.update(requires_email_verification=False)
        self.message_user(
            request,
            f'⚡ Auto-verification enabled for {updated} platform(s). Users will be verified immediately on registration.',
            level=messages.WARNING
        )
    
    @admin.action(description='📧 Send test emails to me')
    def send_test_emails(self, request, queryset):
        """Send test email to current admin user"""
        admin_email = request.user.email
        
        if not admin_email:
            self.message_user(
                request,
                '❌ Your admin account has no email address configured',
                level=messages.ERROR
            )
            return
        
        for platform in queryset:
            if not platform.has_email_config:
                self.message_user(
                    request,
                    f'❌ {platform.name}: No email configuration',
                    level=messages.ERROR
                )
                continue
            
            try:
                method_display = dict(platform._meta.get_field('email_delivery_method').choices).get(
                    platform.email_delivery_method,
                    platform.email_delivery_method
                )
                
                verification_status = "Required" if platform.requires_email_verification else "Auto-Verify"
                
                # Build test email
                subject = f'🧪 Test Email from {platform.name}'
                text_content = (
                    f"Hello {request.user.get_full_name() or request.user.username},\n\n"
                    f"This is a test email from {platform.name}'s email system.\n\n"
                    f"If you received this, your email configuration is working correctly!\n\n"
                    f"Platform: {platform.name}\n"
                    f"From: {platform.get_from_email()}\n"
                    f"Method: {method_display}\n"
                    f"Verification: {verification_status}"
                )
                
                html_content = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #0084ff;">🧪 Test Email</h2>
                    <p>Hello <strong>{request.user.get_full_name() or request.user.username}</strong>,</p>
                    <p>This is a test email from <strong>{platform.name}</strong>'s email system.</p>
                    <div style="background: #e3f2fd; padding: 15px; border-left: 4px solid #0084ff; margin: 20px 0;">
                        <p style="margin: 0;"><strong>✅ Success!</strong> Your email configuration is working correctly.</p>
                    </div>
                    <p><strong>Configuration Details:</strong></p>
                    <ul>
                        <li><strong>Platform:</strong> {platform.name}</li>
                        <li><strong>From Email:</strong> {platform.get_from_email()}</li>
                        <li><strong>Method:</strong> {method_display}</li>
                        <li><strong>Verification:</strong> <span style="background: {'#ff9800' if platform.requires_email_verification else '#4caf50'}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 11px;">{verification_status}</span></li>
                    </ul>
                </div>
                """
                
                # Get BCC emails
                bcc_emails = platform.get_admin_emails_for_bcc()
                
                # Send email
                success, message = platform.send_email(
                    subject=subject,
                    body_text=text_content,
                    body_html=html_content,
                    to_emails=[admin_email],
                    bcc_emails=bcc_emails
                )
                
                if success:
                    bcc_info = f' (BCC: {", ".join(bcc_emails)})' if bcc_emails else ''
                    self.message_user(
                        request,
                        f'✅ Test email sent from {platform.name} to {admin_email}{bcc_info}',
                        level=messages.SUCCESS
                    )
                else:
                    self.message_user(
                        request,
                        f'❌ {platform.name}: {message}',
                        level=messages.ERROR
                    )
                
            except Exception as e:
                self.message_user(
                    request,
                    f'❌ {platform.name}: Failed - {str(e)}',
                    level=messages.ERROR
                )


@admin.register(PlatformStats)
class PlatformStatsAdmin(admin.ModelAdmin):
    list_display = [
        'platform', 'total_users', 'total_webinars',
        'total_enrollments', 'total_revenue', 'last_calculated'
    ]
    list_filter = ['last_calculated']
    search_fields = ['platform__name', 'platform__platform_id']
    readonly_fields = ['last_calculated']


@admin.register(PlatformAPILog)
class PlatformAPILogAdmin(admin.ModelAdmin):
    list_display = [
        'platform', 'method', 'endpoint', 'status_code',
        'response_time_ms', 'ip_address', 'created_at'
    ]
    list_filter = ['platform', 'method', 'status_code', 'created_at']
    search_fields = ['platform__name', 'endpoint', 'ip_address']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'
    
    def has_add_permission(self, request):
        return False
