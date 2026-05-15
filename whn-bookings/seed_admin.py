import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'whn_bookings_dj.settings')
django.setup()

from django.contrib.auth.models import User

def seed_admin():
    username = 'admin'
    password = 'whnadmin123'
    
    if not User.objects.filter(username=username).exists():
        print(f"Creating superuser: {username}...")
        User.objects.create_superuser(
            username=username,
            email='admin@wildhighnights.com',
            password=password
        )
        print("Superuser created successfully!")
    else:
        print(f"Superuser '{username}' already exists.")

if __name__ == '__main__':
    seed_admin()
