from cancheria.domain.payments.models import Deposit
from cancheria.domain.reservations.models import AvailabilityQuery

def test_deposit_remaining_amount():
    assert Deposit(required_amount=100, paid_amount=40).remaining_amount == 60
    assert Deposit(required_amount=100, paid_amount=140).remaining_amount == 0

def test_availability_query_defaults():
    q=AvailabilityQuery(day="01/01/2030")
    assert q.duration_hours == 1.0
