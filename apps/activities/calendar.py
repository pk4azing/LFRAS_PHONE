# apps/activities/calendar.py
from rest_framework import serializers

class CalendarEventSerializer(serializers.Serializer):
    date = serializers.DateField()
    kind = serializers.ChoiceField(choices=["INFO", "WARNING", "EXPIRY"])
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    cd = serializers.IntegerField(required=False, allow_null=True)
    activity_id = serializers.IntegerField(required=False, allow_null=True)
    file_id = serializers.IntegerField(required=False, allow_null=True)
    color = serializers.CharField()