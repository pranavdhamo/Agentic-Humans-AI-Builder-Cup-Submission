#!/usr/bin/env bash
# GCE startup script (runs as root on first boot): install GnuCOBOL and fetch the CardDemo source.
exec > >(tee -a /var/log/carddemo-bootstrap.log) 2>&1
set -ex
BASE=/opt/carddemo-env
mkdir -p "$BASE"
apt-get update
apt-get install -y git gnucobol3 || apt-get install -y git gnucobol
[ -d "$BASE/carddemo" ] || git clone --depth 1 https://github.com/aws-samples/aws-mainframe-modernization-carddemo.git "$BASE/carddemo"
touch "$BASE/.packages-ready"
