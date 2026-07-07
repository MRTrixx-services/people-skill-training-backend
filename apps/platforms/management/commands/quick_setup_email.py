from django.core.management.base import BaseCommand
from apps.platforms.models import Platform


class Command(BaseCommand):
    help = 'Quick setup email for PeopleSkillTraining platform'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-email',
            type=str,
            help='Send test email to this address after setup'
        )

    def handle(self, *args, **options):
        try:
            # Get or create platform
            platform, created = Platform.objects.get_or_create(
                platform_id='people_skill_training',
                defaults={
                    'name': 'PeopleSkillTraining',
                    'invoice_prefix': 'PSINV',
                    'description': 'Professional webinar training platform',
                    'domain': 'peopleskilltraining.com',
                    'support_email': 'support@peopleskilltraining.com',
                    'contact_phone': '+1 (555) 123-4567',
                    'primary_color': '#3B82F6',
                    'secondary_color': '#8B5CF6',
                    'is_active': True,
                    'is_default': True,
                }
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS(f'✅ Created platform: {platform.name}'))
            
            self.stdout.write(f'\n📧 Setting up email for: {platform.name}\n')
            
            # Configure email with your business email
            platform.set_business_email_config(
                smtp_host='businessemail.webeyesoft.com',
                smtp_port=465,
                email_address='support@peopleskilltraining.com',
                email_password='^zD$Hvuv-WIt',
                use_ssl=True,
                from_name='PeopleSkillTraining'
            )
            
            self.stdout.write(self.style.SUCCESS('✅ Email configuration saved and encrypted'))
            
            # Show configuration
            config = platform.get_email_config_summary()
            self.stdout.write(f'\n📊 Configuration:')
            self.stdout.write(f'  Provider: {config["provider"]}')
            self.stdout.write(f'  SMTP Host: {config["smtp_host"]}')
            self.stdout.write(f'  SMTP Port: {config["smtp_port"]}')
            self.stdout.write(f'  Username: {config["smtp_user"]}')
            self.stdout.write(f'  SSL: {config.get("use_ssl", False)}')
            self.stdout.write(f'  Password: 🔒 Encrypted\n')
            
            # Test connection
            self.stdout.write('🧪 Testing SMTP connection...')
            success, message = platform.test_email_connection()
            
            if success:
                self.stdout.write(self.style.SUCCESS(message))
                
                # Send test email if requested
                test_email = options.get('test_email')
                if test_email:
                    self.stdout.write(f'\n📨 Sending test email to {test_email}...')
                    
                    from apps.notifications.email_service import EmailService
                    
                    context = EmailService.get_email_context(
                        platform=platform,
                        user_name='Test User',
                        verification_url='https://peopleskilltraining.com/verify'
                    )
                    
                    EmailService.send_email(
                        subject=f'✅ Test Email from {platform.name}',
                        template_name='verify_email',
                        context=context,
                        recipient_list=[test_email],
                        platform=platform
                    )
                    
                    self.stdout.write(self.style.SUCCESS(f'✅ Test email sent to {test_email}'))
            else:
                self.stdout.write(self.style.ERROR(message))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Setup failed: {str(e)}'))
            import traceback
            self.stdout.write(traceback.format_exc())
