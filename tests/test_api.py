from datetime import date

from app.places.geo import polygon_area_m2


def test_health_and_login(client, city):
    assert client.get("/api/health").json()["db"] == "ok"
    assert client.get("/api/auth/me", headers=city).json()["org_type"] == "city"
    assert client.post("/api/auth/login", json={"username": "busan", "password": "x"}).status_code == 401


def test_dashboard_and_detail(client, city, judged):
    assert judged["meta"]["judge_day"] == "2026-09-20" and judged["meta"]["demo"] is True
    row = next(p for p in judged["places"] if p["id"] == "bukhang")
    for k in ("intent_posts", "intent_ratio", "missing", "response_level", "d1"):
        assert k in row
    d = client.get("/api/admin/places/bukhang", headers=city).json()
    assert d["bottleneck"]["limit_visitors"] == 111111  # 5*600/(0.09*0.3), peak_share 실측
    assert {"intent", "missing", "checklist", "actual_visitors", "trend"} <= set(d)
    assert client.get("/api/admin/dashboard/rising", headers=city).status_code == 200


def test_runs_recorded(client, city, judged):
    runs = client.get("/api/admin/runs", headers=city).json()
    assert runs[0]["status"] == "ok" and runs[0]["trigger"] == "manual" and runs[0]["places"] >= 5


def test_run_with_admin_token(client, judged):
    assert client.post("/api/admin/run", headers={"X-Admin-Token": "nope"}).status_code == 401


def test_polygon_area():
    # 위도 35도에서 가로·세로 약 100m 정사각형 → 약 1만 ㎡
    dlat = 100 / 111_195
    dlon = 100 / (111_195 * 0.8192)
    sq = [[129.0, 35.0], [129.0 + dlon, 35.0], [129.0 + dlon, 35.0 + dlat], [129.0, 35.0 + dlat]]
    assert abs(polygon_area_m2(sq) - 10_000) < 100


def test_bottleneck_and_place_edit(client, city, donggu, judged):
    poly = [[129.1186, 35.1532], [129.1190, 35.1532], [129.1190, 35.1535], [129.1186, 35.1535]]
    res = client.put("/api/admin/places/gwangalli/bottleneck", headers=city,
                     json={"name": "광안리 해변 진입로", "polygon": poly, "peak_share": 0.12, "bottleneck_share": 0.25})
    assert res.status_code == 200, res.text
    b = res.json()["bottleneck"]
    assert 1000 < b["area_m2"] < 1300 and b["limit_visitors"] > 0
    assert client.put("/api/admin/places/gwangalli/bottleneck", headers=donggu,
                      json={"name": "x", "area_m2": 10}).status_code == 403
    assert client.put("/api/admin/places/gwangalli/bottleneck", headers=city, json={"name": "x"}).status_code == 400
    res = client.patch("/api/admin/places/gwangalli", headers=city, json={"base_rest": 45000, "force_watch": True})
    assert res.json()["base_rest"] == 45000 and res.json()["force_watch"] is True
    res = client.post("/api/admin/places", headers=city,
                      json={"id": "songdo", "name": "송도해수욕장", "district": "서구", "keywords": ["송도해수욕장"]})
    assert res.status_code == 201
    assert client.post("/api/admin/places", headers=city,
                       json={"id": "songdo2", "name": "송도해수욕장"}).status_code == 409


def test_alias(client, city):
    res = client.post("/api/admin/aliases", headers=city, json={"alias": "부캉이", "place_id": "bukhang"})
    assert res.status_code == 201
    assert client.post("/api/admin/aliases", headers=city,
                       json={"alias": "부캉이", "place_id": "bukhang"}).status_code == 409
    hits = client.get("/api/places/search", params={"q": "부캉"}).json()
    assert hits[0]["id"] == "bukhang" and hits[0]["matched_alias"] == "부캉이"


def test_response_checklist_police(client, city, donggu, police, judged):
    # 경찰은 요청 받기 전에는 북항을 못 봄
    assert client.get("/api/admin/places/bukhang", headers=police).status_code == 404
    res = client.put("/api/admin/places/bukhang/response", headers=city,
                     json={"judge_day": "2026-09-20", "level": "stage3", "note": "인력 배치",
                           "request_to": ["donggu", "police_dong"]})
    assert res.status_code == 200, res.text
    out = res.json()
    assert {r["org"] for r in out["requests"]} == {"donggu", "police_dong"}
    assert all(r["status"] == "no_contact" for r in out["requests"])
    cl = out["checklist"]
    assert cl["level"] == "stage3" and cl["done"] == 0
    assert client.get("/api/admin/places/bukhang", headers=police).status_code == 200
    res = client.patch(f"/api/admin/checklists/{cl['id']}/items/staff", headers=donggu, json={"done": True})
    item = next(i for i in res.json()["items"] if i["id"] == "staff")
    assert item["done"] and item["by"] == "donggu"
    dash = client.get("/api/admin/dashboard", headers=city).json()
    assert next(p for p in dash["places"] if p["id"] == "bukhang")["response_level"] == "stage3"
    assert client.get("/api/admin/places/bukhang", headers=city).json()["checklist"]["done"] == 1
    assert client.put("/api/admin/places/bukhang/response", headers=city,
                      json={"judge_day": "2026-09-20", "level": "stage2", "request_to": ["busan"]}).status_code == 400


def test_contacts_notifications(client, city):
    assert client.put("/api/admin/contacts/donggu", headers=city,
                      json={"channel": "sms", "to": "010-0000-0000"}).status_code == 200
    assert client.put("/api/admin/contacts/ghost", headers=city,
                      json={"channel": "sms", "to": "010"}).status_code == 404
    ns = client.get("/api/admin/notifications", headers=city).json()
    assert any(n["reason"] == "request" for n in ns)
    assert "[미리봄 3단계] 북항친수공원" in ns[0]["text"]


def test_auto_notify_dedup(client, city, judged):
    from app.core.db import SessionLocal
    from app.judge.models import DailyResult
    from app.response.notify import auto_notify
    with SessionLocal() as s:
        row = s.get(DailyResult, 1)
        # 북항을 3단계로 바꿔 자동 알림을 확인 (가짜 데이터 예측은 1단계)
        payload = dict(row.payload)
        payload["장소"] = [{**p, "단계": "3단계"} if p["장소"] == "북항친수공원" else p for p in payload["장소"]]
        row.payload = payload
        s.commit()
        first = auto_notify(s, row)
        again = auto_notify(s, row)
    assert first >= 1 and again == 0


def test_visitors(client, donggu, city):
    res = client.post("/api/admin/places/bukhang/visitors", headers=donggu,
                      json={"date": "2026-09-19", "visitors": 8800, "source": "동구청 집계"})
    assert res.status_code == 201
    client.post("/api/admin/places/bukhang/visitors", headers=donggu, json={"date": "2026-09-19", "visitors": 9000})
    vs = client.get("/api/admin/places/bukhang/visitors", headers=city).json()
    assert len(vs) == 1 and vs[0]["visitors"] == 9000
    detail = client.get("/api/admin/places/bukhang", headers=city).json()
    assert detail["actual_visitors"][0]["visitors"] == 9000
    assert client.post("/api/admin/places/haeundae/visitors", headers=donggu,
                       json={"date": "2026-09-19", "visitors": 1}).status_code == 404   # 관할 밖
    assert client.post("/api/admin/places/bukhang/visitors", headers=donggu,
                       json={"date": str(date(2099, 1, 1)), "visitors": 1}).status_code == 400


def test_notices_and_sms(client, city):
    res = client.post("/api/admin/notices", headers=city, json={"title": "출입 통제", "body": "…", "place_id": "bukhang"})
    assert res.status_code == 201
    assert client.get("/api/notices").json()[0]["title"] == "출입 통제"
    fc = client.get("/api/places/bukhang/forecast").json()
    assert fc["notices"] and len(fc["days"]) == 3
    sms = client.get("/api/admin/notices/sms-draft", params={"place_id": "bukhang"}, headers=city).json()
    assert sms["text"].startswith("[부산시] 북항친수공원") and len(sms["text"]) <= 90


def test_models_and_classify(client, city, donggu):
    st = client.get("/api/admin/models", headers=city).json()
    assert st["scale"]["ready"] and "intent" in st and "threads" in st
    assert client.get("/api/admin/models", headers=donggu).status_code == 403
    res = client.post("/api/admin/intent/classify", headers=city, json={"texts": ["주말에 부캉이 보러 감"]})
    assert res.status_code in (200, 503)   # 의도 모델 가중치가 없으면 503
    assert client.post("/api/admin/intent/classify", headers=city, json={"texts": ["a"] * 21}).status_code == 400


def test_replay(client, city, donggu):
    assert client.post("/api/admin/replay", headers=donggu, json={"judge_day": "2026-09-20"}).status_code == 403
    res = client.post("/api/admin/replay", headers=city, json={"judge_day": "2026-09-20"})
    assert res.status_code == 200 and res.json()["meta"]["replay"] is True
    assert client.post("/api/admin/replay", headers=city, json={"judge_day": "2099-01-01"}).status_code == 400


def test_citizen_coords_and_nearby(client, judged):
    fc = client.get("/api/places/bukhang/forecast").json()
    assert (fc["place"]["lat"], fc["place"]["lon"]) == (35.1144199, 129.0466221)   # TourAPI 좌표
    # 부산역 근처에서 찾으면 북항이 가장 가깝고, 거리순으로 정렬됨
    hits = client.get("/api/places/search", params={"lat": 35.1152, "lon": 129.0422}).json()
    assert hits[0]["id"] == "bukhang" and hits[0]["distance_m"] < 1000
    ds = [h["distance_m"] for h in hits if h["distance_m"] is not None]
    assert ds == sorted(ds)
    assert client.get("/api/places/search").json()[0]["distance_m"] is None


def test_citizen_timeslots(client, judged):
    res = client.get("/api/places/bukhang/forecast/timeslots")
    assert res.status_code == 200, res.text
    t = res.json()
    assert t["available"] and t["method"]["stations"] == ["중앙", "부산역", "초량"]
    day = t["days"][0]
    assert [x["slot"] for x in day["slots"]] == ["morning", "lunch", "afternoon", "evening"]
    assert day["day_type"] in ("rest", "work")
    assert all(0 < x["share"] < 1 for x in day["slots"])
    # 가장 붐비는 시간대(peak_ratio=1)는 날짜별 혼잡과 같음
    daily = {d["date"]: d["crowd"] for d in client.get("/api/places/bukhang/forecast").json()["days"]}
    rank = {"free": 0, "normal": 1, "busy": 2, "very_busy": 3}
    for d in t["days"]:
        assert max(rank[x["crowd"]] for x in d["slots"]) == rank[daily[d["date"]]]
    assert client.get("/api/places/nope/forecast/timeslots").status_code == 404


def test_citizen_replay_day(client, city):
    # 재현 결과가 없는 날짜는 404 (가짜 값을 만들지 않음)
    assert client.get("/api/places/search", params={"replay_day": "2026-09-19"}).status_code == 404
    assert client.post("/api/admin/replay", headers=city, json={"judge_day": "2026-09-19"}).status_code == 200
    hits = client.get("/api/places/search", params={"replay_day": "2026-09-19"}).json()
    assert hits and hits[0]["tomorrow"]["date"] == "2026-09-20"
    fc = client.get("/api/places/bukhang/forecast", params={"replay_day": "2026-09-19"}).json()
    assert fc["meta"]["replay"] is True and fc["meta"]["judge_day"] == "2026-09-19" and fc["notices"] == []
    ts = client.get("/api/places/bukhang/forecast/timeslots", params={"replay_day": "2026-09-19"}).json()
    assert ts["meta"]["replay"] is True


def test_scenario_not_saved(client, city, donggu):
    from app.core.db import SessionLocal
    from app.judge.models import DailyResult, DailyRun
    with SessionLocal() as s:
        before = (s.query(DailyResult).count(), s.query(DailyRun).count())
    body = {"judge_day": "2026-09-21", "place_id": "bukhang", "multiplier": 2}
    assert client.post("/api/admin/scenario", headers=donggu, json=body).status_code == 403
    res = client.post("/api/admin/scenario", headers=city, json=body)
    assert res.status_code == 200, res.text
    sc = res.json()["meta"]["scenario"]
    assert sc["label"] == "가상 시나리오 · 실제 데이터 아님" and sc["assumption"] and sc["multiplier"] == 2
    assert sc["start"] == "2026-09-18"
    with SessionLocal() as s:   # 실데이터 판정 이력에 안 섞임
        assert (s.query(DailyResult).count(), s.query(DailyRun).count()) == before
    key = sc["key"]
    d = client.get("/api/admin/dashboard", headers=city, params={"scenario": key}).json()
    assert d["meta"]["scenario"]["key"] == key
    detail = client.get("/api/admin/places/bukhang", headers=city, params={"scenario": key}).json()
    assert detail["meta"]["scenario"] and detail["actual_visitors"] == [] and len(detail["trend"]) == 1
    assert client.get("/api/admin/dashboard", headers=donggu, params={"scenario": key}).status_code == 403
    fc = client.get("/api/places/bukhang/forecast", params={"scenario": key}).json()
    assert fc["meta"]["scenario"]["label"] and fc["notices"] == []
    assert client.get("/api/places/search", params={"scenario": key}).status_code == 200
    assert client.get("/api/places/search", params={"scenario": "nope"}).status_code == 404
    # 평소 조회에는 scenario가 None
    assert client.get("/api/places/search").status_code in (200, 404)
