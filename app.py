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
SHEET_ID = "1CXiqec_6Wwf6nKs92cHKbLnzdjr3f3J1D0B3IdnYqFk"
HOJA_SALIENTE = "MOVILIDAD SALIENTE"
HOJA_ENTRANTE = "MOVILIDAD ENTRANTE"

# Descarga todo el libro como .xlsx (respeta los tipos de cada celda)
URL_XLSX = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=xlsx"

# Respaldo local por si no hay conexión (opcional)
ARCHIVO_LOCAL = Path(__file__).parent / "data" / "base.xlsx"

MINUTOS_RECARGA = 10

# Colores (azul = saliente, naranja = entrante; categorías en orden fijo)
AZUL, NARANJA = "#2a78d6", "#eb6834"
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
}.items()}


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

    return sal, ent, fuente, datetime.now()


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


def barras_h(df: pd.DataFrame, col: str, color: str, top: int | None = None, etiqueta="movilidades"):
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

app_ui = ui.page_navbar(
    panel_saliente,
    panel_entrante,
    ui.nav_spacer(),
    ui.nav_control(ui.input_action_button("recargar", "↻ Actualizar datos",
                                          class_="btn-sm btn-light")),
    title="Movilidad Estudiantil · UCSP",
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
        .card-header .form-group { margin-bottom: 0; }
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

    @render.ui
    def aviso():
        datos()
        if error():
            return ui.div(ui.strong("No se pudieron cargar los datos. "), error(),
                          class_="alert alert-danger m-3")

    @render.text
    def estado():
        _, _, fuente, t = req(datos())
        return f"Fuente: {fuente} · Última actualización: {t:%d/%m/%Y %H:%M} · Se actualiza cada {MINUTOS_RECARGA} min."

    # ----- Opciones de los filtros (se actualizan con los datos) -----
    FILTROS_S = {"s_esc": "Esc. Prof. UCSP", "s_dur": "Duración", "s_for": "Formato",
                 "s_con": "Concepto", "s_pais": "País", "s_uni": "Universidad de destino"}
    FILTROS_E = {"e_car": "Carrera", "e_pais": "País", "e_uni": "Universidad de Origen",
                 "e_conv": "Convenio"}

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

    primera_vez = {"s": True}

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
