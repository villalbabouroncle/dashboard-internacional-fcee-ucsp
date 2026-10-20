# -*- coding: utf-8 -*-
"""
Dashboard de Movilidad Estudiantil UCSP (Saliente y Entrante)
Shiny for Python  ·  ejecutar con:  shiny run app.py --reload

Lee la base directamente desde Google Drive cada vez que se abre
(y cada 10 minutos, o al pulsar "Actualizar datos").
Los datos personales (nombres, apellidos, correos) se descartan al cargar.
"""

import io
import json
import os
import re
import unicodedata
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly
import plotly.graph_objects as go
from shiny import App, reactive, render, req, ui

# ─────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────
SHEET_ID = "1T3eqTIyYhKF-QxW-DCApkN29wCz_XXJVjB9yYLjLuUo"
HOJA_SALIENTE = "MOVILIDAD SALIENTE"
HOJA_ENTRANTE = "MOVILIDAD ENTRANTE"
HOJA_DOCENTES = "ACTIVIDADES DOCENTES"     # copia de la pestaña "Consoli" de la base docente
HOJA_CURRICULA = "CURRICULA ALUMNOS"       # BASE_GENERAL de la consulta de currícula, con ID anónimo
HOJA_MATRICULADOS = "MATRICULADOS"         # matriculados por escuela y periodo (Transparencia UCSP)
TIPOS_CURRICULA = ["Clase Espejo", "Profesor Visitante", "COIL"]

# Docentes: nombres completos de las escuelas y tipos que cuentan para el indicador
ESCUELAS = {"ADM": "Administración de Negocios", "CONT": "Contabilidad"}
TIPOS_INDICADOR = ["Clase Espejo", "COIL", "Profesor Visitante"]
TIPOS_PRINCIPALES = TIPOS_INDICADOR + ["Actividad Internacional", "Postulación"]

# Descarga todo el libro como .xlsx (respeta los tipos de cada celda)
URL_XLSX = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=xlsx"

# Respaldo local por si no hay conexión (opcional)
ARCHIVO_LOCAL = Path(__file__).parent / "data" / "base.xlsx"

MINUTOS_RECARGA = 10

# Colores (azul = saliente, naranja = entrante; categorías en orden fijo)
AZUL, NARANJA, VERDE = "#2a78d6", "#eb6834", "#178f65"
PALETA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
          "#e87ba4", "#008300", "#6250d6", "#e34948"]
TINTA, TINTA_2, GRILLA = "#0b0b0b", "#52514e", "#e7e6e2"

# ─────────────────────────────────────────────────────────────
# CARGA DE DATOS
# ─────────────────────────────────────────────────────────────
def _descargar_libro() -> tuple[bytes, str]:
    """Devuelve el .xlsx en bytes y el nombre de la fuente usada."""
    # 1) Cuenta de servicio (si la hoja es privada). Ver README.
    cred = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if cred:
        import gspread
        from gspread.utils import ExportFormat
        gc = gspread.service_account_from_dict(json.loads(cred))
        return gc.open_by_key(SHEET_ID).export(ExportFormat.EXCEL), "Google Drive (cuenta de servicio)"
    # 2) Enlace público ("Cualquier persona con el enlace puede ver")
    problema = None
    try:
        with urllib.request.urlopen(URL_XLSX, timeout=25) as r:
            contenido = r.read()
        if contenido[:2] == b"PK":          # un .xlsx real empieza por "PK"
            return contenido, "Google Drive"
        problema = ("Google no entregó la hoja: revisa que esté compartida como "
                    "'Cualquier persona con el enlace → Lector' y que el SHEET_ID sea correcto.")
    except Exception as e:
        problema = f"No se pudo conectar con Google Drive ({e}). Revisa el SHEET_ID y que la hoja esté compartida."
    print(problema)
    # 3) Copia local
    if ARCHIVO_LOCAL.exists():
        return ARCHIVO_LOCAL.read_bytes(), "copia local (sin conexión a Drive)"
    raise RuntimeError(problema)


def _limpiar_texto(df: pd.DataFrame) -> pd.DataFrame:
    for c in df.columns:
        if df[c].dtype == object or pd.api.types.is_string_dtype(df[c]):
            df[c] = df[c].map(lambda v: re.sub(r"\s+", " ", v).strip() if isinstance(v, str) else v)
            df[c] = df[c].replace({"": pd.NA, "N.A.": pd.NA})
    return df


def _normalizar_periodo(v) -> str | None:
    """'2022-02', '2026 - 01', fecha 2027-02-01, '1/02/2027' -> 'AAAA-SS'."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA:
        return None
    if isinstance(v, (int, float)) and 20000 < v < 80000:   # número de serie de Excel
        v = pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(v))
    if isinstance(v, (pd.Timestamp, datetime)):
        a, m = v.year, v.month
    else:
        s = str(v)
        if mt := re.search(r"(\d{4})\s*[-/.]\s*(\d{1,2})", s):
            a, m = int(mt[1]), int(mt[2])
        elif mt := re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s):   # dd/mm/aaaa
            a, m = int(mt[3]), int(mt[2])
        else:
            return s.strip()
    sem = m if m in (1, 2) else (1 if m <= 7 else 2)
    return f"{a}-{sem:02d}"


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


ISO3 = {_sin_tildes(k): v for k, v in {
    "Alemania": "DEU", "Argentina": "ARG", "Australia": "AUS", "Austria": "AUT",
    "Bélgica": "BEL", "Bolivia": "BOL", "Brasil": "BRA", "Canadá": "CAN",
    "Chile": "CHL", "China": "CHN", "Colombia": "COL", "Corea": "KOR",
    "Corea del Sur": "KOR", "Korea": "KOR", "Costa Rica": "CRI", "Cuba": "CUB",
    "Dinamarca": "DNK", "Ecuador": "ECU", "El Salvador": "SLV", "España": "ESP",
    "Estados Unidos": "USA", "EE.UU.": "USA", "Finlandia": "FIN", "Francia": "FRA",
    "Guatemala": "GTM", "Honduras": "HND", "Hungría": "HUN", "India": "IND",
    "Irlanda": "IRL", "Italia": "ITA", "Japón": "JPN", "México": "MEX",
    "Nicaragua": "NIC", "Noruega": "NOR", "Países Bajos": "NLD", "Holanda": "NLD",
    "Panamá": "PAN", "Paraguay": "PRY", "Perú": "PER", "Polonia": "POL",
    "Portugal": "PRT", "Puerto Rico": "PRI", "Reino Unido": "GBR",
    "República Checa": "CZE", "República Dominicana": "DOM", "Suecia": "SWE",
    "Suiza": "CHE", "Taiwán": "TWN", "Uruguay": "URY", "Venezuela": "VEN",
    "República de Corea": "KOR", "Indonesia": "IDN", "Estados Unidos de América": "USA",
}.items()}


# ─────────────────────────────────────────────────────────────
# DOCENTES (pestaña ACTIVIDADES DOCENTES = columnas de "Consoli")
# ─────────────────────────────────────────────────────────────
_TIPOS_CANON = {_sin_tildes(t): t for t in [
    "Clase Espejo", "COIL", "Profesor Visitante", "Actividad Internacional", "Postulación",
    "Congreso Internacional", "Evento Internacional", "Proyecto Internacional", "Curso", "Charla"]}
_NO_APLICA = {"n.a.", "na", "n/a", "-", "no aplica"}


def _txt(v):
    """Limpia espacios y saltos de línea; devuelve None si está vacío."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA:
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    t = re.sub(r"\s+", " ", str(v)).strip()
    return t or None


def _categoria(v, vacio="Sin información"):
    t = _txt(v)
    if t is None:
        return vacio
    if t.lower() in _NO_APLICA:
        return "No aplica"
    return t


def _canon_tipo(v):
    t = _categoria(v)
    return _TIPOS_CANON.get(_sin_tildes(t), t[:1].upper() + t[1:])


def _canon_dictado(v):
    t = _categoria(v)
    b = _sin_tildes(t)
    if b.startswith("bilateral"):
        return "Bilateral"
    if b.startswith("unilateral"):
        if "ida" in b.split("(")[-1]:
            return "Unilateral (IDA)"
        if "vuelta" in b:
            return "Unilateral (VUELTA)"
        if "ucsp" in b:
            return "Unilateral (en UCSP)"
        return "Unilateral (otro)"
    return t


def _canon_pais(v):
    t = _categoria(v)
    return {"eeuu": "Estados Unidos", "ee.uu.": "Estados Unidos", "usa": "Estados Unidos"}.get(t.lower(), t)


def cargar_docentes(libro: pd.ExcelFile):
    """Devuelve (filas, mensaje). filas = una fila por actividad y carrera (como en Consoli)."""
    if HOJA_DOCENTES not in libro.sheet_names:
        return None, (f"Aún no existe la pestaña {HOJA_DOCENTES} en la hoja del dashboard. "
                      "Créala con la fórmula IMPORTRANGE indicada en el LEEME.")
    d = libro.parse(HOJA_DOCENTES)
    encabezados = " ".join(map(str, d.columns))
    if re.search(r"#(VALUE|REF|N/A|NAME|ERROR)", encabezados):
        return None, (f"La pestaña {HOJA_DOCENTES} muestra un error de fórmula ({encabezados.strip()}). "
                      "Revisa la celda A1 de esa pestaña (puede pedir 'Permitir acceso').")
    falt = [c for c in ["Escuela Profesional", "Semestre", "Tipo de actividad"] if c not in d.columns]
    if falt:
        return None, f"En la pestaña {HOJA_DOCENTES} faltan las columnas: {', '.join(falt)}."

    # Por seguridad, se descartan correos y enlaces aunque vengan en la hoja
    d = d.drop(columns=[c for c in ["N°", "Correo UCSP", "Correo electrónico", "Evidencias",
                                    "Encuesta Satisfacción"] if c in d.columns])
    d = d[d["Semestre"].notna() | d["Tipo de actividad"].notna()].copy()

    def col(nombre):
        return d[nombre] if nombre in d.columns else pd.Series([None] * len(d), index=d.index)

    out = pd.DataFrame(index=d.index)
    out["Periodo"] = col("Semestre").map(_normalizar_periodo).fillna("Sin información")
    out["Carrera"] = col("Escuela Profesional").map(_categoria).map(lambda c: ESCUELAS.get(c, c))
    out["Tipo"] = col("Tipo de actividad").map(_canon_tipo)
    out["Profesor UCSP"] = col("Profesor UCSP").map(_categoria)
    out["Curso"] = col("Curso").map(_categoria)
    out["Grupo"] = col("Grupo").map(_categoria)
    out["Línea del curso"] = col("Línea del curso").map(_categoria)
    out["Fecha"] = col("Fecha de Realización").map(lambda v: _txt(v) or "")
    out["Modalidad"] = col("Modalidad").map(_categoria)
    out["Dictado"] = col("Dictado").map(_canon_dictado)
    out["País"] = col("País Socio").map(_canon_pais)
    out["Universidad"] = col("Universidad Contraparte").map(_categoria)
    out["Par académico"] = col("Par Académico").map(lambda v: _txt(v) or "")
    out["Descripción"] = col("Descripción de la actividad").map(lambda v: _txt(v) or "")
    out["Estado"] = col("Estado").map(_categoria)
    out["Alumnos ADM"] = pd.to_numeric(col("N° Alumnos ADM"), errors="coerce")
    out["Alumnos CONT"] = pd.to_numeric(col("N° Alumnos CONT"), errors="coerce")
    out["Tipo (gráfico)"] = out["Tipo"].where(out["Tipo"].isin(TIPOS_PRINCIPALES), "Otras actividades")
    out["ISO3"] = out["País"].map(lambda p: ISO3.get(_sin_tildes(str(p))))
    # Una misma actividad aparece una vez por carrera: se identifica para no contarla doble en totales
    clave = ["Periodo", "Tipo", "Profesor UCSP", "Curso", "Grupo", "Universidad", "Descripción", "Fecha"]
    out["ID"] = out.groupby(clave, dropna=False, sort=False).ngroup()
    return out.reset_index(drop=True), None


# ─────────────────────────────────────────────────────────────
# INTERNACIONALIZACIÓN DE LA CURRÍCULA (alumnos)
# Misma lógica que la macro GenerarResultados:
#   indicador = alumnos únicos con actividad internacional / matriculados (Transparencia)
#   en un rango de periodos se suman los valores de cada periodo (alumno-semestre)
# ─────────────────────────────────────────────────────────────
def _periodo_num(v):
    """20251 / '2025-1' / '2025-01' -> '2025-01'."""
    t = _txt(v)
    if t is None:
        return None
    m = re.fullmatch(r"(\d{4})\s*-?\s*0?(\d)", t)
    return f"{m[1]}-{int(m[2]):02d}" if m else _normalizar_periodo(v)


def _escuela_nombre(v):
    t = _categoria(v)
    b = _sin_tildes(t)
    if "administracion" in b:
        return "Administración de Negocios"
    if "contabilidad" in b:
        return "Contabilidad"
    return t.title() if t.isupper() else t


def _hoja_ok(libro, nombre, columnas):
    if nombre not in libro.sheet_names:
        return None, f"Aún no existe la pestaña {nombre} en la hoja del dashboard."
    d = libro.parse(nombre)
    encabezados = " ".join(map(str, d.columns))
    if re.search(r"#(VALUE|REF|N/A|NAME|ERROR)", encabezados):
        return None, (f"La pestaña {nombre} muestra un error de fórmula ({encabezados.strip()}). "
                      "Revisa su celda A1 (puede pedir 'Permitir acceso').")
    falt = [c for c in columnas if c not in d.columns]
    if falt:
        return None, f"En la pestaña {nombre} faltan las columnas: {', '.join(falt)}."
    return d, None


def cargar_curricula(libro: pd.ExcelFile):
    """Devuelve ((base, matriculados), mensaje)."""
    b, msg = _hoja_ok(libro, HOJA_CURRICULA,
                      ["PERIODO", "ESCUELA_PROFESIONAL", "ID_ALUMNO", "CURSO", "GRUPO", "TIPO_ACTIVIDAD"])
    if b is None:
        return None, msg
    # Por seguridad: si llegaran nombres o códigos, se descartan
    b = b.drop(columns=[c for c in ["ALUMNO", "CODIGO_ACADEMICO"] if c in b.columns])
    b = b[b["PERIODO"].notna() & b["ID_ALUMNO"].notna()].copy()
    base = pd.DataFrame({
        "Periodo": b["PERIODO"].map(_periodo_num),
        "Escuela": b["ESCUELA_PROFESIONAL"].map(_escuela_nombre),
        "ID": b["ID_ALUMNO"].astype(str),
        "Curso": b["CURSO"].map(_categoria),
        "Grupo": b["GRUPO"].map(_categoria),
        "Profesor": (b["PROFESOR"] if "PROFESOR" in b else pd.Series(index=b.index, dtype=object)).map(_categoria),
        "Línea": (b["LINEA"] if "LINEA" in b else pd.Series(index=b.index, dtype=object)).map(_categoria),
        "Tipo": b["TIPO_ACTIVIDAD"].map(lambda v: _txt(v) or ""),
    }).dropna(subset=["Periodo"])
    for t in TIPOS_CURRICULA:   # un registro puede tener varios tipos ("Clase Espejo, COIL")
        base[t] = base["Tipo"].str.contains(t, case=False, regex=False)

    m, msg_m = _hoja_ok(libro, HOJA_MATRICULADOS, ["PERIODO", "ESCUELA_PROFESIONAL", "MATRICULADOS"])
    if m is not None:
        mat = pd.DataFrame({
            "Periodo": m["PERIODO"].map(_periodo_num),
            "Escuela": m["ESCUELA_PROFESIONAL"].map(_escuela_nombre),
            "Matriculados": pd.to_numeric(m["MATRICULADOS"], errors="coerce"),
        }).dropna()
        mat = mat.groupby(["Periodo", "Escuela"], as_index=False)["Matriculados"].sum()
    else:
        mat = pd.DataFrame(columns=["Periodo", "Escuela", "Matriculados"])
    aviso = None if m is not None else (msg_m + " Se usarán los alumnos de la base como denominador.")
    return (base.reset_index(drop=True), mat), aviso


def resumen_curricula(base: pd.DataFrame, mat: pd.DataFrame, tipos_sel=None) -> pd.DataFrame:
    """Una fila por periodo y escuela con denominador, numerador y desglose por tipo."""
    tipos_sel = tipos_sel or TIPOS_CURRICULA
    act = base[base[tipos_sel].any(axis=1)]
    g = ["Periodo", "Escuela"]
    r = base.groupby(g)["ID"].nunique().rename("En base").to_frame()
    r["Con actividad"] = act.groupby(g)["ID"].nunique()
    for t in TIPOS_CURRICULA:
        r[t] = base[base[t]].groupby(g)["ID"].nunique()
    r = r.fillna(0).astype(int).reset_index()
    r = r.merge(mat, on=g, how="left")
    r["Fuente"] = r["Matriculados"].notna().map({True: "Transparencia UCSP",
                                                 False: "Respaldo: alumnos de la base (falta dato)"})
    r["Matriculados"] = r["Matriculados"].fillna(r["En base"]).astype(int)
    r["%"] = (r["Con actividad"] / r["Matriculados"]).where(r["Matriculados"] > 0, 0)
    return r.sort_values(g).reset_index(drop=True)


def actividades_unicas(filas: pd.DataFrame) -> pd.DataFrame:
    """Una fila por actividad (une las carreras que la comparten)."""
    if filas.empty:
        return filas.assign(Carreras=pd.Series(dtype=str), Alumnos=pd.Series(dtype=float))
    g = filas.groupby("ID", sort=False)
    act = g.first()
    act["Carreras"] = g["Carrera"].agg(lambda s: ", ".join(sorted(set(s))))
    alumnos = g["Alumnos ADM"].max().fillna(0) + g["Alumnos CONT"].max().fillna(0)
    sin_dato = g["Alumnos ADM"].max().isna() & g["Alumnos CONT"].max().isna()
    act["Alumnos"] = alumnos.mask(sin_dato)
    return act.reset_index()


def cargar_datos():
    contenido, fuente = _descargar_libro()
    libro = pd.ExcelFile(io.BytesIO(contenido))
    faltan = [h for h in (HOJA_SALIENTE, HOJA_ENTRANTE) if h not in libro.sheet_names]
    if faltan:
        raise RuntimeError(f"No encuentro la(s) pestaña(s) {', '.join(faltan)}. "
                           f"Pestañas en la hoja: {', '.join(libro.sheet_names)}. "
                           "Los nombres deben coincidir exactamente (mayúsculas y espacios).")
    hojas = {h: libro.parse(h) for h in (HOJA_SALIENTE, HOJA_ENTRANTE)}
    for h, cols in {HOJA_SALIENTE: ["Esc. Prof. UCSP", "Per. Acad.", "País"],
                    HOJA_ENTRANTE: ["Periodo", "Carrera", "País"]}.items():
        encabezados = " ".join(map(str, hojas[h].columns))
        if re.search(r"#(VALUE|REF|N/A|NAME|ERROR)", encabezados) or hojas[h].empty and "#" in encabezados:
            raise RuntimeError(
                f"La pestaña {h} de la hoja del dashboard muestra un error de fórmula ({encabezados.strip()}). "
                "Abre esa hoja en Google Sheets, pasa el mouse sobre la celda A1 de esa pestaña para ver el detalle "
                "y revisa que la base original no haya cambiado (nombre de la pestaña, columnas eliminadas o movidas).")
        falt = [c for c in cols if c not in hojas[h].columns]
        if falt:
            raise RuntimeError(f"En la pestaña {h} faltan las columnas: {', '.join(falt)}. "
                               f"Columnas encontradas: {', '.join(map(str, hojas[h].columns))}.")

    # --- Saliente ---
    sal = hojas[HOJA_SALIENTE].copy()
    sal = sal.rename(columns={"Modalidad": "Duración", "Modalidad.1": "Formato"})
    sal = sal.drop(columns=[c for c in ["Apellidos", "Nombres", "Correo"] if c in sal], errors="ignore")
    sal = sal.dropna(how="all")
    sal = _limpiar_texto(sal)
    sal["Periodo"] = sal["Per. Acad."].map(_normalizar_periodo)
    for c in ["Esc. Prof. UCSP", "Duración", "Formato", "Concepto", "Universidad de destino", "País", "Convenio"]:
        if c in sal:
            sal[c] = sal[c].fillna("Sin información")

    # --- Entrante ---
    ent = hojas[HOJA_ENTRANTE].copy()
    ent = ent.drop(columns=[c for c in ["Nombres", "Correos", "Correo"] if c in ent], errors="ignore")
    ent = ent.dropna(how="all")
    ent = _limpiar_texto(ent)
    ent["Periodo"] = ent["Periodo"].map(_normalizar_periodo)
    for c in ["Carrera", "Universidad de Origen", "País", "Convenio"]:
        if c in ent:
            ent[c] = ent[c].fillna("Sin información")

    for df in (sal, ent):
        df["Periodo"] = df["Periodo"].fillna("Sin información")
        df["Año"] = pd.to_numeric(df["Periodo"].str[:4], errors="coerce")
        df["ISO3"] = df["País"].map(lambda p: ISO3.get(_sin_tildes(str(p))))

    try:
        doc, doc_msg = cargar_docentes(libro)
    except Exception as e:                       # un problema en docentes no tumba lo de alumnos
        doc, doc_msg = None, f"No se pudo leer la pestaña {HOJA_DOCENTES}: {e}"

    try:
        cur, cur_msg = cargar_curricula(libro)
    except Exception as e:
        cur, cur_msg = None, f"No se pudo leer la pestaña {HOJA_CURRICULA}: {e}"

    return sal, ent, doc, doc_msg, cur, cur_msg, fuente, datetime.now()


# ─────────────────────────────────────────────────────────────
# GRÁFICOS
# ─────────────────────────────────────────────────────────────
def _base(fig: go.Figure, alto=360) -> go.Figure:
    fig.update_layout(
        height=alto, margin=dict(l=10, r=20, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, system-ui, sans-serif", size=12, color=TINTA_2),
        hoverlabel=dict(bgcolor="white", font_color=TINTA, bordercolor=GRILLA),
        legend=dict(orientation="h", y=1.08, x=0, title_text="", traceorder="normal"),
        bargap=0.25,
    )
    fig.update_xaxes(gridcolor=GRILLA, zeroline=False, linecolor=GRILLA)
    fig.update_yaxes(gridcolor=GRILLA, zeroline=False, linecolor=GRILLA)
    return fig


def _vacio(msg="Sin datos para los filtros elegidos") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font=dict(size=14, color=TINTA_2))
    fig.update_xaxes(visible=False); fig.update_yaxes(visible=False)
    return _base(fig, 300)


def barras_h(df: pd.DataFrame, col: str, color: str, top: int | None = None, etiqueta="movilidades",
             sin_vacios=False):
    if sin_vacios:   # en rankings no tiene sentido mostrar "Sin información" / "No aplica"
        df = df[~df[col].isin(["Sin información", "No aplica"])]
    if df.empty:
        return _vacio()
    c = df[col].value_counts()
    if top:
        c = c.head(top)
    c = c.iloc[::-1]   # el mayor arriba
    fig = go.Figure(go.Bar(
        x=c.values, y=c.index, orientation="h",
        marker=dict(color=color, cornerradius=4),
        text=c.values, textposition="outside", cliponaxis=False,
        textfont=dict(color=TINTA_2),
        hovertemplate=f"<b>%{{y}}</b><br>%{{x}} {etiqueta}<extra></extra>",
    ))
    fig = _base(fig, alto=max(130, 30 * len(c) + 40))
    fig.update_xaxes(showgrid=False, showticklabels=False)
    fig.update_yaxes(showgrid=False, automargin=True)
    return fig


def barras_periodo(df: pd.DataFrame, color: str, por: str | None, orden_cats: dict):
    if df.empty:
        return _vacio()
    periodos = sorted(df["Periodo"].unique(), key=lambda p: (p == "Sin información", p))
    fig = go.Figure()
    if not por:
        c = df["Periodo"].value_counts().reindex(periodos, fill_value=0)
        fig.add_bar(x=c.index, y=c.values, marker=dict(color=color, cornerradius=4),
                    hovertemplate="<b>%{x}</b><br>%{y} movilidades<extra></extra>")
    else:
        tabla = pd.crosstab(df["Periodo"], df[por]).reindex(periodos, fill_value=0)
        cats = [k for k in orden_cats[por] if k in tabla.columns]   # color fijo por categoría
        for k in cats:
            idx = orden_cats[por].index(k)
            fig.add_bar(x=tabla.index, y=tabla[k], name=k,
                        marker=dict(color=PALETA[idx % len(PALETA)], line=dict(color="white", width=1)),
                        hovertemplate=f"<b>%{{x}}</b><br>{k}: %{{y}}<extra></extra>")
        fig.update_layout(barmode="stack")
    fig = _base(fig, 340)
    fig.update_xaxes(type="category", showgrid=False, tickangle=-45)
    fig.update_layout(bargap=max(0.25, 1 - len(periodos) / 10))   # barras angostas si hay pocos periodos
    fig.update_yaxes(title_text="N.º de estudiantes")
    return fig


def mapa(df: pd.DataFrame, escala: list, etiqueta="movilidades"):
    d = df.dropna(subset=["ISO3"])
    if d.empty:
        return _vacio()
    c = d.groupby(["ISO3", "País"]).size().reset_index(name="n")
    c = c.groupby("ISO3").agg(n=("n", "sum"), País=("País", "first")).reset_index()
    fig = go.Figure(go.Choropleth(
        locations=c["ISO3"], z=c["n"], text=c["País"], colorscale=escala,
        marker_line_color="white", marker_line_width=0.5,
        colorbar=dict(title="", thickness=10, len=0.6),
        hovertemplate=f"<b>%{{text}}</b><br>%{{z}} {etiqueta}<extra></extra>",
    ))
    fig.update_geos(showframe=False, showcoastlines=False, projection_type="natural earth",
                    showcountries=True, countrycolor="#d9d8d4", landcolor="#f1f0ec",
                    bgcolor="rgba(0,0,0,0)")
    return _base(fig, 380)


def _html(fig: go.Figure):
    """Convierte la figura en HTML (usa plotly.js servido por la propia app)."""
    return ui.HTML(fig.to_html(full_html=False, include_plotlyjs=False,
                               config={"displaylogo": False, "responsive": True}))


ESCALA_AZUL = [[0, "#d6e6f8"], [1, "#0d4a96"]]
ESCALA_NARANJA = [[0, "#fde0d2"], [1, "#a8380f"]]
ESCALA_VERDE = [[0, "#d3f0e3"], [1, "#0b5e40"]]

# ─────────────────────────────────────────────────────────────
# INTERFAZ
# ─────────────────────────────────────────────────────────────
def multi(id_, etiqueta):
    return ui.input_selectize(id_, etiqueta, choices=[], multiple=True,
                              options={"placeholder": "Todos", "plugins": ["remove_button"]})


def tarjeta(titulo, salida, nota=None):
    hijos = [ui.card_header(titulo), salida]
    if nota:
        hijos.append(ui.card_footer(nota))
    return ui.card(*hijos, full_screen=True)


panel_saliente = ui.nav_panel(
    "Movilidad saliente",
    ui.layout_sidebar(
        ui.sidebar(
            ui.layout_columns(
                ui.input_select("s_desde", "Periodo desde", choices=[]),
                ui.input_select("s_hasta", "Periodo hasta", choices=[]),
                col_widths=(6, 6), gap="0.5rem",
            ),
            multi("s_esc", "Esc. Prof. UCSP"),
            multi("s_dur", "Modalidad (duración)"),
            multi("s_for", "Modalidad (presencial/virtual)"),
            multi("s_con", "Concepto"),
            multi("s_pais", "País"),
            multi("s_uni", "Universidad de destino"),
            ui.input_action_button("s_reset", "Limpiar filtros", class_="btn-outline-secondary btn-sm"),
            width=290,
        ),
        ui.layout_column_wrap(
            ui.value_box("Estudiantes UCSP en movilidad", ui.output_text("s_kpi_total")),
            ui.value_box("Países de destino", ui.output_text("s_kpi_paises")),
            ui.value_box("Universidades de destino", ui.output_text("s_kpi_unis")),
            ui.value_box("Movilidad presencial", ui.output_text("s_kpi_pres")),
            width=1 / 4, fill=False,
        ),
        tarjeta(
            ui.div(ui.span("Evolución por periodo académico"),
                   ui.div(ui.input_select("s_por", None, width="230px", choices={
                       "": "Sin desagregar", "Esc. Prof. UCSP": "por Esc. Prof.",
                       "Duración": "por Modalidad (duración)", "Formato": "por Presencial/Virtual",
                       "Concepto": "por Concepto"}), class_="ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_ui("s_g_periodo"),
        ),
        ui.layout_columns(
            tarjeta("Destinos en el mundo", ui.output_ui("s_g_mapa")),
            tarjeta("Estudiantes por país de destino", ui.output_ui("s_g_pais")),
            col_widths=(7, 5),
        ),
        ui.layout_columns(
            tarjeta("Top 15 universidades de destino", ui.output_ui("s_g_uni")),
            ui.div(
                tarjeta("Por escuela profesional", ui.output_ui("s_g_esc")),
                tarjeta("Por concepto", ui.output_ui("s_g_con")),
                tarjeta("Por modalidad (duración)", ui.output_ui("s_g_dur")),
            ),
            col_widths=(7, 5),
        ),
        tarjeta("Detalle por universidad de destino", ui.output_data_frame("s_tabla")),
    ),
)

panel_entrante = ui.nav_panel(
    "Movilidad entrante",
    ui.layout_sidebar(
        ui.sidebar(
            ui.layout_columns(
                ui.input_select("e_desde", "Periodo desde", choices=[]),
                ui.input_select("e_hasta", "Periodo hasta", choices=[]),
                col_widths=(6, 6), gap="0.5rem",
            ),
            multi("e_car", "Carrera"),
            multi("e_pais", "País de origen"),
            multi("e_uni", "Universidad de origen"),
            multi("e_conv", "Convenio"),
            ui.input_action_button("e_reset", "Limpiar filtros", class_="btn-outline-secondary btn-sm"),
            width=290,
        ),
        ui.layout_column_wrap(
            ui.value_box("Estudiantes visitantes", ui.output_text("e_kpi_total")),
            ui.value_box("Países de origen", ui.output_text("e_kpi_paises")),
            ui.value_box("Universidades de origen", ui.output_text("e_kpi_unis")),
            ui.value_box("Periodos con movilidad", ui.output_text("e_kpi_per")),
            width=1 / 4, fill=False,
        ),
        tarjeta(
            ui.div(ui.span("Evolución por periodo académico"),
                   ui.div(ui.input_select("e_por", None, width="200px", choices={
                       "": "Sin desagregar", "Carrera": "por Carrera", "País": "por País"}),
                          class_="ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_ui("e_g_periodo"),
        ),
        ui.layout_columns(
            tarjeta("Países de origen en el mundo", ui.output_ui("e_g_mapa")),
            tarjeta("Estudiantes por país de origen", ui.output_ui("e_g_pais")),
            col_widths=(7, 5),
        ),
        ui.layout_columns(
            tarjeta("Universidades de origen", ui.output_ui("e_g_uni")),
            ui.div(
                tarjeta("Por carrera", ui.output_ui("e_g_car")),
                tarjeta("Por convenio", ui.output_ui("e_g_conv")),
            ),
            col_widths=(7, 5),
        ),
        tarjeta("Detalle por universidad de origen", ui.output_data_frame("e_tabla")),
    ),
)

panel_curricula = ui.nav_panel(
    "Internacionalización de la Currícula",
    ui.output_ui("d_aviso"),
    ui.layout_sidebar(
        ui.sidebar(
            ui.layout_columns(
                ui.input_select("d_desde", "Periodo desde", choices=[]),
                ui.input_select("d_hasta", "Periodo hasta", choices=[]),
                col_widths=(6, 6), gap="0.5rem",
            ),
            multi("d_car", "Carrera"),
            multi("d_tipo", "Tipo de actividad"),
            multi("d_mod", "Modalidad"),
            multi("d_dic", "Dictado"),
            multi("d_pais", "País socio"),
            multi("d_uni", "Universidad contraparte"),
            multi("d_prof", "Docente UCSP"),
            multi("d_lin", "Línea del curso"),
            multi("d_est", "Estado"),
            ui.input_action_button("d_reset", "Limpiar filtros", class_="btn-outline-secondary btn-sm"),
            width=290,
        ),
        ui.layout_column_wrap(
            ui.value_box("Actividades del indicador", ui.output_text("d_kpi_ind"),
                         ui.p("Clase Espejo + COIL + Profesor Visitante", class_="small text-muted mb-0")),
            ui.value_box("Clases espejo", ui.output_text("d_kpi_ce")),
            ui.value_box("COIL", ui.output_text("d_kpi_coil")),
            ui.value_box("Profesores visitantes", ui.output_text("d_kpi_pv")),
            ui.value_box("Otras actividades", ui.output_text("d_kpi_otras"),
                         ui.p("Actividad internacional, postulación, congresos…", class_="small text-muted mb-0")),
            ui.value_box("Docentes UCSP participantes", ui.output_text("d_kpi_doc")),
            ui.value_box("Universidades socias", ui.output_text("d_kpi_uni")),
            ui.value_box("Alumnos participantes", ui.output_text("d_kpi_alu"),
                         ui.p("Según N° de alumnos ADM + CONT registrados", class_="small text-muted mb-0")),
            width=1 / 4, fill=False,
        ),
        ui.div(
            ui.strong("¿Cómo se cuentan las actividades? "),
            "En los indicadores generales, cada actividad se cuenta una sola vez: si la misma actividad "
            "(mismo docente, curso, grupo, fecha y universidad) está registrada para Administración y para "
            "Contabilidad, cuenta como 1. El mismo curso dictado en grupos distintos (p. ej. ADM4-1 y ADM4-2) "
            "cuenta como actividades separadas. En los conteos por carrera, una actividad compartida suma en "
            "ambas carreras, igual que en el Resumen de Actividades.",
            class_="alert alert-light border small mb-3",
        ),
        tarjeta(
            ui.div(ui.span("Actividades por periodo académico"),
                   ui.div(ui.input_select("d_por", None, width="230px", choices={
                       "Tipo (gráfico)": "por Tipo de actividad", "Carrera": "por Carrera",
                       "Modalidad": "por Modalidad", "Dictado": "por Dictado", "": "Sin desagregar"}),
                          class_="ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_ui("d_g_periodo"),
            "Cada actividad se cuenta una vez. Al desagregar por carrera, una actividad compartida por ADM y CONT "
            "se cuenta en ambas (igual que en el Resumen de Actividades).",
        ),
        tarjeta("Resumen de actividades por carrera y periodo", ui.output_data_frame("d_resumen"),
                "Mismo cálculo que la pestaña 'Resumen Actividades': número de actividades por carrera, "
                "tipo y periodo. La fila Total suma Clase Espejo + COIL + Profesor Visitante."),
        ui.layout_columns(
            tarjeta("Países socios", ui.output_ui("d_g_mapa")),
            tarjeta("Actividades por país socio", ui.output_ui("d_g_pais")),
            col_widths=(7, 5),
        ),
        ui.layout_columns(
            tarjeta("Top 15 universidades contraparte", ui.output_ui("d_g_uni")),
            tarjeta("Docentes UCSP con más actividades (top 15)", ui.output_ui("d_g_prof")),
            col_widths=(6, 6),
        ),
        ui.layout_columns(
            tarjeta("Por tipo de actividad", ui.output_ui("d_g_tipo")),
            tarjeta("Por línea del curso", ui.output_ui("d_g_lin")),
            col_widths=(6, 6),
        ),
        ui.layout_columns(
            tarjeta("Por modalidad", ui.output_ui("d_g_mod")),
            tarjeta("Por dictado", ui.output_ui("d_g_dic")),
            col_widths=(6, 6),
        ),
        tarjeta(
            ui.div(ui.span("Detalle de actividades"),
                   ui.download_button("d_descargar", "Descargar (CSV)", class_="btn-sm btn-outline-secondary ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_data_frame("d_detalle"),
        ),
    ),
)

def kpi(titulo, id_, nota_id=None):
    extra = [ui.output_text(nota_id, inline=False)] if nota_id else []
    return ui.value_box(titulo, ui.output_text(id_), *extra)


panel_curr_alumnos = ui.nav_panel(
    "Internacionalización de la Currícula",
    ui.output_ui("c_aviso"),
    ui.layout_sidebar(
        ui.sidebar(
            ui.layout_columns(
                ui.input_select("c_desde", "Periodo desde", choices=[]),
                ui.input_select("c_hasta", "Periodo hasta", choices=[]),
                col_widths=(6, 6), gap="0.5rem",
            ),
            multi("c_esc", "Escuela profesional"),
            ui.input_checkbox_group("c_tipo", "Actividades que cuentan para el indicador",
                                    choices=TIPOS_CURRICULA, selected=TIPOS_CURRICULA),
            ui.input_action_button("c_reset", "Limpiar filtros", class_="btn-outline-secondary btn-sm"),
            width=290,
        ),
        ui.layout_column_wrap(
            kpi("% de alumnos con actividad internacional", "c_kpi_pct", "c_kpi_pct_nota"),
            kpi("Alumnos con actividad internacional", "c_kpi_num", "c_kpi_num_nota"),
            kpi("Matriculados (denominador)", "c_kpi_den", "c_kpi_den_nota"),
            width=1 / 3, fill=False,
        ),
        ui.layout_column_wrap(
            kpi("Alumnos en clases espejo", "c_kpi_ce", "c_kpi_ce_nota"),
            kpi("Alumnos en COIL", "c_kpi_coil", "c_kpi_coil_nota"),
            kpi("Alumnos con profesor visitante", "c_kpi_pv", "c_kpi_pv_nota"),
            width=1 / 3, fill=False,
        ),
        ui.div(
            ui.strong("¿Cómo se calcula? "),
            "Para cada periodo y escuela: alumnos únicos que participaron en al menos una actividad "
            "internacional (en cualquiera de sus cursos y grupos) ÷ alumnos matriculados según el Portal de "
            "Transparencia UCSP. Si se elige un rango de periodos, se suman matriculados y participantes de "
            "cada periodo (alumno-semestre): un alumno con actividad en dos periodos cuenta en cada uno. "
            "Un alumno con más de un tipo de actividad aparece en cada tipo, pero en el indicador cuenta una vez.",
            class_="alert alert-light border small mb-3",
        ),
        tarjeta("% de alumnos con actividad internacional por periodo", ui.output_ui("c_g_pct")),
        tarjeta("Alumnos por tipo de actividad y periodo", ui.output_ui("c_g_tipo"),
                "Un alumno puede figurar en más de un tipo."),
        tarjeta("Detalle por periodo", ui.output_data_frame("c_tabla_per"),
                "'En base' = alumnos únicos de la escuela en la base (solo referencia; no se usa como denominador "
                "salvo que falte el dato de Transparencia)."),
        ui.layout_columns(
            tarjeta("Cursos con más alumnos participantes (top 15)", ui.output_ui("c_g_curso")),
            tarjeta("Participaciones por línea del curso", ui.output_ui("c_g_linea"),
                    "Participación = un alumno en un curso con actividad internacional."),
            col_widths=(6, 6),
        ),
        tarjeta(
            ui.div(ui.span("Detalle por curso y grupo"),
                   ui.download_button("c_descargar", "Descargar (CSV)", class_="btn-sm btn-outline-secondary ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_data_frame("c_tabla_grupo"),
            "Sin datos personales: se muestra el número de alumnos por curso y grupo, no el listado de alumnos.",
        ),
    ),
)

panel_docentes = ui.nav_panel(
    "Indicadores de Docentes",
    # Aquí se pueden agregar más subpestañas de docentes junto a panel_curricula
    ui.navset_underline(panel_curricula, id="sub_docentes"),
)

app_ui = ui.page_navbar(
    ui.nav_panel(
        "Indicadores de Alumnos",
        ui.navset_underline(panel_saliente, panel_entrante, panel_curr_alumnos, id="sub_alumnos"),
    ),
    panel_docentes,
    ui.nav_spacer(),
    ui.nav_control(ui.input_action_button("recargar", "↻ Actualizar datos",
                                          class_="btn-sm btn-light")),
    title="Indicadores de Internacionalización FCEE",
    window_title="Indicadores de Internacionalización FCEE",
    footer=ui.div(ui.output_text("estado"), class_="text-muted small px-4 py-2"),
    fillable=False,
    header=ui.TagList(ui.output_ui("aviso"), ui.head_content(ui.tags.script(src="plotlyjs/plotly.min.js")), ui.tags.style("""
        body { background:#f6f6f3; }
        .bslib-value-box .value-box-value { font-size: 2rem; font-weight: 600; }
        .bslib-value-box .value-box-title { font-size: .85rem; color:#52514e; }
        .card-header { font-weight: 600; background: transparent; }
        .navbar { background: #0b2545 !important; }
        .navbar .nav-link, .navbar-brand { color: #fff !important; }
        .navbar .nav-link.active { border-bottom: 2px solid #fff; }
        .navbar-brand { font-weight: 600; }
        #sub_alumnos, #sub_docentes { padding: .75rem 1rem 0; background:#fff; border-bottom:1px solid #e7e6e2; }
        #sub_alumnos .nav-link, #sub_docentes .nav-link { color:#52514e !important; font-weight:500; }
        #sub_alumnos .nav-link.active, #sub_docentes .nav-link.active { color:#0b2545 !important; border-bottom-color:#0b2545; }
        .card-header .form-group { margin-bottom: 0; }
        #d_detalle td, #c_tabla_grupo td, #c_tabla_per td { white-space: nowrap; max-width: 420px; overflow: hidden; text-overflow: ellipsis; }
    """)),
)

# ─────────────────────────────────────────────────────────────
# SERVIDOR
# ─────────────────────────────────────────────────────────────
def _periodos(df):
    """Periodos válidos (AAAA-SS) ordenados."""
    return sorted(p for p in df["Periodo"].unique() if re.fullmatch(r"\d{4}-\d{2}", str(p)))


def _filtrar(df, desde, hasta, filtros: dict):
    validos = _periodos(df)
    d = df
    if validos and desde and hasta:
        desde, hasta = sorted([desde, hasta])
        if (desde, hasta) != (validos[0], validos[-1]):   # solo si el usuario acotó el rango
            d = d[(d["Periodo"] >= desde) & (d["Periodo"] <= hasta) & d["Periodo"].isin(validos)]
    for col, sel in filtros.items():
        if sel:
            d = d[d[col].isin(sel)]
    return d


def _orden(df, cols):
    """Orden fijo de categorías (por frecuencia en toda la base) para que cada una conserve su color."""
    return {c: df[c].value_counts().index.tolist() for c in cols}


def server(input, output, session):

    error = reactive.value(None)

    @reactive.calc
    def datos():
        input.recargar()                                   # botón manual
        reactive.invalidate_later(MINUTOS_RECARGA * 60)    # recarga automática
        try:
            d = cargar_datos()
            error.set(None)
            return d
        except Exception as e:
            print("ERROR al cargar datos:", repr(e))
            error.set(str(e))
            return None

    sal = reactive.calc(lambda: req(datos())[0])
    ent = reactive.calc(lambda: req(datos())[1])

    @reactive.calc
    def doc():
        d = req(datos())[2]
        req(d is not None)          # si falta la pestaña de docentes, solo esa sección queda vacía
        return d

    @render.ui
    def aviso():
        datos()
        if error():
            return ui.div(ui.strong("No se pudieron cargar los datos. "), error(),
                          class_="alert alert-danger m-3")

    @render.text
    def estado():
        *_, fuente, t = req(datos())
        return f"Fuente: {fuente} · Última actualización: {t:%d/%m/%Y %H:%M} · Se actualiza cada {MINUTOS_RECARGA} min."

    # ----- Opciones de los filtros (se actualizan con los datos) -----
    FILTROS_S = {"s_esc": "Esc. Prof. UCSP", "s_dur": "Duración", "s_for": "Formato",
                 "s_con": "Concepto", "s_pais": "País", "s_uni": "Universidad de destino"}
    FILTROS_E = {"e_car": "Carrera", "e_pais": "País", "e_uni": "Universidad de Origen",
                 "e_conv": "Convenio"}
    FILTROS_C = {"c_esc": "Escuela"}
    FILTROS_D = {"d_car": "Carrera", "d_tipo": "Tipo", "d_mod": "Modalidad", "d_dic": "Dictado",
                 "d_pais": "País", "d_uni": "Universidad", "d_prof": "Profesor UCSP",
                 "d_lin": "Línea del curso", "d_est": "Estado"}

    def _poblar(df, filtros, pre, limpiar=False):
        for id_, col in filtros.items():
            opciones = sorted(df[col].dropna().unique().tolist())
            actual = [] if limpiar else [v for v in input[id_]() if v in opciones]
            ui.update_selectize(id_, choices=opciones, selected=actual)
        per = _periodos(df)
        if per:
            d_act, h_act = input[f"{pre}_desde"](), input[f"{pre}_hasta"]()
            desde = per[0] if limpiar or d_act not in per else d_act
            hasta = per[-1] if limpiar or h_act not in per else h_act
            ui.update_select(f"{pre}_desde", choices=per, selected=desde)
            ui.update_select(f"{pre}_hasta", choices=per, selected=hasta)

    primera_vez = {"s": True, "d": True, "c": True}

    @reactive.effect
    def _():
        s, e = sal(), ent()
        with reactive.isolate():
            _poblar(s, FILTROS_S, "s", limpiar=primera_vez["s"])
            _poblar(e, FILTROS_E, "e", limpiar=primera_vez["s"])
        primera_vez["s"] = False

    @reactive.effect
    @reactive.event(input.s_reset)
    def _():
        _poblar(sal(), FILTROS_S, "s", limpiar=True)

    @reactive.effect
    @reactive.event(input.e_reset)
    def _():
        _poblar(ent(), FILTROS_E, "e", limpiar=True)

    # ============ SALIENTE ============
    @reactive.calc
    def s_f():
        return _filtrar(sal(), input.s_desde(), input.s_hasta(), {col: input[id_]() for id_, col in FILTROS_S.items()})

    @render.text
    def s_kpi_total(): return f"{len(s_f()):,}"
    @render.text
    def s_kpi_paises(): return str(s_f()["País"].nunique())
    @render.text
    def s_kpi_unis(): return str(s_f()["Universidad de destino"].nunique())
    @render.text
    def s_kpi_pres():
        d = s_f()
        return f"{(d['Formato'] == 'Presencial').mean():.0%}" if len(d) else "—"

    @render.ui
    def s_g_periodo():
        cols = ["Esc. Prof. UCSP", "Duración", "Formato", "Concepto"]
        return _html(barras_periodo(s_f(), AZUL, input.s_por() or None, _orden(sal(), cols)))

    @render.ui
    def s_g_mapa(): return _html(mapa(s_f(), ESCALA_AZUL))
    @render.ui
    def s_g_pais(): return _html(barras_h(s_f(), "País", AZUL))
    @render.ui
    def s_g_uni(): return _html(barras_h(s_f(), "Universidad de destino", AZUL, top=15))
    @render.ui
    def s_g_esc(): return _html(barras_h(s_f(), "Esc. Prof. UCSP", AZUL))
    @render.ui
    def s_g_con(): return _html(barras_h(s_f(), "Concepto", AZUL))
    @render.ui
    def s_g_dur(): return _html(barras_h(s_f(), "Duración", AZUL))

    @render.data_frame
    def s_tabla():
        d = s_f()
        t = (d.groupby(["Universidad de destino", "País"])
               .agg(Estudiantes=("Periodo", "size"),
                    **{"Primer periodo": ("Periodo", "min"), "Último periodo": ("Periodo", "max")},
                    Convenio=("Convenio", lambda s: ", ".join(sorted(s.dropna().unique()))))
               .reset_index().sort_values("Estudiantes", ascending=False))
        return render.DataGrid(t, filters=True, width="100%", height="420px")

    # ============ CURRÍCULA (ALUMNOS) ============
    @reactive.calc
    def cur():
        c = req(datos())[4]
        req(c is not None)
        return c

    @render.ui
    def c_aviso():
        r = datos()
        if r is not None and r[5]:
            return ui.div(r[5], class_="alert alert-warning m-3")

    @reactive.effect
    def _():
        base, _m = cur()
        with reactive.isolate():
            _poblar(base, FILTROS_C, "c", limpiar=primera_vez["c"])
        primera_vez["c"] = False

    @reactive.effect
    @reactive.event(input.c_reset)
    def _():
        _poblar(cur()[0], FILTROS_C, "c", limpiar=True)
        ui.update_checkbox_group("c_tipo", selected=TIPOS_CURRICULA)

    @reactive.calc
    def c_base():
        base, _m = cur()
        return _filtrar(base, input.c_desde(), input.c_hasta(),
                        {col: input[id_]() for id_, col in FILTROS_C.items()})

    @reactive.calc
    def c_res():
        tipos = list(input.c_tipo()) or TIPOS_CURRICULA
        return resumen_curricula(c_base(), cur()[1], tipos)

    def _tot(col):
        return int(c_res()[col].sum())

    def _pct(n):
        den = _tot("Matriculados")
        return f"{n / den:.1%}" if den else "—"

    @render.text
    def c_kpi_pct():
        return _pct(_tot("Con actividad"))
    @render.text
    def c_kpi_pct_nota():
        n = c_res()["Periodo"].nunique()
        return "Periodo único" if n == 1 else f"{n} periodos sumados (alumno-semestre)"
    @render.text
    def c_kpi_num(): return f"{_tot('Con actividad'):,}"
    @render.text
    def c_kpi_num_nota(): return "Alumnos únicos por periodo"
    @render.text
    def c_kpi_den(): return f"{_tot('Matriculados'):,}"
    @render.text
    def c_kpi_den_nota():
        r = c_res()
        return ("Incluye respaldo de la base en algún periodo"
                if (r["Fuente"] != "Transparencia UCSP").any() else "Fuente: Transparencia UCSP")
    @render.text
    def c_kpi_ce(): return f"{_tot('Clase Espejo'):,}"
    @render.text
    def c_kpi_ce_nota(): return f"{_pct(_tot('Clase Espejo'))} de los matriculados"
    @render.text
    def c_kpi_coil(): return f"{_tot('COIL'):,}"
    @render.text
    def c_kpi_coil_nota(): return f"{_pct(_tot('COIL'))} de los matriculados"
    @render.text
    def c_kpi_pv(): return f"{_tot('Profesor Visitante'):,}"
    @render.text
    def c_kpi_pv_nota(): return f"{_pct(_tot('Profesor Visitante'))} de los matriculados"

    @render.ui
    def c_g_pct():
        r = c_res()
        if r.empty:
            return _html(_vacio())
        fig = go.Figure()
        escuelas = ["Administración de Negocios", "Contabilidad"]
        escuelas += sorted(e for e in r["Escuela"].unique() if e not in escuelas)
        for i, e in enumerate(x for x in escuelas if x in set(r["Escuela"])):
            d = r[r["Escuela"] == e]
            fig.add_bar(x=d["Periodo"], y=d["%"], name=e,
                        marker=dict(color=PALETA[i % len(PALETA)], cornerradius=4),
                        text=[f"{v:.1%}" for v in d["%"]], textposition="outside", cliponaxis=False,
                        textfont=dict(color=TINTA_2),
                        customdata=d[["Con actividad", "Matriculados"]].values,
                        hovertemplate=f"<b>{e}</b> · %{{x}}<br>%{{y:.1%}} "
                                      "(%{customdata[0]:,} de %{customdata[1]:,})<extra></extra>")
        fig = _base(fig, 360)
        fig.update_layout(barmode="group")
        fig.update_xaxes(type="category", showgrid=False)
        fig.update_yaxes(tickformat=".0%", rangemode="tozero", title_text="% de matriculados")
        return _html(fig)

    @render.ui
    def c_g_tipo():
        r = c_res()
        if r.empty:
            return _html(_vacio())
        t = r.groupby("Periodo")[TIPOS_CURRICULA].sum()
        fig = go.Figure()
        for i, tipo in enumerate(TIPOS_CURRICULA):
            fig.add_bar(x=t.index, y=t[tipo], name=tipo,
                        marker=dict(color=PALETA[i + 2], cornerradius=4),
                        text=t[tipo], textposition="outside", cliponaxis=False, textfont=dict(color=TINTA_2),
                        hovertemplate=f"<b>{tipo}</b> · %{{x}}<br>%{{y:,}} alumnos<extra></extra>")
        fig = _base(fig, 340)
        fig.update_layout(barmode="group")
        fig.update_xaxes(type="category", showgrid=False)
        fig.update_yaxes(title_text="Alumnos")
        return _html(fig)

    @render.data_frame
    def c_tabla_per():
        r = c_res()
        t = r[["Periodo", "Escuela", "Matriculados", "Con actividad", "%", "En base"] + TIPOS_CURRICULA + ["Fuente"]].copy()
        t["%"] = t["%"].map(lambda v: f"{v:.1%}")
        t = t.rename(columns={"Matriculados": "Matriculados (denominador)", "%": "% con actividad"})
        return render.DataGrid(t, width="100%", height="360px")

    def _act_filtrada():
        b = c_base()
        tipos = list(input.c_tipo()) or TIPOS_CURRICULA
        return b[b[tipos].any(axis=1)]

    @render.ui
    def c_g_curso():
        a = _act_filtrada()
        if a.empty:
            return _html(_vacio())
        c = a.groupby("Curso")["ID"].nunique().sort_values().tail(15)
        fig = go.Figure(go.Bar(x=c.values, y=c.index, orientation="h",
                               marker=dict(color=AZUL, cornerradius=4), text=c.values,
                               textposition="outside", cliponaxis=False, textfont=dict(color=TINTA_2),
                               hovertemplate="<b>%{y}</b><br>%{x} alumnos<extra></extra>"))
        fig = _base(fig, max(220, 30 * len(c) + 40))
        fig.update_xaxes(showgrid=False, showticklabels=False)
        fig.update_yaxes(showgrid=False, automargin=True)
        return _html(fig)

    @render.ui
    def c_g_linea():
        return _html(barras_h(_act_filtrada(), "Línea", AZUL, top=12, etiqueta="participaciones", sin_vacios=True))

    def _tabla_grupos():
        a = _act_filtrada()
        if a.empty:
            return pd.DataFrame(columns=["Periodo", "Escuela", "Curso", "Grupo", "Profesor", "Línea",
                                         "Tipo de actividad", "Alumnos"])
        t = (a.groupby(["Periodo", "Escuela", "Curso", "Grupo", "Profesor", "Línea", "Tipo"])["ID"]
               .nunique().rename("Alumnos").reset_index()
               .rename(columns={"Tipo": "Tipo de actividad"}))
        return t.sort_values(["Periodo", "Escuela", "Curso", "Grupo"], ascending=[False, True, True, True])

    @render.data_frame
    def c_tabla_grupo():
        return render.DataGrid(_tabla_grupos(), filters=True, width="100%", height="460px")

    @render.download(filename=lambda: f"curricula_alumnos_por_grupo_{datetime.now():%Y%m%d}.csv")
    def c_descargar():
        yield _tabla_grupos().to_csv(index=False, sep=";").encode("utf-8-sig")

    # ============ DOCENTES ============
    @reactive.effect
    def _():
        d = doc()
        with reactive.isolate():
            _poblar(d, FILTROS_D, "d", limpiar=primera_vez["d"])
        primera_vez["d"] = False

    @reactive.effect
    @reactive.event(input.d_reset)
    def _():
        _poblar(doc(), FILTROS_D, "d", limpiar=True)

    @render.ui
    def d_aviso():
        r = datos()
        if r is not None and r[2] is None:
            return ui.div(r[3], class_="alert alert-warning m-3")

    @reactive.calc
    def d_filas():
        return _filtrar(doc(), input.d_desde(), input.d_hasta(),
                        {col: input[id_]() for id_, col in FILTROS_D.items()})

    @reactive.calc
    def d_act():
        return actividades_unicas(d_filas())

    def _n_tipo(tipos):
        a = d_act()
        return f"{int(a['Tipo'].isin(tipos).sum()):,}"

    @render.text
    def d_kpi_ind(): return _n_tipo(TIPOS_INDICADOR)
    @render.text
    def d_kpi_ce(): return _n_tipo(["Clase Espejo"])
    @render.text
    def d_kpi_coil(): return _n_tipo(["COIL"])
    @render.text
    def d_kpi_pv(): return _n_tipo(["Profesor Visitante"])
    @render.text
    def d_kpi_otras():
        a = d_act()
        return f"{int((~a['Tipo'].isin(TIPOS_INDICADOR)).sum()):,}"
    @render.text
    def d_kpi_doc():
        p = d_act()["Profesor UCSP"]
        return str(p[~p.isin(["Sin información", "No aplica"])].nunique())
    @render.text
    def d_kpi_uni():
        u = d_act()["Universidad"]
        return str(u[~u.isin(["Sin información", "No aplica"])].nunique())
    @render.text
    def d_kpi_alu():
        return f"{int(d_act()['Alumnos'].sum()):,}"

    @render.ui
    def d_g_periodo():
        por = input.d_por() or None
        base = d_filas() if por == "Carrera" else d_act()
        orden = {"Tipo (gráfico)": TIPOS_PRINCIPALES + ["Otras actividades"],
                 **_orden(doc(), ["Carrera", "Modalidad", "Dictado"])}
        fig = barras_periodo(base, VERDE, por, orden)
        fig.update_yaxes(title_text="N.º de actividades")
        if not por:
            fig.update_traces(hovertemplate="<b>%{x}</b><br>%{y} actividades<extra></extra>")
        return _html(fig)

    @render.data_frame
    def d_resumen():
        f = d_filas()
        f = f[f["Periodo"].str.match(r"^\d{4}-\d{2}$")]
        if f.empty:
            return render.DataGrid(pd.DataFrame({"Sin datos": []}))
        tabla = pd.crosstab([f["Carrera"], f["Tipo"]], f["Periodo"])
        tabla = tabla[sorted(tabla.columns, reverse=True)]          # periodo más reciente primero
        bloques = []
        for carrera in tabla.index.get_level_values(0).unique():
            t = tabla.loc[carrera]
            orden = [x for x in TIPOS_PRINCIPALES if x in t.index] + sorted(x for x in t.index if x not in TIPOS_PRINCIPALES)
            t = t.reindex(orden)
            t.loc["TOTAL (Clase Espejo + COIL + Prof. Visitante)"] = t.reindex(TIPOS_INDICADOR).fillna(0).sum()
            t = t.reset_index().rename(columns={"index": "Tipo"})
            t.insert(0, "Carrera", carrera)
            bloques.append(t)
        res = pd.concat(bloques, ignore_index=True)
        res.columns = [str(c) for c in res.columns]
        for c in res.columns[2:]:
            res[c] = res[c].fillna(0).astype(int)
        es_total = res["Tipo"].str.startswith("TOTAL")
        estilos = [{"rows": res.index[es_total].tolist(),
                    "style": {"font-weight": "600", "background-color": "#eef7f2"}}]
        return render.DataGrid(res, width="100%", height="560px", styles=estilos)

    @render.ui
    def d_g_mapa(): return _html(mapa(d_act(), ESCALA_VERDE, "actividades"))
    @render.ui
    def d_g_pais(): return _html(barras_h(d_act(), "País", VERDE, top=20, etiqueta="actividades", sin_vacios=True))
    @render.ui
    def d_g_uni(): return _html(barras_h(d_act(), "Universidad", VERDE, top=15, etiqueta="actividades", sin_vacios=True))
    @render.ui
    def d_g_prof(): return _html(barras_h(d_act(), "Profesor UCSP", VERDE, top=15, etiqueta="actividades", sin_vacios=True))
    @render.ui
    def d_g_tipo(): return _html(barras_h(d_act(), "Tipo", VERDE, etiqueta="actividades"))
    @render.ui
    def d_g_lin(): return _html(barras_h(d_act(), "Línea del curso", VERDE, top=12, etiqueta="actividades", sin_vacios=True))
    @render.ui
    def d_g_mod(): return _html(barras_h(d_act(), "Modalidad", VERDE, etiqueta="actividades"))
    @render.ui
    def d_g_dic(): return _html(barras_h(d_act(), "Dictado", VERDE, etiqueta="actividades"))

    def _tabla_detalle():
        a = d_act()
        cols = ["Periodo", "Carreras", "Tipo", "Profesor UCSP", "Curso", "Grupo", "Línea del curso",
                "Fecha", "Modalidad", "Dictado", "País", "Universidad", "Par académico",
                "Descripción", "Estado", "Alumnos"]
        t = a[[c for c in cols if c in a.columns]].copy()
        t["Alumnos"] = t["Alumnos"].map(lambda v: "" if pd.isna(v) else int(v))
        return t.sort_values("Periodo", ascending=False, kind="stable")

    @render.data_frame
    def d_detalle():
        return render.DataGrid(_tabla_detalle(), filters=True, width="100%", height="520px")

    @render.download(filename=lambda: f"actividades_docentes_{datetime.now():%Y%m%d}.csv")
    def d_descargar():
        yield _tabla_detalle().to_csv(index=False, sep=";").encode("utf-8-sig")

    # ============ ENTRANTE ============
    @reactive.calc
    def e_f():
        return _filtrar(ent(), input.e_desde(), input.e_hasta(), {col: input[id_]() for id_, col in FILTROS_E.items()})

    @render.text
    def e_kpi_total(): return f"{len(e_f()):,}"
    @render.text
    def e_kpi_paises(): return str(e_f()["País"].nunique())
    @render.text
    def e_kpi_unis(): return str(e_f()["Universidad de Origen"].nunique())
    @render.text
    def e_kpi_per(): return str(e_f()["Periodo"].nunique())

    @render.ui
    def e_g_periodo():
        return _html(barras_periodo(e_f(), NARANJA, input.e_por() or None, _orden(ent(), ["Carrera", "País"])))

    @render.ui
    def e_g_mapa(): return _html(mapa(e_f(), ESCALA_NARANJA, "estudiantes"))
    @render.ui
    def e_g_pais(): return _html(barras_h(e_f(), "País", NARANJA, etiqueta="estudiantes"))
    @render.ui
    def e_g_uni(): return _html(barras_h(e_f(), "Universidad de Origen", NARANJA, etiqueta="estudiantes"))
    @render.ui
    def e_g_car(): return _html(barras_h(e_f(), "Carrera", NARANJA, etiqueta="estudiantes"))
    @render.ui
    def e_g_conv(): return _html(barras_h(e_f(), "Convenio", NARANJA, etiqueta="estudiantes"))

    @render.data_frame
    def e_tabla():
        d = e_f()
        t = (d.groupby(["Universidad de Origen", "País"])
               .agg(Estudiantes=("Periodo", "size"),
                    **{"Primer periodo": ("Periodo", "min"), "Último periodo": ("Periodo", "max")},
                    Carreras=("Carrera", lambda s: ", ".join(sorted(s.unique()))))
               .reset_index().sort_values("Estudiantes", ascending=False))
        return render.DataGrid(t, filters=True, width="100%", height="380px")


PLOTLY_JS_DIR = Path(plotly.__file__).parent / "package_data"
app = App(app_ui, server, static_assets={"/plotlyjs": PLOTLY_JS_DIR})
