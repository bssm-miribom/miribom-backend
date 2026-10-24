# 빌드 위치는 개발/ (루트). miribom-ai를 같이 넣어야 해서 루트에서 빌드함
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Seoul
# lightgbm 실행에 필요
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 tzdata && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY miribom-backend/requirements.txt miribom-backend/requirements.txt
RUN pip install --no-cache-dir -r miribom-backend/requirements.txt

# 모델 패키지. INSTALL_INTENT=true면 torch·transformers까지 (이미지 커짐)
ARG INSTALL_INTENT=false
COPY miribom-ai /opt/miribom-ai
RUN if [ "$INSTALL_INTENT" = "true" ]; then pip install --no-cache-dir -e "/opt/miribom-ai[intent]"; \
    else pip install --no-cache-dir -e /opt/miribom-ai; fi
ENV MIRIBOM_HOME=/opt/miribom-ai

COPY miribom-backend/app app
EXPOSE 8000
# 스케줄러가 서버 안에서 돌아서 워커는 1개만 씀 (여러 개면 06시 작업이 중복 실행됨)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
