#!/usr/bin/env bash
# Reminder helper. CTFd access tokens are created in the user's profile:
#   CTFd UI -> your avatar -> Access Tokens -> "Generate Token"
# Then store it in `.env` as CTFD_ADMIN_TOKEN=ctfd_xxx (preferred over
# username/password for API access).
echo "Generate an API token in the CTFd UI (profile -> Access Tokens),"
echo "then put it in .env as CTFD_ADMIN_TOKEN=ctfd_..."