# miribom-backend

미리봄 대시보드 서버. FastAPI + PostgreSQL + Redis. AI 모델은 옆 폴더 `miribom-ai`를 설치해서 부르고, 매일 06시(한국시간) 판정을 서버 안 스케줄러(APScheduler)로 돌림

## 폴더 배치 (개발/)
```
개발/
  miribom-ai/         AI 모델 패키지
  miribom-backend/    이 레포
  miribom-frontend/   React Native (Expo)
  docker-compose.yml  전체 실행 (db, redis, backend, frontend)
  .env                .env.example 복사해서 만듦
```

## 실행
```
cd 개발
cp .env.example .env
docker compose up --build
```
- API 문서: http://localhost:8000/docs
- 상태 확인: http://localhost:8000/api/health (db, redis, 다음 06시 실행 시각)

## API
- 명세서: [docs/API.md](docs/API.md) · 실제로 눌러보기: http://localhost:8000/docs
- 시연용 계정: `busan`(부산시), `donggu`(동구청), `police_dong`(경찰, 조치 요청 받은 장소만), 비밀번호는 `.env`의 `SEED_PASSWORD` (기본 `miribom1234`)
- 처음엔 판정 결과가 없음 → `/docs`에서 busan으로 로그인(`/api/auth/login`) 후 `POST /api/admin/run`

## 구조 (기능별 폴더)
```
app/
  main.py          앱, CORS, 시작 시 테이블 생성 + 처음 자료 넣기 + 스케줄러 시작
  core/            config(환경변수·KST) · db(엔진·세션·테이블 생성) · cache(Redis) · seed(처음 자료)
  auth/            로그인(JWT)·기관별 권한 (A-15) · accounts 테이블
  dashboard/       대시보드·급상승 목록·장소 상세 (A-01~A-05, A-09) · views.py = 판정 결과 → 화면 응답
  places/          장소 수정·추가, 병목 구간(A-08, geo.py 면적 계산), 별칭(A-06) · places·aliases 테이블
  judge/           06시 판정 작업(jobs.py)·지금 실행·재현(A-07)·실행 기록 · runtime.py = miribom_ai 작업 폴더
  response/        대응 수준·조치 요청(A-11)·점검표(A-10)·알림(A-12, notify.py)·실측 회신(A-14)
  notices/         공지 등록·시민 표시·안전 문자 문안 (A-13, C-05)
  citizen/         시민 장소 검색·3일 혼잡 (C-01~C-04)
  ai/              모델 상태 카드·방문 의도 분류 시연
  threads/         Threads 콜백(연결 해제·삭제)·심사용 화면
  health/          서버 상태
  static/          privacy.html
tests/             pytest (SQLite + 가짜 Redis + miribom_ai 가짜 데이터)
```
- 기능 폴더마다 `router.py`(API), 필요하면 `models.py`(테이블)와 로직 파일이 있음

## 테스트
```
pip install -r requirements.txt -r requirements-dev.txt -e ../miribom-ai
pytest
```

## 알아둘 것
- `MIRIBOM_DEMO=true`(기본)면 네이버 키·학습 모델 없이 가짜 데이터로 판정함. 운영은 `false` + `NAVER_CLIENT_ID/SECRET` + `miribom-ai/models/`에 학습 모델 필요 (없으면 ModelMissing 오류)
- 스케줄러가 서버 안에 있어서 uvicorn 워커는 1개만 씀. 겹쳐 돌지 않게 Redis 잠금도 걸어둠
- 장소는 처음 한 번 miribom-ai/places.csv에서 가져온 뒤 DB가 기준임 (별칭은 DB에만 있음). 판정 때마다 DB 내용으로 places.csv를 새로 써서 miribom_ai에 넘김
- 과거 재현 때는 그 판정일 07시 전에 등록된 별칭만 씀 (미래 정보 차단)
- 테이블은 지금 시작할 때 `create_all`로 만듦. 스키마가 바뀌기 시작하면 Alembic으로 옮김
- 방문 의도 분류(torch)까지 쓰려면 `.env`에 `INSTALL_INTENT=true` 후 다시 빌드. 06시에 Threads 글을 모으려면 `INTENT_COLLECT=true`, `THREADS_ACCESS_TOKEN` 필요 (실패해도 판정은 계속, 실행 기록 `intent` 칸에 이유가 남음)
- 경보 알림은 `NOTIFY_MODE=dry_run`(기본)이면 기록만 남기고 보내지 않음. 받는 곳은 `PUT /api/admin/contacts/{기관}`
- 새 테이블(daily_runs, responses, checklists, contacts, notifications, visitor_reports)은 서버 시작 때 자동 생성됨. 기존 DB의 places에는 `bottleneck_polygon` 칸이 자동 추가됨
- `/privacy`의 `TEAM_EMAIL`은 실제 팀 메일로 바꿔야 함 [팀 확인]
