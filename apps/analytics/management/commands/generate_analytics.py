from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Count, Avg
from apps.analytics.models import WebinarAnalytics, PlatformMetrics, RevenueAnalytics
from apps.webinars.models import Webinar
from apps.enrollments.models import Enrollment
from apps.payments.models import Payment
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Generate analytics data for webinars and platform metrics'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to generate analytics for'
        )

    def handle(self, *args, **options):
        days = options['days']
        self.stdout.write(f'Generating analytics for the last {days} days...')
        
        # Generate webinar analytics
        self.generate_webinar_analytics()
        
        # Generate platform metrics
        self.generate_platform_metrics(days)
        
        # Generate revenue analytics
        self.generate_revenue_analytics(days)
        
        self.stdout.write(
            self.style.SUCCESS('Successfully generated analytics data')
        )

    def generate_webinar_analytics(self):
        """Generate or update webinar analytics"""
        webinars = Webinar.objects.all()
        
        for webinar in webinars:
            analytics, created = WebinarAnalytics.objects.get_or_create(
                webinar=webinar
            )
            
            # Calculate metrics
            enrollments = Enrollment.objects.filter(webinar=webinar)
            payments = Payment.objects.filter(webinar=webinar, status='completed')
            
            analytics.total_enrollments = enrollments.count()
            analytics.total_revenue = payments.aggregate(
                total=Sum('amount')
            )['total'] or 0
            
            # You can add more complex calculations here
            analytics.save()
            
            if created:
                self.stdout.write(f'Created analytics for {webinar.title}')
            else:
                self.stdout.write(f'Updated analytics for {webinar.title}')

    def generate_platform_metrics(self, days):
        """Generate daily platform metrics"""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        current_date = start_date
        while current_date <= end_date:
            metrics, created = PlatformMetrics.objects.get_or_create(
                date=current_date
            )
            
            # Calculate daily metrics
            metrics.total_users = User.objects.filter(
                date_joined__lte=current_date
            ).count()
            
            metrics.new_users = User.objects.filter(
                date_joined__date=current_date
            ).count()
            
            metrics.total_webinars = Webinar.objects.filter(
                created_at__lte=current_date
            ).count()
            
            metrics.total_enrollments = Enrollment.objects.filter(
                enrolled_at__lte=current_date
            ).count()
            
            metrics.daily_revenue = Payment.objects.filter(
                created_at__date=current_date,
                status='completed'
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            metrics.total_revenue = Payment.objects.filter(
                created_at__lte=current_date,
                status='completed'
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            metrics.save()
            
            current_date += timedelta(days=1)

    def generate_revenue_analytics(self, days):
        """Generate revenue analytics per instructor/webinar"""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        # Get all instructor-webinar combinations with payments
        revenue_data = Payment.objects.filter(
            created_at__date__range=[start_date, end_date],
            status='completed'
        ).values(
            'webinar__instructor', 
            'webinar', 
            'created_at__date'
        ).annotate(
            gross_revenue=Sum('amount'),
            enrollments_count=Count('id')
        )
        
        for data in revenue_data:
            analytics, created = RevenueAnalytics.objects.get_or_create(
                date=data['created_at__date'],
                instructor_id=data['webinar__instructor'],
                webinar_id=data['webinar'],
                defaults={
                    'gross_revenue': data['gross_revenue'],
                    'enrollments_count': data['enrollments_count'],
                    'platform_fee': data['gross_revenue'] * 0.1,  # 10% platform fee
                    'net_revenue': data['gross_revenue'] * 0.9,
                }
            )
            
            if not created:
                analytics.gross_revenue = data['gross_revenue']
                analytics.enrollments_count = data['enrollments_count']
                analytics.platform_fee = data['gross_revenue'] * 0.1
                analytics.net_revenue = data['gross_revenue'] * 0.9
                analytics.save()
