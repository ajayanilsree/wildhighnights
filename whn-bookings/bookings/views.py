from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth.models import User
from .models import Artist, Booking, SiteSettings, ActivityLog, Event, GalleryImage

@ensure_csrf_cookie
def index(request):
    settings = SiteSettings.objects.first()
    if not settings:
        settings = SiteSettings.objects.create()
    artists = Artist.objects.all()
    events = Event.objects.filter(status='Published').order_by('event_date', 'event_time')[:4]
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
            'type': b.type,
            'status': b.status,
            'location': b.location,
            'publicNotes': b.notes, 
        }
        for b in bookings
    ]
    return JsonResponse(data, safe=False)

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password')
            
    return render(request, 'bookings/login.html')

@login_required(login_url='login')
def dashboard_view(request):
    context = {
        'total_artists': Artist.objects.count(),
        'total_bookings': Booking.objects.count(),
        'confirmed_events': Booking.objects.filter(status='confirmed').count(),
        'pending_requests': Booking.objects.filter(status='tentative').count(),
        'recent_bookings': Booking.objects.all().order_by('-date')[:5],
        'activity_logs': ActivityLog.objects.all().order_by('-created_at')[:10],
    }
    return render(request, 'bookings/dashboard.html', context)

@login_required(login_url='login')
def add_booking_view(request):
    artists = Artist.objects.all()
    if request.method == 'POST':
        artist_id = request.POST.get('artist')
        venue = request.POST.get('venue')
        date = request.POST.get('date')
        time = request.POST.get('time')
        location = request.POST.get('location')
        event_type = request.POST.get('type')
        status = request.POST.get('status')
        notes = request.POST.get('notes')

        artist = get_object_or_404(Artist, id=artist_id)
        Booking.objects.create(
            artist=artist,
            venue=venue,
            date=date,
            time=time if time else None,
            location=location,
            type=event_type,
            status=status,
            notes=notes
        )
        ActivityLog.objects.create(action=f"Booking created for {artist.name} at {venue}")
        messages.success(request, 'Booking added successfully!')
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
        messages.success(request, 'Artist created successfully!')
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
        messages.success(request, f"Artist '{artist.name}' updated successfully.")
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
        messages.success(request, f"Event '{event_name}' created successfully!")
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
        messages.success(request, f"Event '{event.event_name}' updated successfully.")
        return redirect('manage_events')

    return render(request, 'bookings/edit_event.html', {'event': event})

@login_required(login_url='login')
def delete_event_view(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    name = event.event_name
    event.delete()
    ActivityLog.objects.create(action=f"Event removed: {name}")
    messages.success(request, f"Event '{name}' removed successfully.")
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
        messages.success(request, 'Gallery image added successfully!')
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
        messages.success(request, 'Gallery image updated successfully.')
        return redirect('manage_gallery')

    return render(request, 'bookings/edit_gallery_image.html', {'image': img})

@login_required(login_url='login')
def delete_gallery_image_view(request, image_id):
    img = get_object_or_404(GalleryImage, id=image_id)
    title = img.title if img.title else 'Untitled'
    img.delete()
    ActivityLog.objects.create(action=f"Gallery image removed: {title}")
    messages.success(request, 'Gallery image deleted.')
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
    messages.success(request, f"Artist '{name}' and associated user deleted.")
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
        messages.success(request, 'Settings updated successfully!')
        return redirect('dashboard')

    return render(request, 'bookings/settings.html', {'settings': settings})

def logout_view(request):
    logout(request)
    return redirect('login')
