import io
import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.service_account import Credentials

# ============================================================
# CONFIGURACIÓN PRINCIPAL
# ============================================================

# Archivo de credenciales del servicio
SERVICE_ACCOUNT_FILE = 'credenciales_drive.json'

# ID del archivo Excel en Google Drive (tu archivo maestro)
EXCEL_FILE_ID = '13JtUWAGNeLHNjpRuthT_Vn0U2bmX9Jen'

# Nombre exacto de la hoja del archivo
SHEET_NAME = 'Hoja1'

# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def leer_excel_drive():
    """
    Lee directamente el Excel maestro desde Google Drive usando
    una cuenta de servicio y devuelve un DataFrame de pandas.
    No modifica ninguna parte de la app ni archivos locales.
    """
    try:
        # Autenticación con la cuenta de servicio
        creds = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )

        # Crear servicio de Drive
        service = build('drive', 'v3', credentials=creds)

        # Descargar archivo Excel
        request = service.files().get_media(fileId=EXCEL_FILE_ID)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        fh.seek(0)

        # Leer contenido con pandas
        df = pd.read_excel(fh, sheet_name=SHEET_NAME)
        print(f"[OK] Archivo leído correctamente: {len(df)} filas, {len(df.columns)} columnas.")
        return df

    except Exception as e:
        print(f"[ERROR] Fallo al leer el Excel desde Drive: {e}")
        return None


# ============================================================
# PRUEBA DIRECTA (solo si ejecutas este módulo manualmente)
# ============================================================

if __name__ == '__main__':
    data = leer_excel_drive()
    if data is not None:
        print(data.head())
