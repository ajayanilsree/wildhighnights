from django.db.models import Q
from datetime import timedelta

from django.utils import timezone

from .models import ClientLead


def employee_follow_up_notifications(request):
    user = getattr(request, 'user', None)
    employee = getattr(user, 'employee', None) if user and user.is_authenticated else None

    if not employee or not getattr(employee, 'is_active', False):
        return {
            'follow_up_notifications': [],
            'notification_count': 0,
            'notification_due_count': 0,
            'notification_today': timezone.localdate(),
            'notification_tomorrow': timezone.localdate() + timedelta(days=1),
            'is_employee_portal_user': False,
        }

    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    follow_up_notifications = list(
        ClientLead.objects.filter(
            employee=employee,
            follow_up_date__in=[today, tomorrow],
        )
        .exclude(status__in=['Converted', 'Not Interested'])
        .order_by('follow_up_date', 'created_at')
    )

    unseen_qs = ClientLead.objects.filter(
        employee=employee,
        follow_up_date__in=[today, tomorrow],
    ).exclude(status__in=['Converted', 'Not Interested'])

    if employee.notifications_last_seen_at:
        unseen_qs = unseen_qs.filter(
            Q(created_date__gt=employee.notifications_last_seen_at)
            | Q(last_updated__gt=employee.notifications_last_seen_at)
        )

    return {
        'follow_up_notifications': follow_up_notifications,
        'notification_count': unseen_qs.count(),
        'notification_due_count': len(follow_up_notifications),
        'notification_today': today,
        'notification_tomorrow': tomorrow,
        'is_employee_portal_user': True,
    }
