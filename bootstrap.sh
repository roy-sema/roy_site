#!/usr/bin/env bash

apt-get update
apt-get install python3-pip redis-server

# Set up virtual env
if ! [ -L /vagrant/env ]; then
  echo "setting up virtual env"
  cd /vagrant
  virtualenv env
  . env/bin/activate
  pip install -r requirements.txt
fi
