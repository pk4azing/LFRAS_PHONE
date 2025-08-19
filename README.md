# LFRAS Phone – CD & CCD Backend

This repository contains the **backend implementation** of the **Lucid Financial Reporting & Analysis Suite (LFRAS)** for **Customer Dashboard (CD)** and **Client’s Customer Dashboard (CCD)**.  
It is built with **Django + Django REST Framework (DRF)** and designed to run in **Docker** with PostgreSQL and S3 integrations.

---

## 🚀 Features

- **Authentication & Accounts**
  - JWT-based login/logout (short-lived & refresh tokens).
  - Forgot & Reset Password with OTP and Email.
  - Audit logs for all login/logout events.
  - Role-based access control (SuperAdmin, CD Admin, LD Employee, CCD User, etc.).

- **CD & CCD Tenants**
  - CD tenants created by LD SuperAdmins.
  - CCD tenants created only by LD/CD Admins.
  - Domain-based validation for emails.
  - Plan limits enforced (employees & CCD users).

- **Employees & Users**
  - CD Admins can manage their employees.
  - CCD users are one-login-per-customer.

- **Activities**
  - CCD Users start an Activity (file upload workflow).
  - Files validated against CD-uploaded config from S3.
  - Automatic zipping of valid files and final storage in S3.
  - Email + Notification + Audit logging at each lifecycle event.
  - Calendar API for activity & file expiry tracking.

- **Tickets**
  - Ticket creation & updates by CD/CCD employees.
  - Visibility restricted to creator + LD Employees.
  - Notifications & emails sent on ticket lifecycle events.

- **Reports**
  - On-demand & scheduled (daily/weekly/monthly) reports.
  - Reports stored in S3 and emailed to requesters.
  - Access controlled by roles.

- **Audit & Notifications**
  - Centralized audit trail (login, activity, ticket, report, downloads).
  - Notifications with levels: Good (Green), Warning (Yellow), Critical (Red).

- **Cron Jobs**
  - Automated file expiry reminders:
    - 4 weeks, 3 weeks, 2 weeks, 1 week, 24h, day-of, post-expiry (24h–96h).
  - Uses `django-cron`.

---

## 📂 Project Structure

lfras_phone/
│── backend/
│   ├── apps/
│   │   ├── accounts/        # Authentication, users, roles
│   │   ├── tenants/         # CD & CCD tenants
│   │   ├── activities/      # File uploads & workflows
│   │   ├── tickets/         # Ticketing system
│   │   ├── reports/         # Reports generation
│   │   ├── notifications/   # Notifications & alerts
│   │   ├── audit/           # Audit logs
│   │   └── utils/           # Common utilities (S3, email, zipping)
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│── docker/                  # Docker configs
│── requirements.txt
│── manage.py

---

## ⚙️ Installation

### 1. Clone Repository
```bash
git clone https://github.com/<your-org>/lfras_phone.git
cd lfras_phone

2. Setup Virtual Environment

python -m venv .venv
source .venv/bin/activate   # Linux/Mac
.venv\Scripts\activate      # Windows

3. Install Dependencies

pip install -r requirements.txt

4. Configure Environment

Create .env file in backend/:

DEBUG=True
SECRET_KEY=your-secret-key
DATABASE_URL=postgres://user:password@localhost:5432/lfras_phone
AWS_STORAGE_BUCKET_NAME=lfras-bucket
EMAIL_HOST=smtp.yourdomain.com
EMAIL_HOST_USER=your-email
EMAIL_HOST_PASSWORD=your-password

5. Run Migrations

python manage.py makemigrations
python manage.py migrate

6. Create SuperUser

python manage.py createsuperuser

7. Run Server

python manage.py runserver


⸻

🐳 Docker Deployment

docker-compose up --build -d

	•	Backend runs on http://localhost:8000
	•	Logs stored in /var/log/django_cron.log

⸻

📡 API Endpoints (Sample)

Endpoint	Method	Description
/api/v1/accounts/login/	POST	Login with credentials
/api/v1/accounts/token/refresh/	POST	Refresh JWT token
/api/v1/accounts/password/forgot/	POST	Request OTP for reset
/api/v1/accounts/password/reset/	POST	Reset password via OTP
/api/v1/tenants/cd/	POST	Create CD tenant (LD only)
/api/v1/tenants/ccd/	POST	Create CCD tenant (LD/CD Admin only)
/api/v1/employees/	GET	List employees of a CD
/api/v1/activities/start/	POST	Start activity
/api/v1/activities/calendar/	GET	Calendar view (Info/Warning/Expiry)
/api/v1/tickets/	POST	Create ticket
/api/v1/reports/	GET	List/download reports


⸻

✅ Tests

pytest


⸻

📝 Contributing
	1.	Fork the repo
	2.	Create your branch (feature/xyz)
	3.	Commit changes
	4.	Open a PR

⸻

📜 License

© 2025 A-Zing Innovations. All rights reserved.
