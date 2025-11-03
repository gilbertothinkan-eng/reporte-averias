import os
import io
from datetime import datetime
from werkzeug.utils import secure_filename
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.credentials import Credentials
import pandas as pd


def subir_reporte_a_drive(df, idintuni, archivos):
    """
    Crea una carpeta en Drive y sube:
    - Excel del reporte (subido desde memoria)
    - Todas las fotos en la misma carpeta

    Retorna: nombre_carpeta, link_publico
    """

    try:
        # ============================
        # AUTENTICACIÓN CON TOKEN OAUTH
        # ============================
        token_str = os.getenv("GOOGLE_OAUTH_TOKEN")
        if not token_str:
            print("[ERROR] Falta la variable GOOGLE_OAUTH_TOKEN en Render.")
            return None, None

        token_data = eval(token_str) if isinstance(token_str, str) else token_str

        creds = Credentials(
            token=token_data["token"],
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data["token_uri"],
            client_id=token_data["client_id"],
            client_secret=token_data.get("client_secret"),
            scopes=token_data["scopes"]
        )

        service = build('drive', 'v3', credentials=creds)

        # ============================
        # CREAR CARPETA PRINCIPAL
        # ============================
        carpeta_principal = 'Reportes Averías'
        resultado = service.files().list(
            q=f"name='{carpeta_principal}' and mimeType='application/vnd.google-apps.folder'",
            spaces='drive'
        ).execute()

        if not resultado.get('files'):
            metadata_principal = {
                'name': carpeta_principal,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            carpeta_principal_id = service.files().create(
                body=metadata_principal, fields='id'
            ).execute()['id']
        else:
            carpeta_principal_id = resultado['files'][0]['id']

        # ============================
        # CREAR SUBCARPETA DEL REPORTE
        # ============================
        nombre_carpeta = f"averia_{idintuni}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        metadata_subcarpeta = {
            'name': nombre_carpeta,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [carpeta_principal_id]
        }

        carpeta_id = service.files().create(
            body=metadata_subcarpeta,
            fields='id'
        ).execute()['id']

        # Hacer carpeta pública
        service.permissions().create(
            fileId=carpeta_id,
            body={"role": "reader", "type": "anyone"},
        ).execute()

        # ============================
        # SUBIR EXCEL DESDE MEMORIA
        # ============================
        excel_buffer = io.BytesIO()
        df.to_excel(excel_buffer, index=False)
        excel_buffer.seek(0)

        excel_metadata = {
            'name': f"reporte_averias_{idintuni}.xlsx",
            'parents': [carpeta_id]
        }

        media = MediaIoBaseUpload(
            excel_buffer,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            resumable=True
        )

        service.files().create(
            body=excel_metadata,
            media_body=media,
            fields='id'
        ).execute()

        print(f"[OK] Excel subido correctamente a {nombre_carpeta}")

        # ============================
        # SUBIR FOTOS
        # ============================
        for clave in archivos:
            for file in archivos.getlist(clave):
                if file and file.filename:
                    nombre_seguro = secure_filename(file.filename)
                    file_buffer = io.BytesIO(file.read())
                    file_buffer.seek(0)

                    metadata_foto = {'name': nombre_seguro, 'parents': [carpeta_id]}
                    media = MediaIoBaseUpload(file_buffer, mimetype=file.mimetype, resumable=True)

                    service.files().create(body=metadata_foto, media_body=media, fields='id').execute()
                    print(f"[OK] Foto subida: {nombre_seguro}")

        # ============================
        # LINK PÚBLICO
        # ============================
        link_publico = f"https://drive.google.com/drive/folders/{carpeta_id}?usp=sharing"

        print(f"[OK] Reporte subido en carpeta: {nombre_carpeta}")
        return nombre_carpeta, link_publico

    except Exception as e:
        print(f"[ERROR] No se pudo subir el reporte a Drive: {e}")
        return None, None
