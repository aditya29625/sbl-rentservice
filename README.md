# SBLRent

SBLRent is a modern Django-based rental platform for property owners (vendors) and tenants. It features secure registration, property listing, booking, payment integration (Razorpay), and robust user/vendor onboarding with document verification.

---

## 🚀 Standout Features

- **Advanced Search & Filtering:**  
  Users can search and filter properties by location, zip code, property type, price range, and using Map.  
  - **Interactive Map Search:** Pick your desired location directly on a map (Leaflet.js integration) for geo-based property results.
  - **Radius-based Search:** Find properties within a specific distance from your chosen point.
  - **Live Filtering:** All filters are seamlessly integrated and redirect to a unified property listing page for a smooth user experience.

- **Wishlist (Save Property):**  
  Users can save/favorite properties with a single click (AJAX-powered heart icon), making it easy to revisit and compare listings.

- **User & Vendor Onboarding:**  
  - Aadhaar upload required for all users.
  - Deferred KYC for vendors via secure email link.
  - Profile management with document verification.

- **Booking & Payment:**  
  - Book properties instantly.
  - Integrated Razorpay payment gateway for secure transactions.
  - Monthly payment logic for ongoing bookings.
  - **Automated rent payment notifications:** Users receive reminders if rent is due or unpaid.

- **Notifications:**  
  - Email alerts for registration, KYC, bookings, and admin actions.

- **Responsive, Modern UI:**  
  - Built with Bootstrap 5 for a professional, mobile-friendly experience.
  - Clean dashboard for both users and vendors.

- **Security & Best Practices:**  
  - Credentials managed via python-decouple and `.env`.
  - CSRF protection, secure authentication, and robust permission checks.

---

## 💡 Why SBLRent Stands Out

- **Real-world Usability:**  
  The platform is designed to solve real rental market problems—location-based search, verified listings, and seamless booking/payment.
- **Investor-Ready:**  
  The codebase is modular, scalable, and ready for cloud deployment (Render, AWS, etc.).
- **Recruiter Appeal:**  
  Demonstrates advanced Django skills, RESTful design, AJAX, payment integration, and modern frontend practices.

---

## Tech Stack

- Python 3.12
- Django 5.2.3
- SQLite (easy to switch to PostgreSQL/MySQL)
- Razorpay (payment gateway)
- Bootstrap 5 (frontend)
- Leaflet.js (interactive maps)
- python-decouple (for environment variables)

---

## Live Site

Primary domain: [https://sblrent.sblconstruction.in/](https://sblrent.sblconstruction.in/)

Visit the deployed app: [sblrent.onrender.com](https://sblrent.onrender.com/)

Visit the deployed on Azure: [https://sblrent-c9ehdmewcqcfhkh7.eastasia-01.azurewebsites.net/](https://sblrent-c9ehdmewcqcfhkh7.eastasia-01.azurewebsites.net/)

---

## Setup Instructions

### 1. Clone the repository
```bash
git clone https://github.com/<your-username>/sblRent.git
cd sblRent
```

### 2. Create and activate a virtual environment
```bash
python3 -m venv myenv
source myenv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables
Create a `.env` file in the root directory with the following keys:
```
SECRET_KEY=your-django-secret-key
RAZORPAY_KEY_ID=your-razorpay-key-id
RAZORPAY_KEY_SECRET=your-razorpay-key-secret
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-email-password
```

For production, start from the template:
```bash
cp .env.production.example .env
```
Then replace all placeholder values before deploying.

### 5. Apply migrations
```bash
python manage.py migrate
```

### 6. Create a superuser (admin)
```bash
python manage.py createsuperuser
```

### 7. Run the development server
```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` in your browser.

### 8. Run local HTTPS (self-signed certificate)
```bash
python manage.py runserver_plus --cert-file certs/localhost.pem 127.0.0.1:8000
```

Then open:
- `https://localhost:8000/`
- `https://127.0.0.1:8000/`

Notes:
- On first run, a self-signed cert is generated under `certs/`.
- Your browser will show a warning once; choose “Advanced” and continue for local development.

---

## Folder Structure

- `core/` - Django project settings
- `home/` - Main app (models, views, templates)
- `accounts/` - User account management
- `media/` - Uploaded files (profile pics, Aadhaar, etc.)
- `static/` - Static files (CSS, JS, images)

---

## Key Files

- `requirements.txt` - Python dependencies
- `manage.py` - Django management script
- `.env` - Environment variables (not committed)

---

## Security Notes

- Never commit your `.env` file or secret keys to version control.
- Use strong passwords and enable 2FA for your email and admin accounts.

---

## Deployment on Render

This project is ready for deployment on [Render](https://render.com/):
Visit the deployed on Azure: [https://sblrent-c9ehdmewcqcfhkh7.eastasia-01.azurewebsites.net/](https://sblrent-c9ehdmewcqcfhkh7.eastasia-01.azurewebsites.net/)

1. Push your code to GitHub (do NOT include your local `myenv` or `db.sqlite3`).
2. Connect your GitHub repo to Render and create a new Web Service.
3. Set the build and start commands:
    - Build command: `pip install -r requirements.txt && python manage.py migrate`
    - Start command: `gunicorn core.wsgi`
4. Add environment variables in the Render dashboard (from your `.env` file).
5. Render will auto-deploy on every push to GitHub.

Live site: [https://sblrent.onrender.com/](https://sblrent.onrender.com/)
Visit the deployed on Azure: [https://sblrent-c9ehdmewcqcfhkh7.eastasia-01.azurewebsites.net/](https://sblrent-c9ehdmewcqcfhkh7.eastasia-01.azurewebsites.net/)

---

## License

All rights reserved. The source code, content, and design of sblrent are the exclusive property of the project owner. No part of this project may be copied, reproduced, distributed, or used in any form without explicit written permission from the owner.

---


# sbl-rentservice
