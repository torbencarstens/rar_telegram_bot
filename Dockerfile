FROM python:3.7-rc
MAINTAINER chabare95@gmail.com

WORKDIR /usr/src/app

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ['python', '-B', '-O', '-OO', 'main.py']