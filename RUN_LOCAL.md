# RUN_LOCAL.md - Huong dan chay Lab 04 Access Gate

Tai lieu nay giup nguoi khac clone repo sach va chay lai Access Gate service trong Docker.

## 1. Clone repo

```bash
git clone <repo-url>
cd lab-04-cuongkaa
```

## 2. Cai dependencies cho Newman/Prism/Spectral

```bash
npm install
```

## 3. Build Docker image

```bash
docker build -t fit4110/access-gate:lab04 .
```

## 4. Run container

```bash
docker run --rm \
  --name fit4110-gate-lab04 \
  -p 8000:8000 \
  --env-file .env.example \
  fit4110/access-gate:lab04
```

Mo terminal khac, kiem tra:

```bash
curl http://localhost:8000/health
```

Ket qua mong doi:

```json
{
  "status": "ok",
  "service": "access-gate",
  "time": "2026-05-26T09:00:00+00:00"
}
```

## 5. Chay Newman test tren container

```bash
npm run test:local
```

Report sinh tai:

```text
reports/newman-lab04-local.xml
reports/newman-lab04-local.html
```

## 6. Dung container

Neu khong dung `--rm` hoac container con chay:

```bash
docker stop fit4110-gate-lab04
```

## 7. Lenh nhanh

```bash
make build
make run
make test-docker
make stop
```
