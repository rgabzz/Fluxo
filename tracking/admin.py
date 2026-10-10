from django.contrib import admin

from .models import BusLocation, Journey, JourneyStopProgress


class ProgressInline(admin.TabularInline):
    model = JourneyStopProgress
    extra = 0


@admin.register(Journey)
class JourneyAdmin(admin.ModelAdmin):
    list_display = ("id", "route", "driver", "status", "started_at", "finished_at", "delay_minutes")
    list_filter = ("status", "route")
    inlines = [ProgressInline]


admin.site.register(BusLocation)
