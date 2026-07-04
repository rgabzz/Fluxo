from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAdminUser,IsAuthenticated
from .models import City,Bus,BusRoute,BusList
from .serializers import CitySerializer,BusSerializer,BusRouteSerializer,BusListSerializer
from .permissions import IsCityAdmin,IsStudent,IsDriverOrCityAdmin

class AdminWriteViewSet(ModelViewSet):
    def get_permissions(self):
        if self.request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            return [IsCityAdmin()]
        return [IsAuthenticated()]

class CityViewSet(AdminWriteViewSet):
    queryset = City.objects.all()
    serializer_class = CitySerializer

class BusViewSet(AdminWriteViewSet):
    queryset = Bus.objects.all()
    serializer_class = BusSerializer

class BusRouteViewSet(AdminWriteViewSet):
    queryset = BusRoute.objects.all()
    serializer_class = BusRouteSerializer
    
class BusListViewSet(ModelViewSet):
    queryset = BusList.objects.all()
    serializer_class = BusListSerializer

    # o motorista é filtrado praq ele n possa editar a lista de outros motoristas
    # o aluno não é fikltrado pq ele so consegue acessar o get msm
    def get_queryset(self):
        user = self.request.user

        if user.role == "DRIVER":
            return BusList.objects.filter(bus_route__bus__driver=user)

        return BusList.objects.all()

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated()]

        if self.request.method in ["POST", "PUT", "PATCH"]:
            return [IsDriverOrCityAdmin()]

        if self.request.method == "DELETE":
            return [IsCityAdmin()]

        return [IsAuthenticated()]