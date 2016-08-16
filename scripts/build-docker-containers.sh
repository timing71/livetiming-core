#!/bin/sh
echo Building docker containers for livetiming...
docker build -t crossbar -f docker/crossbar.docker .
docker build -t livetiming-base -f docker/livetiming-base.docker .
docker build -t livetiming-directory -f docker/livetiming-directory.docker .
docker build -t livetiming-service -f docker/livetiming-service.docker .
docker build -t livetiming-recording -f docker/livetiming-recording.docker .
