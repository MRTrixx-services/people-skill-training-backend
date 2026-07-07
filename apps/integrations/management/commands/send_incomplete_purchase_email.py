from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from apps.users.models import User
from apps.notifications.email_service import EmailService
import logging


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send recovery emails to users who tried to purchase but email failed'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--platform',
            type=str,
            help='Platform ID (e.g., compliancetrained)',
        )
        
        parser.add_argument(
            '--email',
            type=str,
            help='Send to specific email address only',
        )
        
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Users who registered within last N hours (default: 24)',
        )
        
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of emails',
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Test without sending',
        )
        
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Send synchronously',
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )
    
    def handle(self, *args, **options):
        platform_id = options.get('platform')
        email_filter = options.get('email')
        hours = options.get('hours')
        limit = options.get('limit')
        dry_run = options.get('dry_run')
        sync_mode = options.get('sync')
        verbose = options.get('verbose')
        
        self.stdout.write(self.style.HTTP_INFO('='*70))
        self.stdout.write(self.style.HTTP_INFO('🛒 INCOMPLETE PURCHASE RECOVERY CAMPAIGN'))
        self.stdout.write(self.style.HTTP_INFO('='*70))
        
        # Target users who registered recently
        cutoff_time = timezone.now() - timezone.timedelta(hours=hours)
        
        queryset = User.objects.filter(
            is_active=True,
            role='attendee'
        ).select_related('platform')
        
        # ✅ Filter by email if specified (ignore time filter for specific email)
        if email_filter:
            queryset = queryset.filter(email=email_filter)
            self.stdout.write(f"📧 Email filter: {email_filter}")
        else:
            # Only apply time filter if not filtering by specific email
            queryset = queryset.filter(created_at__gte=cutoff_time)
            self.stdout.write(f"⏰ Time range: Last {hours} hours")
            self.stdout.write(f"📅 Since: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if platform_id:
            queryset = queryset.filter(platform__platform_id=platform_id)
            self.stdout.write(f"📍 Platform: {platform_id}")
        
        self.stdout.write("")  # Empty line
        
        if limit:
            queryset = queryset[:limit]
        
        total = queryset.count()
        self.stdout.write(f"✅ Found {total} user(s)\n")
        
        if total == 0:
            self.stdout.write(self.style.WARNING('No users found. Exiting.'))
            return
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🧪 DRY RUN MODE - No emails will be sent\n'))
        
        sent = 0
        failed = 0
        
        for user in queryset:
            try:
                platform = user.platform
                platform_name = platform.name if platform else 'System'
                
                if verbose or email_filter:  # Always verbose for single email
                    self.stdout.write(f"\n📋 Processing: {user.email}")
                    self.stdout.write(f"   Platform: {platform_name}")
                    self.stdout.write(f"   Registered: {user.created_at.strftime('%Y-%m-%d %H:%M')}")
                    self.stdout.write(f"   Verified: {user.is_verified}")
                
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[DRY RUN] Would send recovery email to: {user.email} ({platform_name})"
                        )
                    )
                    sent += 1
                    continue
                
                # Send incomplete purchase recovery email
                if sync_mode:
                    result = self._send_recovery_email(user, platform)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✅ [{platform_name}] Sent to: {user.email}"
                        )
                    )
                    
                    if (verbose or email_filter) and isinstance(result, dict):
                        msg_id = result.get('message_id', 'N/A')
                        self.stdout.write(f"   📨 Message ID: {msg_id}")
                else:
                    # Use Celery for async
                    from apps.notifications.email_service import send_verification_success_email_task
                    task = send_verification_success_email_task.delay(user.id)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✅ [{platform_name}] Queued to: {user.email} (Task: {task.id[:8]}...)"
                        )
                    )
                
                sent += 1
                logger.info(f"Recovery email sent to {user.email} (Platform: {platform_name})")
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Failed: {user.email} - {str(e)}")
                )
                failed += 1
                logger.error(f"Failed to send recovery email to {user.email}: {str(e)}", exc_info=True)
        
        # Summary
        self.stdout.write(self.style.HTTP_INFO('\n' + '='*70))
        self.stdout.write(self.style.HTTP_INFO('📊 CAMPAIGN SUMMARY'))
        self.stdout.write(self.style.HTTP_INFO('='*70))
        self.stdout.write(f"Total targeted: {total}")
        self.stdout.write(self.style.SUCCESS(f"✅ Sent: {sent}"))
        if failed > 0:
            self.stdout.write(self.style.ERROR(f"❌ Failed: {failed}"))
        
        success_rate = (sent / total * 100) if total > 0 else 0
        self.stdout.write(f"📈 Success rate: {success_rate:.1f}%")
        self.stdout.write(self.style.HTTP_INFO('='*70 + '\n'))
    
    def _send_recovery_email(self, user, platform):
        """Send incomplete purchase recovery email"""
        base_url = EmailService.get_base_url(None, platform)
        
        # Calculate time since registration
        hours_since = (timezone.now() - user.created_at).total_seconds() / 3600
        
        context = EmailService.get_email_context(
            user=user,
            platform=platform,
            browse_url=f"{base_url}/webinars/live",
            account_url=f"{base_url}/{user.role}/dashboard",
            support_url=f"{base_url}/contact-support",
            hours_ago=int(hours_since),
            help_email=platform.support_email if platform else 'support@peopleskilltraining.com',
            subject="We noticed you couldn't complete your purchase"
        )
        
        company_name = platform.name if platform else 'PeopleSkillTraining'
        
        return EmailService.send_email(
            subject=f"🔔 {user.first_name}, Let's Complete Your Enrollment at {company_name}",
            template_name="incomplete_purchase_recovery",
            context=context,
            recipient_list=[user.email],
            platform=platform
        )
