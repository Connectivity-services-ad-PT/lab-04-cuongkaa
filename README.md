# FIT4110 Lab 04 - Access Gate Service

Lab 04 dong goi service nhom Gate bang Docker va chay lai Postman/Newman tren container.

Contract dung cho bai nay:

```text
contracts/access-gate.openapi.yaml
```

## Muc tieu

- Build duoc Docker image cho Access Gate service.
- Run duoc container va kiem tra `GET /health` tra `200`.
- Service chay bang non-root user trong container.
- Cau hinh runtime nam trong `.env.example`.
- Newman test pass tren container.
- Sinh report XML/HTML trong `reports/`.

## API chinh

- `GET /health`
- `POST /access/check`
- `GET /policies/access`
- `GET /policies/access/{policyId}`
- `GET /decisions`
- `GET /decisions/{decisionId}`

Tat ca endpoint ngoai `/health` can header:

```text
Authorization: Bearer local-dev-token
```

## Chay local khong Docker

Can Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn iot_app.main:app --app-dir src --host 0.0.0.0 --port 8000
```

Kiem tra:

```bash
curl http://localhost:8000/health
```

## Build va run bang Docker

```bash
docker build -t fit4110/access-gate:lab04 .
```

```bash
docker run --rm \
  --name fit4110-gate-lab04 \
  -p 8000:8000 \
  --env-file .env.example \
  fit4110/access-gate:lab04
```

Kiem tra health:

```bash
curl http://localhost:8000/health
```

## Chay Newman test tren container

```bash
npm install
npm run test:local
```

Report sinh tai:

```text
reports/newman-lab04-local.xml
reports/newman-lab04-local.html
```

## Lenh nhanh

```bash
make install
make lint
make mock
make build
make run
make test-docker
make stop
```

## Artefact can nop

- `Dockerfile`
- `.dockerignore`
- `.env.example`
- `RUN_LOCAL.md`
- `contracts/access-gate.openapi.yaml`
- `postman/collections/FIT4110_lab04_gate_docker.postman_collection.json`
- `postman/environments/FIT4110_lab04_local.postman_environment.json`
- `reports/newman-lab04-local.xml`
- `reports/newman-lab04-local.html`
- Anh/log `docker build`, `docker run`, `GET /health`
- Image tag da push len registry neu giang vien yeu cau
