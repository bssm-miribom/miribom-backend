# 미리봄 API 명세서 (v0.3, 구현 반영)

- 기준: 맥 `miribom-backend` (bbb374c), `miribom-ai` (e7b8d6d), `본선/기능명세/미리봄_기능명세서.md`·`화면명세서.md`·`AI모델_명세서.md`
- v0.2(`miribom-backend/docs/API.md`)에서 바뀐 점: 기능명세 P2·P3 API 추가(🆕), AI 연동 API 추가, 현재 코드와 차이 표(11장)
- 상태 표시: ✅ 구현됨 · 🆕 이번(11.17)에 새로 구현함 · 🔧 이번에 고침
- 2026-11-17 전부 구현, pytest 14개 통과 (SQLite·가짜 Redis·가짜 데이터)
- 2026-11-26 시민 좌표·시간대별 혼잡 추가 (8·12장), pytest 16개 통과
- 주소 `http(s)://<서버>/api` · Swagger `/docs` · JSON, snake_case, 날짜 `YYYY-MM-DD`, 시각 ISO 8601(+09:00)
- 인증: 관리자 API는 `Authorization: Bearer <토큰>` (12시간). 시민 API는 로그인 없음
- 오류: `{"detail": "메시지"}` · 400 입력 · 401 로그인 · 403 권한 · 404 없음 · 409 중복/실행 중 · 500 서버 · 503 설정 없음

---

## 0. 공통 값

### 권한 `org_type`
| 값 | 기관 | 조회 | 입력 |
|---|---|---|---|
| `city` | 부산시 재난안전과 | 전체 | 별칭·병목·공지·재현·실행·조치 요청 |
| `district` | 구·군청 | 관할 구 장소만 | 점검표·회신 |
| `facility` | 시설 관리기관 | `place_ids` 시설만 | 점검표·회신 |
| `police` 🆕 | 경찰 | 조치 요청 받은 장소만 (요청 때 `place_ids`에 자동 추가) | 점검표·회신 |

### 경보 단계 `stage`
| 값 | 이름 | 색 | 뜻 |
|---|---|---|---|
| `normal` | 평상 | - | 급상승 후보 아님 (목록에 안 나옴) |
| `stage1` | 1단계 급상승 후보 | 노랑 | 검색 급증 감지 (지난 1년 상위 1% 2일 연속 또는 최댓값 초과) |
| `stage2` | 2단계 사전 대비 | 주황 | 예측 범위 상단 병목 밀집도 > 1㎡당 5명 |
| `stage3` | 3단계 대응 필요 | 빨강 | 예측 중앙값 병목 밀집도 > 1㎡당 5명 |
| `pending` | 판정 보류 | 회색 | 병목·평소 방문객 값이 없어 계산 안 됨 (위험 없음 아님) |
| `failed` | 수집 실패 | 회색 | 자료 수집 오류 |

### 시민 혼잡 `crowd` [팀 확인]
| 값 | 이름 | 정하는 법 (날짜별) |
|---|---|---|
| `free` | 여유 | 평상 |
| `normal` | 보통 | 1단계·판정 보류 |
| `busy` | 붐빔 | 그날 범위 상단 밀집도 > 5 |
| `very_busy` | 매우 붐빔 | 그날 중앙값 밀집도 > 5 |
| `null` | 예보 준비 중 | 수집 실패·결과 없음 |

### `Forecast` (예측 한 칸)
```json
{"horizon": 1, "date": "2026-09-21", "low": 42000, "mid": 65000, "high": 98000,
 "density_mid": 5.9, "density_high": 8.9, "worst": 190000, "density_worst": 14.3}
```
- `low`·`mid`·`high` = 하루 방문객 하위 10%·중앙값·상위 90%
- `density_*` = 병목 밀집도(명/㎡). 판정 보류면 `null`
- `worst`·`density_worst` = 최악 시나리오(검색 배수만큼 방문 증가 가정). 참고용, 단계에 안 씀

### `JudgeMeta`
```json
{"judge_day": "2026-09-20", "generated_at": "2026-09-20T06:03:11+09:00",
 "demo": false, "replay": false, "stale": false}
```
- `stale` = 07시가 지났는데 오늘 판정이 없음 → "자료 수집 지연" 띠
- `replay` = 과거 사례 재현 결과 → 보라색 배너

### `PlaceRow` (대시보드 한 줄)
```json
{"id": "bukhang", "name": "북항친수공원", "district": "동구", "lat": 35.115, "lon": 129.045,
 "stage": "stage3", "surge_ratio": 14.2, "intent_posts": 312, "intent_ratio": 6.1,
 "d1": {Forecast}, "bottleneck_name": "해상육교 진입로",
 "is_new": true, "new_alias": "부캉이", "reason": "2026-09-21 예측 중앙값 밀집도 5.9명/㎡ > 5",
 "worst_case": "검색이 늘어난 만큼 방문도 늘면 …", "missing": [], "response_level": null}
```
- `intent_posts`·`intent_ratio` 🆕: 어제 가볼래 글 수, 평소(28일 중앙값) 대비 배수. 분류 결과 없으면 `null`
- `missing` 🆕: 판정 보류일 때 빠진 값 (`bottleneck_m2`, `peak_share`, `bottleneck_share`, `base_rest`, `base_work`) → A-09
- `response_level` 🆕: 부산시가 정한 대응 수준 (5장), 없으면 `null`

---

## 1. 상태·인증 (A-15)

| 상태 | 메서드 | 경로 | 권한 | 설명 |
|---|---|---|---|---|
| ✅ | GET | `/health` | 없음 | 서버·DB·Redis 상태, `next_daily_run` |
| ✅ | POST | `/auth/login` | 없음 | `{"username","password"}` → `{"access_token","token_type","account"}` |
| ✅ | GET | `/auth/me` | 로그인 | `account` = `{"username","org_name","org_type","district","can_edit"}` |

- 로그인 실패 401 `"아이디 또는 비밀번호가 맞지 않음"`
- `can_edit` = 부산시만 true

---

## 2. 관리자 대시보드 (A-01~A-05, A-09)

### ✅ GET `/admin/dashboard?judge_day=&replay=`
- 지도·요약 줄용. `normal` 뺀 전체 단계
- 응답 `{"meta": JudgeMeta, "summary": {"stage3","stage2","stage1","pending"}, "places": [PlaceRow]}`
- 정렬: 단계 높은 순 → 급증 배수 높은 순. 관할 밖 장소 빠짐
- `replay=true`는 부산시만 (403). 결과 없으면 404

### ✅ GET `/admin/dashboard/rising?judge_day=&replay=&stage=`
- A-03 표. 3·2단계만. `stage=stage3|stage2` 필터
- 응답 `{"meta", "summary": {"stage3","stage2"}, "places": [PlaceRow + "stage_label"]}`
- 없으면 `places: []` → "오늘 급상승 장소 없음"

### 🔧 GET `/admin/places/{id}?judge_day=&replay=` (A3 장소 상세)
```json
{"meta": {JudgeMeta},
 "place": {"id", "name", "district", "aliases": ["부캉이"]},
 "stage": "stage3", "reason": "…", "worst_case": null, "missing": [],
 "surge": {"ratio": 14.2, "top1pct": 1.33, "year_max": 1.36, "reason": "상위 1%(1.33배) 2일 연속"},
 "intent": {"posts": 312, "ratio": 6.1, "model": "kcelectra-v1"},
 "trend": [{"date": "2026-09-14", "surge_ratio": 1.02, "intent_posts": 40}],
 "actual_visitors": [{"date": "2026-09-19", "visitors": 8800, "source": "동구청 회신"}],
 "forecasts": [{Forecast} ×3],
 "bottleneck": {"name", "area_m2": 600, "limit_per_m2": 5.0, "limit_visitors": 66667, "estimated": true},
 "weather_source": "Open-Meteo",
 "checklist": {ChecklistSummary}}
```
- `trend`: 최근 7일. 날짜는 자료 기준일(D-1)
- `actual_visitors`: 6장 회신값. 지금은 빈 배열
- 🆕 `intent`, `missing`, `checklist`, `trend[].intent_posts`

### ✅ GET `/admin/places`
- 별칭·병목 입력용 장소 목록 `[{"id","name","district","aliases"}]` (관할 안만)

---

## 3. 장소 정보 입력 (A-06, A-08) — 부산시만

| 상태 | 메서드 | 경로 | 설명 |
|---|---|---|---|
| ✅ | GET | `/admin/aliases` | 별칭 목록 |
| ✅ | POST | `/admin/aliases` | `{"alias","place_id"}` → 201 `{"id","alias","place_id","created_at","applies_from"}`. 중복 409 |
| ✅ | DELETE | `/admin/aliases/{id}` | 204 |
| 🆕 | PUT | `/admin/places/{id}/bottleneck` | A-08 병목 구간 지정 |
| 🆕 | PATCH | `/admin/places/{id}` | 평소 방문객·검색어·감시 고정 수정 |
| 🆕 | POST | `/admin/places` | 새 장소 추가 (부캉이처럼 목록에 없는 곳) |

- 별칭: 등록 즉시 대시보드 1단계 표시, 다음 06시 판정부터 검색어 반영. 재현은 판정일 07시 전 별칭만

### 🆕 PUT `/admin/places/{id}/bottleneck`
요청
```json
{"name": "해상육교 진입로", "polygon": [[129.045, 35.115], [129.046, 35.115], …],
 "peak_share": 0.15, "bottleneck_share": 0.3}
```
응답 `{"id", "bottleneck": {"name","area_m2": 612.4,"limit_visitors": 68044,"estimated": true}, "applies_from": "2026-09-21"}`
- `area_m2`는 서버가 다각형(경위도)에서 계산. `area_m2`를 직접 보내도 됨 (다각형 없을 때)
- `peak_share`·`bottleneck_share` 빼면 기존 값 유지. 기존 값도 없으면 판정 보류 유지
- DB 열 추가: `bottleneck_polygon`(JSON)

### 🆕 PATCH `/admin/places/{id}`
요청 (보낸 칸만 바꿈) `{"keywords": ["광안리","광안리해수욕장"], "base_rest": 30000, "base_work": 12000, "force_watch": true, "note": "…"}`
- 응답: 바뀐 장소 전체. 다음 판정부터 반영

### 🆕 POST `/admin/places`
요청 `{"id": "bukhang2", "name": "…", "district": "동구", "lat": …, "lon": …, "keywords": ["…"]}`
- 201. 중복 이름·id 409. 평소 방문객·병목이 없으면 급증 시 판정 보류로 나옴

---

## 4. 판정 실행·재현 (S-01~S-05, A-07)

| 상태 | 메서드 | 경로 | 권한 | 설명 |
|---|---|---|---|---|
| ✅ | POST | `/admin/run` | 부산시 또는 `X-Admin-Token` | 오늘 판정 지금 실행 → 대시보드 응답 |
| ✅ | POST | `/admin/replay` | 부산시 | `{"judge_day","force"}` → 그날 재현 대시보드 응답. 미래 날짜 400 |
| 🆕 | GET | `/admin/runs?limit=20` | 부산시 | 판정 실행 기록 (실패·의도 수집 결과 포함) |

- 실행 중이면 409 `"판정 작업이 이미 실행 중임"` (Redis 잠금 30분)
- 매일 06:00 KST 자동 실행 (APScheduler, 서버 안). 07시가 지나도 없으면 `stale`

### 🆕 GET `/admin/runs`
```json
[{"id": 41, "judge_day": "2026-09-20", "replay": false, "demo": false,
  "created_at": "…", "places": 18, "failed": 0, "trigger": "schedule"}]
```
- 실제 응답 칸: `id, trigger(schedule·manual·replay), judge_day, status(running·ok·failed), result_id, places, failed, intent, error, started_at, finished_at`

---

## 5. 대응 (A-10~A-12, B-01, B-03) 🆕 P2

### 🆕 PUT `/admin/places/{id}/response` (부산시, A-11)
요청 `{"judge_day": "2026-09-20", "level": "stage3", "note": "해상육교 인력 배치", "request_to": ["donggu", "police_dong"]}`
응답 `{"id": 7, "level", "decided_by": "busan", "decided_at", "requests": [{"org","status": "sent"}]}`
- `level`은 경보 단계와 별개로 사람이 정한 대응 수준 (`none`·`stage1`~`stage3`)
- `request_to`에 넣은 기관에 알림(B-01) 발송 + 점검표 생성

- GET `/admin/places/{id}/response?judge_day=` : 그날 결정 기록 (최근 순)
- 단계를 바꾸면 새 점검표를 만들고, 같은 항목의 체크는 이어받음

### 🆕 GET `/admin/checklists?place_id=&judge_day=` · PATCH `/admin/checklists/{id}/items/{item_id}`
```json
{"id": 3, "place_id": "bukhang", "judge_day": "2026-09-20", "level": "stage3",
 "items": [{"id": "staff", "label": "병목 통로 인력 배치", "done": true, "by": "donggu", "at": "…"},
           {"id": "route", "label": "동선 안내 표지", "done": false, "by": null, "at": null},
           {"id": "close", "label": "출입 통제 검토", "done": false, "by": null, "at": null}]}
```
- PATCH 요청 `{"done": true}` → 담당자·시각 자동 기록
- 항목은 단계별 기본 목록(서버 상수). 관할 기관만 체크 가능
- `ChecklistSummary` = `{"id","done": 1,"total": 3}` (장소 상세에 붙음)

### 🆕 경보 알림 (A-12, B-01)
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/admin/notifications?judge_day=` | 보낸 알림 기록 `[{"place_id","org","channel","stage","sent_at","status"}]` |
| GET | `/admin/contacts` | 기관별 받는 곳 목록 (부산시) |
| PUT | `/admin/contacts/{org}` | 기관별 받는 곳 `{"channel": "sms|kakao|email", "to": "…"}` (부산시) |

- 06시 판정 뒤 **2단계 이상 새로 오른 장소**만 관할 기관에 자동 발송 (같은 날 같은 단계 중복 없음)
- 문안: `"[미리봄 3단계] 북항친수공원 · 내일 예상 4.2만~9.8만 명 · 병목 1㎡당 5.9명 · 점검표: <링크>"`. 판정 보류면 빠진 자료 덧붙임
- `status`: `dry_run`(받는 곳 있음, 기록만) · `no_contact`(받는 곳 없음) · `sent`·`failed`(실제 발송 붙인 뒤). `reason`: `auto`(06시) · `request`(조치 요청)
- `NOTIFY_MODE=dry_run`(기본). 실제 발송은 `response/notify.py`의 `send()`만 바꾸면 됨 [팀 확인: 발송 수단·비용]

---

## 6. 실측 회신 (A-14, B-04) 🆕 P3

| 메서드 | 경로 | 권한 | 설명 |
|---|---|---|---|
| POST | `/admin/places/{id}/visitors` | 관할 기관 | `{"date","visitors","source","note"}` → 201 |
| GET | `/admin/places/{id}/visitors?date_from=&date_to=` | 관할 기관 | 회신 목록 → 장소 상세 `actual_visitors` (판정일 전날까지, 최근 30일) |

- 같은 날짜·기관 재입력은 덮어씀. 회신값은 규모 예측 재학습 자료로만 쓰고, 그날 판정에는 안 넣음 (누수 방지)

---

## 7. 공지 (A-13, C-05)

| 상태 | 메서드 | 경로 | 권한 | 설명 |
|---|---|---|---|---|
| ✅ | GET | `/notices` | 없음 | 지금 보이는 공지 |
| ✅ | POST | `/admin/notices` | 부산시 | `{"title","body","place_id"?,"ends_at"?}` → 201 |
| ✅ | DELETE | `/admin/notices/{id}` | 부산시 | 204 |
| 🆕 | GET | `/admin/notices/sms-draft?place_id=` | 부산시 | 안전 안내 문자 검토용 문안 `{"text": "…"}` (90자 안) |

---

## 8. 시민 (C-01~C-05) — 로그인 없음

### 🔧 GET `/places/search?q=&lat=&lon=`
```json
[{"id": "bukhang", "name": "북항친수공원", "district": "동구", "lat": 35.115, "lon": 129.045,
  "distance_m": 312, "matched_alias": "부캉이",
  "tomorrow": {"date": "2026-09-21", "crowd": "very_busy", "label": "매우 붐빔"}}]
```
- 이름·별칭 부분 일치. `q` 비면 전체. 없으면 `[]`
- 🆕 `lat`·`lon`: 장소 좌표(WGS84). 없으면 `null`
- 🆕 `lat`·`lon` 쿼리(내 위치)를 둘 다 주면 `distance_m`(직선 거리, m)을 붙이고 **가까운 순** 정렬, 좌표 없는 장소는 맨 뒤. 안 주면 `distance_m: null`, 가나다순
- 위치를 서버에 보내기 싫으면 쿼리 없이 받아서 프론트에서 `lat`·`lon`으로 정렬해도 됨 (서버는 위치를 저장 안 함)

### 🔧 GET `/places/{id}/forecast`
```json
{"meta": {JudgeMeta}, "place": {"id","name","district","lat","lon"},
 "days": [{"date","crowd","label"} ×3], "least_crowded": "2026-09-23",
 "notices": [], "disclaimer": "예측에 기반한 추정치이며 실제와 다를 수 있음 · 매일 07시 갱신"}
```
- 단계·급증 배수·의도 글 수는 안 내보냄. 재현 결과 안 씀. 3일 다 같으면 `least_crowded: null`
- 🆕 `place`에 `lat`·`lon` 추가

### 🆕 GET `/places/{id}/forecast/timeslots`
```json
{"meta": {JudgeMeta}, "place": {"id","name","district","lat","lon"}, "available": true,
 "days": [{"date": "2026-09-21", "day_type": "rest",
           "slots": [{"slot": "morning", "label": "오전", "start": "09:00", "end": "12:00",
                      "share": 0.174, "crowd": "busy", "crowd_label": "붐빔"},
                     {"slot": "lunch", "label": "점심", "start": "12:00", "end": "14:00", "share": 0.147, "crowd": "very_busy", "crowd_label": "매우 붐빔"},
                     {"slot": "afternoon", "label": "오후", "start": "14:00", "end": "18:00", "share": 0.314, "crowd": "very_busy", "crowd_label": "매우 붐빔"},
                     {"slot": "evening", "label": "저녁", "start": "18:00", "end": "22:00", "share": 0.224, "crowd": "very_busy", "crowd_label": "매우 붐빔"}],
           "least_crowded_slot": "morning"} ×3],
 "method": {"source": "공공데이터포털 3057229 부산교통공사 도시철도 역별 시간대별 승하차 (하차)",
            "period": ["2024-01-01", "2026-09-30"], "stations": ["중앙", "부산역", "초량"],
            "note": "도시철도 하차 실측 비율로 나눈 추정치. 역 하차에는 통근·환승 이용객도 섞임"},
 "disclaimer": "…"}
```
- 시간대 4개 고정: 오전 09–12 · 점심 12–14 · 오후 14–18 · 저녁 18–22
- `day_type`: `rest`(주말·공휴일, `holidays` 패키지 KR) / `work`. 비율표를 이걸로 고름
- `share`: 하루 방문객 중 그 시간대 도착 비중 (22–09시는 빠져서 4개 합 < 1). 막대 높이용
- `crowd`: 날짜별 `crowd`와 같은 4단계. `least_crowded_slot`: 가장 덜 붐비는 시간대, 다 같으면 `null`
- `available: false`: 비율표가 없는 장소(새로 추가한 장소 등) → `days: []`. 판정 결과가 없을 때도 `days: []`
- 방문객 수(명)는 시민 API 원칙대로 안 내보냄

#### 시간대 혼잡 계산 (근거)
1. 장소별 가까운 역(`miribom_ai.alert.peak_share.STATIONS`, `places.csv` peak_share와 같은 대응) 하차 인원을 날짜·시간별로 합침
2. 날짜마다 하루 합으로 나눠 시간별 비율 → 휴일·평일별 **시간별 중앙값** → 합 1로 다시 나눔
3. `peak_ratio` = 그 시간대 가장 붐빈 1시간 ÷ 09–22시 중 가장 붐빈 1시간 (07–09시 출근 하차는 기준에서 뺌)
4. 시간대 밀집도 = 그날 예측 밀집도(중앙값·상단) × `peak_ratio` → 날짜별과 같은 기준(1㎡당 5명)으로 4단계
   - 그래서 가장 붐비는 시간대 = 날짜별 혼잡과 같고, 나머지는 그보다 같거나 낮음
- 표 다시 만들기: `python3 scripts/build_time_profile.py` → `app/citizen/time_profile.json` (원본 CSV는 커밋 안 함)
- 한계 [팀 확인]: 역 하차 ≠ 장소 방문 (북항은 부산역 이용객, 평일 09시대는 통근 섞임). 흰여울은 역이 없어 남포역 대리. 도착 시각 기준이라 머무는 시간 미반영. 시간대별 실측 방문객으로 검증 안 함

#### 휴일 비율표 (2024-01~2026-09, share / peak_ratio)
| 장소 | 역 | 오전 | 점심 | 오후 | 저녁 |
|---|---|---|---|---|---|
| 북항친수공원 | 중앙·부산역·초량 | 0.174 / 0.76 | 0.147 / 0.90 | 0.314 / 1.00 | 0.224 / 0.87 |
| 광안리해수욕장 | 광안·금련산 | 0.133 / 0.55 | 0.149 / 0.76 | 0.374 / 1.00 | 0.257 / 0.88 |
| 해운대해수욕장 | 해운대·중동 | 0.179 / 0.84 | 0.155 / 0.95 | 0.328 / 1.00 | 0.215 / 0.80 |
| 감천문화마을 | 토성 | 0.209 / 0.96 | 0.137 / 0.96 | 0.272 / 1.00 | 0.189 / 0.77 |
| 흰여울문화마을 | 남포(대리) | 0.229 / 0.94 | 0.205 / 1.00 | 0.336 / 0.93 | 0.140 / 0.53 |
- 평일 값은 `app/citizen/time_profile.json`

#### 장소 좌표 출처
- 한국관광공사 TourAPI 국문 관광정보(`KorService2/searchKeyword2`)의 `mapy`(위도)·`mapx`(경도), 2026-11-26 조회. `app/core/seed.py` `TOUR_COORDS`

| 장소 | TourAPI 이름 (contentid) | 위도 | 경도 | 옛 places.csv와 차이 |
|---|---|---|---|---|
| 북항친수공원 | 부산북항 친수공원 (3426656) | 35.1144199 | 129.0466221 | 161m |
| 광안리해수욕장 | 광안리해수욕장 (126078) | 35.1531933 | 129.1189761 | 34m |
| 해운대해수욕장 | 해운대해수욕장 (126081) | 35.1590840 | 129.1602786 | 44m |
| 감천문화마을 | 부산 감천문화마을 (1997221) | 35.0974607 | 129.0105970 | 4m |
| 흰여울문화마을 | 흰여울문화마을 (2684712) | 35.0798897 | 129.0435396 | 216m |
- 새 DB는 처음 넣을 때 이 값을 씀. 이미 있는 DB는 서버 시작 때 좌표가 places.csv 옛 값 그대로인 장소만 바꿈 (관리자가 `PATCH /admin/places/{id}`로 고친 값은 유지)
- 좌표는 장소 대표 지점 하나임 (해변·마을 전체 영역 아님). 새로 추가하는 장소는 관리자 입력값을 씀

---

## 9. AI 연동

### 구조 (HTTP 아님, 서버 안에서 불러씀)
```
06:00 APScheduler → runtime.write_places(DB → places.csv)
  → [🆕 의도] Threads 수집 → miribom_ai.count_intent(posts) → data/intent_counts.csv
  → miribom_ai.run_daily(judge_day, demo, save=False)
       급증 탐지 → 규모 예측(LightGBM, D+1~3) → 경보 판정
  → daily_results(payload JSON) 저장 → Redis latest 캐시
```
- 모델 파일: `MIRIBOM_HOME/models/` (규모 `scale_h{1,2,3}_*.txt`, 의도 `intent/` 약 500MB, git 밖이라 서버에 따로 복사)
- 규모 모델 없으면 운영 판정은 `ModelMissing` → 500. `demo=true`일 때만 가짜 데이터로 즉석 학습

### `run_daily` 결과 → API 필드 대응
| payload (한글 키) | API |
|---|---|
| `판정일`, `생성 시각`, `가짜 데이터` | `meta.judge_day`, `meta.generated_at`, `meta.demo` |
| `장소[].단계`, `이유` | `stage`, `reason` |
| `장소[].급증.오늘 배수`, `상위 기준`, `1년 최대`, `이유` | `surge_ratio`, `surge.top1pct`, `surge.year_max`, `surge.reason` |
| `장소[].예측.{h}.하위10·중앙값·상위90·최악·날짜` | `Forecast.low·mid·high·worst·date` |
| `장소[].밀집도.{날짜}.중앙값·상위90·최악` | `Forecast.density_mid·density_high·density_worst` |
| `장소[].최악 시나리오` | `worst_case` |
| `장소[].날씨 출처` | `weather_source` |
| 🆕 `장소[].의도.어제 글 수`, `평소 대비` | `intent_posts`, `intent_ratio` |
| 🆕 `장소[].빠진 값` | `missing` |

### 🆕 GET `/admin/models` (부산시)
```json
{"scale": {"ready": true, "demo": false, "trained_at": "2026-10-31", "features": ["…"], "surge_elasticity": 1.0,
           "metrics": {"d1_wape": 0.077, "d1_coverage": 0.706, "baseline_prev_day": 0.173, "baseline_weekday": 0.089}},
 "intent": {"ready": false, "name": "beomi/KcELECTRA-base-v2022", "threshold": 0.6, "trained_at": "2026-10-25",
            "metrics": null, "labelers": null, "reason": "모델 가중치 파일 없음 (models/intent/model.safetensors)"},
 "intent_counts": {"ready": false, "last_date": null},
 "surge": {"ready": true, "method": "통계 (지난 1년 상위 1% 2일 연속 또는 1년 최댓값 초과)"},
 "threads": {"collect": false, "token": false, "note": "keyword_search 앱 심사 전에는 내 글만 검색됨"}}
```
- `miribom_ai.model_status()`가 `models/`·`results/` 파일만 읽음 (무거운 라이브러리 안 불러옴)
- 의도 모델 성능(`metrics`)은 다음 학습부터 `threshold.json`에 저장됨

### 🆕 POST `/admin/intent/classify` (부산시, 시연용)
요청 `{"texts": ["이번 주말에 부캉이 보러 갈 거임", "부캉이 뉴스 봤음"]}`
응답 `{"results": [{"label": "가볼래", "score": 0.93}, {"label": "그냥 언급", "score": 0.12}], "model": "kcelectra-v1"}`
- 한 번에 최대 20문장. 입력 문장은 저장 안 함. 모델 없으면 503
- 첫 호출 때 모델을 불러와 메모리에 둠 (2vCPU·4GB 서버라 응답 시간 확인 필요 [팀 확인])

---

## 10. Threads 콜백·기타

| 상태 | 경로 | 설명 |
|---|---|---|
| ✅ | POST `/api/threads/deauthorize` | 연결 해제 (signed_request) |
| ✅ | POST `/api/threads/delete` · GET `/api/threads/delete/{code}` | 데이터 삭제 요청·상태 |
| ✅ | GET `/privacy` | 개인정보처리방침 |
| ✅ | GET `/threads/start·login·callback·demo·logout` | Meta 심사 녹화용 화면 (prefix 없음) |

---

## 11. 구현 결과 (2026-11-17)

| # | 내용 | 결과 |
|---|---|---|
| 1 | `intent_posts` null 고정 | 고침. AI 결과에 `의도`(어제 글 수·평소 대비) 추가 → `intent_posts`·`intent_ratio` |
| 2 | 옛 `routers/alerts.py` | 삭제 |
| 3 | 판정 보류 빠진 값 | AI 결과 `빠진 값` → `missing` |
| 4 | 06시 의도 수집 | `miribom_ai.intent.daily` + 서버 `INTENT_COLLECT` (Threads 장기 토큰·의도 모델 있어야 실제로 돎) |
| 5 | 병목·장소 수정·추가 | 구현 (`places/`) |
| 6 | 대응·점검표·알림 | 구현 (`response/`), 알림은 기록만 |
| 7 | 실측 회신 | 구현 |
| 8 | 실행 기록 | 구현 (`daily_runs`) |
| 9 | 모델 상태·의도 분류 | 구현 (`ai/`). 의도 모델 가중치가 맥에 없어서 지금은 503 |
| 10 | 안전 문자 문안 | 구현 |
| 11 | 경찰 권한 | 구현, 시연 계정 `police_dong` |
| 12 | 문서 | `miribom-backend/docs/API.md` 교체 |

- 백엔드 폴더를 기능별로 나눔: `core/ auth/ dashboard/ places/ judge/ response/ notices/ citizen/ ai/ threads/ health/`

## 12. 시민 좌표·시간대 추가 (2026-11-26)

| # | 내용 | 결과 |
|---|---|---|
| 1 | 시민 검색·예보 응답에 `lat`·`lon` | 추가 (TourAPI 공식 좌표로 교체). 검색에 `lat`·`lon` 쿼리 주면 `distance_m` + 가까운 순 |
| 2 | 시간대별 예측 | `GET /places/{id}/forecast/timeslots` 추가 (도시철도 하차 실측 비율) |

## 팀 확인 필요
- 시간대 구간(오전 09–12 등)과 역↔장소 대응, miribom-ai `places.csv` 좌표도 TourAPI 값으로 맞출지
- 시민 혼잡 4단계 기준, 알림 발송 수단(문자·카카오)·비용
- 대응 점검표 기본 항목, 경찰 계정 범위
- 의도 분류 서버 응답 시간 (CPU 전용 torch)
