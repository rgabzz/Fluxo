from datetime import date, timedelta
from django.db import models

def tomorrow():
    return date.today() + timedelta(days=1)

class Bus(models.Model):
    name = models.CharField(max_length=100)  # ex: "IFRN Apodi 01"
    plate = models.CharField(max_length=10, unique=True)
    capacity = models.IntegerField()

    driver = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': 'DRIVER'}
    )

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
    
class City(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class BusRoute(models.Model):
    bus = models.ForeignKey(Bus, on_delete=models.CASCADE)
    city = models.ForeignKey('City', on_delete=models.PROTECT)

    departure_time_city = models.TimeField()  # 05:40
    departure_time_ifrn = models.TimeField()   # 12:00

    created_at = models.DateTimeField(auto_now_add=True)

class BusList(models.Model):
    bus_route = models.ForeignKey(BusRoute, on_delete=models.CASCADE)
    date = models.DateField(default=tomorrow)

    created_at = models.DateTimeField(auto_now_add=True)

class BusListEntry(models.Model):
    class Meta: # Impede duplicatas
        constraints = [
            models.UniqueConstraint(
                fields=["bus_list", "user"],
                name="unique_user_per_bus_list"
            )
        ]

    bus_list = models.ForeignKey(BusList, on_delete=models.CASCADE)
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)

    stay = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)