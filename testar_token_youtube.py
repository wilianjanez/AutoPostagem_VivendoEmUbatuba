"""
Script para testar e debugar a autenticação do YouTube.
Execute: python testar_token_youtube.py
"""
import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()

CLIENT_ID     = os.getenv("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")

print(f"CLIENT_ID:     {CLIENT_ID[:40]}...")
print(f"CLIENT_SECRET: {CLIENT_SECRET[:10]}...")
print(f"REFRESH_TOKEN: {REFRESH_TOKEN[:30]}...")
print()

resp = requests.post(
    "https://oauth2.googleapis.com/token",
    data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type":    "refresh_token",
    },
    timeout=15
)

print(f"Status: {resp.status_code}")
print(f"Resposta completa:")
print(json.dumps(resp.json(), indent=2))