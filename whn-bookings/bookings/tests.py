from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import date, timedelta
from bookings.models import Artist, Booking, BookingExpense, ClientLead, Employee

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
            amount=Decimal('100.00'),
            borne_by='Artist'
        )
        self.expense2 = BookingExpense.objects.create(
            booking=self.booking,
            name="Travel Gas",
            amount=Decimal('50.00'),
            borne_by='WHN'
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
        """Superuser/staff user should access the account selection page successfully"""
        self.client.login(username='admin', password='adminpassword')
        response = self.client.get(reverse('admin_accounts'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'bookings/admin_accounts_selection.html')

    def test_admin_artist_accounts_success(self):
        """Superuser/staff user should access the artist accounts page successfully"""
        self.client.login(username='admin', password='adminpassword')
        response = self.client.get(reverse('admin_artist_accounts'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'bookings/admin_accounts.html')
        
    def test_accounts_view_calculations(self):
        """Test calculations logic matches the expectations for the selected artist"""
        self.client.login(username='admin', password='adminpassword')
        
        # Select our artist via artist_id parameter
        response = self.client.get(reverse('admin_artist_accounts'), {'artist_id': self.artist.id})
        self.assertEqual(response.status_code, 200)
        
        # Split is Sale (85%)
        # deal_amount = 1000.00
        # total_earnings = 1000 * 0.85 = 850.00
        # artist expenses = 100.00
        # WHN expenses = 50.00
        # net_earnings = 850.00 - 100.00 = 750.00
        # owner_profit = 150.00 WHN share - 50.00 WHN expense = 100.00
        
        self.assertEqual(response.context['total_earnings'], Decimal('850.00'))
        self.assertEqual(response.context['total_expenses'], Decimal('100.00'))
        self.assertEqual(response.context['net_earnings'], Decimal('750.00'))
        
        # Ledger checks
        events_ledger = response.context['events_ledger']
        self.assertEqual(len(events_ledger), 1)
        self.assertEqual(events_ledger[0]['earning'], Decimal('850.00'))
        self.assertEqual(events_ledger[0]['expenses'], Decimal('100.00'))
        self.assertEqual(events_ledger[0]['whn_expenses'], Decimal('50.00'))
        self.assertEqual(events_ledger[0]['owner_profit'], Decimal('100.00'))
        self.assertEqual(events_ledger[0]['net'], Decimal('750.00'))
        self.assertEqual(events_ledger[0]['pct_str'], '85%')

    def test_whn_accounts_calculations(self):
        """WHN accounts deduct only WHN-borne expenses from WHN share"""
        self.client.login(username='admin', password='adminpassword')
        response = self.client.get(reverse('admin_whn_accounts'), {'artist_id': self.artist.id})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'bookings/admin_whn_accounts.html')
        self.assertEqual(response.context['total_whn_earnings'], Decimal('150.00'))
        self.assertEqual(response.context['total_whn_expenses'], Decimal('50.00'))
        self.assertEqual(response.context['net_whn_profit'], Decimal('100.00'))
        self.assertEqual(response.context['whn_ledger'][0]['artist_share'], Decimal('850.00'))
        self.assertEqual(response.context['whn_ledger'][0]['whn_share'], Decimal('150.00'))
        self.assertEqual(response.context['whn_ledger'][0]['owner_profit'], Decimal('100.00'))


class CrmSyncAndCalendarTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(username='admin', password='adminpassword')
        self.employee_user = User.objects.create_user(username='employee', password='employeepassword')
        self.employee = Employee.objects.create(
            user=self.employee_user,
            name='Employee One',
            email='employee@example.com',
            is_active=True,
        )
        self.artist = Artist.objects.create(name='Calendar Artist')

    def test_admin_created_leads_are_visible_in_employee_crm(self):
        lead = ClientLead.objects.create(
            created_by_admin=True,
            created_by=self.admin_user,
            type='lead',
            promoter_name='Admin Lead',
            city='Mumbai',
            venue='Club Admin',
            contact_number='1234567890',
            event_date=date(2026, 7, 10),
            status='Follow-up Needed',
            follow_up_date=date(2026, 7, 1),
        )

        self.client.login(username='employee', password='employeepassword')
        response = self.client.get(reverse('employee_crm'))

        self.assertEqual(response.status_code, 200)
        self.assertIn(lead, list(response.context['leads']))

    def test_crm_calendar_api_scopes_admin_and_employee_records(self):
        other_employee_user = User.objects.create_user(username='other_employee', password='otherpassword')
        other_employee = Employee.objects.create(
            user=other_employee_user,
            name='Other Employee',
            email='other@example.com',
            is_active=True,
        )
        admin_lead = ClientLead.objects.create(
            created_by_admin=True,
            created_by=self.admin_user,
            type='lead',
            promoter_name='Admin Lead',
            city='Pune',
            venue='Admin Venue',
            contact_number='1111111111',
            event_date=date(2026, 7, 11),
            conversion_artist=self.artist,
            status='Follow-up Needed',
            follow_up_date=date(2026, 7, 2),
        )
        past_lead = ClientLead.objects.create(
            created_by_admin=True,
            created_by=self.admin_user,
            type='lead',
            promoter_name='Past Event Lead',
            city='Pune',
            venue='Past Venue',
            contact_number='5555555555',
            event_date=date.today() - timedelta(days=120),
            status='Converted - Pending Booking',
        )
        employee_sale = ClientLead.objects.create(
            employee=self.employee,
            created_by=self.employee_user,
            type='sale',
            promoter_name='Employee Sale',
            city='Mumbai',
            venue='Employee Venue',
            contact_number='3333333333',
            event_date=date(2026, 7, 13),
            status='Follow-up Needed',
            follow_up_date=date(2026, 7, 3),
        )
        other_employee_lead = ClientLead.objects.create(
            employee=other_employee,
            created_by=other_employee_user,
            type='lead',
            promoter_name='Other Employee Lead',
            city='Delhi',
            venue='Other Venue',
            contact_number='4444444444',
            event_date=date(2026, 7, 14),
            status='Follow-up Needed',
            follow_up_date=date(2026, 7, 4),
        )
        booking = Booking.objects.create(
            artist=self.artist,
            venue='Booked Venue',
            location='Goa',
            date=date(2026, 7, 12),
            booking_type='Lead',
            deal_amount=Decimal('1000.00'),
            status='Confirmed',
        )
        booked_lead = ClientLead.objects.create(
            created_by_admin=True,
            created_by=self.admin_user,
            type='sale',
            promoter_name='Booked Lead',
            city='Goa',
            venue='Booked Venue',
            contact_number='2222222222',
            event_date=date(2026, 7, 12),
            conversion_artist=self.artist,
            conversion_booking=booking,
            status='Converted - Booking Created',
        )

        self.client.login(username='admin', password='adminpassword')
        admin_payload = self.client.get(reverse('api_crm_calendar_events')).json()
        admin_titles = [item['extendedProps']['promoterName'] for item in admin_payload]
        artist_payload = self.client.get(reverse('api_artist_calendar_events'), {'artist_id': self.artist.id}).json()
        self.client.logout()

        self.client.login(username='employee', password='employeepassword')
        employee_payload = self.client.get(reverse('api_crm_calendar_events')).json()
        employee_titles = [item['extendedProps']['promoterName'] for item in employee_payload]

        self.assertIn(admin_lead.promoter_name, admin_titles)
        self.assertIn(past_lead.promoter_name, admin_titles)
        self.assertIn(employee_sale.promoter_name, admin_titles)
        self.assertIn(other_employee_lead.promoter_name, admin_titles)
        self.assertNotIn(booked_lead.promoter_name, admin_titles)
        self.assertEqual(employee_titles, [employee_sale.promoter_name])
        self.assertNotIn('crm_entries', artist_payload)
        self.assertNotIn('displayTime', admin_payload[0]['extendedProps'])

    def test_admin_can_delete_crm_entry_and_employee_cannot(self):
        admin_lead = ClientLead.objects.create(
            created_by_admin=True,
            created_by=self.admin_user,
            type='lead',
            promoter_name='Delete Me',
            city='Mumbai',
            venue='Delete Venue',
            contact_number='9999999999',
            event_date=date(2026, 8, 1),
            status='Follow-up Needed',
        )

        self.client.login(username='employee', password='employeepassword')
        employee_response = self.client.post(reverse('admin_crm_delete', args=[admin_lead.id]))
        self.assertEqual(employee_response.status_code, 302)
        self.assertTrue(ClientLead.objects.filter(id=admin_lead.id).exists())
        self.client.logout()

        self.client.login(username='admin', password='adminpassword')
        admin_response = self.client.post(reverse('admin_crm_delete', args=[admin_lead.id]))
        self.assertEqual(admin_response.status_code, 302)
        self.assertFalse(ClientLead.objects.filter(id=admin_lead.id).exists())
