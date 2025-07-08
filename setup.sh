#!/bin/bash

set -xe

apt update
apt install -y devscripts dpkg-dev equivs neovim postgresql python3-psycopg2 nginx uwsgi uwsgi-plugin-python3 postfix
mk-build-deps --install debian/control
dpkg-buildpackage --unsigned-changes --unsigned-buildinfo
cd /root/ && python3 -m http.server 8000 --bind 0.0.0.0 &
