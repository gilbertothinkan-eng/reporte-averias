import io
import os
import json
import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.service_account import Credentials

# ============================================================
# CONFIGURACIÓN PRINCIPAL
# ============================================================

# ID del archivo Excel en Google Drive (tu archivo maestro)
EXCEL_FILE_ID = '13JtUWAGNeLHNjpRuthT_Vn0U2bmX9Jen'

# Nombre exacto de la hoja del archivo
SHEET_NAME = 'Hoja1'


def leer_excel_drive():
    """
    Lee el Excel maestro desde Google Drive usando credenciales
    guardadas en variables de entorno. Devuelve un DataFrame válido.
    """

    try:
        # 1. Leer credenciales desde variable de entorno
        service_account_str = os.getenv("SERVICE_ACCOUNT_JSON")

        if not service_account_str:
            print("[ERROR] La variable SERVICE_ACCOUNT_JSON no está configurada.")
            return pd.DataFrame()  # Evita crasheo

        service_account_info = json.loads(service_account_str)

        # 2. Crear credenciales
        creds = Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )

        # 3. Crear servicio de Drive
        service = build('drive', 'v3', credentials=creds)

        # 4. Descargar archivo Excel
        request = service.files().get_media(fileId=EXCEL_FILE_ID)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        fh.seek(0)

        # 5. Leer contenido con pandas
        df = pd.read_excel(fh, sheet_name=SHEET_NAME)

        print(f"[OK] Excel leído: {len(df)} filas • {len(df.columns)} columnas")
        return df

    except Exception as e:
        print(f"[ERROR] Fallo al leer el Excel desde Drive: {e}")
        return pd.DataFrame()  # retorna df vacío para no romper la app


# ============================================================
# PRUEBA DIRECTA
# ============================================================

if __name__ == '__main__':
    data = leer_excel_drive()
    print(data.head())
