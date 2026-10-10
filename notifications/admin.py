from django.contrib import admin

from .models import Event, EventRead, PushToken


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "title", "route", "level", "created_at")
    list_filter = ("type", "level")
    search_fields = ("title", "message")


admin.site.register(EventRead)
admin.site.register(PushToken)
