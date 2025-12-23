from flask import Flask, render_template, request, redirect, url_for, session, send_file
import pandas as pd
from collections import Counter, defaultdict
import os
from typing import Dict, List, Optional, Set, Tuple, Any

# =========================================================
# CONFIGURACIÓN
# =========================================================
app = Flask(__name__)
app.secret_key = "gilberto_clave_super_secreta"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

vehiculos: List[dict] = []
conteo_ciudades: Dict[str, int] = {}
datos_motos_original = pd.DataFrame()
referencias_seleccionadas: Dict[str, List[dict]] = {}

# =========================================================
# EQUIVALENCIAS (COD INT -> ESPACIOS)
# =========================================================
equivalencias = {
    "AK200ZW": 6, "ATUL RIK": 12, "AK250CR4 EFI": 2, "HIMALAYAN 452": 2,
    "HNTR 350": 2, "300AC": 2, "300DS": 2, "300RALLY": 2,
    "CLASSIC 350": 2, "CONTINENTAL GT 650": 2, "GBR 450": 2,
    "HIMALAYAN": 2, "INTERCEPTOR INT 650": 2, "METEOR 350": 2,
    "METEOR 350 STELLAR": 2, "SCRAM 411": 2, "SCRAM 411 SPIRIT": 2,
    "SHOTGUN 650": 2, "SUPER METEOR 650": 2,
    "AK110NV EIII": 1, "AK125CR4 EIII": 1, "AK125DYN PRO+": 1,
    "AK125FLEX EIII": 1, "AK125NKD EIII": 1, "AK125T-4": 1,
    "AK125TTR EIII": 1, "AK150CR4": 1, "AK200DS+": 1,
    "AK200TTR EIII": 1, "DYNAMIC RX": 1,
}

# =========================================================
# HELPERS
# =========================================================
def norm(x: Any) -> str:
    """Normaliza strings (trim, upper, colapsa espacios)."""
    return " ".join(str(x).replace("\n", " ").strip().upper().split())

def get_equivalencia(cod: Any) -> int:
    return equivalencias.get(norm(cod), 1)

def age_score(fecha: pd.Timestamp) -> int:
    """Score para antigüedad: más antiguo => mayor score."""
    if pd.isna(fecha):
        return 0
    return 10_000_000 - fecha.toordinal()

def knapsack(items: List[Tuple[int, int, int]], capacidad: int) -> Set[int]:
    """
    items: (item_id, peso, age_score)
    Objetivo (en orden):
      1) maximizar peso
      2) maximizar antigüedad
      3) minimizar número de direcciones
    """
    dp = [None] * (capacidad + 1)
    dp[0] = (0, 0, 0, set())  # peso, edad, dirs, ids

    for item_id, peso, edad in items:
        if peso <= 0 or peso > capacidad:
            continue
        for c in range(capacidad, peso - 1, -1):
            prev = dp[c - peso]
            if not prev:
                continue
            cand = (prev[0] + peso, prev[1] + edad, prev[2] + 1, prev[3] | {item_id})
            cur = dp[c]
            if not cur or (
                cand[0] > cur[0] or
                (cand[0] == cur[0] and cand[1] > cur[1]) or
                (cand[0] == cur[0] and cand[1] == cur[1] and cand[2] < cur[2])
            ):
                dp[c] = cand

    best = max((x for x in dp if x), default=None)
    return best[3] if best else set()

def excel_safe_sheet(name: str) -> str:
    s = (name or "SIN_PLACA").strip()
    for ch in ['/', '\\', ':', '*', '?', '[', ']']:
        s = s.replace(ch, '-')
    return (s[:31] if len(s) > 31 else s) or "SIN_PLACA"

# =========================================================
# ROUTES
# =========================================================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("usuario") == "admin" and request.form.get("contrasena") == "1234":
            session["usuario"] = "admin"
            return redirect("/dashboard")
        return render_template("login.html", error="Credenciales inválidas")
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "usuario" not in session:
        return redirect("/")
    return render_template(
        "dashboard.html",
        ciudades=conteo_ciudades,
        vehiculos=vehiculos,
        referencias=referencias_seleccionadas,
        mensaje=session.pop("mensaje", None)
    )

@app.route("/upload", methods=["POST"])
def upload():
    global datos_motos_original, conteo_ciudades, referencias_seleccionadas

    file = request.files.get("file")
    if not file:
        session["mensaje"] = "❌ No se recibió archivo."
        return redirect("/dashboard")

    path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(path)

    df = pd.read_excel(path)

    # VALIDACIONES DURAS
    obligatorias = ["Estado Satf", "Descr EXXIT", "Dirección 1", "COD INT", "Fecha de reserva"]
    faltantes = [c for c in obligatorias if c not in df.columns]
    if faltantes:
        session["mensaje"] = f"❌ Faltan columnas obligatorias: {', '.join(faltantes)}"
        return redirect("/dashboard")

    # FILTRO ESTADO
    datos_motos_original = df[df["Estado Satf"] == 40].copy()

    # NORMALIZACIONES
    datos_motos_original["CIUDAD"] = datos_motos_original["Descr EXXIT"].apply(norm)
    datos_motos_original["DIR"] = datos_motos_original["Dirección 1"].apply(norm)

    # FECHA OFICIAL (ÚNICA)
    datos_motos_original["FECHA"] = pd.to_datetime(
        datos_motos_original["Fecha de reserva"],
        errors="coerce",
        dayfirst=True
    )

    # CONTEO CIUDADES (PLANEADOR)
    conteo_ciudades = dict(Counter(datos_motos_original["CIUDAD"]))

    # REFERENCIAS ESPECIALES POR CIUDAD
    referencias_seleccionadas.clear()
    for (ciudad, cod), grp in datos_motos_original.groupby(["CIUDAD", "COD INT"]):
        eq = get_equivalencia(cod)
        if eq > 1:
            referencias_seleccionadas.setdefault(ciudad, []).append({
                "cod": norm(cod),
                "usar": True
            })

    session["mensaje"] = "✅ Archivo cargado correctamente"
    return redirect("/dashboard")

@app.route("/registrar_vehiculo", methods=["POST"])
def registrar_vehiculo():
    ciudades = [norm(c) for c in request.form.get("ciudades", "").split(",") if c.strip()]
    if not ciudades:
        session["mensaje"] = "❌ Debes indicar al menos una ciudad."
        return redirect("/dashboard")

    vehiculos.append({
        "transportadora": request.form.get("transportadora", "").strip(),
        "conductor": request.form.get("conductor", "").strip(),
        "placa": request.form.get("placa", "").strip(),
        "capacidad": int(request.form.get("cantidad_motos", 0)),
        "ciudades": ciudades
    })
    session["mensaje"] = "✅ Vehículo registrado"
    return redirect("/dashboard")

@app.route("/generar_planeador", methods=["POST"])
def generar_planeador():
    if datos_motos_original.empty or not vehiculos:
        session["mensaje"] = "❌ No hay datos o vehículos."
        return redirect("/dashboard")

    df = datos_motos_original.copy()

    usados_dirs: Set[str] = set()
    usados_idx: Set[int] = set()
    excel_path = os.path.join(UPLOAD_FOLDER, "Despacho_Final.xlsx")

    # =====================================================
    # DETECCIÓN DE COMPETENCIA REAL (MISMO POOL)
    # =====================================================
    pool_map = defaultdict(list)
    for v in vehiculos:
        key = tuple(sorted(v["ciudades"]))
        pool_map[key].append(v)

    vehiculos_ordenados: List[dict] = []
    for pool, vs in pool_map.items():
        if len(vs) == 1:
            vehiculos_ordenados.extend(vs)
        else:
            # Optimización SOLO aquí
            vs_sorted = sorted(
                vs,
                key=lambda v: (len(v["ciudades"]), v["capacidad"])
            )
            vehiculos_ordenados.extend(vs_sorted)

    # =====================================================
    # ASIGNACIÓN
    # =====================================================
    total_asignadas = 0

    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        for v in vehiculos_ordenados:
            pool_ciudades = set(v["ciudades"])
            cap = v["capacidad"]

            bloques: Dict[str, dict] = {}
            for idx, r in df.iterrows():
                if idx in usados_idx:
                    continue
                if r["CIUDAD"] not in pool_ciudades:
                    continue
                if r["DIR"] in usados_dirs or not r["DIR"]:
                    continue

                eq = get_equivalencia(r["COD INT"])
                if eq > 1:
                    refs = referencias_seleccionadas.get(r["CIUDAD"], [])
                    if not any(x["cod"] == norm(r["COD INT"]) and x["usar"] for x in refs):
                        continue

                b = bloques.setdefault(r["DIR"], {"peso": 0, "idx": [], "fecha": None})
                b["peso"] += eq
                b["idx"].append(idx)
                if pd.notna(r["FECHA"]):
                    b["fecha"] = min(b["fecha"], r["FECHA"]) if b["fecha"] else r["FECHA"]

            keys = list(bloques.keys())
            items: List[Tuple[int, int, int]] = []
            for i, k in enumerate(keys):
                if 0 < bloques[k]["peso"] <= cap:
                    items.append((i, bloques[k]["peso"], age_score(bloques[k]["fecha"])))

            sel = knapsack(items, cap)

            idxs: List[int] = []
            carga = 0
            for i in sel:
                d = keys[i]
                usados_dirs.add(d)
                idxs.extend(bloques[d]["idx"])
                carga += bloques[d]["peso"]

            usados_idx.update(idxs)
            total_asignadas += len(idxs)

            hoja = excel_safe_sheet(v["placa"])
            encabezado = pd.DataFrame([{
                "Transportadora": v["transportadora"],
                "Conductor": v["conductor"],
                "Placa": v["placa"],
                "Ciudades": ", ".join(pool_ciudades),
                "Capacidad": cap,
                "Ocupado": carga,
                "Direcciones": len(sel)
            }])

            encabezado.to_excel(writer, sheet_name=hoja, index=False, startrow=0)
            df.loc[idxs].to_excel(writer, sheet_name=hoja, index=False, startrow=3)

    if total_asignadas == 0:
        try:
            os.remove(excel_path)
        except Exception:
            pass
        session["mensaje"] = (
            "⚠️ No se asignó ninguna moto. "
            "Revisa capacidad, referencias especiales o ciudades."
        )
        return redirect("/dashboard")

    return send_file(excel_path, as_attachment=True)

# =========================================================
if __name__ == "__main__":
    app.run(debug=True)
