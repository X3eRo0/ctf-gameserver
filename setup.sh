#!/bin/bash

set -xe

apt update
apt install -y devscripts dpkg-dev equivs neovim postgresql python3-psycopg2 nginx uwsgi uwsgi-plugin-python3 postfix wireguard-tools certbot python3-certbot-nginx
mk-build-deps --install debian/control
dpkg-buildpackage --unsigned-changes --unsigned-buildinfo

echo "[+] Start ansible script now and hit CTRL-C when its done."
cd /root/ && python3 -m http.server 8000 --bind 0.0.0.0

cat <<'EOF' >/etc/uwsgi/apps-available/ctf-gameserver.ini
[uwsgi]
# load the Python 3 plugin so uWSGI can run your WSGI app
plugin = python3


chdir           = /usr/lib/python3/dist-packages/
module          = ctf_gameserver.web.wsgi:application

# Use the prod settings file
env             = DJANGO_SETTINGS_MODULE=prod_settings
pythonpath      = /etc/ctf-gameserver/web

master          = true
processes       = 4
socket          = /run/uwsgi/ctf-gameserver.sock
chmod-socket    = 660
vacuum          = true

uid             = www-data
gid             = www-data
EOF

ln -s /etc/uwsgi/apps-available/ctf-gameserver.ini /etc/uwsgi/apps-enabled/
systemctl enable --now uwsgi

cat <<'EOF' >/etc/nginx/sites-available/ctf-gameserver
upstream ctf_uwsgi {
    server unix:/run/uwsgi/ctf-gameserver.sock;
}

server {
    # Listen on port 80 for all addresses

    # Optionally set your VPS IP or domain here
    server_name x3ero0.dev;
    
    # Proxy everything else to uWSGI
    location / {
        include uwsgi_params;
        uwsgi_pass ctf_uwsgi;
    }

    location /static/admin/ {
        alias /usr/lib/python3/dist-packages/django/contrib/admin/static/admin/;
    }

    # Serve Django static files
    location /static/ {
        alias /usr/lib/python3/dist-packages/ctf_gameserver/web/static/;
    }

    # Serve uploaded files
    location /uploads/ {
        alias /var/www/ctf-gameserver-uploads/;
        add_header Content-Security-Policy "default-src 'none'";
    }

    location = /robots.txt {
        alias /usr/lib/python3/dist-packages/ctf_gameserver/web/static/robots.txt;
    }
}
EOF

rm /etc/nginx/sites-enabled/default
ln -s /etc/nginx/sites-available/ctf-gameserver /etc/nginx/sites-enabled/
nginx -t && sudo systemctl reload nginx

read -p "Enter mailgun password: " password

python3 <<EOF
import sys

file_path = "/etc/ctf-gameserver/web/prod_settings.py"

# Read all lines
with open(file_path, 'r') as f:
    lines = f.readlines()

password = input("Mailgun password: ")

# Replace line 84 (index 83)
lines[83] = f'ALLOWED_HOSTS = ["*", "localhost", "x3ero0.dev"]\n'
lines[54] = f"EMAIL_HOST = 'smtp.mailgun.org'\n"
lines[55] = f"EMAIL_PORT = 2525\n"
lines[56] = f"EMAIL_HOST_USER = 'admin@ctf.x3ero0.dev'\n"
lines[57] = f"EMAIL_HOST_PASSWORD = '$password'\n"

# Write back
with open(file_path, 'w') as f:
    f.writelines(lines)
EOF

systemctl restart uwsgi
echo 'psinghania929@gmail.com\nY\nN\n' | certbot --nginx -d x3ero0.dev

echo "[+] setup done, visit: http://x3ero0.dev/"
