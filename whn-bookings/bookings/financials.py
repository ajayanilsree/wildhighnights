"""Booking accounting. Artist configuration contains ARTIST percentages, not WHN rates."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError

CENT = Decimal('0.01')
HUNDRED = Decimal('100')


def decimal_value(value, label, maximum=None):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            raise ValueError
        if maximum is not None and number > maximum:
            raise ValueError
        if number != number.quantize(CENT):
            raise ValueError
        return number.quantize(CENT)
    except (InvalidOperation, ValueError, TypeError):
        limit = f' between 0 and {maximum}' if maximum is not None else ' of zero or more'
        raise ValidationError(f'{label} must be a finite number{limit}, with at most two decimal places.')


def calculate_booking_financials(deal_amount, whn_expenses, artist_expenses, commission_percentage):
    deal = decimal_value(deal_amount, 'Deal Amount', Decimal('9999999999.99'))
    whn = decimal_value(whn_expenses, 'WHN Expenses')
    artist = decimal_value(artist_expenses, 'Artist Expenses')
    rate = decimal_value(commission_percentage, 'WHN Commission', HUNDRED)
    if whn + artist > deal:
        raise ValidationError('Combined WHN and Artist Expenses cannot exceed the Deal Amount.')
    base = deal - whn - artist
    share = (base * rate / HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP)
    artist_share = base - share
    result = dict(deal_amount=deal, whn_expenses=whn, artist_expenses=artist,
                  total_expenses=whn + artist, commission_base=base,
                  commission_percentage=rate, whn_share=share, artist_share=artist_share,
                  artist_net_payout=artist_share + artist, whn_net_payout=share + whn)
    if result['artist_net_payout'] + result['whn_net_payout'] != deal:
        raise ValidationError('Booking payouts do not reconcile to the Deal Amount.')
    return result


def configured_artist_percentage(booking):
    if booking.booking_type == 'Custom':
        value = booking.custom_artist_percentage
        if value is None:
            raise ValidationError('Custom bookings require an Artist Share percentage.')
    elif booking.booking_type in ('Sale', 'Lead'):
        field = 'sales_commission_percentage' if booking.booking_type == 'Sale' else 'lead_commission_percentage'
        value = getattr(booking.artist, field, None)
        # Pre-0030 artists used these fixed artist shares. Zero is a valid configured rate.
        if value is None:
            value = Decimal('85') if booking.booking_type == 'Sale' else Decimal('90')
    else:
        raise ValidationError('Select a valid booking type.')
    return decimal_value(value, 'Artist Share percentage', HUNDRED)


def booking_financials(booking):
    snapshot = booking.applied_artist_percentage
    pct = snapshot if snapshot is not None else configured_artist_percentage(booking)
    expenses = list(booking.expenses.all())
    totals = {'Artist': Decimal('0.00'), 'WHN': Decimal('0.00')}
    for expense in expenses:
        if expense.borne_by not in totals:
            raise ValidationError('Select Artist or WHN for each expense.')
        totals[expense.borne_by] += decimal_value(expense.amount, 'Expense Amount')
    result = calculate_booking_financials(booking.deal_amount, totals['WHN'], totals['Artist'], HUNDRED - pct)
    result.update(pct=pct / HUNDRED, pct_str=f"{pct.normalize():f}%",
                  artist_commission=result['artist_share'], artist_net=result['artist_net_payout'],
                  rate_source=('booking' if snapshot is not None else
                               'booking_custom' if booking.booking_type == 'Custom' else
                               'current_artist_estimate'))
    return result


def parse_booking_financial_input(post, artist):
    """Validate the whole proposed expense set BEFORE saving/deleting any records."""
    from .models import Booking
    proposed = Booking(artist=artist, booking_type=post.get('booking_type'),
                       custom_artist_percentage=post.get('custom_artist_percentage') or None)
    pct = configured_artist_percentage(proposed)
    deal = decimal_value(post.get('deal_amount') or '0', 'Deal Amount', Decimal('9999999999.99'))
    names, amounts, bearers = (post.getlist(key) for key in
                              ('expense_name[]', 'expense_amount[]', 'expense_borne_by[]'))
    if len(names) != len(amounts) or (bearers and len(bearers) != len(names)):
        raise ValidationError('Each expense requires a name, amount and expense category.')
    rows = []
    totals = {'Artist': Decimal('0.00'), 'WHN': Decimal('0.00')}
    for index, (name, amount) in enumerate(zip(names, amounts)):
        if not name.strip() and not amount:
            continue
        bearer = bearers[index] if bearers else 'WHN'
        if not name.strip() or len(name.strip()) > 150 or bearer not in totals:
            raise ValidationError('Each expense requires a name (up to 150 characters) and Artist or WHN category.')
        amount = decimal_value(amount, 'Expense Amount', Decimal('99999999.99'))
        totals[bearer] += amount
        rows.append(dict(name=name.strip(), amount=amount, borne_by=bearer))
    calculate_booking_financials(deal, totals['WHN'], totals['Artist'], HUNDRED - pct)
    return deal, pct if proposed.booking_type == 'Custom' else None, rows
