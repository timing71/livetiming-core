#!/bin/bash

if [[ -z "$1" ]]; then
  echo "Usage: tag-and-release.sh <version number>"
  exit 1
fi

git checkout develop
git tag "$1"
git checkout master
git merge develop

git push --follow-tags origin master develop
