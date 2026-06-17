from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from decimal import Decimal
import calendar
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.messages import get_messages
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Count, Q, Sum
from django.db.models import DateTimeField
from django.db.models.functions import Coalesce
from django.urls import reverse
from urllib.parse import urlencode
from .models import Artist, Booking, SiteSettings, ActivityLog, Event, GalleryImage, BookingExpense, ArtistAvailability, Employee, ClientLead

CONVERTED_INPUT_STATUS = 'Converted'
CONVERTED_PENDING_STATUS = 'Converted - Pending Booking'
CONVERTED_BOOKED_STATUS = 'Converted - Booking Created'
CONVERTED_STATUSES = {CONVERTED_INPUT_STATUS, CONVERTED_PENDING_STATUS, CONVERTED_BOOKED_STATUS}

def format_percentage(val):
    if val is None:
        return "0%"
    val = Decimal(str(val)).quantize(Decimal('0.01'))
    val_str = str(val)
    if '.' in val_str:
        val_str = val_str.rstrip('0').rstrip('.')
    return f"{val_str}%"


def build_artist_calendar_payload(artist):
    bookings = Booking.objects.filter(artist=artist).select_related('artist').prefetch_related('expenses').order_by('date', 'time')
    bookings_data = []
    for b in bookings:
        deal_amount = b.deal_amount
        gst_percentage = Decimal('18')
        gst_amount = deal_amount * gst_percentage / Decimal('100')
        total_amount = deal_amount + gst_amount
        expenses_data = [
            {
                'name': e.name,
                'amount': float(e.amount.quantize(Decimal('0.01'))),
                'borne_by': e.borne_by or 'WHN',
            }
            for e in b.expenses.all()
        ]
        financials = booking_financials(b)

        bookings_data.append({
            'id': b.id,
            'type': 'booking',
            'date': b.date.strftime('%Y-%m-%d'),
            'title': b.venue,
            'time': b.time.strftime('%H:%M') if b.time else 'TBA',
            'venue': b.venue,
            'location': b.location,
            'duration': b.duration or 'Standard Set',
            'event_type': b.event_type,
            'status': b.status.lower(),
            'status_label': b.status,
            'notes': b.notes or '',
            'artist': b.artist.name,
            'booking_type': b.booking_type,
            'custom_artist_percentage': float(b.custom_artist_percentage.quantize(Decimal('0.01'))) if b.custom_artist_percentage is not None else None,
            'deal_type': b.deal_type,
            'deal_amount': float(deal_amount.quantize(Decimal('0.01'))),
            'gst_amount': float(gst_amount.quantize(Decimal('0.01'))),
            'total_amount': float(total_amount.quantize(Decimal('0.01'))),
            'split_percentage': financials['pct_str'],
            'artist_commission': float(financials['artist_commission'].quantize(Decimal('0.01'))),
            'artist_share': float(financials['artist_net'].quantize(Decimal('0.01'))),
            'net_amount': float(financials['artist_net'].quantize(Decimal('0.01'))),
            'owner_profit': float(financials['owner_profit'].quantize(Decimal('0.01'))),
            'artist_expenses': float(financials['artist_expenses'].quantize(Decimal('0.01'))),
            'whn_expenses': float(financials['whn_expenses'].quantize(Decimal('0.01'))),
            'travel_pdf': b.travel_pdf.url if b.travel_pdf else '',
            'accommodation_pdf': b.accommodation_pdf.url if b.accommodation_pdf else '',
            'accommodation_details': b.accommodation_details or '',
            'ground_transport': b.ground_transport,
            'transport_details': b.transport_details or '',
            'sound_check': b.sound_check,
            'artwork_attachment': b.artwork_attachment.url if b.artwork_attachment else '',
            'expenses': expenses_data
        })

    availabilities = ArtistAvailability.objects.filter(artist=artist, status='busy')
    busy_data = []
    for a in availabilities:
        busy_data.append({
            'id': a.id,
            'type': 'busy',
            'date': a.date.strftime('%Y-%m-%d'),
            'title': 'Busy / Unavailable',
            'note': a.note or '',
            'notes': a.note or ''
        })

    return {
        'bookings': bookings_data,
        'busy_dates': busy_data,
    }


def crm_queryset(base_qs):
    return base_qs.select_related('employee', 'employee__user', 'conversion_artist', 'conversion_booking').annotate(
        crm_created_at_value=Coalesce('created_at', 'created_date', output_field=DateTimeField()),
        crm_updated_at_value=Coalesce('updated_at', 'last_updated', 'created_at', 'created_date', output_field=DateTimeField()),
    )


def booking_split(booking):
    if booking.booking_type == 'Sale':
        return Decimal('0.85'), "85%"
    if booking.booking_type == 'Lead':
        return Decimal('0.90'), "90%"
    if booking.booking_type == 'Custom':
        custom_pct = booking.custom_artist_percentage or Decimal('0.00')
        return custom_pct / Decimal('100'), format_percentage(custom_pct)
    return Decimal('0.90'), "90%"


def booking_financials(booking):
    pct, pct_str = booking_split(booking)
    artist_commission = booking.deal_amount * pct
    whn_share = booking.deal_amount - artist_commission
    artist_expenses = sum(
        (exp.amount for exp in booking.expenses.all() if exp.borne_by == 'Artist'),
        Decimal('0.00')
    )
    whn_expenses = sum(
        (exp.amount for exp in booking.expenses.all() if exp.borne_by != 'Artist'),
        Decimal('0.00')
    )
    return {
        'pct': pct,
        'pct_str': pct_str,
        'artist_commission': artist_commission,
        'whn_share': whn_share,
        'artist_expenses': artist_expenses,
        'whn_expenses': whn_expenses,
        'total_expenses': artist_expenses + whn_expenses,
        'artist_net': artist_commission - artist_expenses,
        'owner_profit': whn_share - whn_expenses,
    }


def normalized_expense_bearer(value):
    return 'Artist' if value == 'Artist' else 'WHN'


def crm_apply_date_filter(qs, period='', from_date=None, to_date=None):
    today = timezone.localdate()
    if period == 'today':
        return qs.filter(crm_created_at_value__date=today)
    if period == 'yesterday':
        return qs.filter(crm_created_at_value__date=today - timedelta(days=1))
    if period == 'week':
        week_start = today - timedelta(days=today.weekday())
        return qs.filter(crm_created_at_value__date__gte=week_start)
    if period == 'month':
        month_start = today.replace(day=1)
        return qs.filter(crm_created_at_value__date__gte=month_start)
    if period == 'year':
        year_start = today.replace(month=1, day=1)
        return qs.filter(crm_created_at_value__date__gte=year_start)
    if period == 'custom' and from_date and to_date:
        return qs.filter(crm_created_at_value__date__range=(from_date, to_date))
    return qs


def crm_apply_conversion_date_filter(qs, period='', from_date=None, to_date=None):
    today = timezone.localdate()
    if period == 'today':
        return qs.filter(crm_updated_at_value__date=today)
    if period == 'yesterday':
        return qs.filter(crm_updated_at_value__date=today - timedelta(days=1))
    if period == 'week':
        week_start = today - timedelta(days=today.weekday())
        return qs.filter(crm_updated_at_value__date__gte=week_start)
    if period == 'month':
        month_start = today.replace(day=1)
        return qs.filter(crm_updated_at_value__date__gte=month_start)
    if period == 'year':
        year_start = today.replace(month=1, day=1)
        return qs.filter(crm_updated_at_value__date__gte=year_start)
    if period == 'custom' and from_date and to_date:
        return qs.filter(crm_updated_at_value__date__range=(from_date, to_date))
    return qs


def crm_build_summary(qs):
    summary = qs.aggregate(
        total_leads=Count('id', filter=Q(type='lead')),
        total_sales=Count('id', filter=Q(type='sale')),
        follow_up_needed=Count('id', filter=Q(status='Follow-up Needed')),
        converted=Count('id', filter=Q(status=CONVERTED_BOOKED_STATUS)),
        converted_leads=Count('id', filter=Q(status=CONVERTED_BOOKED_STATUS, type='lead')),
        converted_sales=Count('id', filter=Q(status=CONVERTED_BOOKED_STATUS, type='sale')),
        converted_lead_amount=Sum('conversion_deal_amount', filter=Q(status=CONVERTED_BOOKED_STATUS, type='lead')),
        converted_sale_amount=Sum('conversion_deal_amount', filter=Q(status=CONVERTED_BOOKED_STATUS, type='sale')),
        not_interested=Count('id', filter=Q(status='Not Interested')),
    )
    return summary


def parse_date_field(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def parse_decimal_field(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(value)
    except Exception:
        return None


def crm_booking_type(lead):
    return 'Sale' if lead.type == 'sale' else 'Lead'


def build_crm_booking_notes(lead):
    notes_parts = [
        f"CRM conversion from {lead.employee.name}",
        f"CRM status: {lead.status}",
        f"Promoter: {lead.promoter_name}",
        f"Contact: {lead.contact_number}",
    ]
    if lead.notes:
        notes_parts.append(f"Notes: {lead.notes}")
    return "\n".join(notes_parts)


def date_from_datetime(value):
    if not value:
        return None
    if timezone.is_aware(value):
        return timezone.localtime(value).date()
    return value.date()


def get_follow_up_result(lead, today=None):
    today = today or timezone.localdate()
    follow_up_date = lead.follow_up_date
    updated_date = date_from_datetime(getattr(lead, 'crm_updated_at_value', None) or lead.crm_updated_at)
    terminal_statuses = CONVERTED_STATUSES | {'Not Interested'}

    if not follow_up_date:
        return ''
    if follow_up_date > today:
        return 'upcoming'
    if updated_date and updated_date >= follow_up_date:
        return 'completed'
    if follow_up_date == today and lead.status == 'Follow-up Needed':
        return 'due_today'
    if lead.status in terminal_statuses:
        return 'completed'
    if follow_up_date < today and (not updated_date or updated_date < follow_up_date):
        return 'missed'
    return 'due_today' if follow_up_date == today else 'missed'


def get_missed_follow_up_count(base_qs=None):
    today = timezone.localdate()
    leads = crm_queryset(base_qs or ClientLead.objects.all()).filter(
        follow_up_date__lt=today
    ).exclude(status__in=list(CONVERTED_STATUSES | {'Not Interested'}))

    missed_count = 0
    for lead in leads:
        if get_follow_up_result(lead, today) == 'missed':
            missed_count += 1
    return missed_count


def format_date_label(value):
    if not value:
        return ''
    return f"{value.strftime('%B')} {value.day}, {value.year}"


def log_activity(action, request=None, role='admin', employee_name=None, related_record=None):
    ActivityLog.objects.create(
        user=request.user if request and request.user.is_authenticated else None,
        employee_name=employee_name,
        role=role,
        action=action,
        related_record=related_record,
    )


def lead_activity_changes(old_lead, lead, employee_name):
    entries = []
    if old_lead.type != lead.type and old_lead.type == 'lead' and lead.type == 'sale':
        entries.append(f"{employee_name} converted Lead to Sale: {lead.promoter_name}")
    elif old_lead.type != lead.type:
        entries.append(f"{employee_name} changed type of {lead.promoter_name} from {old_lead.type.title()} to {lead.type.title()}")

    if old_lead.status != lead.status:
        entries.append(
            f"{employee_name} changed status of {lead.promoter_name} from {old_lead.status} to {lead.status}"
        )

    if old_lead.follow_up_date != lead.follow_up_date:
        follow_up_label = format_date_label(lead.follow_up_date) if lead.follow_up_date else 'No follow-up date'
        entries.append(f"{employee_name} updated follow-up date for {lead.promoter_name} to {follow_up_label}")

    contact_fields_changed = (
        old_lead.promoter_name != lead.promoter_name or
        old_lead.contact_number != lead.contact_number or
        old_lead.city != lead.city or
        old_lead.venue != lead.venue
    )
    if contact_fields_changed:
        entries.append(f"{employee_name} updated client/contact/venue details for {lead.promoter_name}")

    if not entries:
        entries.append(f"{employee_name} updated Lead/Sale: {lead.promoter_name}")
    return entries


@ensure_csrf_cookie
def index(request):
    settings = SiteSettings.objects.first()
    if not settings:
        settings = SiteSettings.objects.create()
    artists = Artist.objects.all()
    events = Event.objects.filter(status='Published').order_by('event_date', 'event_time')
    gallery_images = GalleryImage.objects.filter(is_active=True).order_by("-created_at")
    return render(request, 'bookings/index.html', {
        'settings': settings,
        'artists': artists,
        'events': events,
        'gallery_images': gallery_images
    })

def all_events_view(request):
    events = Event.objects.filter(status='Published').order_by('event_date', 'event_time')
    return render(request, 'bookings/all_events.html', {'events': events})

def api_artists(request):
    artists = Artist.objects.all()
    data = [
        {
            'id': a.slug,
            'name': a.name,
            'genre': a.genre,
            'instagram': a.instagram,
            'image': a.artist_image.url if a.artist_image else None
        }
        for a in artists
    ]
    return JsonResponse(data, safe=False)

def api_bookings(request):
    bookings = Booking.objects.select_related('artist').all()
    data = [
        {
            'id': b.id,
            'artistId': b.artist.slug,
            'venue': b.venue,
            'date': b.date.strftime('%Y-%m-%d'),
            'time': b.time.strftime('%H:%M') if b.time else '',
            'type': b.event_type,
            'status': b.status,
            'location': b.location,
            'publicNotes': b.notes, 
        }
        for b in bookings
    ]
    return JsonResponse(data, safe=False)

def login_view(request):
    if request.user.is_authenticated:
        if request.user.is_superuser or request.user.is_staff:
            return redirect('dashboard')
        elif hasattr(request.user, 'employee') and request.user.employee.is_active:
            return redirect('employee_dashboard')
        elif hasattr(request.user, 'artist'):
            return redirect('artist_dashboard')
        return redirect('artist_dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if hasattr(user, 'employee') and not user.employee.is_active:
                messages.error(request, 'Access Denied: Employee account is deactivated.')
                return render(request, 'bookings/login.html')
            login(request, user)
            if user.is_superuser or user.is_staff:
                return redirect('dashboard')
            elif hasattr(user, 'employee') and user.employee.is_active:
                return redirect('employee_dashboard')
            elif hasattr(user, 'artist'):
                return redirect('artist_dashboard')
            return redirect('artist_dashboard')
        else:
            messages.error(request, 'Invalid username or password')
            
    return render(request, 'bookings/login.html')

@login_required(login_url='login')
def dashboard_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        if hasattr(request.user, 'employee') and request.user.employee.is_active:
            return redirect('employee_dashboard')
        elif hasattr(request.user, 'artist'):
            return redirect('artist_dashboard')
        messages.error(request, "Access Denied: Administrative privileges required.")
        return redirect('login')
        
    context = {
        'total_artists': Artist.objects.count(),
        'total_bookings': Booking.objects.count(),
        'confirmed_events': Booking.objects.filter(status='Confirmed').count(),
        'pending_requests': Booking.objects.filter(status='Tentative').count(),
        'recent_bookings': Booking.objects.all().order_by('-date')[:5],
        'activity_logs': ActivityLog.objects.select_related('user').order_by('-created_at')[:10],
    }
    return render(request, 'bookings/dashboard.html', context)

@login_required(login_url='login')
def add_booking_view(request):
    artists = Artist.objects.all()
    crm_lead = None
    crm_lead_id = request.POST.get('crm_lead_id') or request.GET.get('crm_lead')
    if crm_lead_id:
        crm_qs = ClientLead.objects.select_related('employee', 'employee__user', 'conversion_artist', 'conversion_booking')
        if not (request.user.is_staff or request.user.is_superuser):
            if hasattr(request.user, 'employee'):
                crm_qs = crm_qs.filter(employee=request.user.employee)
            else:
                crm_qs = crm_qs.none()
        crm_lead = get_object_or_404(crm_qs, id=crm_lead_id)

    if request.method == 'POST':
        artist_id = request.POST.get('artist')
        event_type = request.POST.get('event_type')
        venue = request.POST.get('venue')
        location = request.POST.get('location')
        date = request.POST.get('date')
        time = request.POST.get('time')
        duration = request.POST.get('duration')
        
        booking_type = request.POST.get('booking_type')
        custom_pct_val = request.POST.get('custom_artist_percentage')
        if booking_type == 'Custom' and custom_pct_val:
            try:
                custom_artist_percentage = Decimal(custom_pct_val)
                if custom_artist_percentage < Decimal('0'):
                    custom_artist_percentage = Decimal('0')
                elif custom_artist_percentage > Decimal('100'):
                    custom_artist_percentage = Decimal('100')
            except:
                custom_artist_percentage = Decimal('0')
        else:
            custom_artist_percentage = None

        deal_type = request.POST.get('deal_type')
        deal_amount = request.POST.get('deal_amount') or 0.00
        
        ground_transport = request.POST.get('ground_transport')
        sound_check = request.POST.get('sound_check')
        status = request.POST.get('status')
        notes = request.POST.get('notes')
        
        accommodation_details = request.POST.get('accommodation_details')
        transport_details = request.POST.get('transport_details')

        # Files
        travel_pdf = request.FILES.get('travel_pdf')
        accommodation_pdf = request.FILES.get('accommodation_pdf')
        artwork_attachment = request.FILES.get('artwork_attachment')

        artist = get_object_or_404(Artist, id=artist_id)
        
        # Create Booking
        booking = Booking.objects.create(
            artist=artist,
            created_by=request.user,
            event_type=event_type,
            venue=venue,
            location=location,
            date=date,
            time=time if time else None,
            duration=duration,
            booking_type=booking_type,
            custom_artist_percentage=custom_artist_percentage,
            deal_type=deal_type,
            deal_amount=deal_amount,
            travel_pdf=travel_pdf,
            accommodation_pdf=accommodation_pdf,
            accommodation_details=accommodation_details,
            ground_transport=ground_transport,
            transport_details=transport_details if ground_transport == 'Yes' else None,
            sound_check=sound_check,
            artwork_attachment=artwork_attachment,
            status=status,
            notes=notes
        )

        # Dynamic Expenses
        expense_names = request.POST.getlist('expense_name[]')
        expense_amounts = request.POST.getlist('expense_amount[]')
        expense_bearers = request.POST.getlist('expense_borne_by[]')
        for index, (name, amt) in enumerate(zip(expense_names, expense_amounts)):
            if name.strip() and amt:
                BookingExpense.objects.create(
                    booking=booking,
                    name=name.strip(),
                    amount=amt,
                    borne_by=normalized_expense_bearer(expense_bearers[index] if index < len(expense_bearers) else 'WHN')
                )

        if crm_lead:
            crm_lead.conversion_booking = booking
            crm_lead.status = CONVERTED_BOOKED_STATUS
            crm_lead.conversion_event_date = booking.date
            crm_lead.conversion_deal_amount = booking.deal_amount
            crm_lead.conversion_artist = booking.artist
            crm_lead.follow_up_date = None
            crm_lead.save(update_fields=[
                'conversion_booking',
                'status',
                'conversion_event_date',
                'conversion_deal_amount',
                'conversion_artist',
                'follow_up_date',
                'updated_at',
                'last_updated',
            ])
            log_activity(
                f"{crm_lead.employee.name} completed booking for converted {crm_lead.get_type_display()}: {crm_lead.promoter_name}",
                request=request,
                role='employee' if hasattr(request.user, 'employee') else 'admin',
                employee_name=crm_lead.employee.name,
                related_record=crm_lead.promoter_name,
            )

        log_activity(
            f"Booking created: {artist.name} - {venue}",
            request=request,
            role='employee' if hasattr(request.user, 'employee') else 'admin',
            employee_name=request.user.employee.name if hasattr(request.user, 'employee') else None,
            related_record=venue,
        )
        if request.user.is_staff or request.user.is_superuser:
            if request.POST.get('booking_source') == 'calendar':
                redirect_url = reverse('admin_calendar')
                query_params = {
                    'artist': artist.id,
                    'date': date,
                }
                return redirect(f"{redirect_url}?{urlencode(query_params)}")
            return redirect('manage_bookings')
        if request.POST.get('booking_source') == 'employee_calendar':
            redirect_url = reverse('employee_calendar')
            query_params = {
                'artist': artist.id,
                'date': date,
            }
            return redirect(f"{redirect_url}?{urlencode(query_params)}")
        return redirect('employee_bookings')

    selected_artist_id = request.GET.get('artist') or ''
    selected_date = request.GET.get('date') or ''
    booking_source = request.GET.get('source') or ''
    selected_booking_type = ''
    selected_venue = ''
    selected_location = ''
    selected_deal_amount = ''
    selected_notes = ''

    if crm_lead:
        selected_artist_id = str(crm_lead.conversion_artist_id or selected_artist_id or '')
        selected_date = crm_lead.conversion_event_date.isoformat() if crm_lead.conversion_event_date else selected_date
        selected_booking_type = crm_booking_type(crm_lead)
        selected_venue = crm_lead.venue or ''
        selected_location = crm_lead.city or ''
        selected_deal_amount = crm_lead.conversion_deal_amount or ''
        selected_notes = build_crm_booking_notes(crm_lead)
        booking_source = booking_source or 'employee_crm'

    return render(request, 'bookings/add_booking.html', {
        'artists': artists,
        'selected_artist_id': selected_artist_id,
        'selected_date': selected_date,
        'booking_source': booking_source,
        'selected_booking_type': selected_booking_type,
        'selected_venue': selected_venue,
        'selected_location': selected_location,
        'selected_deal_amount': selected_deal_amount,
        'selected_notes': selected_notes,
        'crm_lead': crm_lead,
    })

@login_required(login_url='login')
def add_artist_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        genre = request.POST.get('genre', '')
        instagram = request.POST.get('instagram', '')
        artist_image = request.FILES.get('artist_image')
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # Create User
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return render(request, 'bookings/add_artist.html')
            
        user = User.objects.create_user(username=username, password=password)
        
        # Create Artist
        Artist.objects.create(
            user=user,
            name=name, 
            genre=genre,
            instagram=instagram,
            artist_image=artist_image
        )
        log_activity(
            f"Artist created: {name}",
            request=request,
            role='admin',
            related_record=name,
        )
        return redirect('dashboard')

    return render(request, 'bookings/add_artist.html')

@login_required(login_url='login')
def edit_artist_view(request, artist_id):
    artist = get_object_or_404(Artist, id=artist_id)
    user = artist.user
    
    if request.method == 'POST':
        artist.name = request.POST.get('name')
        artist.genre = request.POST.get('genre', '')
        artist.instagram = request.POST.get('instagram', '')
        
        new_username = request.POST.get('username')
        new_password = request.POST.get('new_password')
        
        # Update User
        if user:
            if new_username and new_username != user.username:
                if User.objects.filter(username=new_username).exists():
                    messages.error(request, 'Username already exists.')
                    return render(request, 'bookings/edit_artist.html', {'artist': artist})
                user.username = new_username
            
            if new_password:
                user.set_password(new_password)
            
            user.save()
        
        # Update Image
        if 'artist_image' in request.FILES:
            artist.artist_image = request.FILES.get('artist_image')
            
        artist.save()
        
        log_activity(
            f"Artist updated: {artist.name}",
            request=request,
            role='admin',
            related_record=artist.name,
        )
        return redirect('manage_artists')

    return render(request, 'bookings/edit_artist.html', {'artist': artist})

@login_required(login_url='login')
def add_event_view(request):
    if request.method == 'POST':
        event_name = request.POST.get('event_name')
        event_date = request.POST.get('event_date')
        event_time = request.POST.get('event_time')
        venue_name = request.POST.get('venue_name')
        location = request.POST.get('location')
        status = request.POST.get('status')
        event_image = request.FILES.get('event_image')
        
        Event.objects.create(
            event_name=event_name,
            event_date=event_date,
            event_time=event_time,
            venue_name=venue_name,
            location=location,
            status=status,
            event_image=event_image
        )
        log_activity(
            f"Event created: {event_name}",
            request=request,
            role='admin',
            related_record=event_name,
        )
        return redirect('manage_events')

    return render(request, 'bookings/add_event.html')

@login_required(login_url='login')
def manage_events_view(request):
    events = Event.objects.all().order_by('-event_date')
    return render(request, 'bookings/manage_events.html', {'events': events})

@login_required(login_url='login')
def edit_event_view(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    if request.method == 'POST':
        event.event_name = request.POST.get('event_name')
        event.event_date = request.POST.get('event_date')
        event.event_time = request.POST.get('event_time')
        event.venue_name = request.POST.get('venue_name')
        event.location = request.POST.get('location')
        event.status = request.POST.get('status')
        
        if 'event_image' in request.FILES:
            event.event_image = request.FILES.get('event_image')
            
        event.save()
        log_activity(
            f"Event updated: {event.event_name}",
            request=request,
            role='admin',
            related_record=event.event_name,
        )
        return redirect('manage_events')

    return render(request, 'bookings/edit_event.html', {'event': event})

@login_required(login_url='login')
def delete_event_view(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    name = event.event_name
    event.delete()
    log_activity(
        f"Event removed: {name}",
        request=request,
        role='admin',
        related_record=name,
    )
    return redirect('manage_events')

@login_required(login_url='login')
def manage_gallery_view(request):
    images = GalleryImage.objects.all().order_by('-created_at')
    return render(request, 'bookings/manage_gallery.html', {'images': images})

@login_required(login_url='login')
def add_gallery_image_view(request):
    if request.method == 'POST':
        title = request.POST.get('title', '')
        image = request.FILES.get('image')
        is_active = request.POST.get('is_active') == 'on'
        
        GalleryImage.objects.create(
            title=title,
            image=image,
            is_active=is_active
        )
        log_activity(
            f"Gallery image added: {title if title else 'Untitled'}",
            request=request,
            role='admin',
            related_record=title if title else 'Untitled',
        )
        return redirect('manage_gallery')

    return render(request, 'bookings/add_gallery_image.html')

@login_required(login_url='login')
def edit_gallery_image_view(request, image_id):
    img = get_object_or_404(GalleryImage, id=image_id)
    if request.method == 'POST':
        img.title = request.POST.get('title', '')
        img.is_active = request.POST.get('is_active') == 'on'
        if 'image' in request.FILES:
            img.image = request.FILES.get('image')
        img.save()
        log_activity(
            f"Gallery image updated: {img.title if img.title else 'Untitled'}",
            request=request,
            role='admin',
            related_record=img.title if img.title else 'Untitled',
        )
        return redirect('manage_gallery')

    return render(request, 'bookings/edit_gallery_image.html', {'image': img})

@login_required(login_url='login')
def delete_gallery_image_view(request, image_id):
    img = get_object_or_404(GalleryImage, id=image_id)
    title = img.title if img.title else 'Untitled'
    img.delete()
    log_activity(
        f"Gallery image removed: {title}",
        request=request,
        role='admin',
        related_record=title,
    )
    return redirect('manage_gallery')

@login_required(login_url='login')
def manage_artists_view(request):
    artists = Artist.objects.all().select_related('user')
    return render(request, 'bookings/manage_artists.html', {'artists': artists})

@login_required(login_url='login')
def delete_artist_view(request, artist_id):
    artist = get_object_or_404(Artist, id=artist_id)
    name = artist.name
    user = artist.user
    
    artist.delete()
    if user:
        user.delete()
        
    log_activity(
        f"Artist removed: {name}",
        request=request,
        role='admin',
        related_record=name,
    )
    return redirect('manage_artists')

@login_required(login_url='login')
def dashboard_settings_view(request):
    settings = SiteSettings.objects.first()
    if not settings:
        settings = SiteSettings.objects.create()

    if request.method == 'POST':
        settings.title = request.POST.get('title')
        settings.instagram_link = request.POST.get('instagram_link')
        settings.contact_email = request.POST.get('contact_email')
        settings.footer_description = request.POST.get('footer_description')
        settings.hero_text = request.POST.get('hero_text')
        settings.save()
        log_activity(
            "Settings updated",
            request=request,
            role='admin',
            related_record='Site Settings',
        )
        return redirect('dashboard')

    return render(request, 'bookings/settings.html', {'settings': settings})

def logout_view(request):
    storage = get_messages(request)
    for _ in storage:
        pass
    logout(request)
    messages.success(request, 'Logged out successfully.')
    return redirect('login')

@login_required(login_url='login')
def manage_bookings_view(request):
    bookings = Booking.objects.select_related('artist').all().order_by('-date')
    return render(request, 'bookings/manage_bookings.html', {'bookings': bookings})

@login_required(login_url='login')
def edit_booking_view(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    artists = Artist.objects.all()
    
    if request.method == 'POST':
        artist_id = request.POST.get('artist')
        event_type = request.POST.get('event_type')
        venue = request.POST.get('venue')
        location = request.POST.get('location')
        date = request.POST.get('date')
        time = request.POST.get('time')
        duration = request.POST.get('duration')
        
        booking_type = request.POST.get('booking_type')
        custom_pct_val = request.POST.get('custom_artist_percentage')
        if booking_type == 'Custom' and custom_pct_val:
            try:
                custom_artist_percentage = Decimal(custom_pct_val)
                if custom_artist_percentage < Decimal('0'):
                    custom_artist_percentage = Decimal('0')
                elif custom_artist_percentage > Decimal('100'):
                    custom_artist_percentage = Decimal('100')
            except:
                custom_artist_percentage = Decimal('0')
        else:
            custom_artist_percentage = None

        deal_type = request.POST.get('deal_type')
        deal_amount = request.POST.get('deal_amount') or 0.00
        
        ground_transport = request.POST.get('ground_transport')
        sound_check = request.POST.get('sound_check')
        status = request.POST.get('status')
        notes = request.POST.get('notes')
        
        accommodation_details = request.POST.get('accommodation_details')
        transport_details = request.POST.get('transport_details')

        artist = get_object_or_404(Artist, id=artist_id)
        
        booking.artist = artist
        booking.event_type = event_type
        booking.venue = venue
        booking.location = location
        booking.date = date
        booking.time = time if time else None
        booking.duration = duration
        booking.booking_type = booking_type
        booking.custom_artist_percentage = custom_artist_percentage
        booking.deal_type = deal_type
        booking.deal_amount = deal_amount
        booking.ground_transport = ground_transport
        booking.sound_check = sound_check
        booking.status = status
        booking.notes = notes
        booking.accommodation_details = accommodation_details
        booking.transport_details = transport_details if ground_transport == 'Yes' else None

        # Update files if supplied
        if 'travel_pdf' in request.FILES:
            booking.travel_pdf = request.FILES.get('travel_pdf')
        if 'accommodation_pdf' in request.FILES:
            booking.accommodation_pdf = request.FILES.get('accommodation_pdf')
        if 'artwork_attachment' in request.FILES:
            booking.artwork_attachment = request.FILES.get('artwork_attachment')

        # Clean transport details if transport is changed to 'No'
        if ground_transport == 'No':
            booking.transport_details = None

        booking.save()

        # Update expenses by clear and rebuild
        booking.expenses.all().delete()
        expense_names = request.POST.getlist('expense_name[]')
        expense_amounts = request.POST.getlist('expense_amount[]')
        expense_bearers = request.POST.getlist('expense_borne_by[]')
        for index, (name, amt) in enumerate(zip(expense_names, expense_amounts)):
            if name.strip() and amt:
                BookingExpense.objects.create(
                    booking=booking,
                    name=name.strip(),
                    amount=amt,
                    borne_by=normalized_expense_bearer(expense_bearers[index] if index < len(expense_bearers) else 'WHN')
                )

        log_activity(
            f"Booking updated: {artist.name} - {venue}",
            request=request,
            role='admin',
            related_record=venue,
        )
        if request.user.is_staff or request.user.is_superuser:
            return redirect('manage_bookings')
        return redirect('employee_bookings')

    return render(request, 'bookings/edit_booking.html', {
        'booking': booking,
        'artists': artists
    })

@login_required(login_url='login')
def delete_booking_view(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    artist_name = booking.artist.name
    venue = booking.venue
    
    booking.delete()
    
    log_activity(
        f"Booking removed: {artist_name} - {venue}",
        request=request,
        role='admin',
        related_record=venue,
    )
    if request.user.is_staff or request.user.is_superuser:
        return redirect('manage_bookings')
    return redirect('employee_bookings')


@login_required(login_url='login')
def total_bookings_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Access Denied: Administrative privileges required.")
        return redirect('login')
        
    now = timezone.now()
    selected_month = request.GET.get('month')
    selected_year = request.GET.get('year')
    
    if selected_month:
        try:
            selected_month = int(selected_month)
        except ValueError:
            selected_month = now.month
    else:
        selected_month = now.month
        
    if selected_year:
        try:
            selected_year = int(selected_year)
        except ValueError:
            selected_year = now.year
    else:
        selected_year = now.year
        
    bookings = Booking.objects.filter(date__year=selected_year, date__month=selected_month).order_by('-date')
    
    total_count = bookings.count()
    confirmed_count = bookings.filter(status='Confirmed').count()
    tentative_count = bookings.filter(status='Tentative').count()
    cancelled_count = bookings.filter(status='Cancelled').count()
    
    months_list = [
        {'value': 1, 'name': 'January'},
        {'value': 2, 'name': 'February'},
        {'value': 3, 'name': 'March'},
        {'value': 4, 'name': 'April'},
        {'value': 5, 'name': 'May'},
        {'value': 6, 'name': 'June'},
        {'value': 7, 'name': 'July'},
        {'value': 8, 'name': 'August'},
        {'value': 9, 'name': 'September'},
        {'value': 10, 'name': 'October'},
        {'value': 11, 'name': 'November'},
        {'value': 12, 'name': 'December'},
    ]
    
    years_list = range(2020, 2031)
    
    context = {
        'bookings': bookings,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'total_count': total_count,
        'confirmed_count': confirmed_count,
        'tentative_count': tentative_count,
        'cancelled_count': cancelled_count,
        'months': months_list,
        'years': years_list,
    }
    return render(request, 'bookings/total_bookings.html', context)


# =========================================================================
# Artist Portal Views & Security Decorator
# =========================================================================

def artist_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                from django.http import JsonResponse
                return JsonResponse({'error': 'Authentication required.'}, status=401)
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path(), login_url='login')
            
        if not hasattr(request.user, 'artist'):
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                from django.http import JsonResponse
                return JsonResponse({'error': 'Access Denied: You do not have an active Artist profile.'}, status=403)
            messages.error(request, "Access Denied: You do not have an active Artist profile.")
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def employee_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                from django.http import JsonResponse
                return JsonResponse({'error': 'Authentication required.'}, status=401)
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path(), login_url='login')
            
        if not (hasattr(request.user, 'employee') and request.user.employee.is_active):
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                from django.http import JsonResponse
                return JsonResponse({'error': 'Access Denied: You do not have an active Employee profile.'}, status=403)
            messages.error(request, "Access Denied: You do not have an active Employee profile.")
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


@artist_required
def artist_dashboard_view(request):
    artist = request.user.artist
    bookings = Booking.objects.filter(artist=artist)
    confirmed_count = bookings.filter(status='Confirmed').count()
    tentative_count = bookings.filter(status='Tentative').count()
    
    context = {
        'artist': artist,
        'total_bookings': bookings.count(),
        'confirmed_count': confirmed_count,
        'tentative_count': tentative_count,
    }
    return render(request, 'bookings/artist_dashboard.html', context)


@artist_required
@ensure_csrf_cookie
def artist_calendar_view(request):
    artist = request.user.artist
    today = timezone.localdate()
    calendar_payload = build_artist_calendar_payload(artist)
    bookings_by_date = {item['date']: item for item in calendar_payload['bookings']}
    busy_by_date = {item['date']: item for item in calendar_payload['busy_dates']}

    month_calendar = calendar.Calendar(firstweekday=6)
    calendar_cells = []
    for week in month_calendar.monthdatescalendar(today.year, today.month):
        week_cells = []
        for day in week:
            date_str = day.strftime('%Y-%m-%d')
            booking = bookings_by_date.get(date_str)
            busy = busy_by_date.get(date_str)
            week_cells.append({
                'date_str': date_str,
                'day': day.day,
                'in_month': day.month == today.month,
                'is_today': day == today,
                'booking': booking,
                'busy': busy,
                'has_booking': bool(booking),
                'is_confirmed': bool(booking and booking['status'] == 'confirmed'),
                'is_tentative': bool(booking and booking['status'] != 'confirmed'),
                'is_busy': bool(busy),
            })
        calendar_cells.append(week_cells)

    return render(request, 'bookings/artist_calendar.html', {
        'artist': artist,
        'current_month_name': today.strftime('%B'),
        'current_year': today.year,
        'calendar_cells': calendar_cells,
        'artist_calendar_payload': calendar_payload,
    })


@login_required(login_url='login')
def admin_calendar_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Access Denied: Administrative privileges required.")
        return redirect('login')
        
    artists = Artist.objects.all().order_by('name')
    selected_artist_id = request.GET.get('artist') or ''
    selected_date = request.GET.get('date') or ''
    return render(request, 'bookings/admin_calendar.html', {
        'artists': artists,
        'selected_artist_id': selected_artist_id,
        'selected_date': selected_date,
    })


@login_required(login_url='login')
def api_artist_calendar_events(request):
    # Enforce role-based access
    if request.user.is_staff or request.user.is_superuser or (hasattr(request.user, 'employee') and request.user.employee.is_active):
        artist_id = request.GET.get('artist_id')
        if not artist_id:
            first_artist = Artist.objects.first()
            if not first_artist:
                return JsonResponse({'bookings': [], 'busy_dates': []})
            artist = first_artist
        else:
            try:
                artist = Artist.objects.get(id=artist_id)
            except Artist.DoesNotExist:
                return JsonResponse({'error': 'Artist not found'}, status=404)
    else:
        if not hasattr(request.user, 'artist'):
            return JsonResponse({'error': 'Access Denied: You do not have an active Artist profile.'}, status=403)
        artist = request.user.artist
    
    return JsonResponse(build_artist_calendar_payload(artist))


@artist_required
def api_add_busy_date(request):
    from django.views.decorators.http import require_POST
    import json
    from datetime import datetime
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
        
    try:
        data = json.loads(request.body)
        date_str = data.get('date')
        note = data.get('note', '')
        if not date_str:
            return JsonResponse({'error': 'Date is required'}, status=400)
        
        artist = request.user.artist
        parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Check if booking exists on this date
        if Booking.objects.filter(artist=artist, date=parsed_date).exists():
            return JsonResponse({'error': 'Cannot mark busy on a booked date.'}, status=400)
        
        obj, created = ArtistAvailability.objects.update_or_create(
            artist=artist,
            date=parsed_date,
            defaults={'status': 'busy', 'note': note}
        )
        return JsonResponse({'success': True, 'id': obj.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@artist_required
def api_remove_busy_date(request):
    from django.views.decorators.http import require_POST
    import json
    from datetime import datetime
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
        
    try:
        data = json.loads(request.body)
        date_str = data.get('date')
        if not date_str:
            return JsonResponse({'error': 'Date is required'}, status=400)
        
        artist = request.user.artist
        parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        ArtistAvailability.objects.filter(artist=artist, date=parsed_date, status='busy').delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@artist_required
def artist_accounts_view(request):
    artist = request.user.artist
    bookings = Booking.objects.filter(artist=artist).order_by('-date')
    
    # Precompute GST and Total for display
    booking_details = []
    for booking in bookings:
        deal_amount = booking.deal_amount
        gst_percentage = Decimal('18')
        gst_amount = deal_amount * gst_percentage / Decimal('100')
        total_amount = deal_amount + gst_amount
        
        financials = booking_financials(booking)
        
        booking_details.append({
            'booking': booking,
            'gst_amount': gst_amount.quantize(Decimal('0.01')),
            'total_amount': total_amount.quantize(Decimal('0.01')),
            'pct_str': financials['pct_str'],
            'earning': financials['artist_commission'].quantize(Decimal('0.01')),
            'expenses': financials['artist_expenses'].quantize(Decimal('0.01')),
            'whn_expenses': financials['whn_expenses'].quantize(Decimal('0.01')),
            'owner_profit': financials['owner_profit'].quantize(Decimal('0.01')),
            'net': financials['artist_net'].quantize(Decimal('0.01'))
        })
        
    return render(request, 'bookings/artist_accounts.html', {
        'artist': artist,
        'booking_details': booking_details
    })


@artist_required
def artist_earnings_view(request):
    artist = request.user.artist
    
    # Extract query params
    selected_month = request.GET.get('month', '')
    selected_year = request.GET.get('year', '')
    
    # Base bookings queryset for this artist
    bookings = Booking.objects.filter(artist=artist).order_by('-date')
    
    # Filter bookings based on selections
    if selected_year and selected_year.isdigit():
        bookings = bookings.filter(date__year=int(selected_year))
    if selected_month and selected_month.isdigit():
        bookings = bookings.filter(date__month=int(selected_month))
        
    now = timezone.now()
    current_month = now.month
    current_year = now.year
    
    total_earnings = Decimal('0.00')
    total_expenses = Decimal('0.00')
    net_earnings = Decimal('0.00')
    monthly_earnings = Decimal('0.00')
    yearly_earnings = Decimal('0.00')
    
    events_ledger = []
    
    # For "This Month" card: if a month is filtered, show that month's earnings.
    # Otherwise, show current month's earnings (filtered by year if year is selected).
    target_month = int(selected_month) if (selected_month and selected_month.isdigit()) else current_month
    target_year_for_month = int(selected_year) if (selected_year and selected_year.isdigit()) else current_year
    
    # For "This Year" card: if a year is filtered, show that year's earnings.
    # Otherwise, show current year's earnings.
    target_year = int(selected_year) if (selected_year and selected_year.isdigit()) else current_year
    
    for booking in bookings:
        financials = booking_financials(booking)
        earning = financials['artist_commission']
        expenses = financials['artist_expenses']
        net = financials['artist_net']
        
        total_earnings += earning
        total_expenses += expenses
        net_earnings += net
        
        if booking.date.year == target_year:
            yearly_earnings += earning
        if booking.date.year == target_year_for_month and booking.date.month == target_month:
            monthly_earnings += earning
            
        events_ledger.append({
            'booking': booking,
            'pct_str': financials['pct_str'],
            'earning': earning.quantize(Decimal('0.01')),
            'expenses': expenses.quantize(Decimal('0.01')),
            'whn_expenses': financials['whn_expenses'].quantize(Decimal('0.01')),
            'owner_profit': financials['owner_profit'].quantize(Decimal('0.01')),
            'net': net.quantize(Decimal('0.01'))
        })
        
    # Get available years for the filter dropdown
    available_years = Booking.objects.filter(artist=artist).dates('date', 'year')
    years = sorted(list(set(d.year for d in available_years)), reverse=True)
    if not years:
        years = [current_year]
        
    months = [
        {'value': 1, 'name': 'January'},
        {'value': 2, 'name': 'February'},
        {'value': 3, 'name': 'March'},
        {'value': 4, 'name': 'April'},
        {'value': 5, 'name': 'May'},
        {'value': 6, 'name': 'June'},
        {'value': 7, 'name': 'July'},
        {'value': 8, 'name': 'August'},
        {'value': 9, 'name': 'September'},
        {'value': 10, 'name': 'October'},
        {'value': 11, 'name': 'November'},
        {'value': 12, 'name': 'December'},
    ]
        
    return render(request, 'bookings/artist_earnings.html', {
        'artist': artist,
        'events_ledger': events_ledger,
        'total_earnings': total_earnings.quantize(Decimal('0.01')),
        'total_expenses': total_expenses.quantize(Decimal('0.01')),
        'net_earnings': net_earnings.quantize(Decimal('0.01')),
        'monthly_earnings': monthly_earnings.quantize(Decimal('0.01')),
        'yearly_earnings': yearly_earnings.quantize(Decimal('0.01')),
        'years': years,
        'months': months,
        'selected_month': selected_month,
        'selected_year': selected_year,
    })


@login_required(login_url='login')
def admin_accounts_selection_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Access Denied: Administrative privileges required.")
        return redirect('login')
    return render(request, 'bookings/admin_accounts_selection.html')


@login_required(login_url='login')
def admin_artist_accounts_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Access Denied: Administrative privileges required.")
        return redirect('login')
        
    artists = Artist.objects.all().order_by('name')
    selected_artist_id = request.GET.get('artist_id', '')
    
    # Extract query params
    selected_month = request.GET.get('month', '')
    selected_year = request.GET.get('year', '')
    
    now = timezone.now()
    current_month = now.month
    current_year = now.year
    
    # Base bookings queryset
    bookings = Booking.objects.none()
    selected_artist = None
    
    if selected_artist_id:
        try:
            selected_artist = Artist.objects.get(id=selected_artist_id)
            bookings = Booking.objects.filter(artist=selected_artist).order_by('-date')
        except Artist.DoesNotExist:
            pass
    elif artists.exists():
        selected_artist = artists.first()
        if selected_artist:
            selected_artist_id = str(selected_artist.id)
            bookings = Booking.objects.filter(artist=selected_artist).order_by('-date')
            
    # Filter bookings based on selections
    if selected_year and selected_year.isdigit():
        bookings = bookings.filter(date__year=int(selected_year))
    if selected_month and selected_month.isdigit():
        bookings = bookings.filter(date__month=int(selected_month))
        
    total_earnings = Decimal('0.00')
    total_expenses = Decimal('0.00')
    net_earnings = Decimal('0.00')
    monthly_earnings = Decimal('0.00')
    yearly_earnings = Decimal('0.00')
    
    events_ledger = []
    
    # For "This Month" card: if a month is filtered, show that month's earnings.
    # Otherwise, show current month's earnings (filtered by year if year is selected).
    target_month = int(selected_month) if (selected_month and selected_month.isdigit()) else current_month
    target_year_for_month = int(selected_year) if (selected_year and selected_year.isdigit()) else current_year
    
    # For "This Year" card: if a year is filtered, show that year's earnings.
    # Otherwise, show current year's earnings.
    target_year = int(selected_year) if (selected_year and selected_year.isdigit()) else current_year
    
    for booking in bookings:
        financials = booking_financials(booking)
        earning = financials['artist_commission']
        expenses = financials['artist_expenses']
        net = financials['artist_net']
        
        total_earnings += earning
        total_expenses += expenses
        net_earnings += net
        
        if booking.date.year == target_year:
            yearly_earnings += earning
        if booking.date.year == target_year_for_month and booking.date.month == target_month:
            monthly_earnings += earning
            
        events_ledger.append({
            'booking': booking,
            'pct_str': financials['pct_str'],
            'earning': earning.quantize(Decimal('0.01')),
            'expenses': expenses.quantize(Decimal('0.01')),
            'whn_expenses': financials['whn_expenses'].quantize(Decimal('0.01')),
            'owner_profit': financials['owner_profit'].quantize(Decimal('0.01')),
            'net': net.quantize(Decimal('0.01'))
        })
        
    # Get available years for the filter dropdown
    years = []
    if selected_artist:
        available_years = Booking.objects.filter(artist=selected_artist).dates('date', 'year')
        years = sorted(list(set(d.year for d in available_years)), reverse=True)
        
    if not years:
        years = [current_year]
        
    months = [
        {'value': 1, 'name': 'January'},
        {'value': 2, 'name': 'February'},
        {'value': 3, 'name': 'March'},
        {'value': 4, 'name': 'April'},
        {'value': 5, 'name': 'May'},
        {'value': 6, 'name': 'June'},
        {'value': 7, 'name': 'July'},
        {'value': 8, 'name': 'August'},
        {'value': 9, 'name': 'September'},
        {'value': 10, 'name': 'October'},
        {'value': 11, 'name': 'November'},
        {'value': 12, 'name': 'December'},
    ]
    
    return render(request, 'bookings/admin_accounts.html', {
        'artists': artists,
        'selected_artist_id': selected_artist_id,
        'selected_artist': selected_artist,
        'events_ledger': events_ledger,
        'total_earnings': total_earnings.quantize(Decimal('0.01')),
        'total_expenses': total_expenses.quantize(Decimal('0.01')),
        'net_earnings': net_earnings.quantize(Decimal('0.01')),
        'monthly_earnings': monthly_earnings.quantize(Decimal('0.01')),
        'yearly_earnings': yearly_earnings.quantize(Decimal('0.01')),
        'years': years,
        'months': months,
        'selected_month': selected_month,
        'selected_year': selected_year,
    })


@login_required(login_url='login')
def admin_whn_accounts_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Access Denied: Administrative privileges required.")
        return redirect('login')

    artists = Artist.objects.all().order_by('name')
    selected_artist_id = request.GET.get('artist_id', '')
    selected_month = request.GET.get('month', '')
    selected_year = request.GET.get('year', '')
    now = timezone.now()
    current_month = now.month
    current_year = now.year

    bookings = Booking.objects.select_related('artist').prefetch_related('expenses').order_by('-date')
    selected_artist = None
    if selected_artist_id:
        try:
            selected_artist = Artist.objects.get(id=selected_artist_id)
            bookings = bookings.filter(artist=selected_artist)
        except Artist.DoesNotExist:
            selected_artist_id = ''

    if selected_year and selected_year.isdigit():
        bookings = bookings.filter(date__year=int(selected_year))
    if selected_month and selected_month.isdigit():
        bookings = bookings.filter(date__month=int(selected_month))

    total_whn_earnings = Decimal('0.00')
    total_whn_expenses = Decimal('0.00')
    net_whn_profit = Decimal('0.00')
    whn_ledger = []

    for booking in bookings:
        financials = booking_financials(booking)
        whn_share = financials['whn_share']
        whn_expenses = financials['whn_expenses']
        owner_profit = financials['owner_profit']

        total_whn_earnings += whn_share
        total_whn_expenses += whn_expenses
        net_whn_profit += owner_profit

        whn_ledger.append({
            'booking': booking,
            'pct_str': financials['pct_str'],
            'artist_share': financials['artist_net'].quantize(Decimal('0.01')),
            'artist_commission': financials['artist_commission'].quantize(Decimal('0.01')),
            'whn_share': whn_share.quantize(Decimal('0.01')),
            'whn_expenses': whn_expenses.quantize(Decimal('0.01')),
            'owner_profit': owner_profit.quantize(Decimal('0.01')),
        })

    available_bookings = Booking.objects.all()
    if selected_artist:
        available_bookings = available_bookings.filter(artist=selected_artist)
    available_years = available_bookings.dates('date', 'year')
    years = sorted(list(set(d.year for d in available_years)), reverse=True)
    if not years:
        years = [current_year]

    months = [
        {'value': 1, 'name': 'January'},
        {'value': 2, 'name': 'February'},
        {'value': 3, 'name': 'March'},
        {'value': 4, 'name': 'April'},
        {'value': 5, 'name': 'May'},
        {'value': 6, 'name': 'June'},
        {'value': 7, 'name': 'July'},
        {'value': 8, 'name': 'August'},
        {'value': 9, 'name': 'September'},
        {'value': 10, 'name': 'October'},
        {'value': 11, 'name': 'November'},
        {'value': 12, 'name': 'December'},
    ]

    return render(request, 'bookings/admin_whn_accounts.html', {
        'artists': artists,
        'selected_artist_id': selected_artist_id,
        'selected_artist': selected_artist,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'months': months,
        'years': years,
        'whn_ledger': whn_ledger,
        'total_whn_earnings': total_whn_earnings.quantize(Decimal('0.01')),
        'total_whn_expenses': total_whn_expenses.quantize(Decimal('0.01')),
        'net_whn_profit': net_whn_profit.quantize(Decimal('0.01')),
    })

# --- Employee Management Views (Admin Only) ---

@login_required(login_url='login')
def manage_employees_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Access Denied: Administrative privileges required.")
        return redirect('dashboard')
    employees = Employee.objects.all().order_by('-created_date')
    missed_follow_up_count = get_missed_follow_up_count()
    return render(request, 'bookings/manage_employees.html', {
        'employees': employees,
        'missed_follow_up_count': missed_follow_up_count,
    })

@login_required(login_url='login')
def add_employee_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')
        
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        address = request.POST.get('address')
        username = request.POST.get('username')
        password = request.POST.get('password')
        is_active = request.POST.get('is_active') == 'on'
        
        try:
            if User.objects.filter(username=username).exists():
                messages.error(request, 'Username already exists.')
            else:
                user = User.objects.create_user(username=username, email=email, password=password)
                user.is_active = is_active
                user.save()
                
                Employee.objects.create(
                    user=user,
                    name=name,
                    email=email,
                    phone=phone,
                    address=address,
                    is_active=is_active
                )
                messages.success(request, 'Employee added successfully.')
                log_activity(
                    f"Added employee {name}",
                    request=request,
                    role='admin',
                    related_record=name,
                )
                return redirect('manage_employees')
        except Exception as e:
            messages.error(request, f'Error adding employee: {str(e)}')
            
    return render(request, 'bookings/add_employee.html')

@login_required(login_url='login')
def edit_employee_view(request, employee_id):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')
        
    employee = get_object_or_404(Employee, id=employee_id)
    
    if request.method == 'POST':
        employee.name = request.POST.get('name')
        employee.user.email = request.POST.get('email')
        employee.phone = request.POST.get('phone')
        employee.address = request.POST.get('address')
        
        password = request.POST.get('password')
        if password:
            employee.user.set_password(password)
            
        employee.is_active = request.POST.get('is_active') == 'on'
        employee.user.is_active = employee.is_active
        
        try:
            employee.user.save()
            employee.save()
            messages.success(request, 'Employee updated successfully.')
            log_activity(
                f"Updated employee {employee.name}",
                request=request,
                role='admin',
                related_record=employee.name,
            )
            return redirect('manage_employees')
        except Exception as e:
            messages.error(request, f'Error updating employee: {str(e)}')
            
    return render(request, 'bookings/edit_employee.html', {'employee': employee})

@login_required(login_url='login')
def delete_employee_view(request, employee_id):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')
        
    employee = get_object_or_404(Employee, id=employee_id)
    if request.method == 'POST':
        name = employee.name
        user = employee.user
        employee.delete()
        user.delete()
        messages.success(request, f'Employee {name} deleted.')
        log_activity(
            f"Deleted employee {name}",
            request=request,
            role='admin',
            related_record=name,
        )
        return redirect('manage_employees')
    return redirect('manage_employees')


@login_required(login_url='login')
def follow_up_status_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    today = timezone.localdate()
    employees = Employee.objects.select_related('user').order_by('name')
    selected_employee_id = request.GET.get('employee') or 'all'
    selected_result = request.GET.get('result') or 'all'
    from_date_raw = request.GET.get('from_date') or ''
    to_date_raw = request.GET.get('to_date') or ''

    selected_employee = None
    if selected_employee_id not in ('', 'all'):
        selected_employee = get_object_or_404(Employee.objects.select_related('user'), id=selected_employee_id)

    from_date = None
    to_date = None
    if from_date_raw:
        try:
            from_date = datetime.strptime(from_date_raw, '%Y-%m-%d').date()
        except ValueError:
            from_date = None
    if to_date_raw:
        try:
            to_date = datetime.strptime(to_date_raw, '%Y-%m-%d').date()
        except ValueError:
            to_date = None

    leads_qs = crm_queryset(ClientLead.objects.filter(follow_up_date__isnull=False))
    if selected_employee:
        leads_qs = leads_qs.filter(employee=selected_employee)
    if from_date and to_date:
        leads_qs = leads_qs.filter(follow_up_date__range=(from_date, to_date))
    elif from_date:
        leads_qs = leads_qs.filter(follow_up_date__gte=from_date)
    elif to_date:
        leads_qs = leads_qs.filter(follow_up_date__lte=to_date)

    follow_up_rows = []
    summary = {
        'total': 0,
        'due_today': 0,
        'missed': 0,
        'completed': 0,
        'upcoming': 0,
    }

    result_labels = {
        'missed': 'Missed',
        'due_today': 'Due Today',
        'completed': 'Completed',
        'upcoming': 'Upcoming',
    }

    for lead in leads_qs.order_by('follow_up_date', 'employee__name', 'promoter_name'):
        result = get_follow_up_result(lead, today)
        if not result:
            continue
        summary['total'] += 1
        if result in summary:
            summary[result] += 1
        if selected_result != 'all' and result != selected_result:
            continue
        follow_up_rows.append({
            'lead': lead,
            'result': result,
            'result_label': result_labels.get(result, result.title()),
            'last_updated': getattr(lead, 'crm_updated_at_value', None) or lead.crm_updated_at,
        })

    return render(request, 'bookings/follow_up_status.html', {
        'employees': employees,
        'selected_employee_id': selected_employee_id,
        'selected_employee': selected_employee,
        'selected_result': selected_result,
        'from_date': from_date_raw,
        'to_date': to_date_raw,
        'summary': summary,
        'follow_up_rows': follow_up_rows,
        'today': today,
    })


@login_required(login_url='login')
def admin_crm_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    employees = Employee.objects.select_related('user').order_by('name')
    artists = Artist.objects.all().order_by('name')
    selected_employee_id = request.GET.get('employee') or request.POST.get('employee') or 'all'
    selected_period = request.GET.get('period') or request.POST.get('period') or ''
    from_date_raw = request.GET.get('from_date') or request.POST.get('from_date') or ''
    to_date_raw = request.GET.get('to_date') or request.POST.get('to_date') or ''

    selected_employee = None
    if selected_employee_id not in ('', 'all'):
        selected_employee = get_object_or_404(Employee.objects.select_related('user'), id=selected_employee_id)

    from_date = None
    to_date = None
    if from_date_raw:
        try:
            from_date = datetime.strptime(from_date_raw, '%Y-%m-%d').date()
        except ValueError:
            from_date = None
    if to_date_raw:
        try:
            to_date = datetime.strptime(to_date_raw, '%Y-%m-%d').date()
        except ValueError:
            to_date = None

    leads_qs = crm_queryset(ClientLead.objects.all())
    if selected_employee:
        leads_qs = leads_qs.filter(employee=selected_employee)
    leads_qs = crm_apply_date_filter(leads_qs, selected_period, from_date, to_date)
    leads = leads_qs.order_by('-crm_created_at_value', '-id')
    summary = crm_build_summary(leads_qs)

    query_params = {
        'employee': selected_employee_id,
        'period': selected_period,
        'from_date': from_date_raw,
        'to_date': to_date_raw,
    }
    query_params = {key: value for key, value in query_params.items() if value}

    if request.method == 'POST':
        lead_id = request.POST.get('lead_id')
        if lead_id:
            lead = get_object_or_404(ClientLead, id=lead_id)
            lead.promoter_name = request.POST.get('promoter_name')
            lead.contact_number = request.POST.get('contact_number')
            lead.type = (request.POST.get('type') or 'lead').strip().lower()
            if lead.type not in ('lead', 'sale'):
                lead.type = 'lead'
            lead.city = request.POST.get('city')
            lead.venue = request.POST.get('venue')
            follow_up_date_raw = request.POST.get('follow_up_date') or None
            lead.follow_up_date = None
            if follow_up_date_raw:
                try:
                    lead.follow_up_date = datetime.strptime(follow_up_date_raw, '%Y-%m-%d').date()
                except ValueError:
                    lead.follow_up_date = None
            lead.conversion_event_date = parse_date_field(request.POST.get('conversion_event_date'))
            lead.conversion_deal_amount = parse_decimal_field(request.POST.get('conversion_deal_amount'))
            conversion_artist_id = request.POST.get('conversion_artist') or None
            lead.conversion_artist = Artist.objects.filter(id=conversion_artist_id).first() if conversion_artist_id else None
            lead.notes = request.POST.get('notes')
            submitted_status = request.POST.get('status', 'Follow-up Needed')
            lead.status = submitted_status

            if lead.status == 'Follow-up Needed' and not lead.follow_up_date:
                messages.error(request, 'Follow-up date is required when status is Follow-up Needed.')
                return redirect(reverse('admin_crm'))

            if submitted_status == CONVERTED_INPUT_STATUS:
                if not lead.conversion_event_date or lead.conversion_deal_amount is None or lead.conversion_deal_amount < 0 or not lead.conversion_artist:
                    messages.error(request, 'Event date, deal amount, and artist are required when status is Converted.')
                    return redirect(reverse('admin_crm'))
                lead.follow_up_date = None
                lead.status = CONVERTED_BOOKED_STATUS if lead.conversion_booking_id else CONVERTED_PENDING_STATUS
            else:
                lead.conversion_event_date = None
                lead.conversion_deal_amount = None
                lead.conversion_artist = None

            lead.save()
            messages.success(request, 'Lead/Sale updated successfully.')
            log_activity(
                f"Admin updated Lead/Sale: {lead.promoter_name}",
                request=request,
                role='admin',
                related_record=lead.promoter_name,
            )
        else:
            messages.error(request, 'Please use the edit action to update a record.')

        redirect_url = reverse('admin_crm')
        if query_params:
            redirect_url = f"{redirect_url}?{urlencode(query_params)}"
        return redirect(redirect_url)

    return render(request, 'bookings/admin_crm.html', {
        'leads': leads,
        'summary': summary,
        'employees': employees,
        'artists': artists,
        'selected_employee_id': selected_employee_id,
        'selected_employee': selected_employee,
        'selected_period': selected_period,
        'from_date': from_date_raw,
        'to_date': to_date_raw,
    })


@login_required(login_url='login')
def admin_crm_conversion_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard')

    employees = Employee.objects.select_related('user').order_by('name')
    selected_employee_id = request.GET.get('employee') or 'all'
    selected_period = request.GET.get('period') or ''
    from_date_raw = request.GET.get('from_date') or ''
    to_date_raw = request.GET.get('to_date') or ''

    selected_employee = None
    if selected_employee_id not in ('', 'all'):
        selected_employee = get_object_or_404(Employee.objects.select_related('user'), id=selected_employee_id)

    from_date = parse_date_field(from_date_raw)
    to_date = parse_date_field(to_date_raw)

    conversion_qs = crm_queryset(ClientLead.objects.filter(status=CONVERTED_BOOKED_STATUS))
    if selected_employee:
        conversion_qs = conversion_qs.filter(employee=selected_employee)
    conversion_qs = crm_apply_conversion_date_filter(conversion_qs, selected_period, from_date, to_date)

    summary = conversion_qs.aggregate(
        lead_count=Count('id', filter=Q(type='lead')),
        sale_count=Count('id', filter=Q(type='sale')),
        lead_value=Sum('conversion_deal_amount', filter=Q(type='lead')),
        sale_value=Sum('conversion_deal_amount', filter=Q(type='sale')),
    )

    aggregate_rows = {
        row['employee__id']: row
        for row in conversion_qs.values('employee__id', 'employee__name').annotate(
            converted_leads=Count('id', filter=Q(type='lead')),
            converted_sales=Count('id', filter=Q(type='sale')),
            lead_deal_amount=Sum('conversion_deal_amount', filter=Q(type='lead')),
            sale_deal_amount=Sum('conversion_deal_amount', filter=Q(type='sale')),
        )
    }

    employee_rows_source = [selected_employee] if selected_employee else list(employees)
    conversion_rows = []
    for employee in employee_rows_source:
        row = aggregate_rows.get(employee.id, {})
        conversion_rows.append({
            'employee_name': employee.name,
            'converted_leads': row.get('converted_leads') or 0,
            'converted_sales': row.get('converted_sales') or 0,
            'lead_deal_amount': row.get('lead_deal_amount') or 0,
            'sale_deal_amount': row.get('sale_deal_amount') or 0,
        })

    return render(request, 'bookings/admin_crm_conversion.html', {
        'employees': employees,
        'selected_employee_id': selected_employee_id,
        'selected_employee': selected_employee,
        'selected_period': selected_period,
        'from_date': from_date_raw,
        'to_date': to_date_raw,
        'summary': summary,
        'conversion_rows': conversion_rows,
    })

# --- Employee Portal Views ---

@employee_required
def employee_dashboard_view(request):
    employee = request.user.employee
    return render(request, 'bookings/employee_dashboard.html', {
        'employee': employee,
    })


@login_required(login_url='login')
@employee_required
@require_POST
def employee_notifications_seen_view(request):
    employee = request.user.employee
    employee.notifications_last_seen_at = timezone.now()
    employee.save(update_fields=['notifications_last_seen_at'])
    return JsonResponse({
        'success': True,
        'notification_count': 0,
    })

@employee_required
def employee_calendar_view(request):
    artists = Artist.objects.all()
    selected_artist_id = request.GET.get('artist')
    selected_date = request.GET.get('date') or ''
    selected_artist = None
    if selected_artist_id:
        try:
            selected_artist = Artist.objects.get(id=selected_artist_id)
        except Artist.DoesNotExist:
            pass
    elif artists.exists():
        selected_artist = artists.first()
        selected_artist_id = str(selected_artist.id)

    return render(request, 'bookings/employee_calendar.html', {
        'artists': artists,
        'selected_artist_id': selected_artist_id,
        'selected_artist': selected_artist,
        'selected_date': selected_date,
    })

@employee_required
def employee_bookings_view(request):
    bookings = Booking.objects.all().order_by('-date')
    return render(request, 'bookings/employee_bookings.html', {'bookings': bookings})

@employee_required
def employee_crm_view(request):
    employee = request.user.employee
    leads = crm_queryset(ClientLead.objects.filter(employee=employee)).order_by('-crm_created_at_value', '-id')
    artists = Artist.objects.all().order_by('name')
    
    if request.method == 'POST':
        lead_id = request.POST.get('lead_id')
        promoter_name = request.POST.get('promoter_name')
        contact_number = request.POST.get('contact_number')
        lead_type = (request.POST.get('type') or 'lead').strip().lower()
        if lead_type not in ('lead', 'sale'):
            lead_type = 'lead'
        city = request.POST.get('city')
        venue = request.POST.get('venue')
        follow_up_date = parse_date_field(request.POST.get('follow_up_date'))
        conversion_event_date = parse_date_field(request.POST.get('conversion_event_date'))
        conversion_deal_amount = parse_decimal_field(request.POST.get('conversion_deal_amount'))
        conversion_artist_id = request.POST.get('conversion_artist') or None
        conversion_artist = None
        if conversion_artist_id:
            conversion_artist = Artist.objects.filter(id=conversion_artist_id).first()
        notes = request.POST.get('notes')
        submitted_status = request.POST.get('status', 'Follow-up Needed')
        is_converted_submission = submitted_status == CONVERTED_INPUT_STATUS
        status = submitted_status

        if status == 'Follow-up Needed' and not follow_up_date:
            messages.error(request, 'Follow-up date is required when status is Follow-up Needed.')
            return redirect('employee_crm')

        if is_converted_submission:
            if not conversion_event_date or conversion_deal_amount is None or conversion_deal_amount < 0 or not conversion_artist:
                messages.error(request, 'Event date, deal amount, and artist are required when status is Converted.')
                return redirect('employee_crm')
            follow_up_date = None
            status = CONVERTED_PENDING_STATUS
        else:
            conversion_event_date = None
            conversion_deal_amount = None
            conversion_artist = None
        
        try:
            should_redirect_to_booking = False
            if lead_id:
                lead = get_object_or_404(ClientLead, id=lead_id, employee=employee)
                old_lead = ClientLead.objects.get(id=lead.id, employee=employee)
                if is_converted_submission and lead.conversion_booking_id:
                    status = CONVERTED_BOOKED_STATUS
                lead.promoter_name = promoter_name
                lead.contact_number = contact_number
                lead.type = lead_type
                lead.city = city
                lead.venue = venue
                lead.follow_up_date = follow_up_date
                lead.conversion_event_date = conversion_event_date
                lead.conversion_deal_amount = conversion_deal_amount
                lead.conversion_artist = conversion_artist
                lead.notes = notes
                lead.status = status
                lead.save()
                should_redirect_to_booking = is_converted_submission and not lead.conversion_booking_id
                messages.success(
                    request,
                    'Lead/Sale saved. Complete the booking details to finish the conversion.'
                    if is_converted_submission else
                    'Lead/Sale updated successfully.'
                )
                for action in lead_activity_changes(old_lead, lead, employee.name):
                    log_activity(
                        action,
                        request=request,
                        role='employee',
                        employee_name=employee.name,
                        related_record=lead.promoter_name,
                    )
            else:
                lead = ClientLead.objects.create(
                    employee=employee,
                    promoter_name=promoter_name,
                    contact_number=contact_number,
                    type=lead_type,
                    city=city,
                    venue=venue,
                    follow_up_date=follow_up_date,
                    conversion_event_date=conversion_event_date,
                    conversion_deal_amount=conversion_deal_amount,
                    conversion_artist=conversion_artist,
                    notes=notes,
                    status=status
                )
                should_redirect_to_booking = is_converted_submission
                messages.success(
                    request,
                    'Lead/Sale saved. Complete the booking details to finish the conversion.'
                    if is_converted_submission else
                    'Lead/Sale added successfully.'
                )
                log_activity(
                    f"{employee.name} added new {'Sale' if lead_type == 'sale' else 'Lead'}: {lead.promoter_name}",
                    request=request,
                    role='employee',
                    employee_name=employee.name,
                    related_record=lead.promoter_name,
                )
            if should_redirect_to_booking:
                redirect_url = reverse('add_booking')
                query_params = {
                    'crm_lead': lead.id,
                    'source': 'employee_crm',
                }
                return redirect(f"{redirect_url}?{urlencode(query_params)}")
            return redirect('employee_crm')
        except Exception as e:
            messages.error(request, f'Error saving lead: {str(e)}')

    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    base_qs = ClientLead.objects.filter(employee=employee)
    summary = base_qs.aggregate(
        today_leads=Count('id', filter=Q(created_at__date=today, type='lead')),
        today_sales=Count('id', filter=Q(created_at__date=today, type='sale')),
        week_leads=Count('id', filter=Q(created_at__date__gte=week_start, type='lead')),
        week_sales=Count('id', filter=Q(created_at__date__gte=week_start, type='sale')),
        month_leads=Count('id', filter=Q(created_at__date__gte=month_start, type='lead')),
        month_sales=Count('id', filter=Q(created_at__date__gte=month_start, type='sale')),
        converted_leads=Count('id', filter=Q(status=CONVERTED_BOOKED_STATUS, type='lead')),
        converted_sales=Count('id', filter=Q(status=CONVERTED_BOOKED_STATUS, type='sale')),
        converted_lead_amount=Sum('conversion_deal_amount', filter=Q(status=CONVERTED_BOOKED_STATUS, type='lead')),
        converted_sale_amount=Sum('conversion_deal_amount', filter=Q(status=CONVERTED_BOOKED_STATUS, type='sale')),
    )

    leads_payload = [
        {
            'id': lead.id,
            'type': lead.type,
            'promoter_name': lead.promoter_name,
            'contact_number': lead.contact_number or '',
            'city': lead.city or '',
            'venue': lead.venue or '',
            'follow_up_date': lead.follow_up_date.isoformat() if lead.follow_up_date else '',
            'conversion_event_date': lead.conversion_event_date.isoformat() if lead.conversion_event_date else '',
            'conversion_deal_amount': str(lead.conversion_deal_amount) if lead.conversion_deal_amount is not None else '',
            'conversion_artist': lead.conversion_artist_id or '',
            'notes': lead.notes or '',
            'status': lead.status,
            'status_label': lead.status,
            'created_at': lead.crm_created_at.isoformat() if lead.crm_created_at else '',
            'updated_at': lead.crm_updated_at.isoformat() if lead.crm_updated_at else '',
            'created_date': lead.created_date.isoformat() if lead.created_date else '',
            'last_updated': lead.last_updated.isoformat() if lead.last_updated else '',
            'was_edited': lead.crm_was_edited,
        }
        for lead in leads
    ]
    conversion_payload = [
        {
            'type': lead.type,
            'date': lead.crm_updated_at.strftime('%Y-%m-%d') if lead.crm_updated_at else '',
            'amount': float(lead.conversion_deal_amount or 0),
        }
        for lead in leads
        if lead.status == CONVERTED_BOOKED_STATUS
    ]

    context = {
        'leads': leads,
        'summary': summary,
        'leads_payload': leads_payload,
        'conversion_payload': conversion_payload,
        'artists': artists,
    }
    return render(request, 'bookings/employee_crm.html', context)
