from django.contrib import admin
from .models import Artist, Booking, ArtistAvailability

@admin.register(ArtistAvailability)
class ArtistAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('artist', 'date', 'status', 'note')
    list_filter = ('artist', 'date', 'status')
    search_fields = ('artist__name', 'note')

@admin.register(Artist)
class ArtistAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'genre')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('artist', 'venue', 'date', 'status', 'event_type')
    list_filter = ('artist', 'status', 'event_type', 'date')
    search_fields = ('venue', 'location', 'notes', 'accommodation_details', 'transport_details')
