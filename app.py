from flask import Flask, render_template, request, redirect, url_for, session, send_file
import pandas as pd
from collections import Counter
import os
from typing import Dict, List, Optional, Set, Tuple, Any

app = Flask(__name__)
app.secret_key = "gilberto_clave_super_secreta"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

vehiculos: List[dict] = []
conteo_ciudades: Dict[str, int] = {}
datos_motos_original = pd.DataFrame()

# DICCIONARIO COMPLETO DE EQUIVALENCIAS basado en COD INT (columna AC)
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

# Para guardar qué referencias selecciona el usuario (SOLO especiales)
referencias_seleccionadas: Dict[str, List[dict]] = {}


def get_equivalencia(cod_int: str) -> int:
    """Retorna la equivalencia en espacios basada en COD INT."""
    if pd.isna(cod_int) or str(cod_int).strip() == "":
        return 1
    return equivalencias.get(str(cod_int).strip().upper(), 1)


def encontrar_referencia_especial(cod_int: str, ciudad: str) -> Optional[dict]:
    """Busca una referencia especial en la lista de referencias seleccionadas de una ciudad."""
    ciudad = str(ciudad).strip().upper()
    if ciudad not in referencias_seleccionadas:
        return None

    cod_int_str = str(cod_int).strip().upper()
    for r in referencias_seleccionadas[ciudad]:
        if str(r["cod_int"]).strip().upper() == cod_int_str:
            return r
    return None


def _excel_safe_sheet_name(name: str) -> str:
    """Excel limita nombre de hoja a 31 chars y prohíbe ciertos símbolos."""
    safe = (str(name) if name is not None else "SIN_PLACA").strip()
    for ch in ['/', '\\', ':', '*', '?', '[', ']']:
        safe = safe.replace(ch, "-")
    safe = safe.strip() or "SIN_PLACA"
    return safe[:31] if len(safe) > 31 else safe


def _norm_dir(x: Any) -> str:
    """Normalización fuerte de dirección (para evitar duplicados por espacios/saltos)."""
    if pd.isna(x):
        return ""
    s = str(x).replace("\n", " ").replace("\r", " ").strip()
    s = " ".join(s.split())
    return s.upper()


def _age_score(min_date: Optional[pd.Timestamp]) -> int:
    """
    Convierte antigüedad a score para desempates:
    Más antiguo => score más alto.
    """
    if min_date is None or pd.isna(min_date):
        return 0
    try:
        ordinal = int(min_date.to_pydatetime().date().toordinal())
        return 10_000_000 - ordinal  # más antiguo => mayor score
    except Exception:
        return 0


def _knapsack_max_peso_age_min_items(items: List[Tuple[int, int, int]], capacidad: int) -> Set[int]:
    """
    Knapsack 0/1:
    Objetivo (en este orden):
    1) maximiza peso <= capacidad  (LLENADO MANDA)
    2) empate: más antiguo (age_score mayor)
    3) empate: menor #items (menos direcciones)
    items: [(item_id, peso, age_score)]
    retorna: {item_id,...}
    """
    if capacidad <= 0 or not items:
        return set()

    # dp[c] = (peso_total, age_total, num_items, set_ids)
    dp: List[Optional[Tuple[int, int, int, Set[int]]]] = [None] * (capacidad + 1)
    dp[0] = (0, 0, 0, set())

    for item_id, w, age_sc in items:
        if w <= 0 or w > capacidad:
            continue
        for c in range(capacidad, w - 1, -1):
            prev = dp[c - w]
            if prev is None:
                continue
            cand = (prev[0] + w, prev[1] + age_sc, prev[2] + 1, prev[3] | {item_id})
            cur = dp[c]
            if cur is None:
                dp[c] = cand
            else:
                # comparar por (peso, age, -num_items)
                if (
                    cand[0] > cur[0]
                    or (cand[0] == cur[0] and cand[1] > cur[1])
                    or (cand[0] == cur[0] and cand[1] == cur[1] and cand[2] < cur[2])
                ):
                    dp[c] = cand

    best: Optional[Tuple[int, int, int, Set[int]]] = None
    for c in range(capacidad, -1, -1):
        st = dp[c]
        if st is None:
            continue
        if best is None:
            best = st
        else:
            if (
                st[0] > best[0]
                or (st[0] == best[0] and st[1] > best[1])
                or (st[0] == best[0] and st[1] == best[1] and st[2] < best[2])
            ):
                best = st

    return best[3] if best else set()


def _tiene_competencia_real(vehiculos_lista: List[dict]) -> bool:
    """
    Competencia real = 2+ vehículos con el MISMO pool de ciudades (mismo set).
    """
    pools = {}
    for v in vehiculos_lista:
        pool = tuple(sorted([c.strip().upper() for c in v.get("ciudades", []) if c.strip()]))
        pools[pool] = pools.get(pool, 0) + 1
        if pools[pool] >= 2:
            return True
    return False


def _ordenar_vehiculos_si_compiten(vehiculos_lista: List[dict], df: pd.DataFrame) -> List[dict]:
    """
    Solo si hay competencia real:
    - ordena dentro de cada grupo (mismo pool) por:
      1) menor #ciudades
      2) menor capacidad
      3) pool más antiguo (min fecha más antigua primero)
    Si NO hay competencia: respeta orden original.
    """
    if not _tiene_competencia_real(vehiculos_lista):
        return vehiculos_lista[:]  # no tocar

    # min fecha por ciudad (para estimar antigüedad del pool)
    min_fecha_por_ciudad: Dict[str, pd.Timestamp] = {}
    if "CIUDAD_NORM" in df.columns and "_FECHA_RESERVA" in df.columns:
        tmp = df[["CIUDAD_NORM", "_FECHA_RESERVA"]].copy()
        tmp = tmp.dropna(subset=["CIUDAD_NORM"])
        # min fecha por ciudad (NaT si todo vacío)
        for ciudad, grp in tmp.groupby("CIUDAD_NORM"):
            mn = grp["_FECHA_RESERVA"].min()
            min_fecha_por_ciudad[str(ciudad)] = mn

    def pool_min_fecha(v: dict) -> pd.Timestamp:
        ciudades = [c.strip().upper() for c in v.get("ciudades", []) if c.strip()]
        mins = []
        for c in ciudades:
            mn = min_fecha_por_ciudad.get(c, pd.NaT)
            if pd.notna(mn):
                mins.append(mn)
        return min(mins) if mins else pd.NaT

    # agrupar por pool exacto
    grupos: Dict[Tuple[str, ...], List[dict]] = {}
    orden_pools: List[Tuple[str, ...]] = []
    for v in vehiculos_lista:
        pool = tuple(sorted([c.strip().upper() for c in v.get("ciudades", []) if c.strip()]))
        if pool not in grupos:
            grupos[pool] = []
            orden_pools.append(pool)
        grupos[pool].append(v)

    salida: List[dict] = []
    for pool in orden_pools:
        vs = grupos[pool]
        if len(vs) == 1:
            salida.extend(vs)
        else:
            # ordenar SOLO este grupo
            vs_sorted = sorted(
                vs,
                key=lambda v: (
                    len([c for c in v.get("ciudades", []) if str(c).strip()]),
                    int(v.get("cantidad_motos", 0)),
                    pool_min_fecha(v) if pd.notna(pool_min_fecha(v)) else pd.Timestamp.max
                )
            )
            salida.extend(vs_sorted)

    return salida


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        contrasena = request.form["contrasena"]
        if usuario == "admin" and contrasena == "1234":
            session["usuario"] = usuario
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Usuario o contraseña incorrectos")
    return render_template("login.html", error=None)


@app.route("/dashboard", methods=["GET"])
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


@app.route("/upload", methods=["POST"])
def upload():
    global conteo_ciudades, datos_motos_original, referencias_seleccionadas
    file = request.files["file"]
    if file and (file.filename.endswith(".xlsx") or file.filename.endswith(".xls")):
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        df = pd.read_excel(filepath)

        # Validación mínima: columnas base
        requeridas = ["Estado Satf", "Descr EXXIT", "Dirección 1", "COD INT", "Fecha de reserva"]
        faltantes = [c for c in requeridas if c not in df.columns]
        if faltantes:
            session["mensaje"] = f"❌ Faltan columnas obligatorias: {', '.join(faltantes)}"
            return redirect(url_for("dashboard"))

        # Filtramos solo Estado Satf = 40
        datos_motos_original = df[df["Estado Satf"] == 40].copy()

        # Conteo de ciudades (Descr EXXIT)
        if "Descr EXXIT" in datos_motos_original.columns:
            conteo = Counter(datos_motos_original["Descr EXXIT"].dropna().astype(str).str.upper())
            conteo_ciudades = dict(sorted(conteo.items(), key=lambda x: x[0]))

        # Construcción del reporte SOLO de referencias especiales por ciudad
        referencias_seleccionadas = {}
        if "COD INT" in datos_motos_original.columns and "Descr EXXIT" in datos_motos_original.columns:
            reporte = (
                datos_motos_original.groupby([datos_motos_original["Descr EXXIT"].astype(str).str.upper(), "COD INT"])
                .size()
                .reset_index(name="Cantidad")
            )
            for _, row in reporte.iterrows():
                ciudad = row["Descr EXXIT"]
                cod_int = row["COD INT"]
                eq = get_equivalencia(cod_int)
                if eq <= 1:
                    continue

                cant = int(row["Cantidad"])
                total = cant * eq
                referencias_seleccionadas.setdefault(ciudad, [])

                # descripción representativa
                mask = (
                    (datos_motos_original["Descr EXXIT"].astype(str).str.upper() == ciudad)
                    & (datos_motos_original["COD INT"] == cod_int)
                )
                descripcion_ejemplo = (
                    datos_motos_original.loc[mask, "Descripcion"].iloc[0]
                    if "Descripcion" in datos_motos_original.columns and not datos_motos_original.loc[mask].empty
                    else str(cod_int)
                )

                referencias_seleccionadas[ciudad].append(
                    {
                        "cod_int": cod_int,
                        "descripcion": descripcion_ejemplo,
                        "cantidad": cant,
                        "equivalencia": eq,
                        "total": total,
                        "usar": True,
                    }
                )

        session["mensaje"] = "✅ Archivo cargado correctamente"
    return redirect(url_for("dashboard"))


@app.route("/actualizar_referencias", methods=["POST"])
def actualizar_referencias():
    global referencias_seleccionadas
    for ciudad, refs in referencias_seleccionadas.items():
        for r in refs:
            key = f"{ciudad}_{r['cod_int']}"
            r["usar"] = key in request.form
    session["mensaje"] = "✅ Selección guardada"
    return redirect(url_for("dashboard"))


@app.route("/registrar_vehiculo", methods=["POST"])
def registrar_vehiculo():
    data = {
        "transportadora": request.form["transportadora"],
        "conductor": request.form["conductor"],
        "placa": request.form["placa"],
        "cantidad_motos": int(request.form["cantidad_motos"]),
        # AQUÍ VA EL POOL REAL: puede ser Barranquilla, Soledad
        "ciudades": [c.strip().upper() for c in request.form["ciudades"].split(",") if c.strip()],
    }
    vehiculos.append(data)
    session["mensaje"] = "✅ Vehículo registrado"
    return redirect(url_for("dashboard"))


@app.route("/generar_planeador", methods=["POST"])
def generar_planeador():
    """
    Lógica final (acordada):
    - Agrupa por Dirección 1 (indivisible)
    - No repite direcciones entre vehículos
    - Llena al máximo por knapsack
      Empates: más antiguo (Fecha de reserva) y luego menos direcciones
    - Respeta equivalencias y selección de especiales
    - Optimiza ORDEN solo si hay competencia real (mismo pool en 2+ vehículos)
    - SIEMPRE retorna respuesta válida (nunca None)
    - Si no hay nada asignable: NO genera Excel vacío, muestra motivo.
    """
    if datos_motos_original.empty:
        session["mensaje"] = "⚠️ No hay datos cargados (sube el Excel primero)."
        return redirect(url_for("dashboard"))

    if not vehiculos:
        session["mensaje"] = "⚠️ No hay vehículos registrados."
        return redirect(url_for("dashboard"))

    df = datos_motos_original.copy()

    # Validaciones obligatorias (nombres exactos)
    required_cols = ["Descr EXXIT", "Dirección 1", "COD INT", "Fecha de reserva"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        session["mensaje"] = f"⚠️ El Excel no tiene columnas requeridas: {', '.join(missing)}."
        return redirect(url_for("dashboard"))

    # Normalizaciones necesarias
    df["CIUDAD_NORM"] = df["Descr EXXIT"].astype(str).str.upper()
    df["DIR_NORM"] = df["Dirección 1"].apply(_norm_dir)

    # FECHA OFICIAL (ÚNICA) = Fecha de reserva
    df["_FECHA_RESERVA"] = pd.to_datetime(df["Fecha de reserva"], errors="coerce", dayfirst=True)

    excel_path = os.path.join(UPLOAD_FOLDER, "Despacho_Final.xlsx")

    direcciones_usadas: Set[str] = set()
    assigned_indices: Set[int] = set()

    columnas_exportar_base = [
        "Nom PV", "No Ped", "Descr", "Descr EXXIT", "Dirección 1",
        "Clnt Envío", "ID Prod", "Descripcion", "ID Serie", "Estado Satf", "COD INT",
        "Fecha de reserva"
    ]
    columnas_exportar = [c for c in columnas_exportar_base if c in df.columns]

    total_asignadas = 0
    total_unidades_asignadas = 0

    # ORDENAR VEHÍCULOS SOLO SI COMPITEN (mismo pool en 2+ vehículos)
    vehiculos_ordenados = _ordenar_vehiculos_si_compiten(vehiculos, df)

    try:
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            for vehiculo in vehiculos_ordenados:
                pool_ciudades = set([c.strip().upper() for c in vehiculo.get("ciudades", []) if c.strip()])
                capacidad = int(vehiculo["cantidad_motos"])

                # Pool de datos: ciudades del vehículo (pueden ser varias)
                df_pool = df[(df["CIUDAD_NORM"].isin(pool_ciudades)) & (~df.index.isin(assigned_indices))]

                # Bloques por dirección: peso total y filas y fecha mínima (más antigua)
                bloques: Dict[str, dict] = {}
                for idx, row in df_pool.iterrows():
                    dir_norm = row["DIR_NORM"]
                    if not dir_norm or dir_norm in ("NAN", "NONE"):
                        continue
                    if dir_norm in direcciones_usadas:
                        continue

                    cod_int = row["COD INT"]
                    eq = get_equivalencia(cod_int)

                    # especiales: respetar selección
                    if eq > 1:
                        # ojo: referencias_seleccionadas está por ciudad (Descr EXXIT upper)
                        ciudad_row = str(row["CIUDAD_NORM"]).strip().upper()
                        ref = encontrar_referencia_especial(cod_int, ciudad_row)
                        if ref is None or not bool(ref.get("usar", False)):
                            continue

                    bloques.setdefault(dir_norm, {"peso": 0, "indices": [], "min_fecha": None})
                    bloques[dir_norm]["peso"] += int(eq)
                    bloques[dir_norm]["indices"].append(idx)

                    f = row["_FECHA_RESERVA"]
                    if pd.notna(f):
                        cur_min = bloques[dir_norm]["min_fecha"]
                        if cur_min is None or pd.isna(cur_min) or f < cur_min:
                            bloques[dir_norm]["min_fecha"] = f

                keys = list(bloques.keys())
                items: List[Tuple[int, int, int]] = []
                for i, k in enumerate(keys):
                    peso = int(bloques[k]["peso"])
                    if 0 < peso <= capacidad:
                        items.append((i, peso, _age_score(bloques[k]["min_fecha"])))

                seleccion_ids = _knapsack_max_peso_age_min_items(items, capacidad)

                indices_vehiculo: List[int] = []
                carga_actual = 0

                for item_id, peso_item, _age_sc in items:
                    if item_id not in seleccion_ids:
                        continue
                    dir_key = keys[item_id]
                    direcciones_usadas.add(dir_key)
                    indices = bloques[dir_key]["indices"]
                    indices_vehiculo.extend(indices)
                    carga_actual += int(peso_item)

                assigned_indices.update(indices_vehiculo)

                asignado = df.loc[indices_vehiculo].copy() if indices_vehiculo else pd.DataFrame(columns=columnas_exportar)

                total_asignadas += len(asignado)
                total_unidades_asignadas += carga_actual

                encabezado = pd.DataFrame([{
                    "Transportadora": vehiculo["transportadora"],
                    "Conductor": vehiculo["conductor"],
                    "Placa": vehiculo["placa"],
                    "Ciudades objetivo": ", ".join(sorted(pool_ciudades)),
                    "Capacidad (espacios)": capacidad,
                    "Ocupado (espacios)": carga_actual,
                    "Cantidad de Direcciones": len(seleccion_ids),
                    "Cantidad de Motos (filas)": len(asignado)
                }])

                hoja = _excel_safe_sheet_name(vehiculo.get("placa", "SIN_PLACA"))
                encabezado.to_excel(writer, sheet_name=hoja, index=False, startrow=0)
                asignado[columnas_exportar].to_excel(writer, sheet_name=hoja, index=False, startrow=3)

        # Si no se asignó absolutamente nada, NO sirve un Excel vacío
        if total_asignadas == 0:
            session["mensaje"] = (
                "⚠️ No se asignó ninguna moto. Posibles causas: "
                "1) todas las direcciones exceden la capacidad, "
                "2) desmarcaste todas las referencias especiales, "
                "3) no hay motos para las ciudades del vehículo."
            )
            if os.path.exists(excel_path):
                try:
                    os.remove(excel_path)
                except Exception:
                    pass
            return redirect(url_for("dashboard"))

        return send_file(excel_path, as_attachment=True)

    except Exception as exc:
        session["mensaje"] = f"❌ Error generando Excel: {exc}"
        return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True)
