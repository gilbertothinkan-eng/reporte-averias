from flask import Flask, render_template, request, jsonify
import pandas as pd
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from leer_excel_drive import leer_excel_drive
from guardar_en_drive import subir_reporte_a_drive

print(">>> Iniciando subida a Drive...")

app = Flask(__name__)

# Ruta del archivo base (motos en tránsito)
DATA_PATH = 'static/data/motos_transito.xlsx'

# Carpeta donde se guardan los reportes locales
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ===============================================================
# 1. Subir el Excel de Motos en Tránsito
# ===============================================================
@app.route('/subir_excel', methods=['GET', 'POST'])
def subir_excel():
    if request.method == 'POST':
        file = request.files['file']
        if file and file.filename.endswith('.xlsx'):
            os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
            file.save(DATA_PATH)
            return "<h3>✅ Archivo cargado correctamente.</h3><a href='/'>Ir al formulario</a>"
        else:
            return "<h3>⚠️ Cargue un archivo con extensión .xlsx</h3>"
    return render_template('subir_excel.html')


# ===============================================================
# 2. Formulario principal
# ===============================================================
@app.route('/')
def formulario():
    if not os.path.exists(DATA_PATH):
        return "<h3>⚠️ Aún no se ha cargado el archivo de motos en tránsito.</h3><a href='/subir_excel'>Subir archivo</a>"
    df = leer_excel_drive()
    idintuni_unicos = sorted(df['IDIntUni'].dropna().unique().tolist())
    return render_template('form.html', idintuni=idintuni_unicos)


# ===============================================================
# 3. Obtener series asociadas al traslado
# ===============================================================
@app.route('/get_series/<idintuni>')
def get_series(idintuni):
    df = leer_excel_drive()
    filtrado = df[df['IDIntUni'] == idintuni][['IDSerie']].dropna()
    series = sorted(filtrado['IDSerie'].unique().tolist())
    return jsonify(series)


# ===============================================================
# 4. Obtener datos del IDSerie
# ===============================================================
@app.route('/get_datos/<idserie>')
def get_datos(idserie):
    df = leer_excel_drive()
    fila = df[df['IDSerie'] == idserie].head(1)
    if fila.empty:
        return jsonify({'Articulo': '', 'Descripcion': ''})
    datos = {
        'Articulo': str(fila['Articulo'].values[0]),
        'Descripcion': str(fila['Descripcion'].values[0])
    }
    return jsonify(datos)


# ===============================================================
# 5. Recibir formulario y guardar reporte + Enviar a Drive
# ===============================================================
@app.route('/guardar_reporte', methods=['POST'])
def guardar_reporte():
    try:
        fecha = request.form.get('fecha')
        idintuni = request.form.get('idintuni')
        punto_venta = request.form.get('punto_venta')
        centro_servicio = request.form.get('centro_servicio')
        responsable = request.form.get('responsable')
        transportadora = request.form.get('transportadora')
        placa = request.form.get('placa')

        # Construir DataFrame con los registros enviados
        registros = []
        bloques = zip(
            request.form.getlist('idserie[]'),
            request.form.getlist('articulo[]'),
            request.form.getlist('descripcion[]'),
            request.form.getlist('n_reporte[]'),
            request.form.getlist('pieza_solicitada[]'),
            request.form.getlist('novedad[]'),
            request.form.getlist('metodo_recuperacion[]'),
            request.form.getlist('costo_reparacion[]')
        )

        for bloque in bloques:
            registros.append({
                'Fecha': fecha,
                'IDIntUni': idintuni,
                'PuntoVenta': punto_venta,
                'CentroServicio': centro_servicio,
                'Responsable': responsable,
                'Transportadora': transportadora,
                'Placa': placa,
                'IDSerie': bloque[0],
                'Articulo': bloque[1],
                'Descripcion': bloque[2],
                'N°Reporte': bloque[3],
                'PiezaSolicitada': bloque[4],
                'Novedad': bloque[5],
                'MetodoRecuperacion': bloque[6],
                'CostoReparacion': bloque[7]
            })

        df = pd.DataFrame(registros)
        print(">>> Verificando contenido antes de subir a Drive...")
        print(df.head())
        print(">>> Archivos recibidos:", request.files.keys())
        print(">>> Cantidad de registros en DataFrame:", len(df))

        # 🔵 Enviar a Google Drive y obtener nombre carpeta + link
        nombre_carpeta, link_publico = subir_reporte_a_drive(df, idintuni, request.files)

        # ✅ Pantalla final estilizada
        return f"""
<div style="
    font-family: Arial; 
    max-width: 500px; 
    margin: 40px auto; 
    padding: 20px; 
    border-radius: 12px; 
    background-color: #f1f8ff; 
    text-align: center; 
    box-shadow: 0 0 10px rgba(0,0,0,0.15);
">
    <h2 style="color: #2e8b57; margin-bottom:14px;">✅ Reporte Generado con Éxito</h2>
    
    <p style="font-size: 17px; color: #333; margin-top: 0;">
        La carpeta fue creada en Google Drive:<br><br>
        <b>{nombre_carpeta}</b>
    </p>

    <button onclick="(function() {{
        try {{
            if (navigator.share) {{
                navigator.share({{
                    title: 'Reporte de Avería',
                    text: '📁 Evidencia del reporte',
                    url: '{link_publico}'
                }});
            }} else {{
                navigator.clipboard.writeText('{link_publico}');
                alert('✅ Link copiado');
            }}
        }} catch (e) {{
            navigator.clipboard.writeText('{link_publico}');
            alert('✅ Link copiado');
        }}
    }})()"
        style="padding: 12px 20px; background-color: #007bff; color: white; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; margin: 8px;">
        📤 Compartir Link
    </button>

    <button onclick="window.location.href = '/?r=' + new Date().getTime();" 
        style="padding: 12px 20px; background-color: #6c757d; color: white; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; margin: 8px;">
        ⬅️ Volver
    </button>
</div>
"""

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return f"<h3>❌ Error al guardar reporte: {str(e)}</h3>"


# ===============================================================
# EJECUCIÓN LOCAL
# ===============================================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
