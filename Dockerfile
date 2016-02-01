FROM python:2.7

RUN mkdir /app
WORKDIR /app
ADD . /app

RUN python setup.py install
