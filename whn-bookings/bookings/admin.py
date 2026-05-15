from django.contrib import admin
from .models import Artist, Booking

@admin.register(Artist)
class ArtistAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'genre')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('artist', 'venue', 'date', 'status', 'type')
    list_filter = ('artist', 'status', 'type', 'date')
    search_fields = ('venue', 'location', 'notes')
