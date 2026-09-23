"""
Sync endpoint for offline operations.

Accepts a batch of operations from the PWA's IndexedDB queue,
applies them in order, and returns per-operation results.
"""
import logging

from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import SyncBatchSerializer

logger = logging.getLogger(__name__)


# Registry of allowed sync endpoints and their handlers.
# Only endpoints in this registry can be synced — this prevents
# the offline queue from being used as an arbitrary request proxy.
SYNC_HANDLERS = {}


def register_sync_handler(endpoint_pattern, handler):
    """Register a handler for a sync endpoint pattern."""
    SYNC_HANDLERS[endpoint_pattern] = handler


class ConflictError(Exception):
    """Raised when an offline operation conflicts with server state."""

    def __init__(self, message, server_state=None):
        super().__init__(message)
        self.server_state = server_state or {}


class SyncView(APIView):
    """
    Accept a batch of offline operations and apply them.

    POST /api/v1/sync/
    {
        "operations": [
            {
                "operation": "POST",
                "endpoint": "/api/v1/sync/reservations/42/status/",
                "payload": {"status": "CHIN", "unit_id": 5, "rate": "50000"},
                "created_at": "2026-09-20T13:30:00Z"
            }
        ]
    }
    """

    def post(self, request):
        serializer = SyncBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        results = []
        for op in serializer.validated_data['operations']:
            result = self._apply_operation(op, request)
            results.append(result)

        conflicts = sum(1 for r in results if r['status'] == 'conflict')
        failed = sum(1 for r in results if r['status'] == 'failed')

        return Response({
            'results': results,
            'total': len(results),
            'synced': len(results) - conflicts - failed,
            'conflicts': conflicts,
            'failed': failed,
        }, status=status.HTTP_200_OK)

    def _apply_operation(self, op, request):
        endpoint = op['endpoint']

        # Find a matching handler
        handler = None
        for pattern, h in SYNC_HANDLERS.items():
            if endpoint.startswith(pattern):
                handler = h
                break

        if handler is None:
            logger.warning(f'Unregistered sync endpoint: {endpoint}')
            return {
                'endpoint': endpoint,
                'status': 'rejected',
                'error': 'Endpoint not registered for sync',
            }

        try:
            with transaction.atomic():
                result = handler(op, request=request)
            return {
                'endpoint': endpoint,
                'status': 'synced',
                'result': result,
            }
        except ConflictError as e:
            logger.info(f'Sync conflict on {endpoint}: {e}')
            return {
                'endpoint': endpoint,
                'status': 'conflict',
                'error': str(e),
                'server_state': e.server_state,
            }
        except Exception as e:
            logger.exception(f'Sync operation failed: {endpoint}')
            return {
                'endpoint': endpoint,
                'status': 'failed',
                'error': str(e),
            }