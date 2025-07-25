#!/bin/bash

set -xe

apt update
apt install -y devscripts dpkg-dev equivs neovim postgresql python3-psycopg2 nginx uwsgi uwsgi-plugin-python3 postfix wireguard-tools certbot python3-certbot-nginx iptables iproute2 python3-pip python3-venv
mk-build-deps --install debian/control
dpkg-buildpackage --unsigned-changes --unsigned-buildinfo

echo "[+] Start ansible script now and hit CTRL-C when its done."
python3 -m http.server 8000 -d /root/ --bind 0.0.0.0

# create team_uploads directory
mkdir -p /var/www/team-downloads

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

systemctl restart uwsgi

cp ./academy-logo.png /var/www/gameserver_uploads/

certbot --nginx -d x3ero0.dev --non-interactive --agree-tos --email you@yourdomain.com --no-eff-email

chmod +w /var/crash

# To allow packets to route from one team to another
echo "net.ipv4.ip_forward = 1" | tee /etc/sysctl.d/99-ipforward.conf
sysctl --system

mkdir -p /opt/checker

# create checker env
python3 -m venv /opt/env/
ln -s /usr/lib/python3/dist-packages/ctf_gameserver /opt/env/lib/python3.12/site-packages/ctf_gameserver

echo "[+] setup done, visit: http://x3ero0.dev/"
