from django.core.management.base import BaseCommand
from apps.users.models import User
from apps.notifications.email_service import EmailService
from apps.platforms.models import Platform
import traceback


class Command(BaseCommand):
    help = 'Test email sending directly (no Celery) with full debugging'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            required=True,
            help='User email address to send test email',
        )
        
        parser.add_argument(
            '--platform',
            type=str,
            help='Platform ID (e.g., compliancetrained)',
        )
        
        parser.add_argument(
            '--template',
            type=str,
            default='verification_success',
            choices=['verification_success', 'password_reset', 'password_changed_notification'],
            help='Email template to test',
        )
        
        parser.add_argument(
            '--user-id',
            type=int,
            help='Specific user ID to use (if multiple users with same email)',
        )
    
    def handle(self, *args, **options):
        email = options['email']
        platform_id = options.get('platform')
        template = options.get('template')
        user_id = options.get('user_id')
        
        self.stdout.write(self.style.HTTP_INFO('='*70))
        self.stdout.write(self.style.HTTP_INFO('🧪 DIRECT EMAIL TEST (NO CELERY)'))
        self.stdout.write(self.style.HTTP_INFO('='*70))
        
        # Step 1: Find user (with duplicate handling)
        self.stdout.write(f"\n📋 Step 1: Looking up user...")
        try:
            # Build query
            user_query = User.objects.filter(email=email).select_related('platform')
            
            # Filter by user ID if specified
            if user_id:
                user_query = user_query.filter(id=user_id)
            # Filter by platform if specified
            elif platform_id:
                user_query = user_query.filter(platform__platform_id=platform_id)
            
            users = user_query.all()
            
            if not users.exists():
                self.stdout.write(self.style.ERROR(f"❌ User not found: {email}"))
                if platform_id:
                    self.stdout.write(f"   (on platform: {platform_id})")
                return
            
            # Handle multiple users
            if users.count() > 1:
                self.stdout.write(self.style.WARNING(f"⚠️  Found {users.count()} users with email: {email}\n"))
                
                for idx, u in enumerate(users, 1):
                    self.stdout.write(f"   User {idx}:")
                    self.stdout.write(f"      - ID: {u.id}")
                    self.stdout.write(f"      - Platform: {u.platform.name if u.platform else 'None'} ({u.platform.platform_id if u.platform else 'N/A'})")
                    self.stdout.write(f"      - Role: {u.role}")
                    self.stdout.write(f"      - Verified: {u.is_verified}")
                    self.stdout.write(f"      - Created: {u.date_joined}")
                
                self.stdout.write(self.style.WARNING("\n⚠️  Using first user. To select specific user, use:"))
                self.stdout.write(f"   --user-id=<ID> or --platform=<platform_id>\n")
            
            user = users.first()
            
            self.stdout.write(self.style.SUCCESS(f"✅ User selected: {user.email}"))
            self.stdout.write(f"   - ID: {user.id}")
            self.stdout.write(f"   - Name: {user.first_name} {user.last_name}")
            self.stdout.write(f"   - Role: {user.role}")
            self.stdout.write(f"   - Verified: {user.is_verified}")
            self.stdout.write(f"   - User's Platform: {user.platform.name if user.platform else 'None'}")
            self.stdout.write(f"   - User's Platform ID: {user.platform.platform_id if user.platform else 'None'}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error finding user: {str(e)}"))
            traceback.print_exc()
            return
        
        # Step 2: Determine platform to use
        self.stdout.write(f"\n📋 Step 2: Determining platform...")
        
        # Start with user's platform
        platform = user.platform
        
        # Override if platform_id specified and different
        if platform_id:
            if not platform or platform.platform_id != platform_id:
                try:
                    platform = Platform.objects.get(platform_id=platform_id)
                    self.stdout.write(self.style.WARNING(f"⚠️  Overriding user's platform with: {platform.name}"))
                except Platform.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"❌ Platform not found: {platform_id}"))
                    return
            else:
                self.stdout.write(self.style.SUCCESS(f"✅ Using user's platform: {platform.name}"))
        else:
            if platform:
                self.stdout.write(self.style.SUCCESS(f"✅ Using user's platform: {platform.name}"))
            else:
                self.stdout.write(self.style.WARNING("⚠️  User has no platform - using default settings"))
        
        if platform:
            self.stdout.write(f"\n   Platform Details:")
            self.stdout.write(f"   - Name: {platform.name}")
            self.stdout.write(f"   - ID: {platform.platform_id}")
            self.stdout.write(f"   - Domain: {platform.domain}")
            self.stdout.write(f"   - Support Email: {platform.support_email}")
            
            # ✅ Show Brevo API key source
            if hasattr(platform, 'email_settings') and platform.email_settings:
                brevo_key = platform.email_settings.get('brevo_api_key')
                if brevo_key:
                    self.stdout.write(f"   - Brevo API Key: {brevo_key[:20]}... (platform-specific)")
                else:
                    self.stdout.write(f"   - Brevo API Key: Using default from settings")
            else:
                self.stdout.write(f"   - Email Settings: {platform.email_settings}")
                self.stdout.write(f"   - Brevo API Key: Using default from settings")
        
        # Step 3: Test Brevo client
        self.stdout.write(f"\n📋 Step 3: Testing Brevo API client...")
        try:
            brevo_client = EmailService.get_brevo_client(platform)
            self.stdout.write(self.style.SUCCESS("✅ Brevo client initialized successfully"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Brevo client failed: {str(e)}"))
            traceback.print_exc()
            return
        
        # Step 4: Get email context
        self.stdout.write(f"\n📋 Step 4: Building email context...")
        try:
            base_url = EmailService.get_base_url(None, platform)
            
            if template == 'verification_success':
                context = EmailService.get_email_context(
                    user=user,
                    platform=platform,
                    login_url=f"{base_url}/login",
                    dashboard_url=f"{base_url}/{user.role}",
                    subject="Email Verified Successfully!"
                )
            elif template == 'password_reset':
                context = EmailService.get_email_context(
                    user=user,
                    platform=platform,
                    reset_url=f"{base_url}/reset-password?token=TEST123&email={user.email}",
                    reset_token="TEST123",
                    subject="Reset Your Password"
                )
            elif template == 'password_changed_notification':
                # ✅ Get platform settings for support email
                platform_settings = EmailService.get_platform_settings(platform)
                
                context = EmailService.get_email_context(
                    user=user,
                    platform=platform,
                    login_url=f"{base_url}/login",
                    support_url=f"{base_url}/contact-support",
                    support_email=platform_settings.get('support_email'),
                    subject="Password Changed Successfully"
                )
            
            self.stdout.write(self.style.SUCCESS("✅ Email context built"))
            self.stdout.write(f"\n   Context Details:")
            self.stdout.write(f"   - Company Name: {context.get('company_name')}")
            self.stdout.write(f"   - From Email: {context.get('from_email')}")
            self.stdout.write(f"   - From Name: {context.get('from_name')}")
            self.stdout.write(f"   - Support Email: {context.get('support_email')}")
            self.stdout.write(f"   - Website URL: {context.get('website_url')}")
            self.stdout.write(f"   - Platform Name: {context.get('platform_name')}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Context building failed: {str(e)}"))
            traceback.print_exc()
            return
        
        # Step 5: Test template rendering
        self.stdout.write(f"\n📋 Step 5: Testing template rendering...")
        try:
            from django.template.loader import render_to_string
            html_content = render_to_string(f'emails/{template}.html', context)
            self.stdout.write(self.style.SUCCESS(f"✅ Template rendered successfully"))
            self.stdout.write(f"   - Template: {template}.html")
            self.stdout.write(f"   - HTML length: {len(html_content)} characters")
            
            # ✅ Check for platform name in content
            if platform and platform.name in html_content:
                self.stdout.write(self.style.SUCCESS(f"   - ✅ Platform name '{platform.name}' found in email content"))
            elif platform:
                self.stdout.write(self.style.WARNING(f"   - ⚠️  Platform name '{platform.name}' NOT found in email content"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Template rendering failed: {str(e)}"))
            traceback.print_exc()
            return
        
        # Step 6: Send email via Brevo
        self.stdout.write(f"\n📋 Step 6: Sending email via Brevo API...")
        self.stdout.write(f"   Using platform: {platform.name if platform else 'Default'}")
        
        try:
            if template == 'verification_success':
                result = EmailService.send_verification_success_email(
                    user=user,
                    platform=platform  # ✅ EXPLICIT PLATFORM
                )
            elif template == 'password_reset':
                result = EmailService.send_password_reset_email(
                    user=user,
                    reset_token="TEST123",
                    platform=platform  # ✅ EXPLICIT PLATFORM
                )
            elif template == 'password_changed_notification':
                result = EmailService.send_password_change_notification(
                    user=user,
                    platform=platform  # ✅ EXPLICIT PLATFORM
                )
            
            self.stdout.write(self.style.SUCCESS("\n✅ EMAIL SENT SUCCESSFULLY!"))
            
            if isinstance(result, dict):
                self.stdout.write(f"   - Message ID: {result.get('message_id', 'N/A')}")
                self.stdout.write(f"   - Recipients: {result.get('recipients', [])}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR("\n❌ EMAIL SEND FAILED!"))
            self.stdout.write(self.style.ERROR(f"   Error: {str(e)}"))
            self.stdout.write(self.style.ERROR("\n📄 Full Traceback:"))
            traceback.print_exc()
            return
        
        # Summary
        self.stdout.write(self.style.HTTP_INFO('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('✅ TEST COMPLETED SUCCESSFULLY'))
        self.stdout.write(self.style.HTTP_INFO('='*70))
        self.stdout.write(f"✉️  Email sent to: {user.email}")
        self.stdout.write(f"🏢 Platform used: {platform.name if platform else 'Default'}")
        self.stdout.write(f"📧 From: {context.get('from_email')} ({context.get('from_name')})")
        self.stdout.write(f"📋 Template: {template}")
        self.stdout.write(f"🔗 Support: {context.get('support_email')}")
        self.stdout.write(self.style.HTTP_INFO('='*70 + '\n'))
        
        # ✅ Additional tips
        self.stdout.write(self.style.WARNING("💡 Next Steps:"))
        self.stdout.write("   1. Check your email inbox for the message")
        self.stdout.write("   2. Verify the sender and support email are correct")
        self.stdout.write("   3. Check that platform branding appears in email")
        if platform:
            self.stdout.write(f"   4. Login to Brevo to view email statistics")
        self.stdout.write("")
