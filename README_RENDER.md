# Despliegue en Render — Reporte de Averías (Flask)

## 1) Archivos clave incluidos
- `auth_drive.py` → Usa `GOOGLE_SERVICE_ACCOUNT_JSON` para autenticarse (sin archivo físico).
- `guardar_en_drive.py` → Sube Excel y fotos DIRECTO a Drive (sin guardar en disco).
- `Procfile` → Indica a Render cómo arrancar: `gunicorn app:app`.
- `render.yaml` → Config opcional para deploy automático.
- `.renderignore` / `.gitignore` → Evita subir credenciales y archivos temporales.
- `requirements.txt` → Dependencias actualizadas.

## 2) Variables en Render
- Crear variable **`GOOGLE_SERVICE_ACCOUNT_JSON`** con el **contenido completo** del JSON de tu service account.
  *Entra al archivo `service_account.json`, copia TODO el contenido (incluye llaves, comillas, etc.) y pégalo tal cual en el valor de la variable.*

## 3) Pasos de Deploy (interfaz web de Render)
1. Crea un nuevo **Web Service** en https://dashboard.render.com/
2. Conecta tu repo (o sube un repo nuevo con este proyecto).
3. En **Environment** elige **Python**.
4. En **Build Command** pon: `pip install -r requirements.txt`
5. En **Start Command** pon: `gunicorn app:app`
6. Ve a **Environment → Add Environment Variable** y crea:
   - Key: `GOOGLE_SERVICE_ACCOUNT_JSON`
   - Value: **(pega el JSON completo)**
7. Deploy.

## 4) Uso
- Endpoint `/subir_excel` para cargar datos.
- Endpoint `/guardar_reporte` genera Excel y sube fotos directo a Drive.
- El HTML de confirmación devuelve el link de la carpeta.

## 5) Notas
- El almacenamiento local (`uploads/`) ya no se usa en Render.
- En local, si quieres seguir probando, puedes mantener `service_account.json`.
- No publiques `service_account.json` en el repositorio.
