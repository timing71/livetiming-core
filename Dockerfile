FROM python:2.7

RUN mkdir /app
WORKDIR /app
ADD . /app

RUN pip install --upgrade pip
RUN python setup.py develop
