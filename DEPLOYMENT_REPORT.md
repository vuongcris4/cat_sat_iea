# 🚀 Báo Cáo Deploy Cat Sat IEA Lên Production

**Ngày**: 2026-03-02  
**Server**: DigitalOcean Droplet — `152.42.166.171`  
**Region**: Singapore (sgp1)  
**Spec**: 2 vCPU / 4GB RAM (`s-2vcpu-4gb`)  
**OS**: Ubuntu 24.04 LTS

---

## 1. Tổng Quan

Ứng dụng Cat Sat IEA đã được deploy lên DigitalOcean với kiến trúc production-ready, hỗ trợ **nhiều người dùng đồng thời** và có **CI/CD tự động** qua GitHub Actions.

### Trạng thái

| Hạng mục | Trạng thái |
|----------|------------|
| App chạy production | ✅ Online tại `http://152.42.166.171` |
| Multi-user (PostgreSQL) | ✅ Hoạt động |
| CI/CD tự động | ✅ GitHub Actions — auto deploy khi push `main` |
| Logging system | ✅ `optimization_logs` app sẵn sàng |
| Reverse proxy + HTTPS-ready | ✅ Caddy |
| WebSocket support | ✅ Daphne ASGI + Redis Channel Layer |

---

## 2. Kiến Trúc Production

```
┌─────────────┐
│  User/Browser│
└──────┬──────┘
       │ HTTP/WS
       ▼
┌─────────────┐
│   Caddy     │ ← Reverse proxy (:80/:443)
│   (Alpine)  │   Auto HTTPS khi gán domain
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│   Daphne    │────▶│   Redis 7   │ ← Channel Layer (WebSocket)
│ (ASGI :8000)│     │  (Alpine)   │
└──────┬──────┘     └─────────────┘
       │
       ▼
┌─────────────┐
│ PostgreSQL  │ ← Database chính
│    16       │   Hỗ trợ concurrent connections
│  (Alpine)   │
└─────────────┘
```

### Docker Containers

| Container | Image | Vai trò |
|-----------|-------|---------|
| `catsat_caddy` | caddy:2-alpine | Reverse proxy, auto-HTTPS |
| `catsat_web` | python:3.11-slim (custom) | Django + Daphne ASGI server |
| `catsat_postgres` | postgres:16-alpine | Database chính |
| `catsat_redis` | redis:7-alpine | Channel layer cho WebSocket |

---

## 3. Hỗ Trợ Nhiều Người Dùng (Multi-User)

### Đã thực hiện

1. **SQLite → PostgreSQL**: Chuyển từ SQLite (single-writer lock) sang PostgreSQL 16 — hỗ trợ hàng trăm kết nối đồng thời.

2. **ASGI Server (Daphne)**: Thay vì WSGI đơn luồng, sử dụng Daphne ASGI server — xử lý nhiều request song song + WebSocket.

3. **Redis Channel Layer**: WebSocket connections được quản lý qua Redis — cho phép nhiều user nhận kết quả real-time đồng thời.

4. **User Authentication**: Mỗi user có tài khoản riêng, mỗi phiên tối ưu hóa được gán cho user tương ứng.

5. **Optimization Logging**: Model `OptimizationLog` ghi lại:
   - User nào chạy
   - Module nào (MC Tự Động / MC Laser)
   - Input data + Parameters
   - Output summary
   - Thời gian chạy (duration)
   - Status (success/error/timeout)

### Tạo user mới

```bash
# SSH vào server
ssh root@152.42.166.171

# Tạo user
docker exec -it catsat_web python manage.py createsuperuser

# Hoặc tạo user thường qua Admin panel
# Truy cập: http://152.42.166.171/admin/
```

---

## 4. CI/CD Pipeline

### Workflow: `.github/workflows/deploy.yml`

```
Push code lên main
       │
       ▼
GitHub Actions Runner
       │
       ▼ SSH vào server
┌──────────────────┐
│ git pull         │
│ docker compose   │
│   up -d --build  │
│ Health check     │
└──────────────────┘
```

### GitHub Secrets (đã cấu hình)

| Secret | Mô tả |
|--------|--------|
| `DO_HOST` | IP server: `152.42.166.171` |
| `DO_USERNAME` | User SSH: `root` |
| `DO_SSH_KEY` | Private key (ed25519) |
| `DO_SSH_PORT` | Port SSH: `22` |

### Cách hoạt động

1. Developer push code lên branch `main`
2. GitHub Actions tự động trigger workflow `deploy.yml`
3. Workflow SSH vào server DigitalOcean
4. Chạy `git pull origin main` để lấy code mới
5. Chạy `docker compose -f docker-compose.prod.yml up -d --build` để rebuild + restart
6. Health check: kiểm tra app trả về HTTP 200

> **Không cần thao tác thủ công** — chỉ cần push code, app tự động cập nhật trong ~2 phút.

---

## 5. Quá Trình Deploy Chi Tiết

### Bước 1: Provision Droplet (Terraform)

```hcl
# infrastructure/environments/digitalocean/terraform.tfvars
region        = "sgp1"
droplet_name  = "catsat"
droplet_size  = "s-2vcpu-4gb"    # 2 vCPU, 4GB RAM cho OR-Tools
droplet_image = "ubuntu-24-04-x64"
```

```bash
terraform apply  # → Droplet IP: 152.42.166.171
```

### Bước 2: Chuẩn Bị Server

```bash
# Cài Docker
ssh root@152.42.166.171
curl -fsSL https://get.docker.com | sh

# Tạo SSH key + thêm deploy key vào GitHub
ssh-keygen -t ed25519
# → Thêm public key vào GitHub repo Settings > Deploy Keys

# Clone repo
git clone git@github.com:vuongcris4/cat_sat_iea.git /opt/cat_sat_iea
```

### Bước 3: Cấu Hình Environment

```bash
# Tạo file .env (copy từ .env.example)
cp .env.example .env
# Sửa các giá trị: SECRET_KEY, DB_PASSWORD, ALLOWED_HOSTS
```

### Bước 4: Push Production Files

Các file đã thêm/sửa trên branch `main`:

| File | Mô tả |
|------|--------|
| `Dockerfile` | Multi-stage build: Python 3.11 + libpq-dev + entrypoint |
| `docker-compose.prod.yml` | 4 services: postgres, redis, web, caddy |
| `entrypoint.sh` | Wait PG → migrate → collectstatic → daphne |
| `Caddyfile` | Reverse proxy :80 → web:8000 |
| `requirements.txt` | Thêm `psycopg2-binary` |
| `iea_project/settings.py` | PostgreSQL qua env vars, WhiteNoise |
| `iea_project/urls.py` | Thêm `/logs/` route |
| `optimization_logs/` | Django app: Model, Admin, Views, Templates |
| `.github/workflows/deploy.yml` | CI/CD workflow |
| `.env.example` | Template file môi trường |

### Bước 5: Docker Compose Up

```bash
cd /opt/cat_sat_iea
docker compose -f docker-compose.prod.yml up -d --build
```

Kết quả:
```
catsat_caddy      Up (Caddy reverse proxy)
catsat_web        Up (Daphne ASGI)
catsat_postgres   Up (healthy)
catsat_redis      Up
```

### Bước 6: Migrations & Superuser

```bash
docker exec catsat_web python manage.py makemigrations
docker exec catsat_web python manage.py migrate
docker exec -it catsat_web python manage.py createsuperuser
```

### Bước 7: Cấu Hình GitHub Secrets

Thêm 4 secrets vào GitHub repo → Settings → Secrets → Actions:
- `DO_HOST`, `DO_USERNAME`, `DO_SSH_KEY`, `DO_SSH_PORT`

---

## 6. Cấu Trúc File Production

```
cat_sat_iea/
├── .github/workflows/deploy.yml    # CI/CD
├── .env.example                     # Template env
├── Caddyfile                        # Reverse proxy config
├── Dockerfile                       # Docker image
├── docker-compose.prod.yml          # Production compose
├── entrypoint.sh                    # Container entrypoint
├── requirements.txt                 # Dependencies
├── iea_project/
│   ├── settings.py                  # PostgreSQL + env vars
│   ├── urls.py                      # Routing + /logs/
│   └── asgi.py                      # ASGI config
├── optimization_logs/               # Logging app
│   ├── models.py                    # OptimizationLog model
│   ├── admin.py                     # Admin registration
│   ├── views.py                     # History view
│   └── templates/                   # UI templates
├── cat_sat/                         # Module MC Tự Động
├── cat_laser_roi/                   # Module MC Laser
└── accounts/                        # Authentication
```

---

## 7. Vận Hành

### Xem logs
```bash
ssh root@152.42.166.171
docker logs catsat_web -f --tail 50
```

### Restart services
```bash
cd /opt/cat_sat_iea
docker compose -f docker-compose.prod.yml restart
```

### Backup database
```bash
docker exec catsat_postgres pg_dump -U catsat catsat > backup_$(date +%Y%m%d).sql
```

### Gán domain (auto-HTTPS)
Sửa `Caddyfile`:
```
catsat.dongnama.app {
    reverse_proxy catsat_web:8000
}
```
Trỏ DNS A record → `152.42.166.171`, rồi restart Caddy.

---

## 8. Chi Phí

| Hạng mục | Chi phí/tháng |
|----------|---------------|
| Droplet s-2vcpu-4gb | ~$24 USD |
| GitHub Actions | Miễn phí (public repo) |
| Domain (nếu có) | ~$10-15 USD/năm |
| **Tổng** | **~$24 USD/tháng** |
