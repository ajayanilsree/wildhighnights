"""Opt-in real-browser workflow against Django's disposable test database."""
import os
from decimal import Decimal
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse

from .financials import booking_financials
from .models import Artist, Booking


@skipUnless(os.getenv('WHN_BROWSER_TESTS') == '1', 'Set WHN_BROWSER_TESTS=1 with Playwright/Chromium installed.')
class LedgerBrowserTests(StaticLiveServerTestCase):
    def test_create_edit_reload_and_mobile_ledger(self):
        from playwright.sync_api import sync_playwright, expect

        admin = User.objects.create_user('browser_admin', is_staff=True)
        self.client.force_login(admin)
        # Playwright's synchronous driver maintains an event loop in this test thread;
        # ORM assertions still execute serially, never as concurrent async operations.
        with patch.dict(os.environ, DJANGO_ALLOW_ASYNC_UNSAFE='true'), sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, timeout=15000)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                page.context.add_cookies([dict(name='sessionid', value=self.client.cookies['sessionid'].value,
                                              url=self.live_server_url)])

                def visit(route, args=None):
                    page.goto(self.live_server_url + reverse(route, args=args), wait_until='load')
                    expect(page.locator('#loader')).to_be_hidden()

                visit('add_artist')
                page.locator('[name="name"]').fill('Browser Test Artist')
                page.locator('[name="sales_commission_percentage"]').fill('80')
                page.locator('[name="lead_commission_percentage"]').fill('90')
                page.locator('button[type="submit"]').click()
                page.wait_for_url('**/dashboard/')
                artist = Artist.objects.get(name='Browser Test Artist')
                self.assertEqual(artist.sales_commission_percentage, Decimal('80'))

                visit('add_booking')
                page.locator('[name="artist"]').select_option(str(artist.pk))
                for name, value in [('venue', 'Browser accounting example'), ('location', 'Goa'), ('date', '2026-10-20'), ('deal_amount', '160000')]:
                    page.locator(f'[name="{name}"]').fill(value)
                page.locator('[name="booking_type"][value="Lead"]').check(force=True)
                for name, amount, bearer in [('WHN Travel', '20000', 'WHN'), ('Artist Hotel', '10000', 'Artist')]:
                    page.locator('#add-expense-btn').click()
                    row = page.locator('.expense-row').last
                    row.locator('[name="expense_name[]"]').fill(name)
                    row.locator('[name="expense_amount[]"]').fill(amount)
                    row.locator('[name="expense_borne_by[]"]').select_option(bearer)
                page.locator('button[type="submit"]').click()
                page.wait_for_url('**/dashboard/bookings/')
                booking = Booking.objects.get(venue='Browser accounting example')
                visit('admin_whn_accounts')
                row = page.locator('tbody tr').filter(has_text='Browser accounting example')
                expect(row).to_contain_text('127000.00')
                expect(row).to_contain_text('33000.00')
                self.assertEqual(booking_financials(booking)['whn_net_payout'], Decimal('33000'))

                visit('edit_booking', [booking.pk])
                page.locator('[name="expense_amount[]"]').first.fill('21000')
                page.locator('button[type="submit"]').click()
                page.wait_for_url('**/dashboard/bookings/')
                visit('admin_whn_accounts')
                page.reload(wait_until='load')
                expect(page.locator('tbody tr').filter(has_text='Browser accounting example')).to_contain_text('33900.00')
                booking.refresh_from_db()
                result = booking_financials(booking)
                self.assertEqual(result['whn_net_payout'] + result['artist_net_payout'], Decimal('160000'))

                # Goa regression fixture through the existing edit form.
                visit('edit_booking', [booking.pk])
                page.locator('[name="venue"]').fill('Hammerzz Makarena')
                page.locator('[name="deal_amount"]').fill('80000')
                page.locator('[name="expense_amount[]"]').first.fill('15909')
                page.locator('[name="expense_amount[]"]').last.fill('0')
                page.locator('button[type="submit"]').click()
                page.wait_for_url('**/dashboard/bookings/')
                visit('admin_whn_accounts')
                row = page.locator('tbody tr').filter(has_text='Hammerzz Makarena')
                expect(row).to_contain_text('6409.10')
                expect(row).to_contain_text('57681.90')
                expect(row).to_contain_text('22318.10')
                self.assertNotIn('-7909', row.inner_text())

                visit('edit_booking', [booking.pk])
                page.locator('[name="expense_amount[]"]').first.fill('90000')
                page.locator('button[type="submit"]').click()
                expect(page.locator('[role="alert"]')).to_contain_text('Combined WHN and Artist Expenses cannot exceed')
                expect(page.locator('[name="expense_amount[]"]').first).to_have_value('90000')
                expect(page.locator('[name="venue"]')).to_have_value('Hammerzz Makarena')
                page.locator('[name="expense_amount[]"]').first.fill('15909')
                page.locator('button[type="submit"]').click()
                page.wait_for_url('**/dashboard/bookings/')
                visit('admin_whn_accounts')

                screenshots = os.getenv('WHN_QA_SCREENSHOTS')
                if screenshots:
                    Path(screenshots).mkdir(parents=True, exist_ok=True)
                    for section in page.locator('[data-aos]').all():
                        section.scroll_into_view_if_needed()
                        expect(section).to_have_css('opacity', '1')
                    page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
                    page.wait_for_function('window.scrollY === 0')
                    page.screenshot(path=str(Path(screenshots) / 'booking-ledger-desktop.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                scroller = page.locator('.overflow-x-auto').filter(has=page.locator('table'))
                self.assertTrue(scroller.evaluate('(el) => el.scrollWidth > el.clientWidth'))
                scroller.evaluate('(el) => el.scrollLeft = el.scrollWidth')
                expect(page.locator('th').filter(has_text='WHN Net Payout')).to_be_visible()
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 391)
                if screenshots:
                    page.screenshot(path=str(Path(screenshots) / 'booking-ledger-mobile.png'), full_page=True)
            finally:
                browser.close()
