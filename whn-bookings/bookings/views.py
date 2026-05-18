from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Artist, Booking, SiteSettings, ActivityLog, Event, GalleryImage, BookingExpense

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
        elif hasattr(request.user, 'artist'):
            return redirect('artist_dashboard')
        return redirect('artist_dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            if user.is_superuser or user.is_staff:
                return redirect('dashboard')
            elif hasattr(user, 'artist'):
                return redirect('artist_dashboard')
            return redirect('artist_dashboard')
        else:
            messages.error(request, 'Invalid username or password')
            
    return render(request, 'bookings/login.html')

@login_required(login_url='login')
def dashboard_view(request):
    context = {
        'total_artists': Artist.objects.count(),
        'total_bookings': Booking.objects.count(),
        'confirmed_events': Booking.objects.filter(status='Confirmed').count(),
        'pending_requests': Booking.objects.filter(status='Tentative').count(),
        'recent_bookings': Booking.objects.all().order_by('-date')[:5],
        'activity_logs': ActivityLog.objects.all().order_by('-created_at')[:10],
    }
    return render(request, 'bookings/dashboard.html', context)

@login_required(login_url='login')
def add_booking_view(request):
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
        deal_type = request.POST.get('deal_type')
        deal_amount = request.POST.get('deal_amount') or 0.00
        
        ground_transport = request.POST.get('ground_transport')
        sound_check = request.POST.get('sound_check')
        status = request.POST.get('status')
        notes = request.POST.get('notes')

        # Files
        travel_pdf = request.FILES.get('travel_pdf')
        accommodation_pdf = request.FILES.get('accommodation_pdf')
        ground_transport_attachment = request.FILES.get('ground_transport_attachment')
        artwork_attachment = request.FILES.get('artwork_attachment')

        artist = get_object_or_404(Artist, id=artist_id)
        
        # Create Booking
        booking = Booking.objects.create(
            artist=artist,
            event_type=event_type,
            venue=venue,
            location=location,
            date=date,
            time=time if time else None,
            duration=duration,
            booking_type=booking_type,
            deal_type=deal_type,
            deal_amount=deal_amount,
            travel_pdf=travel_pdf,
            accommodation_pdf=accommodation_pdf,
            ground_transport=ground_transport,
            ground_transport_attachment=ground_transport_attachment if ground_transport == 'Yes' else None,
            sound_check=sound_check,
            artwork_attachment=artwork_attachment,
            status=status,
            notes=notes
        )

        # Dynamic Expenses
        expense_names = request.POST.getlist('expense_name[]')
        expense_amounts = request.POST.getlist('expense_amount[]')
        for name, amt in zip(expense_names, expense_amounts):
            if name.strip() and amt:
                BookingExpense.objects.create(
                    booking=booking,
                    name=name.strip(),
                    amount=amt
                )

        ActivityLog.objects.create(action=f"Booking created: {artist.name} - {venue}")
        return redirect('dashboard')

    return render(request, 'bookings/add_booking.html', {'artists': artists})

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
        ActivityLog.objects.create(action=f"Artist created: {name}")
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
        
        ActivityLog.objects.create(action=f"Artist updated: {artist.name}")
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
        ActivityLog.objects.create(action=f"Event created: {event_name}")
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
        ActivityLog.objects.create(action=f"Event updated: {event.event_name}")
        return redirect('manage_events')

    return render(request, 'bookings/edit_event.html', {'event': event})

@login_required(login_url='login')
def delete_event_view(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    name = event.event_name
    event.delete()
    ActivityLog.objects.create(action=f"Event removed: {name}")
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
        ActivityLog.objects.create(action=f"Gallery image added: {title if title else 'Untitled'}")
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
        ActivityLog.objects.create(action=f"Gallery image updated: {img.title if img.title else 'Untitled'}")
        return redirect('manage_gallery')

    return render(request, 'bookings/edit_gallery_image.html', {'image': img})

@login_required(login_url='login')
def delete_gallery_image_view(request, image_id):
    img = get_object_or_404(GalleryImage, id=image_id)
    title = img.title if img.title else 'Untitled'
    img.delete()
    ActivityLog.objects.create(action=f"Gallery image removed: {title}")
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
        
    ActivityLog.objects.create(action=f"Artist removed: {name}")
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
        ActivityLog.objects.create(action="Settings updated")
        return redirect('dashboard')

    return render(request, 'bookings/settings.html', {'settings': settings})

def logout_view(request):
    logout(request)
    messages.success(request, 'Logged out successfully')
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
        deal_type = request.POST.get('deal_type')
        deal_amount = request.POST.get('deal_amount') or 0.00
        
        ground_transport = request.POST.get('ground_transport')
        sound_check = request.POST.get('sound_check')
        status = request.POST.get('status')
        notes = request.POST.get('notes')

        artist = get_object_or_404(Artist, id=artist_id)
        
        booking.artist = artist
        booking.event_type = event_type
        booking.venue = venue
        booking.location = location
        booking.date = date
        booking.time = time if time else None
        booking.duration = duration
        booking.booking_type = booking_type
        booking.deal_type = deal_type
        booking.deal_amount = deal_amount
        booking.ground_transport = ground_transport
        booking.sound_check = sound_check
        booking.status = status
        booking.notes = notes

        # Update files if supplied
        if 'travel_pdf' in request.FILES:
            booking.travel_pdf = request.FILES.get('travel_pdf')
        if 'accommodation_pdf' in request.FILES:
            booking.accommodation_pdf = request.FILES.get('accommodation_pdf')
        if 'ground_transport_attachment' in request.FILES:
            booking.ground_transport_attachment = request.FILES.get('ground_transport_attachment')
        if 'artwork_attachment' in request.FILES:
            booking.artwork_attachment = request.FILES.get('artwork_attachment')

        # Clean transport attachment if transport is changed to 'No'
        if ground_transport == 'No':
            booking.ground_transport_attachment = None

        booking.save()

        # Update expenses by clear and rebuild
        booking.expenses.all().delete()
        expense_names = request.POST.getlist('expense_name[]')
        expense_amounts = request.POST.getlist('expense_amount[]')
        for name, amt in zip(expense_names, expense_amounts):
            if name.strip() and amt:
                BookingExpense.objects.create(
                    booking=booking,
                    name=name.strip(),
                    amount=amt
                )

        ActivityLog.objects.create(action=f"Booking updated: {artist.name} - {venue}")
        return redirect('manage_bookings')

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
    
    ActivityLog.objects.create(action=f"Booking removed: {artist_name} - {venue}")
    return redirect('manage_bookings')


# =========================================================================
# Artist Portal Views & Security Decorator
# =========================================================================

def artist_required(view_func):
    @login_required(login_url='login')
    def _wrapped_view(request, *args, **kwargs):
        if not hasattr(request.user, 'artist'):
            messages.error(request, "Access Denied: You do not have an active Artist profile.")
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
def artist_calendar_view(request):
    artist = request.user.artist
    bookings = Booking.objects.filter(artist=artist).order_by('date', 'time')
    return render(request, 'bookings/artist_calendar.html', {
        'artist': artist,
        'bookings': bookings
    })


@artist_required
def artist_accounts_view(request):
    artist = request.user.artist
    bookings = Booking.objects.filter(artist=artist).order_by('-date')
    
    # Precompute GST and Total for display
    booking_details = []
    for booking in bookings:
        deal_amount = booking.deal_amount
        # GST is dynamically 18% in UI
        gst_percentage = 18
        gst_amount = deal_amount * gst_percentage / 100
        total_amount = deal_amount + gst_amount
        
        booking_details.append({
            'booking': booking,
            'gst_amount': gst_amount,
            'total_amount': total_amount
        })
        
    return render(request, 'bookings/artist_accounts.html', {
        'artist': artist,
        'booking_details': booking_details
    })


@artist_required
def artist_earnings_view(request):
    artist = request.user.artist
    bookings = Booking.objects.filter(artist=artist).order_by('-date')
    
    now = timezone.now()
    current_month = now.month
    current_year = now.year
    
    from decimal import Decimal
    
    total_earnings = Decimal('0.00')
    total_expenses = Decimal('0.00')
    net_earnings = Decimal('0.00')
    monthly_earnings = Decimal('0.00')
    yearly_earnings = Decimal('0.00')
    
    events_ledger = []
    
    for booking in bookings:
        # Commission splits: Sale = 85%, Lead = 90%
        if booking.booking_type == 'Sale':
            pct = Decimal('0.85')
            pct_str = "85%"
        else:
            pct = Decimal('0.90')
            pct_str = "90%"
            
        earning = booking.deal_amount * pct
        expenses = sum((exp.amount for exp in booking.expenses.all()), Decimal('0.00'))
        net = earning - expenses
        
        total_earnings += earning
        total_expenses += expenses
        net_earnings += net
        
        # Check time matching for current month/year
        if booking.date.year == current_year:
            yearly_earnings += earning
            if booking.date.month == current_month:
                monthly_earnings += earning
                
        events_ledger.append({
            'booking': booking,
            'pct_str': pct_str,
            'earning': earning,
            'expenses': expenses,
            'net': net
        })
        
    return render(request, 'bookings/artist_earnings.html', {
        'artist': artist,
        'events_ledger': events_ledger,
        'total_earnings': total_earnings,
        'total_expenses': total_expenses,
        'net_earnings': net_earnings,
        'monthly_earnings': monthly_earnings,
        'yearly_earnings': yearly_earnings
    })
