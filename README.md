# CertifyPro 🎓

**CertifyPro** is a lightweight, high-performance certificate generation and automated dispatch system. Built with **FastAPI** and **Vanilla JS**, it allows organizations to design, mass-generate, and email personalized certificates in seconds.

Developed and maintained by **Laukik Rathod**.

---

## 🚀 Features

- **Live Layout Editor**: Drag-and-drop name placement with a real-time preview canvas.
- **Resolution Independence**: Uses a ratio-based coordinate system (0–1) ensuring that certificates look identical on any template resolution.
- **Bulk Processing**: Import hundreds of participants via CSV and generate PDFs in seconds.
- **Automated Dispatch**: Integrated SMTP engine for bulk emailing with PDF attachments and rate-limit handling.
- **Robust Persistence**: SQLite-backed participant tracking and JSON-based layout versioning.
- **Production Ready**: Optimized for speed, reliability, and clean code standards.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, ReportLab (PDF Engine).
- **Frontend**: Vanilla JavaScript (ES6+), HTML5, CSS3 (Modular design).
- **Database**: SQLite (Local persistence).
- **Storage**: JSON for layout configuration artifacts.

---

## 📦 Project Structure

```text
certificate_system/
├── app/
│   ├── static/             # Frontend assets (HTML/JS/CSS)
│   ├── main.py             # FastAPI entry point & API routes
│   ├── certificate_generator.py # PDF rendering logic (ReportLab)
│   ├── email_service.py    # SMTP dispatch engine
│   ├── models.py           # SQLAlchemy database schemas
│   └── database.py         # DB connection & initialization
├── templates/              # Certificate PNG templates
├── generated/              # Output directory for generated PDFs
├── .env                    # System environment variables (SMTP creds)
├── layout.json            # Persisted layout configuration (ratios)
└── start_dashboard.bat     # Windows one-click launcher
```

---

## 🔧 Installation & Setup

### 1. Prerequisites
- Python 3.11 or higher installed on your system.
- A Gmail account with 2-Step Verification enabled for **App Passwords**.

### 2. Environment Configuration
Create a `.env` file in the root directory:
```env
SENDER_EMAIL=your-email@gmail.com
APP_PASSWORD=your-16-char-app-password
```

### 3. Installation
```powershell
# Clone the repository
git clone https://github.com/Laukikrathod2007/CertifyPro.git
cd CertifyPro/certificate_system

# Install dependencies
pip install -r requirements.txt
```

### 4. Running the Application
Simply double-click the `start_dashboard.bat` file or run:
```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```
Access the dashboard at: **http://127.0.0.1:8002**

---

## 📊 CSV Format Requirement
The system expects a standard `.csv` file with the following headers:
| Name | Email |
| :--- | :--- |
| John Doe | john@example.com |
| Laukik Rathod | laukik@example.com |

---

## 🏗️ Technical Implementation Notes

- **Coordinate System**: Unlike traditional pixel-based systems, CertifyPro stores layout data as float ratios. This prevents the "coordinate desync" bug where preview positions don't match final PDF exports across different image resolutions.
- **Concurrency**: Bulk uploads use optimized Pandas `to_sql` batches for near-instant ingestion, even with large participant lists.
- **State Management**: The frontend maintains a dedicated state object `S` that synchronizes the canvas coordinate system with the backend JSON schema.

---

## 👤 Author
**Laukik Rathod**  
[GitHub](https://github.com/Laukikrathod2007) | [Project Repository](https://github.com/Laukikrathod2007/CertifyPro)
