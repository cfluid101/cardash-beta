#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 manual_test.py
result=$?
printf '\nPress Return to close this window.\n'
read -r
exit "$result"
