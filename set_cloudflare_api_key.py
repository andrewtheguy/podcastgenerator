#!/usr/bin/env python3
import keyring,sys
password = sys.stdin.read().rstrip()
keyring.set_password("podcastgenerator", "planethub.info", password)
