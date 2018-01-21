#!/bin/bash
export $(cat livetiming.env | xargs) && crossbar start --cbdir=crossbar --config dev.json
