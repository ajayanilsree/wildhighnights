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

class Booking(models.Model):
    TYPE_CHOICES = [
        ('performance', 'Performance'),
        ('shoot', 'Shoot'),
        ('vacation', 'Vacation'),
        ('travel', 'Travel'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('confirmed', 'Confirmed'),
        ('tentative', 'Tentative'),
        ('cancelled', 'Cancelled'),
    ]

    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='bookings')
    venue = models.CharField(max_length=200)
    date = models.DateField()
    time = models.TimeField(null=True, blank=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='performance')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmed')
    location = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.artist.name} - {self.venue} ({self.date})"

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
