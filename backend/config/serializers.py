from rest_framework import serializers


class MoneySerializer(serializers.Serializer):
    pesewas = serializers.IntegerField()
    display = serializers.CharField()


class StrictSerializer(serializers.Serializer):
    """Refuses fields it does not know, instead of quietly ignoring them.

    For requests where an extra field is a warning sign, such as a client trying to send a price.
    """

    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        if isinstance(data, dict):
            unknown = sorted(set(data) - set(self.fields))
            if unknown:
                raise serializers.ValidationError(
                    {key: "This field is not accepted." for key in unknown}
                )
        return super().to_internal_value(data)
