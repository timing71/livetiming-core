#!/bin/bash
export $(cat livetiming.env | grep -v "^#" | xargs) && crossbar start --cbdir=crossbar --config dev.json
