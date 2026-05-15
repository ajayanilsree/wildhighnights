import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'whn_bookings_dj.settings')
django.setup()

from bookings.models import Artist

def seed():
    artists = [
        { 'name': 'DJ Paroma',       'avatar': '🎧', 'color': '#7C3AED' },
        { 'name': 'Eve',             'avatar': '🌸', 'color': '#FF2D55' },
        { 'name': 'Shanaya',         'avatar': '✨', 'color': '#FF9F0A' },
        { 'name': 'Shameless Mani',  'avatar': '🔥', 'color': '#0A84FF' },
    ]

    for a_data in artists:
        artist, created = Artist.objects.get_or_create(
            name=a_data['name'],
            defaults={'avatar': a_data['avatar'], 'color': a_data['color']}
        )
        if created:
            print(f"Created artist: {artist.name}")
        else:
            print(f"Artist already exists: {artist.name}")

if __name__ == '__main__':
    seed()
