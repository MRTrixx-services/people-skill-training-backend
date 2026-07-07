from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import Q
from apps.users.models import User
from apps.notifications.email_service import EmailService, send_verification_success_email_task
import logging
import traceback


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send verification success/welcome emails to users'
    
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
            help='Send success email to a specific user email',
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
            '--verified-only',
            action='store_true',
            help='Send only to verified users (default: all active users)',
        )
        
        parser.add_argument(
            '--unverified-only',
            action='store_true',
            help='Send only to unverified users (motivational welcome)',
        )
        
        parser.add_argument(
            '--role',
            type=str,
            choices=['instructor', 'attendee', 'admin'],
            help='Filter by user role',
        )
        
        # ✅ NEW: Verbose debugging option
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed debugging information',
        )
    
    def handle(self, *args, **options):
        """Main command execution"""
        platform_filter = options.get('platform')
        email_filter = options.get('email')
        days_filter = options.get('days')
        limit = options.get('limit')
        dry_run = options.get('dry_run')
        sync_mode = options.get('sync')
        verified_only = options.get('verified_only')
        unverified_only = options.get('unverified_only')
        role_filter = options.get('role')
        verbose = options.get('verbose')
        
        self.stdout.write(self.style.HTTP_INFO('='*60))
        self.stdout.write(self.style.HTTP_INFO('🎉 Starting Verification Success Email Campaign'))
        self.stdout.write(self.style.HTTP_INFO('='*60))
        
        # ✅ IMPROVED: Show execution mode
        mode = "🧪 DRY RUN" if dry_run else ("🔄 SYNC" if sync_mode else "⚡ ASYNC (Celery)")
        self.stdout.write(self.style.WARNING(f"Mode: {mode}\n"))
        
        # Build query for users
        queryset = User.objects.filter(is_active=True).select_related('platform')
        
        # Apply verification status filter
        if verified_only:
            queryset = queryset.filter(is_verified=True)
            self.stdout.write(self.style.SUCCESS("✅ Target: ONLY verified users"))
        elif unverified_only:
            queryset = queryset.filter(is_verified=False)
            self.stdout.write(self.style.WARNING("⏳ Target: ONLY unverified users (motivational)"))
        else:
            self.stdout.write(self.style.HTTP_INFO("🌐 Target: ALL active users"))
        
        # Apply other filters
        if platform_filter:
            queryset = queryset.filter(platform__platform_id=platform_filter)
            self.stdout.write(f"📍 Platform filter: {platform_filter}")
        
        if email_filter:
            queryset = queryset.filter(email=email_filter)
            self.stdout.write(f"📧 Email filter: {email_filter}")
        
        if role_filter:
            queryset = queryset.filter(role=role_filter)
            self.stdout.write(f"👤 Role filter: {role_filter}")
        
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
        
        # Show breakdown
        verified_count = queryset.filter(is_verified=True).count()
        unverified_count = queryset.filter(is_verified=False).count()
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Found {total_users} users'))
        self.stdout.write(f"  - Verified: {verified_count}")
        self.stdout.write(f"  - Unverified: {unverified_count}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n🧪 DRY RUN MODE - No emails will be sent\n'))
        
        # ✅ IMPROVED: Check Celery worker status if using async mode
        if not sync_mode and not dry_run:
            try:
                from peopleskilltrainingapp.celery import app
                inspector = app.control.inspect()
                active_workers = inspector.ping()
                
                if active_workers:
                    self.stdout.write(self.style.SUCCESS(f"✅ Celery workers active: {list(active_workers.keys())}"))
                else:
                    self.stdout.write(self.style.ERROR("❌ WARNING: No Celery workers detected!"))
                    self.stdout.write(self.style.WARNING("   Emails will be queued but not sent until worker starts."))
                    self.stdout.write(self.style.WARNING("   Consider using --sync flag for immediate sending.\n"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"⚠️  Could not check Celery status: {str(e)}\n"))
        
        # Send verification success emails
        sent_count = 0
        failed_count = 0
        
        for user in queryset:
            try:
                verification_badge = "✅" if user.is_verified else "⏳"
                status_text = "VERIFIED" if user.is_verified else "UNVERIFIED"
                platform_name = user.platform.name if user.platform else 'System'
                
                # ✅ IMPROVED: Show user details in verbose mode
                if verbose:
                    self.stdout.write(self.style.HTTP_INFO(f"\n📋 Processing user:"))
                    self.stdout.write(f"   Email: {user.email}")
                    self.stdout.write(f"   Platform: {platform_name} ({user.platform.platform_id if user.platform else 'N/A'})")
                    self.stdout.write(f"   Status: {status_text}")
                    self.stdout.write(f"   Role: {user.role.upper()}")
                
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[DRY RUN] {verification_badge} Would send success email to: {user.email} "
                            f"(Platform: {platform_name}) "
                            f"[{status_text}] [Role: {user.role.upper()}]"
                        )
                    )
                    sent_count += 1
                    continue
                
                # Send success/welcome email
                if sync_mode:
                    # ✅ IMPROVED: Synchronous sending with detailed error handling
                    try:
                        result = EmailService.send_verification_success_email(
                            user=user,
                            platform=user.platform
                        )
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✅ [{platform_name}] {verification_badge} Sent (sync) to: {user.email} "
                                f"[{status_text}] [Role: {user.role.upper()}]"
                            )
                        )
                        
                        # ✅ NEW: Show Brevo message ID if available
                        if verbose and isinstance(result, dict):
                            msg_id = result.get('message_id', 'N/A')
                            self.stdout.write(self.style.HTTP_INFO(f"   📨 Brevo Message ID: {msg_id}"))
                            
                    except Exception as email_error:
                        # ✅ IMPROVED: Detailed error reporting
                        self.stdout.write(
                            self.style.ERROR(f"❌ Email send failed for {user.email}")
                        )
                        if verbose:
                            self.stdout.write(self.style.ERROR(f"   Error: {str(email_error)}"))
                            self.stdout.write(self.style.ERROR(f"   Traceback:\n{traceback.format_exc()}"))
                        raise  # Re-raise to be caught by outer try-except
                        
                else:
                    # ✅ IMPROVED: Async Celery task with better tracking
                    try:
                        task = send_verification_success_email_task.delay(user.id)
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✅ [{platform_name}] {verification_badge} Queued (async {task.id[:8]}...) to: {user.email} "
                                f"[{status_text}] [Role: {user.role.upper()}]"
                            )
                        )
                        
                        # ✅ NEW: Show task status in verbose mode
                        if verbose:
                            self.stdout.write(self.style.HTTP_INFO(f"   🔑 Full Task ID: {task.id}"))
                            self.stdout.write(self.style.HTTP_INFO(f"   📊 Task Status: {task.status}"))
                            
                    except Exception as celery_error:
                        self.stdout.write(
                            self.style.ERROR(f"❌ Celery task failed for {user.email}")
                        )
                        if verbose:
                            self.stdout.write(self.style.ERROR(f"   Error: {str(celery_error)}"))
                        raise
                
                sent_count += 1
                logger.info(
                    f"Verification success email sent to {user.email} "
                    f"(Platform: {platform_name}, Status: {status_text}, Role: {user.role})"
                )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Failed to send to {user.email}: {str(e)}")
                )
                failed_count += 1
                logger.error(
                    f"Failed to send verification success email to {user.email}: {str(e)}", 
                    exc_info=True
                )
                
                # ✅ NEW: Show full traceback in verbose mode
                if verbose:
                    self.stdout.write(self.style.ERROR(f"\n{traceback.format_exc()}"))
        
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
        
        # ✅ NEW: Success rate
        if total_users > 0:
            success_rate = (sent_count / total_users) * 100
            self.stdout.write(f"📈 Success rate: {success_rate:.1f}%")
        
        self.stdout.write(self.style.HTTP_INFO('='*60 + '\n'))
        
        # ✅ NEW: Post-execution recommendations
        if not sync_mode and not dry_run and sent_count > 0:
            self.stdout.write(self.style.WARNING("\n💡 Tips:"))
            self.stdout.write("   • Monitor tasks in Flower: http://your-server:5555")
            self.stdout.write("   • Check Celery logs: tail -f /var/log/celery/*.log")
            self.stdout.write("   • Verify email delivery in Brevo dashboard\n")
