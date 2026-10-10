"""Permissões únicas do projeto. Os outros apps importam daqui."""
from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Prefeitura (CITY_ADMIN), SYSTEM_ADMIN ou superuser."""

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.is_fluxo_admin)


class IsDriver(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.is_driver)


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role == "STUDENT")


class IsDriverOrAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_driver or u.is_fluxo_admin))
