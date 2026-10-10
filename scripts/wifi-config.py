#!/usr/bin/env python3
"""Create a private maintenance Wi-Fi config without putting credentials in argv."""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import re

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=Path('private/maintenance.yaml'))
parser.add_argument('--wpa2-derived-key', action='store_true', help='Store a derived WPA2 PSK; incompatible with WPA3-only networks')
args = parser.parse_args()
ssid = input('Wi-Fi SSID: ')
country = input('Two-letter regulatory country code: ').upper()
password = getpass.getpass('Wi-Fi passphrase: ')
if not 1 <= len(ssid.encode()) <= 32 or not re.fullmatch('[A-Z]{2}', country):
    parser.error('Invalid SSID length or country code')
if not 8 <= len(password) <= 63:
    parser.error('Passphrase must contain 8 to 63 characters')
if args.wpa2_derived_key:
    password = hashlib.pbkdf2_hmac('sha1', password.encode(), ssid.encode(), 4096, 32).hex()
quote = json.dumps
content = f'''apiVersion: v1alpha1
kind: WifiConfig
name: wlan0
countryCode: {quote(country)}
networks:
  - ssid: {quote(ssid)}
    psk: {quote(password)}
---
apiVersion: v1alpha1
kind: LinkConfig
name: wlan0
up: true
---
apiVersion: v1alpha1
kind: DHCPv4Config
name: wlan0
'''
args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
    output.write(content)
print(f'Created {args.output}; this config and any image embedding it are private.')
