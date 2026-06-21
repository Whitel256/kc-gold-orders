# KCG Order System - Cloudflare Tunnel Setup Guide

## What this does
Your app runs on YOUR PC. Cloudflare creates a secure tunnel so
tablets at all branches can access it from anywhere via the internet.

```
Tablet (any branch)
       ↓ internet
Cloudflare Tunnel (free)
       ↓
Your PC (Flask app on port 5000)
       ↓
MySQL (local database)
```

---

## STEP 1: Install MySQL (if not installed)

Download XAMPP from: https://www.apachefriends.org/
- Install XAMPP
- Open XAMPP Control Panel
- Start MySQL
- Your MySQL password is blank by default in XAMPP

Or if you have MySQL already installed, just make sure it's running.

---

## STEP 2: Create the database

Open MySQL command line or phpMyAdmin and run:
```sql
CREATE DATABASE jewellery_orders;
```

Then import the schema (if using command line):
```
mysql -u root -p jewellery_orders < schema.sql
```

Or open phpMyAdmin → select jewellery_orders → Import → select schema.sql

---

## STEP 3: Edit the .env file

Open `.env` in notepad and set your MySQL password:
```
SECRET_KEY=kcg-jewellery-secret-2024
DB_USER=root
DB_PASS=           ← your MySQL password (blank if XAMPP)
DB_HOST=localhost
DB_PORT=3306
DB_NAME=jewellery_orders
```

---

## STEP 4: Run the app

Double-click `START.bat`

You should see:
```
* Running on http://0.0.0.0:5000
```

Test in browser: http://localhost:5000

---

## STEP 5: Set up Cloudflare Tunnel (one time only)

### 5a. Create free Cloudflare account
Go to: https://cloudflare.com → Sign up free

### 5b. Download cloudflared
Go to: https://github.com/cloudflare/cloudflared/releases/latest
Download: `cloudflared-windows-amd64.exe`
Rename it to: `cloudflared.exe`
Place it in: `C:\cloudflared\cloudflared.exe`

### 5c. Quick tunnel (no domain needed - easiest!)

Open a NEW command prompt window and run:
```
C:\cloudflared\cloudflared.exe tunnel --url http://localhost:5000
```

You will see a URL like:
```
https://random-words-here.trycloudflare.com
```

⚠️ This URL changes every time you restart. For a permanent URL, see below.

### 5d. Permanent URL (needs a domain - recommended)

1. Add a domain to Cloudflare (or buy one ~₹800/year from Namecheap)
2. Run: `C:\cloudflared\cloudflared.exe tunnel login`
3. Run: `C:\cloudflared\cloudflared.exe tunnel create kcg-orders`
4. Create file `C:\cloudflared\config.yml`:
```yaml
tunnel: <your-tunnel-id>
credentials-file: C:\Users\YourName\.cloudflared\<tunnel-id>.json

ingress:
  - hostname: orders.yourdomain.com
    service: http://localhost:5000
  - service: http_status:404
```
5. Run: `C:\cloudflared\cloudflared.exe tunnel run kcg-orders`
6. In Cloudflare dashboard → DNS → Add CNAME:
   - Name: orders
   - Target: <tunnel-id>.cfargotunnel.com

---

## STEP 6: Share the URL with branches

Give all branch tablets the URL:
- Quick tunnel: `https://random-words.trycloudflare.com`
- Permanent: `https://orders.yourdomain.com`

Each branch logs in with their username/password.

---

## Daily startup routine

1. Make sure PC is ON
2. Start MySQL (XAMPP → Start MySQL)
3. Double-click `START.bat`
4. Run cloudflared in another window (or set it as Windows startup)

---

## Default login credentials (change after first login!)

Run `seed.py` first to create default users:
```
python seed.py
```

| Username   | Password    | Role        |
|------------|-------------|-------------|
| admin      | password123 | Admin       |
| headoffice | password123 | Head Office |
| branch1    | password123 | Branch 1    |
| branch2    | password123 | Branch 2    |
| branch3    | password123 | Branch 3    |
| branch4    | password123 | Branch 4    |
| branch5    | password123 | Branch 5    |

---

## Auto-start on Windows boot (optional)

To make cloudflared start automatically:
```
C:\cloudflared\cloudflared.exe service install
```

This runs the tunnel as a Windows service — starts automatically with PC.
