"""
Script para gerar o Refresh Token do YouTube.
Execute UMA VEZ para obter o token permanente.
Atualiza o .env automaticamente!
"""
import json, os, re
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID     = os.getenv("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")

print(f"Usando Client ID: {CLIENT_ID[:40]}...")
print()

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

client_config = {
    "installed": {
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
        "token_uri":     "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8080"]
    }
}

with open("client_secrets.json", "w") as f:
    json.dump(client_config, f)

print("🌐 Abrindo navegador para autenticação...")
print("   Faça login com livingubatuba2021@gmail.com e autorize.")

flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", scopes=SCOPES)
credentials = flow.run_local_server(port=8080)

refresh_token = credentials.refresh_token

print("\n" + "="*60)
print("✅ AUTENTICAÇÃO CONCLUÍDA!")
print("="*60)
print(f"\nRefresh Token:\n{refresh_token}")

# Atualiza o .env automaticamente
env_path = ".env"
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        env_content = f.read()

    if "YOUTUBE_REFRESH_TOKEN=" in env_content:
        # Substitui o token existente
        env_content = re.sub(
            r"YOUTUBE_REFRESH_TOKEN=.*",
            f"YOUTUBE_REFRESH_TOKEN={refresh_token}",
            env_content
        )
        print("\n✅ .env atualizado automaticamente!")
    else:
        # Adiciona o token no final
        env_content += f"\nYOUTUBE_REFRESH_TOKEN={refresh_token}\n"
        print("\n✅ YOUTUBE_REFRESH_TOKEN adicionado ao .env!")

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content)
else:
    print(f"\n⚠️  Arquivo .env não encontrado.")
    print(f"   Adicione manualmente: YOUTUBE_REFRESH_TOKEN={refresh_token}")

print("="*60)

# Remove arquivo temporário
try:
    os.remove("client_secrets.json")
except:
    pass