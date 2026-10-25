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
- 시연용 계정: `busan`(부산시), `donggu`(동구청), 비밀번호는 `.env`의 `SEED_PASSWORD` (기본 `miribom1234`)
- 처음엔 판정 결과가 없음 → `/docs`에서 busan으로 로그인(`/api/auth/login`) 후 `POST /api/admin/run`

## 구조
```
app/
  main.py      앱, CORS, 시작 시 테이블 생성 + 처음 자료 넣기 + 스케줄러 시작
  config.py    환경변수
  db.py        테이블 (places, aliases, accounts, daily_results, notices, deletion_requests)
  seed.py      처음 실행 때 장소(miribom-ai/places.csv)·시연용 계정 넣기
  auth.py      로그인(JWT), 기관별 권한
  runtime.py   miribom_ai 작업 폴더 준비, DB 장소+별칭으로 places.csv 쓰기
  jobs.py      06시 판정 작업 (miribom_ai.run_daily → DB 저장 → Redis 최신값)
  views.py     판정 결과 → 대시보드·장소 상세·시민 혼잡 응답
  routers/     health, auth, admin, public(시민), threads
  static/      privacy.html
```

## 알아둘 것
- `MIRIBOM_DEMO=true`(기본)면 네이버 키·학습 모델 없이 가짜 데이터로 판정함. 운영은 `false` + `NAVER_CLIENT_ID/SECRET` + `miribom-ai/models/`에 학습 모델 필요 (없으면 ModelMissing 오류)
- 스케줄러가 서버 안에 있어서 uvicorn 워커는 1개만 씀. 겹쳐 돌지 않게 Redis 잠금도 걸어둠
- 장소는 처음 한 번 miribom-ai/places.csv에서 가져온 뒤 DB가 기준임 (별칭은 DB에만 있음). 판정 때마다 DB 내용으로 places.csv를 새로 써서 miribom_ai에 넘김
- 과거 재현 때는 그 판정일 07시 전에 등록된 별칭만 씀 (미래 정보 차단)
- 테이블은 지금 시작할 때 `create_all`로 만듦. 스키마가 바뀌기 시작하면 Alembic으로 옮김
- 방문 의도 분류(torch)까지 쓰려면 `.env`에 `INSTALL_INTENT=true` 후 다시 빌드
- `/privacy`의 `TEAM_EMAIL`은 실제 팀 메일로 바꿔야 함 [팀 확인]
