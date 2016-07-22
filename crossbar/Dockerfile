FROM debian:jessie

ENV PYTHONUNBUFFERED 1

RUN apt-get update
RUN apt-get -y install build-essential libssl-dev libffi-dev libreadline-dev libbz2-dev libsqlite3-dev libncurses5-dev python-pip python-dev
RUN apt-get clean
RUN pip install --upgrade cffi
RUN pip install crossbar

RUN mkdir /config
WORKDIR /config
COPY ./config.json /config

EXPOSE 8080

ENTRYPOINT ["crossbar", "start", "--cbdir", "/config"]
