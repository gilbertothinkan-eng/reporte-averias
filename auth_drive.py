import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ============================================================
# AUTENTICACIÓN A GOOGLE DRIVE (Service Account por ENV VAR)
# ============================================================
# Usa la variable de entorno GOOGLE_SERVICE_ACCOUNT_JSON
# para cargar el JSON de credenciales de forma segura en Render.
# Si no existe, intenta fallback a service_account.json (ejecución local).
# ============================================================

SCOPES = ['https://www.googleapis.com/auth/drive']

def obtener_servicio_drive():
    creds = None
    sa_env = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_env:
        info = json.loads(sa_env)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        # Modo local: archivo físico
        service_account_file = os.path.join(os.path.dirname(__file__), "service_account.json")
        creds = Credentials.from_service_account_file(service_account_file, scopes=SCOPES)

    return build('drive', 'v3', credentials=creds)
