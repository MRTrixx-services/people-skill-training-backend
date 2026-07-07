# apps/webinars/filters.py - Updated for new Zoom integration
import django_filters
from django.db.models import Q, Exists, OuterRef
from .models import Webinar, Category

class WebinarFilter(django_filters.FilterSet):
    """Enhanced filter for webinars with Zoom integration support"""
    
    # Date filters
    date_from = django_filters.DateTimeFilter(field_name='scheduled_date', lookup_expr='gte')
    date_to = django_filters.DateTimeFilter(field_name='scheduled_date', lookup_expr='lte')
    
    # Category filter
    category = django_filters.ModelChoiceFilter(queryset=Category.objects.all())
    category_name = django_filters.CharFilter(field_name='category__name', lookup_expr='icontains')
    
    # Speaker filter
    speaker = django_filters.NumberFilter(field_name='speaker__id')
    speaker_name = django_filters.CharFilter(method='filter_speaker_name')
    
    # Status and features
    status = django_filters.ChoiceFilter(choices=Webinar.STATUS_CHOICES)
    skill_level = django_filters.ChoiceFilter(choices=Webinar.DIFFICULTY_CHOICES)
    
    # Availability
    has_spots = django_filters.BooleanFilter(method='filter_has_spots')
    has_enrollment_limit = django_filters.BooleanFilter(field_name='has_enrollment_limit')
    
    # Content filters
    
    # Updated Zoom integration filters
    has_zoom_meeting = django_filters.BooleanFilter(method='filter_has_zoom_meeting')
    has_zoom_webinar = django_filters.BooleanFilter(method='filter_has_zoom_webinar')
    has_zoom_integration = django_filters.BooleanFilter(method='filter_has_zoom_integration')
    has_recordings = django_filters.BooleanFilter(method='filter_has_recordings')
    
    # Pricing filters
    price_min = django_filters.NumberFilter(method='filter_price_min')
    price_max = django_filters.NumberFilter(method='filter_price_max')
    is_free = django_filters.BooleanFilter(method='filter_is_free')
    
    # Time-based filters
    is_upcoming = django_filters.BooleanFilter(method='filter_is_upcoming')
    is_live_now = django_filters.BooleanFilter(method='filter_is_live_now')
    is_completed = django_filters.BooleanFilter(method='filter_is_completed')
    
    class Meta:
        model = Webinar
        fields = [
            'category', 'webinar_type','status', 'skill_level',
            'speaker', 'has_enrollment_limit'
        ]
    
    def filter_speaker_name(self, queryset, name, value):
        """Filter by speaker name"""
        return queryset.filter(
            Q(speaker__first_name__icontains=value) |
            Q(speaker__last_name__icontains=value)
        )
    
    def filter_has_spots(self, queryset, name, value):
        """Filter webinars that have available spots"""
        if value:
            from django.db.models import Count, F
            return queryset.filter(
                Q(has_enrollment_limit=False) |
                Q(has_enrollment_limit=True, 
                  enrollments__count__lt=F('max_attendees'))
            ).annotate(enrollment_count=Count('enrollments'))
        return queryset
    
    def filter_has_zoom_meeting(self, queryset, name, value):
        """Filter webinars with Zoom meetings"""
        from apps.integrations.models import ZoomMeeting
        
        if value:
            return queryset.filter(
                Exists(ZoomMeeting.objects.filter(webinar=OuterRef('pk')))
            )
        else:
            return queryset.exclude(
                Exists(ZoomMeeting.objects.filter(webinar=OuterRef('pk')))
            )
    
    def filter_has_zoom_webinar(self, queryset, name, value):
        """Filter webinars with Zoom webinars"""
        from apps.integrations.models import ZoomWebinar
        
        if value:
            return queryset.filter(
                Exists(ZoomWebinar.objects.filter(webinar=OuterRef('pk')))
            )
        else:
            return queryset.exclude(
                Exists(ZoomWebinar.objects.filter(webinar=OuterRef('pk')))
            )
    
    def filter_has_zoom_integration(self, queryset, name, value):
        """Filter webinars with any Zoom integration"""
        from apps.integrations.models import ZoomMeeting, ZoomWebinar
        
        if value:
            return queryset.filter(
                Q(Exists(ZoomMeeting.objects.filter(webinar=OuterRef('pk')))) |
                Q(Exists(ZoomWebinar.objects.filter(webinar=OuterRef('pk'))))
            )
        else:
            return queryset.exclude(
                Q(Exists(ZoomMeeting.objects.filter(webinar=OuterRef('pk')))) |
                Q(Exists(ZoomWebinar.objects.filter(webinar=OuterRef('pk'))))
            )
    
    def filter_has_recordings(self, queryset, name, value):
        """Filter webinars with recording links"""
        from apps.integrations.models import ZoomRecording
        
        if value:
            return queryset.filter(
                Q(Exists(ZoomRecording.objects.filter(
                    Q(meeting__webinar=OuterRef('pk')) |
                    Q(webinar_recording__webinar=OuterRef('pk'))
                )))
            )
        else:
            return queryset.exclude(
                Q(Exists(ZoomRecording.objects.filter(
                    Q(meeting__webinar=OuterRef('pk')) |
                    Q(webinar_recording__webinar=OuterRef('pk'))
                )))
            )
    
    def filter_price_min(self, queryset, name, value):
        """Filter by minimum price"""
        return queryset.filter(
            Q(pricing_data__live_single_price__gte=value) |
            Q(pricing_data__live_multi_price__gte=value) |
            Q(pricing_data__recorded_single_price__gte=value) |
            Q(pricing_data__recorded_multi_price__gte=value)
        )
    
    def filter_price_max(self, queryset, name, value):
        """Filter by maximum price"""
        return queryset.filter(
            Q(pricing_data__live_single_price__lte=value) |
            Q(pricing_data__live_multi_price__lte=value) |
            Q(pricing_data__recorded_single_price__lte=value) |
            Q(pricing_data__recorded_multi_price__lte=value)
        )
    
    def filter_is_free(self, queryset, name, value):
        """Filter free webinars"""
        if value:
            # Free webinars have all prices as 0 or null
            return queryset.filter(
                Q(pricing_data__live_single_price__isnull=True) &
                Q(pricing_data__live_multi_price__isnull=True) &
                Q(pricing_data__recorded_single_price__isnull=True) &
                Q(pricing_data__recorded_multi_price__isnull=True)
            )
        else:
            # Paid webinars have at least one non-zero price
            return queryset.filter(
                Q(pricing_data__live_single_price__gt=0) |
                Q(pricing_data__live_multi_price__gt=0) |
                Q(pricing_data__recorded_single_price__gt=0) |
                Q(pricing_data__recorded_multi_price__gt=0)
            )
    
    def filter_is_upcoming(self, queryset, name, value):
        """Filter upcoming webinars"""
        from django.utils import timezone
        
        if value:
            return queryset.filter(scheduled_date__gt=timezone.now())
        else:
            return queryset.filter(scheduled_date__lte=timezone.now())
    
    def filter_is_live_now(self, queryset, name, value):
        """Filter currently live webinars"""
        from django.utils import timezone
        from django.db.models import F
        
        now = timezone.now()
        
        if value:
            return queryset.filter(
                scheduled_date__lte=now,
                scheduled_date__gt=now - F('duration') * 60  # Convert minutes to seconds
            )
        else:
            return queryset.exclude(
                scheduled_date__lte=now,
                scheduled_date__gt=now - F('duration') * 60
            )
    
    def filter_is_completed(self, queryset, name, value):
        """Filter completed webinars"""
        from django.utils import timezone
        from django.db.models import F
        
        now = timezone.now()
        
        if value:
            return queryset.filter(
                scheduled_date__lt=now - F('duration') * 60
            )
        else:
            return queryset.exclude(
                scheduled_date__lt=now - F('duration') * 60
            )
