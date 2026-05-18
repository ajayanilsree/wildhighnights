from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('events/', views.all_events_view, name='all_events'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('dashboard/bookings/', views.manage_bookings_view, name='manage_bookings'),
    path('dashboard/bookings/add/', views.add_booking_view, name='add_booking'),
    path('dashboard/bookings/<int:booking_id>/edit/', views.edit_booking_view, name='edit_booking'),
    path('dashboard/bookings/<int:booking_id>/delete/', views.delete_booking_view, name='delete_booking'),
    path('dashboard/events/', views.manage_events_view, name='manage_events'),
    path('dashboard/events/add/', views.add_event_view, name='add_event'),
    path('dashboard/events/<int:event_id>/edit/', views.edit_event_view, name='edit_event'),
    path('dashboard/events/<int:event_id>/delete/', views.delete_event_view, name='delete_event'),
    path('dashboard/gallery/', views.manage_gallery_view, name='manage_gallery'),
    path('dashboard/gallery/add/', views.add_gallery_image_view, name='add_gallery_image'),
    path('dashboard/gallery/<int:image_id>/edit/', views.edit_gallery_image_view, name='edit_gallery_image'),
    path('dashboard/gallery/<int:image_id>/delete/', views.delete_gallery_image_view, name='delete_gallery_image'),
    path('dashboard/artists/', views.manage_artists_view, name='manage_artists'),
    path('dashboard/artists/add/', views.add_artist_view, name='add_artist'),
    path('dashboard/artists/<int:artist_id>/edit/', views.edit_artist_view, name='edit_artist'),
    path('dashboard/artists/<int:artist_id>/delete/', views.delete_artist_view, name='delete_artist'),
    path('dashboard/settings/', views.dashboard_settings_view, name='dashboard_settings'),
    
    # Artist Portal Routes
    path('artist/dashboard/', views.artist_dashboard_view, name='artist_dashboard'),
    path('artist/calendar/', views.artist_calendar_view, name='artist_calendar'),
    path('artist/accounts/', views.artist_accounts_view, name='artist_accounts'),
    path('artist/earnings/', views.artist_earnings_view, name='artist_earnings'),
    
    path('api/artists/', views.api_artists, name='api_artists'),
    path('api/bookings/', views.api_bookings, name='api_bookings'),
]
