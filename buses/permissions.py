from rest_framework.permissions import BasePermission

class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.role == "STUDENT"
        )


class IsDriver(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.role == "DRIVER"
        )


class IsCityAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            (
                request.user.role == "CITY_ADMIN"
                or request.user.is_superuser
            )
        )


class IsDriverOrCityAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            (
                request.user.role in ["DRIVER", "CITY_ADMIN"]
                or request.user.is_superuser
            )
        )