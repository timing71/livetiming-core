#!/bin/bash
pushd web
mkdir .git
npm version $@
rmdir .git
popd
