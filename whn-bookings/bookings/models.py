from django.db import models
from django.utils.text import slugify
from django.contrib.auth.models import User

class Artist(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    genre = models.CharField(max_length=100, blank=True)
    instagram = models.CharField(max_length=255, blank=True)
    artist_image = models.ImageField(upload_to="artists/", blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Artist.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class ArtistAvailability(models.Model):
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(max_length=20, choices=[('busy', 'Busy')])
    note = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('artist', 'date')

    def __str__(self):
        return f"{self.artist.name} - {self.date} ({self.status})"

class Booking(models.Model):
    EVENT_TYPE_CHOICES = [
        ('Private', 'Private'),
        ('Campus', 'Campus'),
        ('Club', 'Club'),
    ]
    BOOKING_TYPE_CHOICES = [
        ('Sale', 'Sale'),
        ('Lead', 'Lead'),
    ]
    DEAL_TYPE_CHOICES = [
        ('++ Deal', '++ Deal'),
        ('All Inclusive Deal', 'All Inclusive Deal'),
        ('Landed Deal', 'Landed Deal'),
    ]
    STATUS_CHOICES = [
        ('Tentative', 'Tentative'),
        ('Confirmed', 'Confirmed'),
        ('Cancelled', 'Cancelled'),
    ]
    YES_NO_CHOICES = [
        ('Yes', 'Yes'),
        ('No', 'No'),
    ]

    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='bookings')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES, default='Club')
    venue = models.CharField(max_length=200)
    location = models.CharField(max_length=255)
    date = models.DateField()
    time = models.TimeField(null=True, blank=True)
    duration = models.CharField(max_length=100, blank=True, null=True)
    
    booking_type = models.CharField(max_length=10, choices=BOOKING_TYPE_CHOICES, default='Sale')
    deal_type = models.CharField(max_length=30, choices=DEAL_TYPE_CHOICES, default='Landed Deal')
    deal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    travel_pdf = models.FileField(upload_to="booking_docs/travel/", blank=True, null=True)
    accommodation_pdf = models.FileField(upload_to="booking_docs/accommodation/", blank=True, null=True)
    accommodation_details = models.TextField(blank=True, null=True)
    
    ground_transport = models.CharField(max_length=5, choices=YES_NO_CHOICES, default='No')
    transport_details = models.TextField(blank=True, null=True)
    
    sound_check = models.CharField(max_length=5, choices=YES_NO_CHOICES, default='No')
    artwork_attachment = models.FileField(upload_to="booking_docs/artwork/", blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Tentative')
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.artist.name} - {self.venue} ({self.date})"

class BookingExpense(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="expenses")
    name = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.name}: {self.amount} for {self.booking}"

class SiteSettings(models.Model):
    title = models.CharField(max_length=200, default='Wild High Nights')
    instagram_link = models.URLField(default='https://www.instagram.com/whn_wild_high_nights?igsh=MXJoODl5NTlnc2J5ZQ%3D%3D')
    contact_email = models.EmailField(default='info@wildhighnights.com')
    footer_description = models.TextField(default='Discover unforgettable nightlife experiences, artists, DJs, and exclusive events across the globe.')
    hero_text = models.TextField(default='Discover unforgettable nightlife experiences, artists, DJs, and exclusive events across the globe.')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return "Global Site Settings"

class Event(models.Model):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Published', 'Published'),
    ]
    event_name = models.CharField(max_length=200)
    event_date = models.DateField()
    event_time = models.TimeField()
    venue_name = models.CharField(max_length=200)
    location = models.CharField(max_length=255)
    event_image = models.ImageField(upload_to='events/')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Published')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.event_name

class GalleryImage(models.Model):
    title = models.CharField(max_length=150, blank=True)
    image = models.ImageField(upload_to="gallery/")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title if self.title else f"Image {self.id}"

class ActivityLog(models.Model):
    action = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} at {self.created_at}"
