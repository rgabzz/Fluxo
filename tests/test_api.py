from datetime import timedelta
from unittest import mock

from django.db import IntegrityError, transaction
from django.utils import timezone

from buses.models import BusList, Stop
from notifications.models import Event
from tracking.models import Journey
from users.models import User

from .base import BASE_LNG, FluxoTestCase, stop_lat


class AuthTests(FluxoTestCase):
    def test_public_register_cannot_choose_role(self):
        r = self.client.post(
            "/api/auth/register/",
            {"username": "novo", "password": "Senh@Forte123", "role": "SYSTEM_ADMIN"},
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(User.objects.get(username="novo").role, "STUDENT")

    def test_register_rejects_weak_password(self):
        r = self.client.post("/api/auth/register/", {"username": "n2", "password": "123"})
        self.assertEqual(r.status_code, 400)

    def test_jwt_login_and_me(self):
        r = self.client.post("/api/token/", {"username": "aluno", "password": "x" * 12})
        self.assertEqual(r.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        self.assertEqual(self.client.get("/api/auth/me/").data["role"], "STUDENT")

    def test_anonymous_cannot_read_routes(self):
        self.assertEqual(self.client.get("/api/routes/").status_code, 401)

    def test_admin_creates_driver_student_cannot(self):
        body = {"username": "mot3", "password": "Senh@Forte123", "role": "DRIVER"}
        self.login(self.student)
        self.assertEqual(self.client.post("/api/users/", body).status_code, 403)
        self.login(self.admin)
        self.assertEqual(self.client.post("/api/users/", body).status_code, 201)
        self.assertEqual(User.objects.get(username="mot3").role, "DRIVER")

    def test_city_admin_cannot_create_system_admin(self):
        self.login(self.admin)
        r = self.client.post("/api/users/", {"username": "s", "password": "Senh@Forte123", "role": "SYSTEM_ADMIN"})
        self.assertEqual(r.status_code, 400)


class RouteTests(FluxoTestCase):
    def test_student_can_read_but_not_write(self):
        self.login(self.student)
        self.assertEqual(self.client.get("/api/routes/").status_code, 200)
        self.assertEqual(self.client.patch(f"/api/routes/{self.route.pk}/", {"shift": "NIGHT"}).status_code, 403)
        self.assertEqual(self.client.post(f"/api/routes/{self.route.pk}/suspend/").status_code, 403)

    def test_routes_include_ordered_stops_and_filters(self):
        self.login(self.student)
        r = self.client.get("/api/routes/?city=%d&shift=MORNING" % self.city.pk)
        self.assertEqual([s["name"] for s in r.data[0]["stops"]], ["P1", "P2", "P3"])
        self.assertEqual(self.client.get("/api/routes/?shift=NIGHT").data, [])

    def test_route_time_change_emits_route_updated(self):
        self.login(self.admin)
        r = self.client.patch(f"/api/routes/{self.route.pk}/", {"departure_time_city": "06:00:00"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Event.objects.filter(type="ROUTE_UPDATED", route=self.route).exists())

    def test_patch_without_relevant_change_emits_nothing(self):
        self.login(self.admin)
        self.client.patch(f"/api/routes/{self.route.pk}/", {"code": "itau-manha"})
        self.assertFalse(Event.objects.filter(type="ROUTE_UPDATED").exists())

    def test_cannot_change_operating_status_by_patch(self):
        self.login(self.admin)
        self.client.patch(f"/api/routes/{self.route.pk}/", {"operating_status": "SUSPENDED"})
        self.route.refresh_from_db()
        self.assertEqual(self.route.operating_status, "ACTIVE")

    def test_suspend_and_resume_emit_events_and_block_journey(self):
        self.login(self.admin)
        self.assertEqual(self.client.post(f"/api/routes/{self.route.pk}/suspend/", {"note": "Chuva"}).status_code, 200)
        self.assertEqual(self.client.post(f"/api/routes/{self.route.pk}/suspend/").status_code, 409)
        self.login(self.driver)
        self.assertEqual(self.client.post("/api/journeys/", {"route": self.route.pk}).status_code, 409)
        self.login(self.admin)
        self.client.post(f"/api/routes/{self.route.pk}/resume/")
        self.assertEqual(Event.objects.filter(type="OPERATING_CHANGED").count(), 2)

    def test_favorite_toggle(self):
        self.login(self.student)
        self.assertEqual(self.client.post(f"/api/routes/{self.route.pk}/favorite/").status_code, 204)
        self.assertTrue(self.client.get("/api/routes/").data[0]["is_favorite"])
        self.client.delete(f"/api/routes/{self.route.pk}/favorite/")
        self.assertFalse(self.client.get("/api/routes/").data[0]["is_favorite"])


class CityTests(FluxoTestCase):
    def test_delete_city_with_routes_is_409_not_500(self):
        self.login(self.admin)
        self.assertEqual(self.client.delete(f"/api/cities/{self.city.pk}/").status_code, 409)

    def test_delete_empty_city(self):
        from buses.models import City

        c = City.objects.create(name="Vazia")
        self.login(self.admin)
        self.assertEqual(self.client.delete(f"/api/cities/{c.pk}/").status_code, 204)


class StopTests(FluxoTestCase):
    def test_pending_stop_cannot_have_coordinates(self):
        self.login(self.admin)
        r = self.client.post("/api/stops/", {"route": self.route.pk, "order": 9, "name": "X", "latitude": 1, "longitude": 1})
        self.assertEqual(r.status_code, 400)

    def test_confirmed_stop_requires_coordinates(self):
        self.login(self.admin)
        r = self.client.post("/api/stops/", {"route": self.route.pk, "order": 9, "name": "X", "coord_status": "CONFIRMED"})
        self.assertEqual(r.status_code, 400)

    def test_pending_to_confirmed_via_patch(self):
        s = Stop.objects.create(route=self.route, order=9, name="Nova")
        self.login(self.admin)
        r = self.client.patch(f"/api/stops/{s.pk}/", {"coord_status": "CONFIRMED", "latitude": -5.7, "longitude": -37.7})
        self.assertEqual(r.status_code, 200)

    def test_db_constraint_blocks_inconsistent_stop(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Stop.objects.create(route=self.route, order=50, name="Y", coord_status="CONFIRMED")

    def test_reorder(self):
        self.login(self.admin)
        ids = [s.pk for s in self.stops]
        r = self.client.post(f"/api/routes/{self.route.pk}/stops/reorder/", {"order": ids[::-1]}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([s["name"] for s in r.data], ["P3", "P2", "P1"])
        self.assertEqual(list(self.route.stops.order_by("order").values_list("name", flat=True)), ["P3", "P2", "P1"])
        bad = self.client.post(f"/api/routes/{self.route.pk}/stops/reorder/", {"order": ids[:2]}, format="json")
        self.assertEqual(bad.status_code, 400)


class JourneyTests(FluxoTestCase):
    def start(self, user=None):
        self.login(user or self.driver)
        return self.client.post("/api/journeys/", {"route": self.route.pk})

    def test_only_route_driver_can_start(self):
        self.assertEqual(self.start(self.student).status_code, 403)
        self.assertEqual(self.start(self.driver2).status_code, 403)
        r = self.start(self.driver)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["status"], "IN_PROGRESS")
        self.assertTrue(Event.objects.filter(type="JOURNEY_STARTED").exists())

    def test_second_active_journey_same_route_conflicts(self):
        self.start()
        self.assertEqual(self.start().status_code, 409)

    def test_gps_auto_advances_in_order_and_emits_stop_reached(self):
        jid = self.start().data["id"]
        base = timezone.now()
        # 3 amostras em cima da P1
        for sec in (0, 5, 10):
            r = self.client.post(f"/api/journeys/{jid}/location/", self.sample(stop_lat(0), seconds=sec - 12, base=base))
            self.assertEqual(r.status_code, 200, r.data)
        j = self.client.get(f"/api/journeys/{jid}/").data
        self.assertEqual([p["stop_name"] for p in j["progress"]], ["P1"])
        self.assertEqual(j["next_stop_id"], self.stops[1].pk)
        self.assertEqual(Event.objects.filter(type="STOP_REACHED").count(), 1)

    def test_gps_on_wrong_stop_does_not_skip(self):
        jid = self.start().data["id"]
        base = timezone.now()
        for sec in (0, 5, 10):  # em cima da P3, mas a próxima é a P1
            self.client.post(f"/api/journeys/{jid}/location/", self.sample(stop_lat(2), seconds=sec - 12, base=base))
        self.assertEqual(Journey.objects.get(pk=jid).progress.count(), 0)

    def test_location_is_visible_to_students_via_live(self):
        jid = self.start().data["id"]
        self.client.post(f"/api/journeys/{jid}/location/", self.sample(-5.59, seconds=-1))
        self.login(self.student)
        live = self.client.get(f"/api/routes/{self.route.pk}/live/").data
        self.assertEqual(live["journey"]["id"], jid)
        self.assertAlmostEqual(live["location"]["latitude"], -5.59)
        self.assertFalse(live["location"]["stale"])
        self.assertEqual([s["state"] for s in live["stops"]], ["current", "upcoming", "upcoming"])

    def test_student_cannot_post_location_or_change_progress(self):
        jid = self.start().data["id"]
        self.login(self.student)
        self.assertEqual(self.client.post(f"/api/journeys/{jid}/location/", self.sample(-5.6)).status_code, 403)
        self.assertEqual(self.client.post(f"/api/journeys/{jid}/stops/{self.stops[0].pk}/reach/").status_code, 403)
        self.assertEqual(self.client.post(f"/api/journeys/{jid}/cancel/").status_code, 403)

    def test_other_driver_cannot_operate_journey(self):
        jid = self.start().data["id"]
        self.login(self.driver2)
        self.assertEqual(self.client.post(f"/api/journeys/{jid}/location/", self.sample(-5.6)).status_code, 403)

    def test_invalid_coordinates_rejected(self):
        jid = self.start().data["id"]
        self.assertEqual(self.client.post(f"/api/journeys/{jid}/location/", self.sample(123.0)).status_code, 400)

    def test_old_and_out_of_order_samples(self):
        jid = self.start().data["id"]
        now = timezone.now()
        r = self.client.post(f"/api/journeys/{jid}/location/", self.sample(-5.6, seconds=0, base=now))
        self.assertEqual(r.data["accepted"], 1)
        r = self.client.post(f"/api/journeys/{jid}/location/", self.sample(-5.7, seconds=-30, base=now))  # mais antiga
        self.assertEqual((r.data["accepted"], r.data["ignored"]), (0, 1))

    def test_offline_batch_replay_advances_progress(self):
        jid = self.start().data["id"]
        past = timezone.now() - timedelta(minutes=10)  # amostras antigas, de quando estava sem sinal
        samples = [self.sample(stop_lat(0), seconds=i * 5, base=past) for i in range(3)]
        r = self.client.post(f"/api/journeys/{jid}/location/", {"samples": samples, "replay": True}, format="json")
        self.assertEqual(r.data["reached_stops"], [self.stops[0].pk])
        # sem replay, as mesmas amostras antigas não contam para parada
        jid2 = None
        Journey.objects.filter(pk=jid).update(status="CANCELED")
        jid2 = self.start().data["id"]
        r = self.client.post(f"/api/journeys/{jid2}/location/", {"samples": samples}, format="json")
        self.assertEqual(r.data["reached_stops"], [])

    def test_batch_size_limit(self):
        jid = self.start().data["id"]
        samples = [self.sample(-5.6, seconds=i) for i in range(51)]
        r = self.client.post(f"/api/journeys/{jid}/location/", {"samples": samples}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_manual_reach_respects_order(self):
        jid = self.start().data["id"]
        self.assertEqual(self.client.post(f"/api/journeys/{jid}/stops/{self.stops[1].pk}/reach/").status_code, 409)
        self.assertEqual(self.client.post(f"/api/journeys/{jid}/stops/{self.stops[0].pk}/reach/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/journeys/{jid}/stops/{self.stops[0].pk}/reach/").status_code, 409)

    def test_last_stop_does_not_finish_journey(self):
        jid = self.start().data["id"]
        for s in self.stops:
            self.client.post(f"/api/journeys/{jid}/stops/{s.pk}/reach/")
        j = self.client.get(f"/api/journeys/{jid}/").data
        self.assertEqual(j["status"], "IN_PROGRESS")
        self.assertIsNone(j["next_stop_id"])

    def test_delay_cancel_finish_flow_and_events(self):
        jid = self.start().data["id"]
        r = self.client.post(f"/api/journeys/{jid}/delay/", {"minutes": 15, "note": "Trânsito"})
        self.assertEqual(r.data["delay_minutes"], 15)
        self.assertEqual(self.client.post(f"/api/journeys/{jid}/delay/", {"minutes": 0}).status_code, 400)
        self.client.post(f"/api/journeys/{jid}/finish/")
        self.assertEqual(self.client.post(f"/api/journeys/{jid}/finish/").status_code, 409)
        self.assertEqual(self.client.post(f"/api/journeys/{jid}/location/", self.sample(-5.6)).status_code, 409)
        types = set(Event.objects.values_list("type", flat=True))
        self.assertTrue({"JOURNEY_STARTED", "DELAY_REPORTED", "JOURNEY_FINISHED"} <= types)
        # nova jornada na mesma rota é permitida depois de finalizar
        self.assertEqual(self.start().status_code, 201)

    def test_cancel_emits_status_changed(self):
        jid = self.start().data["id"]
        self.client.post(f"/api/journeys/{jid}/cancel/", {"reason": "Pane"})
        e = Event.objects.get(type="STATUS_CHANGED")
        self.assertEqual((e.level, e.message), ("URGENT", "Pane"))

    def test_live_without_journey(self):
        self.login(self.student)
        live = self.client.get(f"/api/routes/{self.route.pk}/live/").data
        self.assertIsNone(live["journey"])
        self.assertIsNone(live["location"])
        self.assertTrue(all(s["state"] == "upcoming" for s in live["stops"]))


class NotificationTests(FluxoTestCase):
    def setUp(self):
        # student segue a rota; student2 não
        from buses.models import RouteFavorite

        RouteFavorite.objects.create(user=self.student, route=self.route)

    def count(self, user):
        self.login(user)
        return self.client.get("/api/notifications/").data

    def test_student_only_gets_followed_routes_and_global_notices(self):
        self.login(self.admin)
        self.client.post("/api/notices/", {"title": "Geral", "level": "INFO"})
        self.client.post("/api/notices/", {"title": "Da rota", "route": self.route.pk, "level": "URGENT"})
        self.assertEqual(len(self.count(self.student)["results"]), 2)
        self.assertEqual([n["title"] for n in self.count(self.student2)["results"]], ["Geral"])

    def test_student_cannot_publish_notice(self):
        self.login(self.student)
        self.assertEqual(self.client.post("/api/notices/", {"title": "x"}).status_code, 403)

    def test_stop_reached_never_reaches_the_bell(self):
        self.login(self.driver)
        jid = self.client.post("/api/journeys/", {"route": self.route.pk}).data["id"]
        self.client.post(f"/api/journeys/{jid}/stops/{self.stops[0].pk}/reach/")
        self.assertTrue(Event.objects.filter(type="STOP_REACHED").exists())
        types = [n["type"] for n in self.count(self.student)["results"]]
        self.assertEqual(types, ["JOURNEY_STARTED"])

    def test_read_state_is_per_user_and_badge_counts_unread(self):
        self.login(self.admin)
        self.client.post("/api/notices/", {"title": "Geral"})
        nid = self.count(self.student)["results"][0]["id"]
        self.login(self.student)
        self.assertEqual(self.client.post(f"/api/notifications/{nid}/read/").status_code, 204)
        a = self.count(self.student)
        self.assertEqual(a["unread_count"], 0)
        self.assertTrue(a["results"][0]["read"])  # histórico preservado
        self.assertEqual(self.count(self.student2)["unread_count"], 1)  # outro usuário continua não lido

    def test_read_all_and_unread_filter(self):
        self.login(self.admin)
        for t in "abc":
            self.client.post("/api/notices/", {"title": t})
        self.login(self.student)
        self.assertEqual(self.client.get("/api/notifications/unread-count/").data["unread_count"], 3)
        self.client.post("/api/notifications/read-all/")
        self.assertEqual(self.client.get("/api/notifications/?unread=1").data["results"], [])

    def test_cannot_read_event_you_cannot_see(self):
        self.login(self.admin)
        self.client.post("/api/notices/", {"title": "Da rota", "route": self.route.pk})
        eid = Event.objects.get().pk
        self.login(self.student2)
        self.assertEqual(self.client.post(f"/api/notifications/{eid}/read/").status_code, 404)

    def test_reservation_also_makes_student_a_recipient(self):
        bl = BusList.objects.create(bus_route=self.route, date=timezone.localdate())
        self.login(self.student2)
        self.assertEqual(self.client.post(f"/api/bus-lists/{bl.pk}/join/").status_code, 201)
        self.login(self.admin)
        self.client.post("/api/notices/", {"title": "Da rota", "route": self.route.pk})
        self.assertEqual(len(self.count(self.student2)["results"]), 1)

    def test_driver_sees_only_own_route_events(self):
        self.login(self.admin)
        self.client.post("/api/notices/", {"title": "Da rota", "route": self.route.pk})
        self.assertEqual(len(self.count(self.driver)["results"]), 1)
        self.assertEqual(len(self.count(self.driver2)["results"]), 0)

    def test_after_id_for_incremental_polling(self):
        self.login(self.admin)
        self.client.post("/api/notices/", {"title": "um"})
        first = self.count(self.student)["results"][0]["id"]
        self.login(self.admin)
        self.client.post("/api/notices/", {"title": "dois"})
        self.login(self.student)
        r = self.client.get(f"/api/notifications/?after_id={first}")
        self.assertEqual([n["title"] for n in r.data["results"]], ["dois"])


class PushTests(FluxoTestCase):
    def test_token_registration_and_validation(self):
        self.login(self.student)
        self.assertEqual(self.client.post("/api/push-tokens/", {"token": "lixo"}).status_code, 400)
        ok = {"token": "ExponentPushToken[abc]", "platform": "android"}
        self.assertEqual(self.client.post("/api/push-tokens/", ok).status_code, 204)
        self.login(self.student2)  # mesmo aparelho, outro login => token muda de dono
        self.client.post("/api/push-tokens/", ok)
        from notifications.models import PushToken

        self.assertEqual(PushToken.objects.get().user, self.student2)
        self.client.delete("/api/push-tokens/", {"token": ok["token"]})
        self.assertEqual(PushToken.objects.count(), 0)

    def test_push_goes_to_followers_not_to_actor_and_cleans_dead_tokens(self):
        from buses.models import RouteFavorite
        from notifications import services
        from notifications.models import PushToken

        RouteFavorite.objects.create(user=self.student, route=self.route)
        PushToken.objects.create(user=self.student, token="ExponentPushToken[aluno]")
        PushToken.objects.create(user=self.student2, token="ExponentPushToken[outro]")
        PushToken.objects.create(user=self.admin, token="ExponentPushToken[admin]")
        ev = services.emit_event("NOTICE", title="Chuva", message="Rota suspensa", route=self.route, actor=self.admin)

        resp = mock.Mock()
        resp.json.return_value = {"data": [{"status": "error", "details": {"error": "DeviceNotRegistered"}}]}
        with mock.patch("notifications.services.requests.post", return_value=resp) as post:
            services.send_push_for_event(ev.pk)
        sent = post.call_args.kwargs["json"]
        self.assertEqual([m["to"] for m in sent], ["ExponentPushToken[aluno]"])
        self.assertEqual(sent[0]["title"], "Chuva")
        self.assertFalse(PushToken.objects.filter(token="ExponentPushToken[aluno]").exists())  # token morto removido

    def test_push_failure_never_breaks_the_api(self):
        from notifications import services

        ev = services.emit_event("NOTICE", title="x", actor=self.admin)
        with mock.patch("notifications.services.requests.post", side_effect=RuntimeError("sem rede")):
            from notifications.models import PushToken

            PushToken.objects.create(user=self.student, token="ExponentPushToken[a]")
            with self.assertLogs("notifications.services", level="ERROR"):
                services.send_push_for_event(ev.pk)  # não deve levantar


class BusListTests(FluxoTestCase):
    def setUp(self):
        self.bl = BusList.objects.create(bus_route=self.route, date=timezone.localdate() + timedelta(days=1))

    def test_driver_creates_list_only_for_own_route(self):
        from buses.models import Bus, BusRoute

        other = BusRoute.objects.create(city=self.city, bus=Bus.objects.create(name="B2", plate="BBB0002", capacity=10, driver=self.driver2), shift="NIGHT")
        self.login(self.driver)
        self.assertEqual(self.client.post("/api/bus-lists/", {"bus_route": other.pk, "date": "2030-01-01"}).status_code, 400)
        self.assertEqual(self.client.post("/api/bus-lists/", {"bus_route": self.route.pk, "date": "2030-01-01"}).status_code, 201)
        # duplicada
        self.assertEqual(self.client.post("/api/bus-lists/", {"bus_route": self.route.pk, "date": "2030-01-01"}).status_code, 400)

    def test_student_cannot_create_list(self):
        self.login(self.student)
        self.assertEqual(self.client.post("/api/bus-lists/", {"bus_route": self.route.pk}).status_code, 403)

    def test_join_leave_and_counts(self):
        self.login(self.student)
        self.assertEqual(self.client.post(f"/api/bus-lists/{self.bl.pk}/join/", {"stay": True}).status_code, 201)
        self.assertEqual(self.client.post(f"/api/bus-lists/{self.bl.pk}/join/", {"stay": False}).status_code, 200)  # idempotente
        d = self.client.get(f"/api/bus-lists/{self.bl.pk}/").data
        self.assertEqual((d["entries_count"], d["joined"], d["capacity"]), (1, True, 2))
        self.assertEqual(len(self.client.get("/api/bus-lists/mine/").data), 1)
        self.client.delete(f"/api/bus-lists/{self.bl.pk}/leave/")
        self.assertEqual(self.client.get(f"/api/bus-lists/{self.bl.pk}/").data["entries_count"], 0)

    def test_passenger_list_visible_only_to_route_driver_and_admin(self):
        self.login(self.student)
        self.client.post(f"/api/bus-lists/{self.bl.pk}/join/")
        self.assertEqual(self.client.get(f"/api/bus-lists/{self.bl.pk}/entries/").status_code, 403)
        self.login(self.driver2)
        self.assertEqual(self.client.get(f"/api/bus-lists/{self.bl.pk}/entries/").status_code, 404)  # nem enxerga a lista
        self.login(self.driver)
        self.assertEqual(len(self.client.get(f"/api/bus-lists/{self.bl.pk}/entries/").data), 1)
        self.login(self.admin)
        self.assertEqual(len(self.client.get(f"/api/bus-lists/{self.bl.pk}/entries/").data), 1)

    def test_cannot_join_suspended_route(self):
        self.route.operating_status = "SUSPENDED"
        self.route.save()
        self.login(self.student)
        self.assertEqual(self.client.post(f"/api/bus-lists/{self.bl.pk}/join/").status_code, 409)


class SeedTests(FluxoTestCase):
    def test_seed_is_idempotent_and_never_invents_coordinates(self):
        from django.core.management import call_command

        call_command("seed_fluxo", verbosity=0)
        call_command("seed_fluxo", verbosity=0)
        from buses.models import BusRoute

        sev = BusRoute.objects.get(code="severiano-tarde")
        self.assertEqual(sev.stops.count(), 7)
        self.assertEqual(BusRoute.objects.get(code="felipe-guerra-manha").stops.count(), 0)
        seeded = Stop.objects.filter(route__code__in=["severiano-manha", "caraubas-manha", "rodolfo-fernandes-noite"])
        self.assertFalse(seeded.exclude(coord_status="PENDING").exists())
        self.assertFalse(seeded.filter(latitude__isnull=False).exists())
