from django.core.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_exception_handler

from events.services import EventClosedError
from operations.services import StaffPermissionError


def exception_handler(exc, context):
    """Exception handler central para toda la capa DRF del proyecto.

    Reemplaza el patron repetido `except Exception as exc: JsonResponse({"ok": False,
    "error": str(exc)}, status=400)` que existia en los ~9 endpoints JSON manuales de
    commerce/operations. Mapea las excepciones de negocio conocidas a codigos HTTP
    consistentes y deja pasar (retorna None) cualquier error verdaderamente inesperado
    para que se reporte como 500 - antes esos errores de programacion se enmascaraban
    silenciosamente como 400.
    """
    response = drf_default_exception_handler(exc, context)
    if response is not None:
        # Ya manejado por DRF (ValidationError de serializer, NotAuthenticated, etc.)
        if not isinstance(response.data, dict) or "ok" not in response.data:
            response.data = {"ok": False, "error": _flatten_drf_errors(response.data)}
        return response

    # EventClosedError hereda de django.core.exceptions.ValidationError, no de
    # ValueError - debe chequearse antes que el ValueError generico.
    if isinstance(exc, (StaffPermissionError, PermissionDenied)):
        return Response({"ok": False, "error": str(exc) or "No autorizado."}, status=403)
    if isinstance(exc, EventClosedError):
        return Response(
            {"ok": False, "error": str(exc) or "El evento no acepta operaciones en este momento."},
            status=409,
        )
    if isinstance(exc, ValueError):
        return Response({"ok": False, "error": str(exc)}, status=400)
    return None


def _flatten_drf_errors(data):
    if isinstance(data, dict):
        parts = []
        for key, value in data.items():
            first_value = value[0] if isinstance(value, list) and value else value
            parts.append(f"{key}: {first_value}")
        return "; ".join(parts)
    if isinstance(data, list):
        return "; ".join(str(item) for item in data)
    return str(data)
