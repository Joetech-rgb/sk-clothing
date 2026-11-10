from apps.catalog.serializers import MAX_LINE_QUANTITY, PriceItemSerializer
from apps.orders.views import ItemSerializer


def test_the_limit_is_one_thousand_per_item():
    assert MAX_LINE_QUANTITY == 1000


def test_the_price_and_order_endpoints_accept_and_refuse_the_same_quantities():
    # A customer must never be quoted a quantity that checkout then refuses.
    for serializer in (PriceItemSerializer, ItemSerializer):
        assert serializer(data={"variant_id": 1, "quantity": 1000}).is_valid()
        assert not serializer(data={"variant_id": 1, "quantity": 1001}).is_valid()
        assert not serializer(data={"variant_id": 1, "quantity": 0}).is_valid()
