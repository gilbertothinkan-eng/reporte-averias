from flask import Flask, render_template, request, redirect, url_for, session, send_file
import pandas as pd
from collections import Counter
import os
from typing import Dict, List, Optional, Set, Tuple

app = Flask(__name__)
app.secret_key = "gilberto_clave_super_secreta"

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

vehiculos: List[dict] = []
conteo_ciudades: Dict[str, int] = {}
datos_motos_original = pd.DataFrame()

# ================== EQUIVALENCIAS ==================
equivalencias = {
    "AK200ZW": 6,
    "ATUL RIK": 12,
    "AK250CR4 EFI": 2,
    "HIMALAYAN 452": 2,
    "HNTR 350": 2,
    "300AC": 2,
    "300DS": 2,
    "300RALLY": 2,
    "CLASSIC 350": 2,
    "CONTINENTAL GT 650": 2,
    "GBR 450": 2,
    "HIMALAYAN": 2,
    "INTERCEPTOR INT 650": 2,
    "METEOR 350": 2,
    "METEOR 350 STELLAR": 2,
    "SCRAM 411": 2,
    "SCRAM 411 SPIRIT": 2,
    "SHOTGUN 650": 2,
    "SUPER METEOR 650": 2,
    "AK110NV EIII": 1,
    "AK125CR4 EIII": 1,
    "AK125DYN PRO+": 1,
    "AK125FLEX EIII": 1,
    "AK125NKD EIII": 1,
    "AK125T-4": 1,
    "AK125TTR EIII": 1,
    "AK150CR4": 1,
    "AK200DS+": 1,
    "AK200TTR EIII": 1,
    "DYNAMIC RX": 1,
}

referencias_seleccionadas: Dict[str, List[dict]] = {}

# ================== UTILIDADES ==================
def get_equivalencia(cod_int: str) -> int:
    if pd.isna(cod_int):
        return 1
    return equivalencias.get(str(cod_int).strip().upper(), 1)

def encontrar_referencia_especial(cod_int: str, ciudad: str) -> Optional[dict]:
    ciudad = ciudad.upper()
    for r in referencias_seleccionadas.get(ciudad, []):
        if str(r["cod_int"]).strip().upper() == str(cod_int).strip().upper():
            return r
    return None

def _excel_safe_sheet_name(name: str) -> str:
    safe = str(name or "SIN_PLACA")
    for c in ['/', '\\', ':', '*', '?', '[', ']']:
        safe = safe.replace(c, "-")
    return safe[:31]

def _fecha_ts(v):
    try:
        return int(pd.to_datetime(v, dayfirst=True).timestamp())
    except Exception:
        return 10**18

# ================== LOGIN ==================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["usuario"] == "admin" and request.form["contrasena"] == "1234":
            session["usuario"] = "admin"
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Credenciales incorrectas")
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "usuario" not in session:
        return redirect(url_for("login"))
    mensaje = session.pop("mensaje", None)
    return render_template(
        "dashboard.html",
        ciudades=conteo_ciudades,
        referencias=referencias_seleccionadas,
        vehiculos=vehiculos,
        mensaje=mensaje,
    )

# ================== CARGA EXCEL ==================
@app.route("/upload", methods=["POST"])
def upload():
    global datos_motos_original, conteo_ciudades, referencias_seleccionadas

    file = request.files["file"]
    path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(path)

    df = pd.read_excel(path)
    df = df[df["Estado Satf"] == 40].copy()

    datos_motos_original = df
    conteo_ciudades = dict(Counter(df["Descr EXXIT"].str.upper()))

    referencias_seleccionadas = {}
    grp = df.groupby([df["Descr EXXIT"].str.upper(), "COD INT"]).size().reset_index(name="Cantidad")
    for _, r in grp.iterrows():
        eq = get_equivalencia(r["COD INT"])
        if eq > 1:
            referencias_seleccionadas.setdefault(r["Descr EXXIT"], []).append({
                "cod_int": r["COD INT"],
                "cantidad": int(r["Cantidad"]),
                "equivalencia": eq,
                "total": eq * int(r["Cantidad"]),
                "usar": True
            })

    session["mensaje"] = "Archivo cargado correctamente"
    return redirect(url_for("dashboard"))

# ================== VEHÍCULOS ==================
@app.route("/registrar_vehiculo", methods=["POST"])
def registrar_vehiculo():
    vehiculos.append({
        "transportadora": request.form["transportadora"],
        "conductor": request.form["conductor"],
        "placa": request.form["placa"],
        "cantidad_motos": int(request.form["cantidad_motos"]),
        "ciudades": [c.strip().upper() for c in request.form["ciudades"].split(",")]
    })
    return redirect(url_for("dashboard"))

# ================== PLANEADOR FINAL ==================
@app.route("/generar_planeador", methods=["POST"])
def generar_planeador():
    if datos_motos_original.empty or not vehiculos:
        session["mensaje"] = "Faltan datos o vehículos"
        return redirect(url_for("dashboard"))

    df = datos_motos_original.copy()
    df["CIUDAD"] = df["Descr EXXIT"].str.upper()
    df["DIR"] = df["Dirección 1"].str.upper().str.strip()
    df["_FECHA"] = df["Reserva"].apply(_fecha_ts)

    direcciones_usadas = set()
    usados = set()
    excel_path = os.path.join(UPLOAD_FOLDER, "Despacho_Final.xlsx")

    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        for v in vehiculos:
            ciudad = v["ciudades"][0]
            capacidad = v["cantidad_motos"]

            df_c = df[(df["CIUDAD"] == ciudad) & (~df.index.isin(usados))]
            bloques = {}

            for i, r in df_c.sort_values("_FECHA").iterrows():
                if r["DIR"] in direcciones_usadas:
                    continue

                eq = get_equivalencia(r["COD INT"])
                if eq > 1:
                    ref = encontrar_referencia_especial(r["COD INT"], ciudad)
                    if not ref or not ref["usar"]:
                        continue

                bloques.setdefault(r["DIR"], {"peso": 0, "idx": [], "fecha": r["_FECHA"]})
                bloques[r["DIR"]]["peso"] += eq
                bloques[r["DIR"]]["idx"].append(i)

            carga = 0
            seleccion = []
            for d in sorted(bloques, key=lambda x: bloques[x]["fecha"]):
                if carga + bloques[d]["peso"] <= capacidad:
                    seleccion.append(d)
                    carga += bloques[d]["peso"]

            filas = []
            for d in seleccion:
                direcciones_usadas.add(d)
                filas.extend(bloques[d]["idx"])
                usados.update(bloques[d]["idx"])

            hoja = _excel_safe_sheet_name(v["placa"])
            header = pd.DataFrame([{
                "Placa": v["placa"],
                "Ciudad": ciudad,
                "Capacidad": capacidad,
                "Ocupado": carga
            }])
            header.to_excel(writer, sheet_name=hoja, index=False)
            df.loc[filas].to_excel(writer, sheet_name=hoja, startrow=3, index=False)

    return send_file(excel_path, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
