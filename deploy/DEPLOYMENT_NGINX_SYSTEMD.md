Deployment Bundle (Nginx + systemd)

1) Nginx HTTPS
- Update domain + cert paths in nginx/pos.conf
- Copy to /etc/nginx/sites-available/pos.conf
- Enable and reload:
  - ln -s /etc/nginx/sites-available/pos.conf /etc/nginx/sites-enabled/pos.conf
  - nginx -t && systemctl reload nginx

2) systemd services
- Copy files from deploy/systemd/ to /etc/systemd/system/
- Edit environment values (DATABASE_URL, REDIS_URL, MAIN_ADMIN_EMAIL, MAIN_ADMIN_HASH, BACKUP_ENCRYPTION_KEY)
- Enable and start:
  - systemctl daemon-reload
  - systemctl enable universal-pos.service
  - systemctl start universal-pos.service
  - systemctl enable universal-pos-backup.timer
  - systemctl start universal-pos-backup.timer

3) Frontend CDN
- Set VITE_CDN_BASE to your CDN origin (e.g., https://cdn.example.com/)
- Build frontend and upload dist/ to the CDN origin.

4) Redis sessions
- Ensure REDIS_URL is set for session store + rate limiting.

Notes
- The backend enforces HTTPS when ENFORCE_HTTPS=1.
- Use a valid Fernet key for BACKUP_ENCRYPTION_KEY.
