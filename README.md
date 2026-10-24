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
- 처음엔 판정 결과가 없음 → `curl -X POST localhost:8000/api/admin/run` 로 한 번 돌림

## API
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | /api/health | 서버·DB·Redis 상태, 다음 예약 실행 시각 |
| GET | /api/alerts/latest | 최신 판정 결과 (Redis 캐시) |
| GET | /api/alerts/{YYYY-MM-DD} | 특정 판정일 결과 |
| POST | /api/admin/run?judge_day=&demo= | 지금 판정 실행 (judge_day 주면 과거 재현). ADMIN_TOKEN 설정 시 `X-Admin-Token` 헤더 필요 |
| POST | /api/threads/deauthorize | Threads 연결 해제 콜백 |
| POST | /api/threads/delete | Threads 데이터 삭제 콜백 (확인 코드 반환) |
| GET | /api/threads/delete/{code} | 삭제 요청 상태 |
| GET | /privacy | 개인정보처리방침 |

## 구조
```
app/
  main.py      앱, CORS, 시작 시 테이블 생성 + 스케줄러 시작
  config.py    환경변수
  db.py        테이블 (daily_results, deletion_requests)
  cache.py     Redis
  jobs.py      06시 판정 작업 (miribom_ai.run_daily → DB 저장 → Redis 최신값)
  routers/     health, alerts, threads
  static/      privacy.html
```

## 알아둘 것
- `MIRIBOM_DEMO=true`(기본)면 네이버 키·학습 모델 없이 가짜 데이터로 판정함. 운영은 `false` + `NAVER_CLIENT_ID/SECRET` + `miribom-ai/models/`에 학습 모델 필요 (없으면 ModelMissing 오류)
- 스케줄러가 서버 안에 있어서 uvicorn 워커는 1개만 씀. 겹쳐 돌지 않게 Redis 잠금도 걸어둠
- 테이블은 지금 시작할 때 `create_all`로 만듦. 스키마가 바뀌기 시작하면 Alembic으로 옮김
- 방문 의도 분류(torch)까지 쓰려면 `.env`에 `INSTALL_INTENT=true` 후 다시 빌드
- `/privacy`의 `TEAM_EMAIL`은 실제 팀 메일로 바꿔야 함 [팀 확인]
