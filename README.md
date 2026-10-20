# Vehicle Parking App

A parking lot management web app built with Python and Flask, made as the Modern Application Development I (MAD-1) project of the IIT Madras BS degree.

An admin creates parking lots and manages spots and users. Users find a lot, book a spot for their vehicle and release it when they leave, and are billed by the hour.

## Features

**Admin**
- Create, edit and delete parking lots. Spots are generated automatically from the number of slots.
- See each spot's status (available or occupied) and who is parked there.
- Manage users. A user with an active booking cannot be deleted.
- Summary page with charts of slot availability and revenue per lot (Matplotlib).

**User**
- Sign up, log in and edit your profile.
- Search lots by name, address or pincode.
- Book the first free spot in a lot (up to 3 active bookings, one per vehicle).
- Release a booking. Cost is the hourly price times the time parked, with a minimum charge of ₹20.
- See your booking history.

## Tech stack

Python · Flask · Flask-SQLAlchemy (SQLite locally, PostgreSQL via `DATABASE_URL`) · Flask-WTF (CSRF protection) · Jinja2 · Bootstrap · Matplotlib

## Data model

- **User**: username, hashed password, name, address, pincode
- **Parking**: lot name, address, pincode, price per hour, number of slots
- **ParkingSpot**: belongs to a lot; status `A` (available) or `O` (occupied)
- **Booking**: user, spot, vehicle number, start/end time, cost

## Run locally

```bash
python -m venv venv
venv\Scripts\activate        # Windows (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env       # macOS/Linux: cp .env.example .env
```

Edit `.env` and set your own `SECRET_KEY` (32+ random characters) and `ADMIN_PASSWORD` (8+ characters). The app will not start without them. Then:

```bash
python app.py
```

Open http://127.0.0.1:5000 and log in as `admin` with the `ADMIN_PASSWORD` you set. Changing `ADMIN_PASSWORD` and restarting updates the admin password.

## Security notes

- Secrets come from environment variables (`.env` is not committed). The app refuses to start without a strong `SECRET_KEY` and an `ADMIN_PASSWORD`.
- Sessions end automatically when a password changes or the account is deleted.
- Passwords are hashed with Werkzeug.
- Admin pages require the admin account; users can only see and release their own bookings.
- All forms, including delete and logout, use POST with CSRF tokens.
- Older commits of this repository contain a hard-coded key and admin password from the first version. They are no longer used and must never be reused.

## Deploy

The included `Procfile` runs `gunicorn app:app`. Set `SECRET_KEY`, `ADMIN_PASSWORD`, `DATABASE_URL` and `SESSION_COOKIE_SECURE=1` in your host's environment settings.
