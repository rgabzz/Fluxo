# Mantido por compatibilidade com o código antigo; a fonte única agora é users.permissions.
from users.permissions import IsAdmin, IsDriver, IsDriverOrAdmin, IsStudent

IsCityAdmin = IsAdmin
IsDriverOrCityAdmin = IsDriverOrAdmin

__all__ = ["IsStudent", "IsDriver", "IsCityAdmin", "IsDriverOrCityAdmin", "IsAdmin", "IsDriverOrAdmin"]
