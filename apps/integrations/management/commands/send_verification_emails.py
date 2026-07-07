from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import Q
from apps.users.models import User
from apps.authentication.models import EmailVerificationToken
from apps.notifications.email_service import EmailService, send_verification_email_task
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send verification emails to users (unverified by default, or all users with --include-verified)'
    
    def add_arguments(self, parser):
        """Add command-line arguments"""
        parser.add_argument(
            '--platform',
            type=str,
            help='Send emails only to users of a specific platform (platform_id)',
        )
        
        parser.add_argument(
            '--email',
            type=str,
            help='Send verification email to a specific user email',
        )
        
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='Send to users registered within last N days (e.g., --days 7)',
        )
        
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit the number of emails to send (e.g., --limit 100)',
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate sending without actually sending emails',
        )
        
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Send emails synchronously instead of using Celery tasks',
        )
        
        parser.add_argument(
            '--recreate-tokens',
            action='store_true',
            help='Create new verification tokens for users who already have expired ones',
        )
        
        # ✅ NEW: Include already verified users
        parser.add_argument(
            '--include-verified',
            action='store_true',
            help='Send verification emails to already verified users as well',
        )
        
        # ✅ NEW: Send ONLY to verified users
        parser.add_argument(
            '--only-verified',
            action='store_true',
            help='Send verification emails ONLY to already verified users',
        )
    
    def handle(self, *args, **options):
        """Main command execution"""
        platform_filter = options.get('platform')
        email_filter = options.get('email')
        days_filter = options.get('days')
        limit = options.get('limit')
        dry_run = options.get('dry_run')
        sync_mode = options.get('sync')
        recreate_tokens = options.get('recreate_tokens')
        include_verified = options.get('include_verified')  # ✅ NEW
        only_verified = options.get('only_verified')        # ✅ NEW
        
        self.stdout.write(self.style.HTTP_INFO('='*60))
        self.stdout.write(self.style.HTTP_INFO('🚀 Starting Verification Email Campaign'))
        self.stdout.write(self.style.HTTP_INFO('='*60))
        
        # ✅ Build query based on verification status
        queryset = User.objects.filter(is_active=True).select_related('platform')
        
        # ✅ Handle verification status filter
        if only_verified:
            # Send ONLY to verified users
            queryset = queryset.filter(is_verified=True)
            self.stdout.write(self.style.WARNING("🔵 Target: ONLY verified users"))
        elif include_verified:
            # Send to ALL users (verified + unverified)
            self.stdout.write(self.style.WARNING("🟡 Target: ALL users (verified + unverified)"))
        else:
            # Default: Send ONLY to unverified users
            queryset = queryset.filter(is_verified=False)
            self.stdout.write(self.style.SUCCESS("🟢 Target: ONLY unverified users (default)"))
        
        # Apply other filters
        if platform_filter:
            queryset = queryset.filter(platform__platform_id=platform_filter)
            self.stdout.write(f"📍 Platform filter: {platform_filter}")
        
        if email_filter:
            queryset = queryset.filter(email=email_filter)
            self.stdout.write(f"📧 Email filter: {email_filter}")
        
        if days_filter:
            cutoff_date = timezone.now() - timezone.timedelta(days=days_filter)
            queryset = queryset.filter(date_joined__gte=cutoff_date)
            self.stdout.write(f"📅 Time filter: Last {days_filter} days")
        
        if limit:
            queryset = queryset[:limit]
            self.stdout.write(f"🔢 Limit: {limit} users")
        
        # Get total count
        total_users = queryset.count()
        
        if total_users == 0:
            self.stdout.write(self.style.WARNING('⚠️  No users found matching criteria'))
            return
        
        # ✅ Show breakdown
        verified_count = queryset.filter(is_verified=True).count()
        unverified_count = queryset.filter(is_verified=False).count()
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Found {total_users} users'))
        self.stdout.write(f"  - Verified: {verified_count}")
        self.stdout.write(f"  - Unverified: {unverified_count}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n🧪 DRY RUN MODE - No emails will be sent\n'))
        
        # Send verification emails
        sent_count = 0
        failed_count = 0
        skipped_count = 0
        
        for user in queryset:
            try:
                # ✅ Show user verification status
                verification_badge = "✅" if user.is_verified else "⏳"
                
                # Check for existing valid token
                existing_token = EmailVerificationToken.objects.filter(
                    user=user,
                    is_used=False
                ).order_by('-created_at').first()
                
                # Determine if we need a new token
                needs_new_token = (
                    not existing_token or 
                    existing_token.is_expired() or 
                    recreate_tokens
                )
                
                if needs_new_token:
                    if existing_token and not existing_token.is_used:
                        # Mark old tokens as used
                        EmailVerificationToken.objects.filter(
                            user=user, 
                            is_used=False
                        ).update(is_used=True)
                        self.stdout.write(f"  🔄 Invalidated old token for {user.email}")
                    
                    # Create new verification token
                    verification_token = EmailVerificationToken.objects.create(user=user)
                    token = verification_token.token
                    self.stdout.write(f"  🔑 New token created: {token[:16]}...")
                else:
                    token = existing_token.token
                    self.stdout.write(f"  ✓ Using existing valid token")
                
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[DRY RUN] {verification_badge} Would send to: {user.email} "
                            f"(Platform: {user.platform.name if user.platform else 'None'}) "
                            f"[{'VERIFIED' if user.is_verified else 'UNVERIFIED'}]"
                        )
                    )
                    sent_count += 1
                    continue
                
                # Send email
                platform_name = user.platform.name if user.platform else 'System'
                status_text = "VERIFIED" if user.is_verified else "UNVERIFIED"
                
                if sync_mode:
                    # Synchronous sending
                    EmailService.send_verification_email(
                        user=user,
                        verification_token=token,
                        platform=user.platform
                    )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✅ [{platform_name}] {verification_badge} Sent (sync) to: {user.email} [{status_text}]"
                        )
                    )
                else:
                    # Async Celery task
                    task = send_verification_email_task.delay(user.id, token)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✅ [{platform_name}] {verification_badge} Queued (async {task.id[:8]}...) to: {user.email} [{status_text}]"
                        )
                    )
                
                sent_count += 1
                logger.info(
                    f"Verification email sent to {user.email} "
                    f"(Platform: {platform_name}, Status: {status_text})"
                )
                
            except EmailVerificationToken.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"❌ No token found for: {user.email}")
                )
                failed_count += 1
                logger.error(f"Token not found for user: {user.email}")
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Failed to send to {user.email}: {str(e)}")
                )
                failed_count += 1
                logger.error(f"Failed to send verification email to {user.email}: {str(e)}", exc_info=True)
        
        # Summary
        self.stdout.write(self.style.HTTP_INFO('\n' + '='*60))
        self.stdout.write(self.style.HTTP_INFO('📊 Campaign Summary'))
        self.stdout.write(self.style.HTTP_INFO('='*60))
        self.stdout.write(f"Total users targeted: {total_users}")
        self.stdout.write(f"  - Verified users: {verified_count}")
        self.stdout.write(f"  - Unverified users: {unverified_count}")
        self.stdout.write(self.style.SUCCESS(f"✅ Successfully sent: {sent_count}"))
        
        if failed_count > 0:
            self.stdout.write(self.style.ERROR(f"❌ Failed: {failed_count}"))
        
        if skipped_count > 0:
            self.stdout.write(self.style.WARNING(f"⏭️  Skipped: {skipped_count}"))
        
        self.stdout.write(self.style.HTTP_INFO('='*60 + '\n'))
