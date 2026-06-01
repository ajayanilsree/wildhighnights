from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import date
from bookings.models import Artist, Booking, BookingExpense

class AdminAccountsTest(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Create users
        self.admin_user = User.objects.create_superuser(username='admin', password='adminpassword')
        self.artist_user = User.objects.create_user(username='artist1', password='artistpassword')
        self.non_artist_user = User.objects.create_user(username='regular', password='regularpassword')
        
        # Create Artist profile for artist_user
        self.artist = Artist.objects.create(
            user=self.artist_user,
            name="Test Performer",
            genre="Electronic",
            instagram="test_perf"
        )
        
        # Create another artist profile
        self.other_artist = Artist.objects.create(
            name="Another Performer",
            genre="Techno",
            instagram="another_perf"
        )

        # Create a booking with expenses for our artist
        self.booking = Booking.objects.create(
            artist=self.artist,
            event_type='Club',
            venue='Ibiza Club',
            location='Spain',
            date=date(2026, 5, 20),
            booking_type='Sale', # 85% split
            deal_type='Landed Deal',
            deal_amount=Decimal('1000.00'),
            status='Confirmed'
        )
        
        # Create expense
        self.expense1 = BookingExpense.objects.create(
            booking=self.booking,
            name="Catering",
            amount=Decimal('100.00')
        )
        self.expense2 = BookingExpense.objects.create(
            booking=self.booking,
            name="Travel Gas",
            amount=Decimal('50.00')
        )
        
    def test_anonymous_user_redirected(self):
        """Anonymous user trying to access admin accounts should be redirected to login"""
        response = self.client.get(reverse('admin_accounts'))
        self.assertRedirects(response, f"/login/?next={reverse('admin_accounts')}")
        
    def test_artist_user_redirected(self):
        """Artist user trying to access admin accounts should be redirected (not authorized)"""
        self.client.login(username='artist1', password='artistpassword')
        response = self.client.get(reverse('admin_accounts'))
        # Should redirect to login or dashboard settings since they lack admin privileges.
        # views.py redirects to 'login' and adds a message
        self.assertRedirects(response, reverse('login'), target_status_code=302)
        
    def test_regular_user_redirected(self):
        """Regular non-staff user trying to access admin accounts should be redirected"""
        self.client.login(username='regular', password='regularpassword')
        response = self.client.get(reverse('admin_accounts'))
        self.assertRedirects(response, reverse('login'), target_status_code=302)
        
    def test_admin_user_success(self):
        """Superuser/staff user should access the page successfully"""
        self.client.login(username='admin', password='adminpassword')
        response = self.client.get(reverse('admin_accounts'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'bookings/admin_accounts.html')
        
    def test_accounts_view_calculations(self):
        """Test calculations logic matches the expectations for the selected artist"""
        self.client.login(username='admin', password='adminpassword')
        
        # Select our artist via artist_id parameter
        response = self.client.get(reverse('admin_accounts'), {'artist_id': self.artist.id})
        self.assertEqual(response.status_code, 200)
        
        # Split is Sale (85%)
        # deal_amount = 1000.00
        # total_earnings = 1000 * 0.85 = 850.00
        # total_expenses = 100.00 + 50.00 = 150.00
        # net_earnings = 850.00 - 150.00 = 700.00
        
        self.assertEqual(response.context['total_earnings'], Decimal('850.00'))
        self.assertEqual(response.context['total_expenses'], Decimal('150.00'))
        self.assertEqual(response.context['net_earnings'], Decimal('700.00'))
        
        # Ledger checks
        events_ledger = response.context['events_ledger']
        self.assertEqual(len(events_ledger), 1)
        self.assertEqual(events_ledger[0]['earning'], Decimal('850.00'))
        self.assertEqual(events_ledger[0]['expenses'], Decimal('150.00'))
        self.assertEqual(events_ledger[0]['net'], Decimal('700.00'))
        self.assertEqual(events_ledger[0]['pct_str'], '85%')
