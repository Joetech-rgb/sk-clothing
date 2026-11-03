import math

from rest_framework import serializers

from config.serializers import MoneySerializer, StrictSerializer

from .fees import DOORSTEP, METHODS, STATION


class StationSerializer(serializers.Serializer):
    name = serializers.CharField()
    fee = MoneySerializer()


class QuoteRequestSerializer(StrictSerializer):
    method = serializers.ChoiceField(choices=sorted(METHODS))
    station_name = serializers.CharField(required=False, max_length=100, allow_blank=True)
    latitude = serializers.FloatField(required=False, min_value=-90, max_value=90)
    longitude = serializers.FloatField(required=False, min_value=-180, max_value=180)

    def validate_latitude(self, value: float) -> float:
        if not math.isfinite(value):
            raise serializers.ValidationError("Enter a valid number.")
        return value

    def validate_longitude(self, value: float) -> float:
        if not math.isfinite(value):
            raise serializers.ValidationError("Enter a valid number.")
        return value

    def validate(self, attrs):  # type: ignore[no-untyped-def]
        method = attrs["method"]
        if method == STATION and not attrs.get("station_name", "").strip():
            raise serializers.ValidationError({"station_name": "Enter the station name."})
        if method == DOORSTEP:
            missing = {
                key: "This field is required for doorstep delivery."
                for key in ("latitude", "longitude")
                if attrs.get(key) is None
            }
            if missing:
                raise serializers.ValidationError(missing)
        return attrs


class QuoteResponseSerializer(serializers.Serializer):
    method = serializers.CharField()
    status = serializers.CharField()
    fee = MoneySerializer(allow_null=True)
    cod_allowed = serializers.BooleanField()
    reason = serializers.CharField(allow_null=True)
    road_km = serializers.CharField(allow_null=True)
