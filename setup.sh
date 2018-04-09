#!/bin/bash

pip install virtualenv
virtualenv --no-site-packages --distribute .venv
source .venv/bin/activate
pip install -r requirements.txt
