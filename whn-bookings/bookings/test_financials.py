from datetime import date
from decimal import Decimal
from importlib import import_module
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import reverse

from .financials import calculate_booking_financials, booking_financials, configured_artist_percentage
from .models import Artist, Booking, BookingExpense, Employee, ClientLead
from .views import attach_conversion_commission, build_artist_calendar_payload


class CalculationTests(SimpleTestCase):
    def check_case(self, deal, whn, artist, rate, whn_share, artist_share, whn_payout, artist_payout):
        result = calculate_booking_financials(deal, whn, artist, rate)
        for key, expected in [('whn_share', whn_share), ('artist_share', artist_share),
                              ('whn_net_payout', whn_payout), ('artist_net_payout', artist_payout)]:
            self.assertEqual(result[key], Decimal(expected), key)
        self.assertEqual(result['commission_base'], Decimal(deal) - Decimal(whn) - Decimal(artist))
        self.assertEqual(result['artist_net_payout'] + result['whn_net_payout'], Decimal(deal))
        return result

    def test_client_160000(self):
        self.check_case('160000', '20000', '10000', '10', '13000', '117000', '33000', '127000')

    def test_goa_hammerzz(self):
        self.check_case('80000', '15909', '0', '10', '6409.10', '57681.90', '22318.10', '57681.90')

    def test_esani_sale(self):
        self.check_case('100000', '5000', '5000', '20', '18000', '72000', '23000', '77000')

    def test_esani_lead(self):
        self.check_case('100000', '5000', '5000', '15', '13500', '76500', '18500', '81500')

    def test_no_expenses(self):
        self.check_case('100000', '0', '0', '10', '10000', '90000', '10000', '90000')

    def test_only_whn_expenses(self):
        self.check_case('100000', '10000', '0', '10', '9000', '81000', '19000', '81000')

    def test_only_artist_expenses(self):
        self.check_case('100000', '0', '10000', '10', '9000', '81000', '9000', '91000')

    def test_expenses_equal_deal(self):
        self.check_case('100000', '60000', '40000', '10', '0', '0', '60000', '40000')

    def test_zero_deal(self):
        self.check_case('0', '0', '0', '10', '0', '0', '0', '0')

    def test_boundaries(self):
        self.check_case('100', '10', '10', '0', '0', '80', '10', '90')
        self.check_case('100', '10', '10', '100', '80', '0', '90', '10')

    def test_decimal_rate_half_up_rounding(self):
        self.check_case('0.10', '0', '0', '15', '0.02', '0.08', '0.02', '0.08')
        self.check_case('100.01', '0.01', '0.01', '12.35', '12.35', '87.64', '12.36', '87.65')

    def test_reconciliation_across_cent_values_and_rates(self):
        for cents in range(101):
            for rate in ['0', '0.01', '10', '12.35', '50', '99.99', '100']:
                result = calculate_booking_financials(Decimal(cents) / 100, 0, 0, rate)
                self.assertEqual(result['artist_net_payout'] + result['whn_net_payout'], result['deal_amount'])

    def test_expenses_exceed_deal(self):
        with self.assertRaisesMessage(ValidationError, 'Combined WHN and Artist Expenses cannot exceed'):
            calculate_booking_financials('100000', '80000', '30000', '10')

    def test_negative_nonfinite_out_of_range_and_excess_precision(self):
        for index, values in [(0, ['-1', 'NaN', 'Infinity', 'abc', '1.001', '10000000000']),
                              (1, ['-1', 'NaN', '-Infinity', '1.001']),
                              (2, ['-1', 'Infinity', '1.001']),
                              (3, ['-0.01', '100.01', 'NaN', 'Infinity', '1.001'])]:
            for value in values:
                with self.subTest(index=index, value=value), self.assertRaises(ValidationError):
                    args = ['100', '0', '0', '10']
                    args[index] = value
                    calculate_booking_financials(*args)


class BookingWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('ledger_admin', is_staff=True)
        self.employee_user = User.objects.create_user('ledger_employee')
        self.employee = Employee.objects.create(user=self.employee_user, name='Employee', email='test@example.com')
        self.artist_user = User.objects.create_user('ledger_artist')
        self.artist = Artist.objects.create(user=self.artist_user, name='DJ Paroma', sales_commission_percentage=85, lead_commission_percentage=90)
        self.esani = Artist.objects.get(name='Esani')
        self.client.force_login(self.admin)

    def data(self, **overrides):
        data = dict(artist=str(self.artist.pk), event_type='Club', venue='Hammerzz Makarena', location='Goa',
                    date='2026-10-20', time='', duration='90 minutes', booking_type='Lead',
                    deal_type='Landed Deal', deal_amount='160000', ground_transport='No', sound_check='No',
                    status='Confirmed', notes='Preserve notes', **{'expense_name[]': ['Travel', 'Artist hotel'],
                    'expense_amount[]': ['20000', '10000'], 'expense_borne_by[]': ['WHN', 'Artist']})
        data.update(overrides)
        return data

    def create(self, **overrides):
        response = self.client.post(reverse('add_booking'), self.data(**overrides))
        self.assertEqual(response.status_code, 302)
        return Booking.objects.latest('pk')

    def test_create_ledger_edit_reload_complete_workflow(self):
        booking = self.create()
        self.assertEqual(booking.expenses.count(), 2)
        self.assertEqual(booking.applied_artist_percentage, Decimal('90'))
        financials = booking_financials(booking)
        self.assertEqual(financials['artist_net_payout'], Decimal('127000'))
        self.assertEqual(financials['whn_net_payout'], Decimal('33000'))
        url = reverse('admin_whn_accounts')
        response = self.client.get(url)
        for text in ['Artist Expenses', 'Artist Net Payout', 'WHN Net Payout', 'Hammerzz Makarena', 'DJ Paroma', 'Lead', '20 Oct 2026', 'overflow-x-auto']:
            self.assertContains(response, text)
        self.assertNotContains(response, 'WHN Net Profit')
        self.assertEqual(response.context['total_whn_net_payout'], Decimal('33000'))
        for amounts, deal in [(['21000', '10000'], '160000'), (['21000', '15000'], '160000'), (['21000', '15000'], '180000')]:
            response = self.client.post(reverse('edit_booking', args=[booking.pk]), self.data(
                deal_amount=deal, **{'expense_amount[]': amounts}))
            self.assertEqual(response.status_code, 302)
            booking.refresh_from_db()
            result = booking_financials(booking)
            self.assertEqual(result['whn_expenses'], Decimal(amounts[0]))
            self.assertEqual(result['artist_expenses'], Decimal(amounts[1]))
            self.assertEqual(result['artist_net_payout'] + result['whn_net_payout'], Decimal(deal))
            response = self.client.get(url)
            self.assertEqual(response.context['total_whn_net_payout'], result['whn_net_payout'])
            self.assertEqual(booking.notes, 'Preserve notes')
            self.assertEqual(booking.status, 'Confirmed')

    def test_goa_fixture_matches_client_without_changing_input(self):
        booking = self.create(deal_amount='80000', **{'expense_name[]': ['Travel'], 'expense_amount[]': ['15909'], 'expense_borne_by[]': ['WHN']})
        result = booking_financials(booking)
        self.assertEqual(result['whn_share'], Decimal('6409.10'))
        self.assertEqual(result['artist_share'], Decimal('57681.90'))
        self.assertEqual(result['whn_net_payout'], Decimal('22318.10'))
        self.assertEqual(booking.deal_amount, Decimal('80000'))
        self.assertEqual(booking.expenses.get().amount, Decimal('15909'))

    def test_artist_and_type_select_correct_independent_rates(self):
        booking = self.create(deal_amount='100000', **{'expense_amount[]': ['5000', '5000']})
        for artist, kind, whn_share, payout in [(self.esani, 'Sale', '18000', '23000'),
                                             (self.esani, 'Lead', '13500', '18500'),
                                             (self.artist, 'Lead', '9000', '14000')]:
            response = self.client.post(reverse('edit_booking', args=[booking.pk]), self.data(
                artist=str(artist.pk), booking_type=kind, deal_amount='100000', **{'expense_amount[]': ['5000', '5000']}))
            self.assertEqual(response.status_code, 302)
            booking.refresh_from_db()
            result = booking_financials(booking)
            self.assertEqual(result['whn_share'], Decimal(whn_share))
            self.assertEqual(result['whn_net_payout'], Decimal(payout))

    def test_artist_settings_edit_does_not_reprice_saved_booking(self):
        booking = self.create()
        self.artist.lead_commission_percentage = Decimal('70')
        self.artist.save()
        booking.refresh_from_db()
        self.assertEqual(booking_financials(booking)['whn_share'], Decimal('13000'))
        self.client.post(reverse('edit_booking', args=[booking.pk]), self.data())
        booking.refresh_from_db()
        self.assertEqual(booking.applied_artist_percentage, Decimal('90'))

    def test_legacy_estimate_is_explicit_and_never_backfilled(self):
        booking = self.create()
        Booking.objects.filter(pk=booking.pk).update(applied_artist_percentage=None)
        booking.refresh_from_db()
        self.assertEqual(booking_financials(booking)['rate_source'], 'current_artist_estimate')
        self.assertContains(self.client.get(reverse('admin_whn_accounts')), 'Estimate: historical rate unrecorded')
        self.client.post(reverse('edit_booking', args=[booking.pk]), self.data())
        booking.refresh_from_db()
        self.assertIsNone(booking.applied_artist_percentage)

    def test_invalid_creation_and_edit_preserve_all_records(self):
        booking = self.create()
        original_expenses = list(booking.expenses.values())
        invalid = [dict(deal_amount='-1'), dict(deal_amount='NaN'), dict(deal_amount='100'),
                   {'expense_amount[]': ['-1', '10000']}, {'expense_amount[]': ['Infinity', '10000']},
                   {'expense_amount[]': ['1.001', '10000']}, {'expense_amount[]': ['100']},
                   {'expense_borne_by[]': ['Invalid', 'Artist']}, dict(booking_type='invalid'),
                   dict(booking_type='Custom', custom_artist_percentage='101'),
                   dict(booking_type='Custom', custom_artist_percentage=''),
                   {'expense_name[]': ['', 'Artist hotel']}]
        for overrides in invalid:
            for url in [reverse('add_booking'), reverse('edit_booking', args=[booking.pk])]:
                with self.subTest(overrides=overrides, url=url):
                    response = self.client.post(url, self.data(**overrides))
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(Booking.objects.count(), 1)
                    booking.refresh_from_db()
                    self.assertEqual(booking.deal_amount, Decimal('160000'))
                    self.assertEqual(list(booking.expenses.values()), original_expenses)

    def test_atomic_save_rolls_back_on_expense_write_failure(self):
        booking = self.create()
        with patch('bookings.views.BookingExpense.objects.create', side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('edit_booking', args=[booking.pk]), self.data(deal_amount='180000'))
        booking.refresh_from_db()
        self.assertEqual(booking.deal_amount, Decimal('160000'))
        self.assertEqual(booking.expenses.count(), 2)

    def test_authorized_employee_can_create_and_edit(self):
        self.client.force_login(self.employee_user)
        booking = self.create()
        response = self.client.post(reverse('edit_booking', args=[booking.pk]), self.data())
        self.assertEqual(response.status_code, 302)

    def test_unauthorized_roles_cannot_write_or_change_commissions(self):
        booking = self.create()
        regular = User.objects.create_user('ordinary')
        inactive = User.objects.create_user('inactive')
        Employee.objects.create(user=inactive, name='Inactive', email='inactive@example.com', is_active=False)
        restricted = User.objects.create_user('whnsocial')
        Employee.objects.create(user=restricted, name='Calendar only', email='calendar@example.com')
        for user in [regular, inactive, restricted, self.artist_user]:
            self.client.force_login(user)
            for url in [reverse('add_booking'), reverse('edit_booking', args=[booking.pk]),
                        reverse('add_artist'), reverse('edit_artist', args=[self.artist.pk])]:
                self.assertEqual(self.client.post(url, self.data()).status_code, 403)
        self.assertEqual(Booking.objects.count(), 1)

    def test_anonymous_cannot_write(self):
        self.client.logout()
        self.assertEqual(self.client.post(reverse('add_booking'), self.data()).status_code, 302)
        self.assertFalse(Booking.objects.exists())

    def test_calendar_api_values_match_ledger_and_are_read_only(self):
        booking = self.create()
        result = booking_financials(booking)
        response = self.client.get(reverse('api_artist_calendar_events'), {'artist_id': self.artist.pk})
        payload = response.json()['bookings'][0]
        for key in ['whn_share', 'artist_share', 'artist_net_payout', 'whn_net_payout', 'commission_base']:
            self.assertEqual(Decimal(payload[key]), result[key])
        self.client.post(reverse('api_bookings'), self.data(deal_amount='1'))
        booking.refresh_from_db()
        self.assertEqual(booking.deal_amount, Decimal('160000'))
        self.client.force_login(self.artist_user)
        response = self.client.get(reverse('api_artist_calendar_events'), {'artist_id': self.esani.pk})
        self.assertEqual({row['artist'] for row in response.json()['bookings']}, {'DJ Paroma'})

    def test_artist_accounts_and_earnings_agree_with_backend(self):
        self.create()
        self.client.force_login(self.artist_user)
        response = self.client.get(reverse('artist_accounts'))
        self.assertEqual(response.context['booking_details'][0]['net'], Decimal('127000'))
        response = self.client.get(reverse('artist_earnings'))
        self.assertEqual(response.context['net_earnings'], Decimal('127000'))

    def test_filter_sort_and_aggregate_reconciliation(self):
        first = self.create()
        second = self.create(artist=str(self.esani.pk), booking_type='Sale', date='2026-09-01')
        response = self.client.get(reverse('admin_whn_accounts'))
        self.assertEqual([row['booking'].pk for row in response.context['whn_ledger']], [first.pk, second.pk])
        self.assertEqual(response.context['total_artist_net_payout'] + response.context['total_whn_net_payout'], response.context['total_deal_amount'])
        for filters in [dict(artist_id=self.artist.pk), dict(month='10', year='2026')]:
            response = self.client.get(reverse('admin_whn_accounts'), filters)
            self.assertEqual([row['booking'].pk for row in response.context['whn_ledger']], [first.pk])

    def test_custom_and_missing_legacy_settings(self):
        booking = self.create(booking_type='Custom', custom_artist_percentage='87.65')
        self.assertEqual(booking_financials(booking)['commission_percentage'], Decimal('12.35'))
        for kind, field, expected in [('Sale', 'sales_commission_percentage', '85'), ('Lead', 'lead_commission_percentage', '90')]:
            setattr(self.artist, field, None)
            proposed = Booking(artist=self.artist, booking_type=kind)
            self.assertEqual(configured_artist_percentage(proposed), Decimal(expected))

    def test_model_and_admin_validation(self):
        booking = self.create()
        for model in [BookingExpense(booking=booking, name='Invalid', amount=-1),
                      BookingExpense(booking=booking, name='Excess', amount=160000)]:
            with self.assertRaises(ValidationError):
                model.full_clean()
        self.artist.sales_commission_percentage = Decimal('101')
        with self.assertRaises(ValidationError):
            self.artist.full_clean()

    def test_linked_crm_quote_uses_actual_booking_financials(self):
        booking = self.create()
        lead = ClientLead(conversion_artist=self.artist, conversion_booking=booking, conversion_deal_amount=booking.deal_amount)
        attach_conversion_commission(lead)
        self.assertEqual(lead.conversion_commission_amount, Decimal('117000'))


class MigrationSafetyTests(TransactionTestCase):
    def test_existing_bookings_and_expenses_survive_without_invented_historical_rate(self):
        old = [('bookings', '0030_artist_commission_rates_and_esani')]
        latest = [('bookings', '0032_correct_esani_artist_shares')]
        executor = MigrationExecutor(connection)
        executor.migrate(old)
        try:
            apps = executor.loader.project_state(old).apps
            OldArtist = apps.get_model('bookings', 'Artist')
            OldBooking = apps.get_model('bookings', 'Booking')
            OldExpense = apps.get_model('bookings', 'BookingExpense')
            OldArtist.objects.get_or_create(name='Esani', defaults={'slug': 'esani', 'sales_commission_percentage': 20, 'lead_commission_percentage': 15})
            OldArtist.objects.filter(name='Esani').update(sales_commission_percentage=20, lead_commission_percentage=15)
            artist = OldArtist.objects.create(name='Historical Artist', slug='historical', sales_commission_percentage=82, lead_commission_percentage=91)
            booking = OldBooking.objects.create(artist=artist, venue='Historical booking', location='Goa', date=date(2026, 1, 1), deal_amount=80000, booking_type='Lead', status='Confirmed')
            expense = OldExpense.objects.create(booking=booking, name='WHN travel', amount=15909, borne_by='WHN')
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            booking = Booking.objects.get(pk=booking.pk)
            self.assertEqual(Booking.objects.count(), 1)
            self.assertEqual(booking.deal_amount, Decimal('80000'))
            self.assertEqual(booking.status, 'Confirmed')
            self.assertIsNone(booking.applied_artist_percentage)
            self.assertEqual(BookingExpense.objects.get(pk=expense.pk).amount, Decimal('15909'))
            self.assertEqual(booking_financials(booking)['artist_expenses'], Decimal('0'))
            artist.refresh_from_db()
            self.assertEqual(artist.lead_commission_percentage, Decimal('91'))
            self.assertEqual(artist.sales_commission_percentage, Decimal('82'))
            migration = import_module('bookings.migrations.0032_correct_esani_artist_shares')
            with connection.schema_editor() as editor:
                migration.correct_esani(executor.loader.project_state(latest).apps, editor)
            self.assertEqual(Artist.objects.get(name='Esani').sales_commission_percentage, Decimal('80'))
            self.assertEqual(Artist.objects.get(name='Esani').lead_commission_percentage, Decimal('85'))
            Artist.objects.filter(name='Esani').update(sales_commission_percentage=77)
            with connection.schema_editor() as editor:
                migration.correct_esani(executor.loader.project_state(latest).apps, editor)
            self.assertEqual(Artist.objects.get(name='Esani').sales_commission_percentage, Decimal('77'))
        finally:
            MigrationExecutor(connection).migrate(latest)
