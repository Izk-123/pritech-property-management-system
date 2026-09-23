from rest_framework import serializers


class SyncOperationSerializer(serializers.Serializer):
    """A single operation from the offline queue."""

    operation = serializers.ChoiceField(
        choices=['POST', 'PATCH', 'DELETE'],
    )
    endpoint = serializers.CharField(max_length=500)
    payload = serializers.DictField()
    created_at = serializers.DateTimeField()


class SyncBatchSerializer(serializers.Serializer):
    """A batch of operations to sync."""

    operations = SyncOperationSerializer(many=True, max_length=100)
    tenant_schema = serializers.CharField(max_length=63, required=False)