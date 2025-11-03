import io
from datetime import datetime
from googleapiclient.http import MediaIoBaseUpload
from auth_drive import obtener_servicio_drive
from werkzeug.utils import secure_filename
import pandas as pd

# ============================================================
# SUBIR DIRECTO A GOOGLE DRIVE (SIN ARCHIVOS LOCALES)
# ============================================================

def _asegurar_carpeta(service, nombre, parent_id=None):
    q = f"name = '{nombre}' and mimeType = 'application/vnd.google-apps.folder'"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    res = service.files().list(q=q, fields="files(id,name,parents)").execute()
    files = res.get('files', [])
    if files:
        return files[0]['id']
    meta = {'name': nombre, 'mimeType': 'application/vnd.google-apps.folder'}
    if parent_id:
        meta['parents'] = [parent_id]
    return service.files().create(body=meta, fields='id').execute()['id']

def _subir_bytes(service, carpeta_id, data_bytes, filename, mimetype):
    media = MediaIoBaseUpload(io.BytesIO(data_bytes), mimetype=mimetype, resumable=False)
    meta = {'name': filename, 'parents': [carpeta_id]}
    return service.files().create(body=meta, media_body=media, fields='id').execute()['id']

def subir_reporte_a_drive(df, idintuni, archivos):
    """
    Crea estructura en Drive y sube:
    - Excel del reporte (en memoria)
    - Todas las fotos recibidas (stream, sin guardar en disco)
    Retorna: nombre_carpeta, link_publico
    """
    try:
        service = obtener_servicio_drive()

        # === Carpeta raíz del proyecto ===
        root_id = _asegurar_carpeta(service, 'Reportes Averías')

        # === Subcarpeta por fecha (YYYY-MM-DD) ===
        hoy = datetime.now().strftime('%Y-%m-%d')
        fecha_id = _asegurar_carpeta(service, hoy, parent_id=root_id)

        # === Carpeta del reporte (ID + timestamp) ===
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        nombre_carpeta = f"averia_{idintuni}_{timestamp}"
        carpeta_id = _asegurar_carpeta(service, nombre_carpeta, parent_id=fecha_id)

        # === Excel en memoria ===
        excel_buf = io.BytesIO()
        with pd.ExcelWriter(excel_buf, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='reporte')
        excel_bytes = excel_buf.getvalue()
        _subir_bytes(service, carpeta_id, excel_bytes, f"reporte_averias_{idintuni}.xlsx",
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # === Fotos (stream) ===
        for key in archivos:
            # Esperamos claves como 'foto[]' o similares; pueden venir múltiples
            file_storage = archivos.get(key)
            if not file_storage:
                continue
            # file_storage puede ser lista si es múltiple
            values = file_storage if isinstance(file_storage, list) else [file_storage]
            for fs in values:
                if not getattr(fs, 'filename', ''):
                    continue
                nombre_seguro = secure_filename(fs.filename)
                contenido = fs.stream.read()
                if not contenido:
                    continue
                _subir_bytes(service, carpeta_id, contenido, nombre_seguro, fs.mimetype or 'application/octet-stream')

        link_publico = f"https://drive.google.com/drive/folders/{carpeta_id}?usp=sharing"
        return nombre_carpeta, link_publico

    except Exception as e:
        print(f"[ERROR] No se pudo subir el reporte a Drive: {e}")
        return None, None
