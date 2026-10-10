from django.contrib import admin

from .models import Bus, BusList, BusListEntry, BusRoute, City, RouteFavorite, Stop


class StopInline(admin.TabularInline):
    model = Stop
    extra = 0
    ordering = ("order",)
    fields = ("order", "name", "coord_status", "latitude", "longitude")


@admin.register(BusRoute)
class BusRouteAdmin(admin.ModelAdmin):
    list_display = ("__str__", "code", "bus", "operating_status", "departure_time_city", "departure_time_ifrn")
    list_filter = ("city", "shift", "operating_status")
    search_fields = ("code", "city__name")
    inlines = [StopInline]


@admin.register(Stop)
class StopAdmin(admin.ModelAdmin):
    list_display = ("route", "order", "name", "coord_status", "latitude", "longitude")
    list_filter = ("coord_status", "route")
    search_fields = ("name",)


admin.site.register(City)
admin.site.register(Bus)
admin.site.register(BusList)
admin.site.register(BusListEntry)
admin.site.register(RouteFavorite)
