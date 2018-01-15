#!/usr/bin/env bash

cd /vagrant
. env/bin/activate
export FLASK_APP=app.py
flask run --host=0.0.0.0
