#!/bin/bash
pushd web > /dev/null
mkdir .git
npm version $@
rmdir .git
popd > /dev/null
