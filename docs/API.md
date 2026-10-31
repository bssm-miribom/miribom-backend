# 미리봄 API 명세서 (v0.2)

- 기준: 미리봄_기능명세서.md, 미리봄_화면명세서.md (MVP), miribom-ai `run_daily()` 결과 형식
- 주소: `http://localhost:8000/api` · 실제 동작 확인은 `/docs` (Swagger)
- 형식: JSON, 필드 이름은 영어 snake_case, 날짜는 `YYYY-MM-DD`, 시각은 ISO 8601(+09:00)
- 인증: 관리자 API는 `Authorization: Bearer <토큰>` (로그인으로 받음). 시민 API는 로그인 없음
- 오류: `{"detail": "사람이 읽는 메시지"}` + 상태 코드 (400 입력 오류, 401 로그인 필요, 403 권한 없음, 404 없음, 409 중복, 500 서버)

## 0. 공통 값

### 경보 단계 `stage`
| 값 | 화면 이름 | 색 | 뜻 |
|---|---|---|---|
| `normal` | 평상 | - | 급상승 후보 아님 (목록에 안 나옴) |
| `stage1` | 1단계 급상승 후보 | 노랑 | 검색 급증 감지 |
| `stage2` | 2단계 사전 대비 | 주황 | 예측 범위 상단 밀집도 > 1㎡당 5명 |
| `stage3` | 3단계 대응 필요 | 빨강 | 예측 중앙값 밀집도 > 1㎡당 5명 |
| `pending` | 판정 보류 | 회색 | 병목 구간·평소 방문객 값이 없어 계산 안 됨 |
| `failed` | 수집 실패 | 회색 | 자료 수집 오류 |

### 시민 혼잡 `crowd` (C-02) [팀 확인]
| 값 | 이름 | 색 | 정하는 법 (날짜별) |
|---|---|---|---|
| `free` | 여유 | 초록 | 급상승 후보 아님 |
| `normal` | 보통 | 노랑 | 1단계 또는 판정 보류 |
| `busy` | 붐빔 | 주황 | 그날 예측 범위 상단 밀집도 > 5 |
| `very_busy` | 매우 붐빔 | 빨강 | 그날 예측 중앙값 밀집도 > 5 |
| `null` | 예보 준비 중 | 회색 | 수집 실패 또는 판정 결과 없음 |

### 예측 한 칸 `Forecast`
```json
{"horizon": 1, "date": "2026-09-21", "low": 42000, "mid": 65000, "high": 98000,
 "density_mid": 5.9, "density_high": 8.9, "worst": 190000, "density_worst": 14.3}
```
- `low`·`mid`·`high` = 하루 방문객 하위 10% · 중앙값 · 상위 90%
- `density_*` = 병목 밀집도(명/㎡). 판정 보류 장소는 `null`
- `worst`·`density_worst` = **최악 시나리오** (참고용): 검색이 평소의 N배면 방문도 N배라고 가정한 값. 실측(도시철도 하차)과 맞지 않는 가정이라 경보 단계에는 안 씀. 급증이 아닌 장소·예전 판정 결과는 `null`
- 화면 문구 예: "최악 시나리오(검색 증가만큼 방문 증가 가정) 19만 명"

### 판정 메타 `JudgeMeta` (대시보드·시민 화면 공통 헤더)
```json
{"judge_day": "2026-09-20", "generated_at": "2026-09-20T06:03:11+09:00",
 "demo": false, "replay": false, "stale": false}
```
- `stale: true` = 오늘 판정이 아직 없어 지난 판정을 보여주는 중 (화면: "자료 수집 지연" 띠)
- `replay: true` = 과거 사례 재현 결과 (화면: 보라색 재현 배너)

---

## 1. 상태

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/health` | 서버·DB·Redis 상태, 다음 06시 실행 시각 |

## 2. 인증 (A1, A-15)

### POST `/auth/login`
요청 `{"username": "busan", "password": "..."}`
응답
```json
{"access_token": "eyJ...", "token_type": "bearer",
 "account": {"username": "busan", "org_name": "부산시 재난안전과", "org_type": "city",
             "district": null, "can_edit": true}}
```
- 실패 401 `"아이디 또는 비밀번호가 맞지 않음"`
- `org_type`: `city`(부산시, 전체 조회·입력) · `district`(구·군청, 관할 구만) · `facility`(시설 관리기관, 관리 시설만)
- `can_edit`: 별칭 등록·재현·공지 가능 여부 (부산시만 true)
- 토큰 유효 12시간

### GET `/auth/me`
- 응답: 위 `account`

## 3. 관리자 대시보드 (A2·A3·A4)

### GET `/admin/dashboard?judge_day=&replay=`
- 기본: 가장 최근 판정 (재현 제외). `judge_day`를 주면 그날 결과, `replay=true`면 그날 재현 결과
- 계정 관할 밖 장소는 빠짐
```json
{"meta": {JudgeMeta},
 "summary": {"stage3": 1, "stage2": 1, "stage1": 2, "pending": 1},
 "places": [
   {"id": "bukhang", "name": "북항친수공원", "district": "동구", "lat": 35.115, "lon": 129.045,
    "stage": "stage3", "surge_ratio": 14.2, "intent_posts": 312,
    "d1": {Forecast}, "bottleneck_name": "해상육교 진입로",
    "is_new": true, "new_alias": "부캉이", "reason": "2026-09-21 예측 중앙값 밀집도 5.9명/㎡ > 5",
    "worst_case": "검색이 늘어난 만큼 방문도 늘면 2026-09-24 밀집도 14.3명/㎡ (실측으로 확인 안 된 가정)"}
 ]}
```
- `worst_case`: 최악 시나리오 밀집도가 1㎡당 5명을 넘을 때만 문장, 아니면 `null`. 단계와 별개로 "주의" 표시용
- `places`는 `normal` 빼고 단계 높은 순 → 급증 배수 높은 순 (A-03 기본 정렬)
- `intent_posts`: 방문 의도 분류 전이라 지금은 `null` (Threads 승인 후)
- `is_new`: 전날 판정에서 평상이었다가 이번에 올라온 장소, 또는 판정 뒤 새 별칭이 등록된 장소
- 별칭을 막 등록한 평상 장소는 `stage1`, `reason: "신규 별칭 '부캉이' 등록 · 다음 판정부터 반영"`으로 바로 나옴 (A-06)

### GET `/admin/dashboard/rising?judge_day=&replay=&stage=`
A-03 급상승 장소 목록 (A2 오른쪽 표). **3단계·2단계만** 나옴. 1단계·판정 보류·수집 실패는 빠짐 (지도·요약 줄은 `/admin/dashboard` 사용)
- `judge_day`·`replay`: `/admin/dashboard`와 같음
- `stage`: `stage3` 또는 `stage2`를 주면 그 단계만 (요약 줄 단계 누름 필터). 비우면 둘 다
```json
{"meta": {JudgeMeta},
 "summary": {"stage3": 1, "stage2": 1},
 "places": [
   {"id": "bukhang", "name": "북항친수공원", "district": "동구", "lat": 35.115, "lon": 129.045,
    "stage": "stage3", "stage_label": "3단계 대응 필요", "surge_ratio": 14.2, "intent_posts": null,
    "d1": {Forecast}, "bottleneck_name": "해상육교 진입로",
    "is_new": true, "new_alias": "부캉이", "reason": "2026-09-21 예측 중앙값 밀집도 5.9명/㎡ > 5"}
 ]}
```
- 표 칸 대응: 장소 `name` / 단계 `stage_label` / 급증 배수 `surge_ratio` / 방문 의도 글 `intent_posts` / D+1 예상 방문객 `d1.mid`(`d1.low`~`d1.high`) / 예상 병목 밀집도 `d1.density_mid`
- 정렬: 단계 높은 순 → 급증 배수 높은 순. `summary`는 `stage` 필터와 상관없이 3·2단계 전체 수
- 계정 관할 밖 장소는 빠짐. 해당 장소가 없으면 `places: []` → 화면 "오늘 급상승 장소 없음"
- 판정 결과가 아예 없으면 404 (`/admin/dashboard`와 같음)

### GET `/admin/places/{id}?judge_day=&replay=`
A3 장소 상세
```json
{"meta": {JudgeMeta},
 "place": {"id": "bukhang", "name": "북항친수공원", "district": "동구", "aliases": ["부캉이"]},
 "stage": "stage3", "reason": "…", "surge": {"ratio": 14.2, "top1pct": 1.33, "year_max": 1.36, "reason": "상위 1%(1.33배) 2일 연속"},
 "trend": [{"date": "2026-09-14", "surge_ratio": 1.02}, …],
 "actual_visitors": [],
 "forecasts": [{Forecast}, {Forecast}, {Forecast}],
 "bottleneck": {"name": "해상육교 진입로", "area_m2": 600, "limit_per_m2": 5.0,
                "limit_visitors": 66667, "estimated": true},
 "weather_source": "Open-Meteo"}
```
- `trend`: 판정일 기준 최근 7일 급증 배수. 저장된 날마다 판정 결과에서 모음 (같은 모드끼리: 운영은 운영, 재현은 재현)
- `actual_visitors`: 장소별 실측 자료가 없어서 지금은 빈 배열 → 화면 "실측 자료 없음"
- `bottleneck.limit_visitors`: 병목 기준(1㎡당 5명)을 하루 방문객으로 바꾼 값 (그래프 2 가로선). 보류 장소는 `null`
- `bottleneck.estimated: true` = 체류 비중이 현장 확인 전 추정치

### GET `/admin/places`
- 별칭 등록 때 고를 장소 목록 `[{"id", "name", "district", "aliases": [...]}]` (관할 안만)

### POST `/admin/aliases` (부산시만)
요청 `{"alias": "부캉이", "place_id": "bukhang"}`
응답 201 `{"id": 1, "alias": "부캉이", "place_id": "bukhang", "created_at": "…", "applies_from": "2026-09-21"}`
- 이미 쓰는 별칭(장소 이름 포함) 409 `"이미 등록된 별칭"`
- 등록한 별칭은 다음 판정부터 검색어에 들어감. 재현할 때는 그 판정일 07시 전에 등록된 별칭만 씀 (미래 정보 차단)

### GET `/admin/aliases` · DELETE `/admin/aliases/{id}` (부산시만)

### POST `/admin/replay` (부산시만, A-07)
요청 `{"judge_day": "2026-09-20"}`
- 그날 07시까지 받을 수 있던 자료로 판정을 다시 돌림 (몇십 초 걸릴 수 있음)
- 응답: 그날 재현 결과로 만든 `GET /admin/dashboard` 응답과 같은 형식
- 이미 돌린 날짜는 다시 돌리지 않고 저장된 결과를 줌. `"force": true`면 다시 돌림

### POST `/admin/run` (부산시만)
- 06시를 기다리지 않고 오늘 판정을 지금 실행. 응답: `GET /admin/dashboard`와 같은 형식

## 4. 공지 (A-13, C-05)

| 메서드 | 경로 | 권한 | 설명 |
|---|---|---|---|
| GET | `/notices` | 없음 | 지금 보이는 공지 `[{"id","title","body","place_id","created_at","ends_at"}]` |
| POST | `/admin/notices` | 부산시 | `{"title", "body", "place_id"(선택), "ends_at"(선택)}` |
| DELETE | `/admin/notices/{id}` | 부산시 | 내림 |

## 5. 시민 (C1·C2)

### GET `/places/search?q=부캉이`
```json
[{"id": "bukhang", "name": "북항친수공원", "district": "동구", "matched_alias": "부캉이",
  "tomorrow": {"date": "2026-09-21", "crowd": "very_busy", "label": "매우 붐빔"}}]
```
- 장소 이름·별칭 부분 일치. `q`가 비면 전체 (가나다순)
- 결과 없으면 빈 배열 → 화면 "아직 예보가 없는 장소임"

### GET `/places/{id}/forecast`
```json
{"meta": {JudgeMeta},
 "place": {"id": "bukhang", "name": "북항친수공원", "district": "동구"},
 "days": [{"date": "2026-09-21", "crowd": "very_busy", "label": "매우 붐빔"}, …3개],
 "least_crowded": "2026-09-23",   // 3일이 다 같은 단계면 null
 "notices": [ … ],
 "disclaimer": "예측에 기반한 추정치이며 실제와 다를 수 있음 · 매일 07시 갱신"}
```
- 경보 단계·급증 배수·방문 의도 글 수는 시민 응답에 넣지 않음
- 재현 결과는 시민 화면에 안 씀 (항상 최신 운영 판정)

## 6. Threads 콜백, 기타

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/threads/deauthorize` | Threads 연결 해제 (signed_request) |
| POST | `/threads/delete` | 데이터 삭제 요청 → `{"url", "confirmation_code"}` |
| GET | `/threads/delete/{code}` | 삭제 요청 상태 |
| GET | `/privacy` (prefix 없음) | 개인정보처리방침 |
| GET | `/threads/start` (prefix 없음) | Threads 연결 안내 화면 (Meta 심사 녹화용) |
| GET | `/threads/login` (prefix 없음) | Threads 동의 화면으로 보냄 (threads_basic, threads_keyword_search) |
| GET | `/threads/callback` (prefix 없음) | 코드 → 토큰 교환, 토큰은 Redis에 1시간만 둠. Meta에 등록할 콜백 주소 |
| GET | `/threads/demo` (prefix 없음) | 장소별 키워드 검색 결과와 가볼래 글 수 (지금은 키워드 규칙) |
| GET | `/threads/logout` (prefix 없음) | 연결 끊기 |

- 환경변수: `THREADS_APP_ID`, `THREADS_APP_SECRET`(Threads 앱 것, 페이스북 앱 것과 다름), `PUBLIC_BASE_URL`(https 주소)

## 7. 시연용 계정 (개발 DB에 자동 생성) [팀 확인]
| 아이디 | 기관 | 범위 |
|---|---|---|
| `busan` | 부산시 재난안전과 (city) | 전체 |
| `donggu` | 동구청 (district, 동구) | 북항친수공원 등 동구 장소 |
- 비밀번호는 `.env`의 `SEED_PASSWORD` (기본 `miribom1234`, 개발용)

## 8. 지금 안 되는 것
- 방문 의도 글 수(`intent_posts`): Threads 승인·분류 모델 학습 뒤
- 장소별 실측 방문객(`actual_visitors`): 장소 단위 자료 확보 뒤 (지금 학습 자료는 구·군 단위)
- 병목 구간 지정(A-08), 점검표(A-10), 조치 요청·알림 발송(A-11·12): P2, 추후
