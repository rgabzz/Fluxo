# Fluxo — Back-end (Django + DRF)

API do Fluxo 2.0 (transporte escolar/acadêmico). Evolução do projeto BusCar: mantém usuários, cidades,
ônibus, rotas e listas, e adiciona **paradas, jornadas com GPS, progresso automático, avisos/notificações,
favoritos e push**.

## Rodando local

```bash
python -m venv venv && source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # ajuste SECRET_KEY
python manage.py migrate
python manage.py seed_fluxo                            # rotas/paradas do relatório da V2
python manage.py createsuperuser
python manage.py runserver
python manage.py test tests                            # 61 testes
```

Django Admin em `/admin/`: é a forma mais rápida de **cadastrar as coordenadas reais das paradas**
(Rotas → abrir a rota → tabela de paradas → status `Confirmada` + lat/lng).

## Deploy (Render)
`build.sh` já faz install + collectstatic + migrate. Start command: `gunicorn setup.wsgi`.
Variáveis: `SECRET_KEY`, `DEBUG=False`, `DATABASE_URL` (Postgres), opcional `EXPO_ACCESS_TOKEN`.
> SQLite não persiste no Render; use Postgres em produção.

## Perfis
| Role | Pode |
|---|---|
| `STUDENT` | ler rotas/paradas/jornadas, favoritar, entrar/sair de listas, ver o próprio sino |
| `DRIVER` | iniciar/operar jornada **das próprias rotas**, enviar GPS, atraso, cancelar/finalizar, criar listas |
| `CITY_ADMIN` / `SYSTEM_ADMIN` / superuser | tudo de gestão: usuários, ônibus, rotas, paradas, suspender/retomar, avisos |

O cadastro público (`/api/auth/register/`) **sempre cria aluno**. Motoristas e admins são criados por um admin
(`POST /api/users/`) ou no Django Admin.

## Endpoints (tudo exige `Authorization: Bearer <access>`, exceto login/registro)

**Auth**: `POST /api/token/` · `POST /api/token/refresh/` · `POST /api/auth/register/` · `GET /api/auth/me/`

**Rotas e paradas**
- `GET /api/routes/?city=&shift=MORNING|AFTERNOON|NIGHT&operating_status=` — já vem com `stops` ordenadas e `is_favorite`
- `POST/PATCH/DELETE /api/routes/<id>/` (admin) — mudar horário/ônibus/turno gera evento `ROUTE_UPDATED`
- `POST /api/routes/<id>/suspend/` · `/resume/` (admin, `{"note": "..."}`) — gera `OPERATING_CHANGED`
- `POST|DELETE /api/routes/<id>/favorite/`
- `GET/POST/PATCH/DELETE /api/stops/?route=<id>` (admin escreve) · `POST /api/routes/<id>/stops/reorder/ {"order":[ids]}`
- `GET /api/cities/` · `/api/buses/` (admin escreve)

**Mapa ao vivo (polling a cada ~5 s)**
- `GET /api/routes/<id>/live/` — rota, jornada ativa, posição do ônibus (`stale` se >60 s sem atualizar) e
  paradas com `state: done | current | upcoming`. É tudo que a tela de mapa/timeline precisa em 1 chamada.

**Jornada (motorista)**
- `POST /api/journeys/ {"route": id}` — inicia (`JOURNEY_STARTED`)
- `POST /api/journeys/<id>/location/` — uma amostra `{latitude, longitude, accuracy, speed, heading, recorded_at}`
  **ou** fila offline `{"samples":[...até 50], "replay": true}`. Resposta: `{accepted, ignored, reached_stops, departed_stops}`
- `POST /api/journeys/<id>/stops/<stop_id>/reach/` — confirma manualmente a PRÓXIMA parada (único caminho para paradas sem coordenada)
- `POST /api/journeys/<id>/delay/ {"minutes": 15, "note": "..."}` · `/cancel/ {"reason"}` · `/finish/`
- `GET /api/journeys/?route=&status=&active=1`

**Notificações (sino + tela de avisos)**
- `GET /api/notifications/?route=&unread=1&after_id=&limit=` → `{unread_count, results:[{id,type,title,message,level,read,...}]}`
- `GET /api/notifications/unread-count/` · `POST /api/notifications/<id>/read/` · `POST /api/notifications/read-all/`
- `POST /api/notices/` (admin) — aviso `{title, message, level: INFO|IMPORTANT|URGENT, route?}`; sem `route` vai para todos
- `POST|DELETE /api/push-tokens/ {"token":"ExponentPushToken[...]", "platform":"android"}`

**Listas de embarque**: `/api/bus-lists/` · `POST /<id>/join/ {"stay": bool}` · `DELETE /<id>/leave/` · `GET /<id>/entries/` (motorista da rota/admin) · `GET /mine/`

## Regras de GPS (servidor) — iguais ao relatório da V2
Chegada = 3 amostras seguidas a ≤ 75 m da próxima parada · saída = 2 amostras a > 125 m · precisão > 40 m é ignorada ·
amostra com mais de 30 s de idade só atualiza a posição (não conta para parada, exceto `replay`) ·
intervalo máximo entre amostras da sequência: 20 s · ordem respeitada, sem pular nem regredir ·
parada sem coordenada nunca avança sozinha · a última parada **não** finaliza a jornada.
Valores em `FLUXO_TRACKING` (`setup/settings.py`). Lógica pura em `tracking/progress.py`.

## Notificações — quem recebe
`StopReached` atualiza o progresso mas **não** vai ao sino nem gera push. Os demais eventos chegam a:
aluno → rotas que favoritou ou onde tem reserva (+ avisos gerais) · motorista → rotas do seu ônibus ·
admin → tudo. Leitura é por usuário. Push (Expo) sai após o commit, em segundo plano, e falha de push nunca derruba a API.

## Mapeamento com o app (LocalAppRepository → API)
Crie um `ApiAppRepository` com a mesma interface do `LocalAppRepository`: `routes/stops` ← `/api/routes/`;
timeline/mapa ← `/api/routes/<id>/live/`; `LocalTrackingService` do motorista ← `POST /journeys/<id>/location/`
(guarde amostras numa fila local quando sem internet e reenvie com `replay:true`); sino ← `/api/notifications/`.
O campo `code` da rota guarda o ID antigo do app (ex.: `itau-manha`) para não quebrar dados existentes.

## Limitações conhecidas / próximos passos
- Tempo real é por **polling**. Quando precisar de push de verdade em tela aberta: Django Channels + Redis (o modelo já separa tudo em `services.py`).
- Push em thread simples; se o volume crescer, trocar por Celery/RQ.
- Coordenadas reais das paradas ainda precisam ser cadastradas (o seed não inventa nenhuma).
- Sem auditoria de quem editou rotas além dos eventos.
