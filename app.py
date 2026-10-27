# -*- coding: utf-8 -*-
"""
Dashboard "Internacionalización FCEE" – Universidad Católica San Pablo
Shiny for Python  ·  ejecutar con:  shiny run app.py --reload

Lee la base directamente desde Google Drive cada vez que se abre
(y cada 10 minutos, o al pulsar "Actualizar datos").
Los detalles por estudiante muestran nombres, correos y códigos (decisión de la Facultad para el seguimiento).
"""

import hmac
import io
import json
import os
import re
import time
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
HOJA_CURRICULA = "CURRICULA DE ALUMNOS"       # BASE_GENERAL de la consulta de currícula, con ID anónimo
HOJA_MATRICULADOS = "MATRICULADOS"         # matriculados por escuela y periodo (Transparencia UCSP)
TIPOS_CURRICULA = ["Clase Espejo", "Profesor Visitante", "COIL"]

# Docentes: nombres completos de las escuelas y tipos que cuentan para el indicador
ESCUELAS = {"ADM": "Administración de Negocios", "CONT": "Contabilidad"}
TIPOS_INDICADOR = ["Clase Espejo", "COIL", "Profesor Visitante"]
TIPOS_PRINCIPALES = TIPOS_INDICADOR + ["Actividad Internacional", "Postulación"]
# Docentes de la Facultad por periodo (denominador del % de docentes que participan).
# Información proporcionada por el coordinador administrativo de la facultad.
# Cada docente es un código anónimo de 8 caracteres generado a partir de su DNI (no contiene nombres, DNI ni
# correos). Sirve para que, al elegir varios periodos, cada docente cuente una sola vez.
# Para agregar un periodo, pásale a Claude la lista de docentes del periodo y genera los códigos.
DOCENTES_FACULTAD_IDS = {
    "2025-01": {
        "Administración de Negocios": """
            0544eb3f 0c581d56 0dce0df8 11ac876f 17634421 193425e4 1d75ffcf 1e84ee6f 2520d283 25c832f8
            2700b99b 273224f6 27df6a66 2b5d8160 2c5f31a8 2e759b27 2f413f05 3156b2ae 3262dfd0 32dc120b
            34678430 37b85856 39454449 3c50d30f 3c59a46c 3cd13290 3f2cf6b0 4056c176 433940b8 4a889974
            4b9f100c 4c2ff615 4d83cf06 5a3884c5 5b397e7d 6167d997 6246e1e0 6ecc90db 6eea8f78 6efcd10c
            7157871a 746b5165 757a6f15 7d4aadb2 7fe4cc21 8232e153 83fc7cf1 88d14922 88fc84ca 89957cec
            8a8daa04 8ce8abe0 918912c3 9213183e 92419f23 984a45b9 99d1b264 a47a8baa a61841e1 ab10cb2d
            ab8036c1 b8f4f564 ba236f11 bc0e6b3c bc340010 c2436869 c547ec1f c5e2ce91 c8ac9261 c9c49e17
            cbbf0aac cbf57e79 d0cb9ed6 d312138b d31eb6f5 d6366e40 dc03a6e2 de8c5d7d eb2f08f6 efa8642d
            f77db332 f798771e f806f46a fb4f54e3 fce8e78f ff091d00 ff90dbac
        """.split(),
        "Contabilidad": """
            02a86056 083997b4 0c581d56 0dce0df8 1583f79d 17634421 193425e4 1e84ee6f 2b5d8160 2e759b27
            303f94cd 3156b2ae 3262dfd0 33f7c78d 34678430 3cd13290 4a889974 4b9f100c 4c2ff615 4d83cf06
            57cd9f82 607f1285 6246e1e0 6eea8f78 6efcd10c 7157871a 746b5165 7d4aadb2 7e2cd05a 7fe4cc21
            88fc84ca 89957cec 92419f23 984a45b9 a47a8baa ab10cb2d ab8036c1 afd0c02b b8f4f564 bc340010
            c547ec1f c5e2ce91 cb887f6e cbf57e79 d312138b d45277f8 d6366e40 dc03a6e2 dc45b0b5 de8c5d7d
            e0da78a0 eb2f08f6 f77db332 f798771e f806f46a fb4f54e3 fddced5f
        """.split(),
    },
    "2025-02": {
        "Administración de Negocios": """
            0c581d56 0dce0df8 11ac876f 17634421 193425e4 1d75ffcf 2520d283 25c832f8 2b5d8160 2c5f31a8
            2f413f05 3156b2ae 34678430 37b85856 39454449 3c50d30f 3c59a46c 3cd13290 3f2cf6b0 4056c176
            433940b8 4a889974 4b9f100c 4c2ff615 4d83cf06 5a3884c5 5b397e7d 6167d997 6246e1e0 6eea8f78
            6efcd10c 7157871a 757a6f15 75def08c 7d4aadb2 8232e153 83fc7cf1 87db642a 88d14922 88fc84ca
            89957cec 918912c3 9213183e 92419f23 99d1b264 a47a8baa a61841e1 ab10cb2d b8f4f564 ba236f11
            bc0e6b3c bc340010 c2436869 c50c9cf3 c5e2ce91 c8ac9261 c9c49e17 cbf57e79 d0cb9ed6 d31eb6f5
            d393fb0f d6366e40 dc03a6e2 de8c5d7d e89e2135 efa8642d f77db332 fb4f54e3 fce8e78f fddced5f
            ff091d00 ff90dbac
        """.split(),
        "Contabilidad": """
            083997b4 0c581d56 0dce0df8 193425e4 2b5d8160 2b804842 303f94cd 3156b2ae 33f7c78d 34678430
            37b85856 4a889974 4d83cf06 5a0fa63d 6246e1e0 6eea8f78 7157871a 746b5165 7e2cd05a 89957cec
            918912c3 a47a8baa ab10cb2d afd0c02b b8f4f564 ba236f11 c5e2ce91 c8ac9261 cb887f6e cbf57e79
            d312138b d393fb0f d45277f8 dc03a6e2 dc45b0b5 de8c5d7d f77db332 f798771e f806f46a fb4f54e3
            fddced5f
        """.split(),
    },
    "2026-01": {
        "Administración de Negocios": """
            0544eb3f 0c581d56 0dce0df8 11ac876f 17634421 193425e4 1948e567 1d75ffcf 1e84ee6f 2520d283
            25c832f8 27df6a66 2b5d8160 2c5f31a8 3156b2ae 3262dfd0 32dc120b 34678430 37b85856 39454449
            3c50d30f 3c59a46c 3cd13290 3f2cf6b0 4056c176 433940b8 4a889974 4b9f100c 4c2ff615 4d83cf06
            5b397e7d 6167d997 6246e1e0 638f36b6 6ecc90db 6eea8f78 7157871a 73648a03 746b5165 757a6f15
            7d4aadb2 8232e153 83fc7cf1 88d14922 88fc84ca 89957cec 8ce8abe0 918912c3 9213183e 92419f23
            984a45b9 99d1b264 a47a8baa a61841e1 ab10cb2d ab8036c1 b8f4f564 ba236f11 bc0e6b3c bc340010
            c2436869 c50c9cf3 c5e2ce91 c8ac9261 c9c49e17 cbf57e79 d0cb9ed6 d393fb0f d3fb639a d45277f8
            dc03a6e2 de8c5d7d e89e2135 eb2f08f6 efa8642d f77db332 fb4f54e3 fce8e78f fddced5f ff091d00
            ff90dbac
        """.split(),
        "Contabilidad": """
            083997b4 0c581d56 0dce0df8 11ac876f 193425e4 1e84ee6f 27df6a66 2b5d8160 2b804842 303f94cd
            3156b2ae 33f7c78d 34678430 37b85856 462dfc77 4c2ff615 4d83cf06 57cd9f82 607f1285 6246e1e0
            638f36b6 6eea8f78 7157871a 73648a03 746b5165 7e2cd05a 88fc84ca 89957cec 918912c3 a47a8baa
            ab8036c1 afd0c02b b8f4f564 ba236f11 bc340010 c5e2ce91 c8ac9261 cb887f6e cbf57e79 cf9b3958
            d312138b d393fb0f dc03a6e2 dc45b0b5 de8c5d7d e0da78a0 f77db332 f798771e f806f46a fb4f54e3
            fddced5f
        """.split(),
    },
    "2026-02": {
        "Administración de Negocios": """
            0544eb3f 0c581d56 0dce0df8 11ac876f 13a53b1b 17634421 177392d0 193425e4 1948e567 1d14480d
            1e84ee6f 2520d283 25c832f8 2700b99b 273224f6 27df6a66 29aaebee 2afefda8 2b5d8160 2c5f31a8
            3156b2ae 3262dfd0 32dc120b 34678430 39454449 3c50d30f 3c59a46c 3cd13290 3f2cf6b0 4056c176
            433940b8 4a889974 4c2ff615 4d83cf06 52dafee8 5a3884c5 5b397e7d 6167d997 638f36b6 65413005
            6ecc90db 6eea8f78 6efcd10c 73648a03 746b5165 757a6f15 7d4aadb2 7fe4cc21 8232e153 83fc7cf1
            87db642a 88d14922 88fc84ca 89957cec 8ce8abe0 918912c3 9213183e 92419f23 996c807a 9e2672e9
            a47a8baa a47ef11c a61841e1 a86e7f51 ab10cb2d ab8036c1 b8f4f564 bc0e6b3c bc340010 c2436869
            c4e6e87c c50c9cf3 c8ac9261 c9c49e17 cbf57e79 d0cb9ed6 d393fb0f d3fb639a dc03a6e2 de8c5d7d
            eb2f08f6 efa8642d f77db332 fb4f54e3 fce8e78f fddced5f ff091d00
        """.split(),
        "Contabilidad": """
            083997b4 0c581d56 0dce0df8 11ac876f 193425e4 1948e567 1d14480d 2b5d8160 2b804842 2c5f31a8
            303f94cd 3156b2ae 3262dfd0 33f7c78d 34678430 462dfc77 4c2ff615 4d83cf06 52dafee8 57cd9f82
            5a3884c5 607f1285 638f36b6 65413005 6eea8f78 73648a03 746b5165 7e2cd05a 7fe4cc21 88fc84ca
            89957cec 918912c3 996c807a a47ef11c a772711b a86e7f51 ab10cb2d ab8036c1 afd0c02b b8f4f564
            bc340010 c8ac9261 cb887f6e cbf57e79 cf9b3958 d312138b d3fb639a dc03a6e2 dc45b0b5 de418542
            de8c5d7d e0da78a0 f77db332 f798771e f806f46a fddced5f
        """.split(),
    },
}

# Descarga todo el libro como .xlsx (respeta los tipos de cada celda)
URL_XLSX = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=xlsx"

# Respaldo local por si no hay conexión (opcional)
ARCHIVO_LOCAL = Path(__file__).parent / "data" / "base.xlsx"

MINUTOS_RECARGA = 10

# Clave de acceso: se define como variable secreta DASH_CLAVE en Connect Cloud (Settings → Variables).
# Nunca se escribe aquí, porque el repositorio es público. Si la variable no existe, el dashboard no pide clave.
CLAVE = os.environ.get("DASH_CLAVE", "")

# Torneo CompanyGame: base unificada (hoja aparte, compartida como "Cualquier persona con el enlace")
CG_SHEET_ID = "1XI5cre6hGCRHsshf4hh9HlVCIdBu0QSTXknRY2wbURM"
CG_ARCHIVO_LOCAL = Path(__file__).parent / "data" / "companygame.xlsx"
CG_CATS = ["Administración", "Finanzas y Contabilidad", "Marketing"]
CG_HITOS = ["Ingresó al sistema", "Plan de acción", "Ronda 1", "Ronda 2", "Ronda 3", "Ronda 4",
            "Informe final", "Video final"]

# ─────────────────────────────────────────────────────────────
# TEMA DE COLORES  →  para cambiar el aspecto del dashboard, cambia solo esta línea:
TEMA = os.environ.get("DASH_TEMA", "oscuro")    # opciones: marino, granate, oscuro, claro, cielo
# ─────────────────────────────────────────────────────────────
_CAT_CLARO = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
_CAT_OSCURO = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
TEMAS = {
    # serie_s / serie_e / serie_d = color de Saliente / Entrante+Currícula alumnos / Docentes
    "marino": dict(nota_fondo="#eeeeea", nota_texto="#5c5b57", modo="light", barra="#0b2545", barra_texto="#ffffff", acento="#0b2545", fondo="#f6f6f3",
                   superficie="#ffffff", tinta="#0b0b0b", tinta_2="#52514e", grilla="#e7e6e2",
                   tierra="#f1f0ec", fronteras="#d9d8d4", paleta=_CAT_CLARO,
                   serie_s="#2a78d6", serie_e="#eb6834", serie_d="#178f65",
                   escala_s=["#d6e6f8", "#0d4a96"], escala_e=["#fde0d2", "#a8380f"], escala_d=["#d3f0e3", "#0b5e40"]),
    "granate": dict(nota_fondo="#f1ece4", nota_texto="#6a5f55", modo="light", barra="#6b1d2a", barra_texto="#ffffff", acento="#c9a227", fondo="#faf7f2",
                    superficie="#ffffff", tinta="#1f1a17", tinta_2="#5c524a", grilla="#ece5da",
                    tierra="#f3eee6", fronteras="#dcd3c5",
                    paleta=["#8c2338", "#c9a227", "#008f9c", "#d1784f", "#5b4b8a", "#7a8b3d", "#b55a7d", "#3e5c8a"],
                    serie_s="#8c2338", serie_e="#b8860b", serie_d="#2f6f73",
                    escala_s=["#f3d9de", "#6b1d2a"], escala_e=["#f6ead0", "#8a6508"], escala_d=["#d5ebec", "#1f4e51"]),
    "oscuro": dict(nota_fondo="#2a2f37", nota_texto="#a9b0ba", modo="dark", barra="#0f1216", barra_texto="#f0efec", acento="#3987e5", fondo="#15181c",
                   superficie="#1e2227", tinta="#f0efec", tinta_2="#c3c2b7", grilla="#30353c",
                   tierra="#2a2f36", fronteras="#454b53", paleta=_CAT_OSCURO,
                   serie_s="#3987e5", serie_e="#e0703a", serie_d="#22b07d",
                   escala_s=["#1d3554", "#7fb6f2"], escala_e=["#4a2615", "#f2a47c"], escala_d=["#163a2c", "#6fd8ac"]),
    "claro": dict(nota_fondo="#f3f4f6", nota_texto="#4b5563", modo="light", barra="#ffffff", barra_texto="#0f3d3a", acento="#0f766e", fondo="#ffffff",
                  superficie="#ffffff", tinta="#111827", tinta_2="#4b5563", grilla="#e5e7eb",
                  tierra="#f3f4f6", fronteras="#d1d5db",
                  paleta=["#0a8f84", "#e4572e", "#4f46e5", "#d4a017", "#db2777", "#15803d", "#0369a1", "#9333ea"],
                  serie_s="#0f766e", serie_e="#e4572e", serie_d="#4f46e5",
                  escala_s=["#ccefea", "#0b5450"], escala_e=["#fbdcd2", "#a83a1b"], escala_d=["#dfdefb", "#3730a3"]),
    "cielo": dict(nota_fondo="#e9eef6", nota_texto="#526077", modo="light", barra="linear-gradient(90deg, #1e3a8a, #2563eb)", barra_texto="#ffffff",
                  acento="#2563eb", fondo="#f3f6fb", superficie="#ffffff", tinta="#0f172a", tinta_2="#475569",
                  grilla="#e2e8f0", tierra="#eef2f7", fronteras="#cbd5e1",
                  paleta=["#2563eb", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#0891b2", "#ec4899", "#65a30d"],
                  serie_s="#2563eb", serie_e="#f59e0b", serie_d="#10b981",
                  escala_s=["#dbe7fd", "#1e3a8a"], escala_e=["#fdecc8", "#92400e"], escala_d=["#d1f5e8", "#065f46"]),
}
T = TEMAS.get(TEMA, TEMAS["marino"])
AZUL, NARANJA, VERDE = T["serie_s"], T["serie_e"], T["serie_d"]
PALETA = T["paleta"]
TINTA, TINTA_2, GRILLA = T["tinta"], T["tinta_2"], T["grilla"]

# ─────────────────────────────────────────────────────────────
# CARGA DE DATOS
# ─────────────────────────────────────────────────────────────
def _descargar_libro(sheet_id: str = SHEET_ID, local: Path = ARCHIVO_LOCAL) -> tuple[bytes, str]:
    """Devuelve el .xlsx en bytes y el nombre de la fuente usada."""
    # 1) Cuenta de servicio (si la hoja es privada). Ver README.
    cred = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if cred:
        import gspread
        from gspread.utils import ExportFormat
        gc = gspread.service_account_from_dict(json.loads(cred))
        return gc.open_by_key(sheet_id).export(ExportFormat.EXCEL), "Google Drive (cuenta de servicio)"
    # 2) Enlace público ("Cualquier persona con el enlace puede ver")
    problema = None
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    try:
        with urllib.request.urlopen(url, timeout=25) as r:
            contenido = r.read()
        if contenido[:2] == b"PK":          # un .xlsx real empieza por "PK"
            return contenido, "Google Drive"
        problema = ("Google no entregó la hoja: revisa que esté compartida como "
                    "'Cualquier persona con el enlace → Lector' y que el SHEET_ID sea correcto.")
    except Exception as e:
        problema = f"No se pudo conectar con Google Drive ({e}). Revisa el SHEET_ID y que la hoja esté compartida."
    print(problema)
    # 3) Copia local
    if local.exists():
        return local.read_bytes(), "copia local (sin conexión a Drive)"
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
    t = re.sub(r"\s+", " ", str(v).replace("_x000D_", " ")).strip()
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
    # En profesor visitante, cada par académico cuenta como una actividad aparte (una sesión con dos visitantes = 2)
    par = out["Par académico"].str.strip().str.lower()
    out["_par"] = par.where((out["Tipo"] == "Profesor Visitante") & ~par.isin(["", "n.a.", "no aplica"]), "")
    clave = ["Periodo", "Tipo", "Profesor UCSP", "Curso", "Grupo", "Universidad", "Descripción", "Fecha", "_par"]
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
    b = b[b["PERIODO"].notna() & b["ID_ALUMNO"].notna()].copy()
    base = pd.DataFrame({
        "Periodo": b["PERIODO"].map(_periodo_num),
        "Escuela": b["ESCUELA_PROFESIONAL"].map(_escuela_nombre),
        "ID": b["ID_ALUMNO"].astype(str),
        "Código": (b["CODIGO_ACADEMICO"] if "CODIGO_ACADEMICO" in b else pd.Series(index=b.index, dtype=object))
                  .map(lambda v: _txt(v) or ""),
        "Alumno": (b["ALUMNO"] if "ALUMNO" in b else pd.Series(index=b.index, dtype=object))
                  .map(lambda v: _txt(v) or ""),
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
    # Una misma actividad puede tener varios pares académicos (una fila por cada uno): se muestran todos
    if "Par académico" in filas:
        act["Par académico"] = g["Par académico"].agg(
            lambda s: ", ".join(dict.fromkeys(x for x in s if x and x not in ("N.A.", "No aplica"))))
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
    sal = sal.dropna(how="all")
    sal = _limpiar_texto(sal)
    sal["Periodo"] = sal["Per. Acad."].map(_normalizar_periodo)
    for c in ["Esc. Prof. UCSP", "Duración", "Formato", "Concepto", "Universidad de destino", "País", "Convenio"]:
        if c in sal:
            sal[c] = sal[c].fillna("Sin información")

    # --- Entrante ---
    ent = hojas[HOJA_ENTRANTE].copy()
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
        hoverlabel=dict(bgcolor=T["superficie"], font_color=TINTA, bordercolor=GRILLA),
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
                        marker=dict(color=PALETA[idx % len(PALETA)], line=dict(color=T["superficie"], width=1)),
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
        marker_line_color=T["superficie"], marker_line_width=0.5,
        colorbar=dict(title="", thickness=10, len=0.6),
        hovertemplate=f"<b>%{{text}}</b><br>%{{z}} {etiqueta}<extra></extra>",
    ))
    fig.update_geos(showframe=False, showcoastlines=False, projection_type="natural earth",
                    showcountries=True, countrycolor=T["fronteras"], landcolor=T["tierra"],
                    bgcolor="rgba(0,0,0,0)")
    return _base(fig, 380)


def _html(fig: go.Figure):
    """Convierte la figura en HTML (usa plotly.js servido por la propia app)."""
    return ui.HTML(fig.to_html(full_html=False, include_plotlyjs=False,
                               config={"displaylogo": False, "responsive": True}))


# ─────────────────────────────────────────────────────────────
# TORNEO COMPANYGAME (base unificada aparte)
# ─────────────────────────────────────────────────────────────
_CG_HOJAS = ["UCSP_EDICIONES", "UCSP_CATEGORIAS", "TORNEO_GLOBAL", "EQUIPOS_HITOS", "RANKING_RONDAS",
             "PARTICIPANTES", "COMPETENCIAS", "EQUIPOS_2024", "EQUIPOS_2025"]


def _cg_num(df, cols):
    for c in cols:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def cargar_companygame():
    """Lee la base unificada CompanyGame. Encabezados en la fila 3; se descartan las notas al pie."""
    contenido, fuente = _descargar_libro(CG_SHEET_ID, CG_ARCHIVO_LOCAL)
    libro = pd.ExcelFile(io.BytesIO(contenido))
    faltan = [h for h in _CG_HOJAS if h not in libro.sheet_names]
    if faltan:
        raise RuntimeError(f"En la base CompanyGame faltan las pestañas: {', '.join(faltan)}.")
    d = {}
    for h in _CG_HOJAS:
        df = libro.parse(h, header=2)
        df.columns = [str(c).strip() for c in df.columns]
        df = _limpiar_texto(df)
        if "Año" in df:
            df["Año"] = pd.to_numeric(df["Año"], errors="coerce")
            df = df[df["Año"].between(2000, 2100)].copy()
            df["Año"] = df["Año"].astype(int)
        else:
            df = df[df["Categoría"].isin(CG_CATS)].copy()
        d[h] = df
    _cg_num(d["UCSP_EDICIONES"], [c for c in d["UCSP_EDICIONES"].columns if c != "Año"])
    _cg_num(d["TORNEO_GLOBAL"], [c for c in d["TORNEO_GLOBAL"].columns if c != "Año"])
    cat = d["UCSP_CATEGORIAS"]
    _cg_num(cat, [c for c in cat.columns if c not in ("Año", "Categoría", "Nota")])
    rr = d["RANKING_RONDAS"]
    _cg_num(rr, [c for c in rr.columns if c not in ("Año", "Categoría", "Equipo")])
    _cg_num(d["COMPETENCIAS"], ["Equipos clasificados", "Destacado %", "Satisfactorio %", "Suficiente %",
                                "Insuficiente %", "Destacado + Satisfactorio %"])
    e24 = d["EQUIPOS_2024"]
    _cg_num(e24, [c for c in e24.columns if c not in ("Categoría", "Equipo", "Estado", "Entregó informe final")])
    _cg_num(d["EQUIPOS_HITOS"], ["Integrantes", "Rondas completadas (de 4)"])
    for c in CG_HITOS + ["Completó las 4 rondas"]:
        d["EQUIPOS_HITOS"][c] = d["EQUIPOS_HITOS"][c].fillna("s/d")
    return d, fuente, datetime.now()


def _mezcla(c1: str, c2: str, t: float) -> str:
    """Color intermedio entre c1 y c2 (t entre 0 y 1)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


COLOR_CAT = {c: PALETA[i] for i, c in enumerate(CG_CATS)}
VERDE_OK, ROJO_NO = "#2fbf71", "#e66767"


def _ordinal(v):
    return "–" if pd.isna(v) else f"{int(v)}.º"


def cg_participacion(ed: pd.DataFrame):
    if ed.empty:
        return _vacio()
    fig = go.Figure()
    tonos = [_mezcla(T["escala_s"][0], T["escala_s"][1], t) for t in (0.35, 0.65, 1.0)]
    for col, nombre, color in zip(["Equipos inscritos", "Equipos activos", "Equipos clasificados"],
                                  ["Inscritos", "Activos", "Clasificados"], tonos):
        fig.add_bar(x=ed["Año"].astype(str), y=ed[col], name=nombre, marker=dict(color=color, cornerradius=4),
                    text=ed[col].map(lambda v: "" if pd.isna(v) else int(v)), textposition="outside",
                    cliponaxis=False, textfont=dict(color=TINTA_2),
                    hovertemplate=f"<b>%{{x}}</b><br>{nombre}: %{{y}} equipos<extra></extra>")
    fig = _base(fig, 340)
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08)
    fig.update_xaxes(type="category", showgrid=False)
    fig.update_yaxes(title_text="N.º de equipos UCSP")
    return fig


def cg_clasificacion(ed: pd.DataFrame):
    d = ed.dropna(subset=["Clasificados / inscritos"])
    if d.empty:
        return _vacio()
    x = d["Año"].astype(str)
    fig = go.Figure()
    fig.add_scatter(x=x, y=d["Clasificados / inscritos del torneo"], name="Promedio del torneo",
                    mode="lines+markers", line=dict(color=TINTA_2, width=2, dash="dot"), marker=dict(size=7),
                    hovertemplate="<b>%{x}</b><br>Torneo: %{y:.0%}<extra></extra>")
    fig.add_scatter(x=x, y=d["Clasificados / inscritos"], name="UCSP", mode="lines+markers+text",
                    line=dict(color=T["acento"], width=3), marker=dict(size=9),
                    text=d["Clasificados / inscritos"].map(lambda v: f"{v:.0%}"), textposition="top center",
                    textfont=dict(color=TINTA),
                    hovertemplate="<b>%{x}</b><br>UCSP: %{y:.0%}<extra></extra>")
    fig = _base(fig, 340)
    fig.update_xaxes(type="category", showgrid=False)
    fig.update_yaxes(tickformat=".0%", range=[0, 1.05], title_text="Equipos clasificados ÷ inscritos")
    return fig


def cg_posiciones(cat: pd.DataFrame, cats):
    d = cat[cat["Categoría"].isin(cats)].dropna(subset=["Posición UCSP (ranking indexado)"])
    if d.empty:
        return _vacio("Sin posiciones publicadas para las categorías elegidas")
    fig = go.Figure()
    for c in [k for k in CG_CATS if k in cats]:
        s = d[d["Categoría"] == c].sort_values("Año")
        if s.empty:
            continue
        inst = s["Instituciones en la categoría"].map(lambda v: "" if pd.isna(v) else f" de {int(v)} instituciones")
        fig.add_scatter(x=s["Año"].astype(str), y=s["Posición UCSP (ranking indexado)"], name=c,
                        mode="lines+markers+text", line=dict(color=COLOR_CAT[c], width=3), marker=dict(size=9),
                        text=s["Posición UCSP (ranking indexado)"].map(_ordinal), textposition="top center",
                        textfont=dict(color=COLOR_CAT[c]), customdata=inst,
                        hovertemplate=f"<b>{c} · %{{x}}</b><br>Puesto %{{y}}%{{customdata}}<extra></extra>")
    fig = _base(fig, 340)
    fig.update_xaxes(type="category", showgrid=False, categoryorder="category ascending")
    fig.update_yaxes(autorange="reversed", title_text="Puesto (1 = primer lugar)", rangemode="tozero")
    return fig


COLOR_CARRERA = {"Administración de Negocios": PALETA[6], "Contabilidad": PALETA[3]}


def cg_estudiantes(part: pd.DataFrame, cats, por="Categoría"):
    d = part[part["Categoría"].isin(cats)]
    if d.empty:
        return _vacio()
    t = pd.crosstab(d["Año"], d[por])
    if por == "Categoría":
        orden, colores, sufijo = CG_CATS, COLOR_CAT, "categoría "
    else:
        orden = list(COLOR_CARRERA) + sorted(k for k in t.columns if k not in COLOR_CARRERA)
        colores, sufijo = COLOR_CARRERA, "carrera "
    fig = go.Figure()
    for i, c in enumerate([k for k in orden if k in t.columns]):
        fig.add_bar(x=t.index.astype(str), y=t[c], name=c,
                    marker=dict(color=colores.get(c, PALETA[(i + 4) % len(PALETA)]),
                                line=dict(color=T["superficie"], width=1)),
                    hovertemplate=f"<b>%{{x}}</b><br>{sufijo}{c}: %{{y}} estudiantes<extra></extra>")
    tot = t.sum(axis=1)
    fig.add_scatter(x=tot.index.astype(str), y=tot.values, mode="text", text=tot.values, textposition="top center",
                    textfont=dict(color=TINTA), showlegend=False, hoverinfo="skip")
    fig = _base(fig, 340)
    fig.update_layout(barmode="stack", bargap=0.45)
    fig.update_xaxes(type="category", showgrid=False)
    fig.update_yaxes(title_text="N.º de estudiantes", range=[0, tot.max() * 1.15])
    return fig


def _pct_hitos(h: pd.DataFrame) -> pd.DataFrame:
    """% de equipos que cumplió cada hito (sobre equipos con dato), por año."""
    filas = []
    for a, g in h.groupby("Año"):
        for k in CG_HITOS:
            si, no = (g[k] == "Sí").sum(), (g[k] == "No").sum()
            filas.append(dict(Año=a, Hito=k, Sí=si, Base=si + no, Pct=si / (si + no) if si + no else None))
    return pd.DataFrame(filas)


def cg_hitos_evolucion(h: pd.DataFrame, cats):
    d = h[h["Categoría"].isin(cats)]
    if d.empty:
        return _vacio()
    p = _pct_hitos(d)
    anios = sorted(p["Año"].unique())
    fig = go.Figure()
    colores = [PALETA[6], PALETA[4], PALETA[3], PALETA[7], PALETA[5]]
    for i, a in enumerate(anios):
        s = p[p["Año"] == a]
        ultimo = i == len(anios) - 1
        color = T["acento"] if ultimo else colores[(len(anios) - 2 - i) % len(colores)]
        fig.add_scatter(x=s["Hito"], y=s["Pct"], name=str(a), mode="lines+markers", connectgaps=False,
                        line=dict(color=color, width=3.5 if ultimo else 2),
                        marker=dict(size=7), customdata=s[["Sí", "Base"]].values,
                        hovertemplate=f"<b>{a} · %{{x}}</b><br>%{{y:.0%}} (%{{customdata[0]}} de %{{customdata[1]}} equipos)<extra></extra>")
    fig = _base(fig, 360)
    fig.update_xaxes(showgrid=False, categoryorder="array", categoryarray=CG_HITOS)
    fig.update_yaxes(tickformat=".0%", range=[0, 1.05], title_text="% de equipos que lo cumplió")
    return fig


def cg_competencias(comp: pd.DataFrame, cats):
    d = comp[comp["Categoría"].isin(cats)]
    if d.empty:
        return _vacio("Sin evaluación de competencias para las categorías elegidas")
    g = d.groupby(["Año", "Categoría"])["Destacado + Satisfactorio %"].mean().reset_index()
    fig = go.Figure()
    for c in [k for k in CG_CATS if k in g["Categoría"].unique()]:
        s = g[g["Categoría"] == c]
        fig.add_bar(x=s["Año"].astype(str), y=s["Destacado + Satisfactorio %"] / 100, name=c,
                    marker=dict(color=COLOR_CAT[c], cornerradius=4),
                    text=(s["Destacado + Satisfactorio %"] / 100).map(lambda v: f"{v:.0%}"), textposition="outside",
                    cliponaxis=False, textfont=dict(color=TINTA_2),
                    hovertemplate=f"<b>{c} · %{{x}}</b><br>%{{y:.0%}} en Destacado o Satisfactorio<extra></extra>")
    fig = _base(fig, 360)
    fig.update_layout(barmode="group", bargap=0.35, margin=dict(t=60),
                      legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0))
    fig.update_xaxes(type="category", showgrid=False)
    fig.update_yaxes(tickformat=".0%", range=[0, 1.12])
    return fig


def cg_rondas(rr: pd.DataFrame):
    rondas = ["Ranking ronda 1", "Ranking ronda 2", "Ranking ronda 3", "Ranking ronda 4"]
    d = rr.dropna(subset=rondas, how="all")
    if d.empty:
        return _vacio("Esta edición no tiene ranking por ronda en la base")
    fig = go.Figure()
    vistos = set()
    for _, r in d.sort_values(["Categoría", "Equipo"]).iterrows():
        c = r["Categoría"]
        y = [r[k] for k in rondas]
        ult = max(i for i, v in enumerate(y) if not pd.isna(v))
        fig.add_scatter(x=[f"Ronda {i}" for i in range(1, 5)], y=y, name=c, legendgroup=c,
                        showlegend=c not in vistos, mode="lines+markers",
                        line=dict(color=COLOR_CAT.get(c, TINTA_2), width=2), marker=dict(size=7),
                        hovertemplate=f"<b>{r['Equipo']}</b><br>%{{x}}: puesto %{{y}}<extra>{c}</extra>")
        fig.add_annotation(x=f"Ronda {ult + 1}", y=y[ult], text=str(r["Equipo"]), showarrow=False,
                           xanchor="left", xshift=8, font=dict(size=10, color=COLOR_CAT.get(c, TINTA_2)))
        vistos.add(c)
    fig = _base(fig, max(380, 22 * len(d) + 120))
    fig.update_xaxes(showgrid=False, categoryorder="array", categoryarray=[f"Ronda {i}" for i in range(1, 5)])
    fig.update_yaxes(autorange="reversed", title_text="Puesto en el simulador (1 = mejor)")
    fig.update_layout(margin=dict(r=170))
    return fig


def cg_mapa_hitos(h: pd.DataFrame):
    if h.empty:
        return _vacio()
    d = h.sort_values(["Categoría", "Equipo"]).iloc[::-1]
    etiquetas = d["Equipo"] + "  ·  " + d["Categoría"].map(lambda c: {"Administración": "Adm.",
                                                                       "Finanzas y Contabilidad": "Fin.",
                                                                       "Marketing": "Mkt."}.get(c, c))
    val = d[CG_HITOS].replace({"Sí": 1, "No": 0, "s/d": None}).astype(float)
    txt = d[CG_HITOS].values
    sin = _mezcla(T["superficie"], T["tinta_2"], 0.25)
    fig = go.Figure(go.Heatmap(
        z=val.values, x=CG_HITOS, y=etiquetas, text=txt, texttemplate="%{text}",
        textfont=dict(size=10, color=TINTA), colorscale=[[0, _mezcla(T["superficie"], ROJO_NO, 0.45)],
                                                          [1, _mezcla(T["superficie"], VERDE_OK, 0.6)]],
        zmin=0, zmax=1, showscale=False, xgap=3, ygap=3,
        hovertemplate="<b>%{y}</b><br>%{x}: %{text}<extra></extra>"))
    fig = _base(fig, max(260, 26 * len(d) + 70))
    fig.update_layout(plot_bgcolor=sin)
    fig.update_xaxes(side="top", showgrid=False)
    fig.update_yaxes(showgrid=False, automargin=True)
    return fig


def cg_competencias_detalle(comp: pd.DataFrame):
    if comp.empty:
        return _vacio("Esta edición no tiene evaluación de competencias en la base")
    niveles = [("Destacado %", _mezcla(T["superficie"], VERDE_OK, 1.0)),
               ("Satisfactorio %", _mezcla(T["superficie"], VERDE_OK, 0.55)),
               ("Suficiente %", _mezcla(T["superficie"], "#e3a008", 0.7)),
               ("Insuficiente %", _mezcla(T["superficie"], ROJO_NO, 0.9))]
    d = comp.copy()
    d["Etiqueta"] = d["Competencia"] + " · " + d["Categoría"].map(
        {"Administración": "Adm.", "Finanzas y Contabilidad": "Fin.", "Marketing": "Mkt."})
    d = d.sort_values(["Competencia", "Categoría"], ascending=False)
    fig = go.Figure()
    for col, color in niveles:
        fig.add_bar(y=d["Etiqueta"], x=d[col] / 100, name=col.replace(" %", ""), orientation="h",
                    marker=dict(color=color, line=dict(color=T["superficie"], width=1)),
                    hovertemplate=f"<b>%{{y}}</b><br>{col.replace(' %', '')}: %{{x:.0%}}<extra></extra>")
    fig = _base(fig, max(300, 24 * len(d) + 90))
    fig.update_layout(barmode="stack", bargap=0.3)
    fig.update_xaxes(tickformat=".0%", range=[0, 1], showgrid=False)
    fig.update_yaxes(showgrid=False, automargin=True)
    return fig


# ─────────────────────────────────────────────────────────────
# ENCUESTAS DE SATISFACCIÓN (internacionalización de la currícula)
# Una hoja de Google por periodo, compartida como "Cualquier persona con el enlace → Lector".
# Para agregar un periodo nuevo, añade una línea: "AAAA-SS": "ID de la hoja".
# ─────────────────────────────────────────────────────────────
ENCUESTAS_SATISFACCION = {
    "2026-01": "1ylMidkIzk3KhwI_hek8XEvs7SIDUQ8t6PvPnrNJgg9Y",
}
# (texto que identifica la columna, etiqueta corta, dimensión)
ENC_ITEMS = [
    ("cumplio con mis expectativas", "Cumplió mis expectativas", "Aprendizaje"),
    ("objetivos de la clase", "Los objetivos fueron claros", "Aprendizaje"),
    ("contenidos desarrollados", "Contenidos relevantes para mi formación", "Aprendizaje"),
    ("metodologia utilizada", "La metodología facilitó mi aprendizaje", "Aprendizaje"),
    ("interaccion con estudiantes", "La interacción con otra universidad me enriqueció", "Impacto intercultural"),
    ("diferentes perspectivas", "Conocí otras perspectivas académicas o culturales", "Impacto intercultural"),
    ("comodo", "Me sentí cómodo(a) en un entorno internacional/virtual", "Impacto intercultural"),
    ("incremento mi interes", "Aumentó mi interés en actividades internacionales", "Impacto intercultural"),
    ("organizacion de la actividad", "La organización fue adecuada", "Logística y soporte"),
    ("plataforma tecnologica", "La plataforma funcionó correctamente", "Logística y soporte"),
    ("duracion de la sesion", "La duración fue apropiada", "Logística y soporte"),
    ("explico los temas", "El/la docente explicó con claridad", "Rol docente"),
    ("participacion activa", "Se promovió la participación activa", "Rol docente"),
    ("espacio para preguntas", "Hubo espacio para preguntas e interacción", "Rol docente"),
]
ENC_DIMENSIONES = ["Aprendizaje", "Impacto intercultural", "Logística y soporte", "Rol docente"]
ENC_LABELS = [e[1] for e in ENC_ITEMS]
ENC_CALIF = ["Deficiente", "Regular", "Buena", "Muy Buena", "Excelente"]
ENC_RECOM = ["Sí", "Tal vez", "No"]


def _clave(t) -> str:
    return re.sub(r"\s+", " ", _sin_tildes(str(t)).lower()).strip()


def cargar_encuestas():
    """Une las encuestas de todos los periodos. Devuelve (datos, avisos)."""
    partes, avisos = [], []
    for periodo, sid in sorted(ENCUESTAS_SATISFACCION.items()):
        try:
            contenido, _f = _descargar_libro(sid, Path(__file__).parent / "data" / f"encuesta_{periodo}.xlsx")
            d = pd.read_excel(io.BytesIO(contenido), sheet_name=0)
        except Exception as e:
            avisos.append(f"No se pudo leer la encuesta {periodo}: {e}")
            continue
        cols = {_clave(c): c for c in d.columns}

        def buscar(frag):
            f = _clave(frag)
            return next((orig for k, orig in cols.items() if f in k), None)

        base = {"Fecha": buscar("marca temporal"), "Correo": buscar("correo"), "Programa": buscar("programa"),
                "Curso": buscar("curso"), "Semestre": buscar("semestre"),
                "Calificación": buscar("calificarias"), "Recomienda": buscar("recomendarias"),
                "Aspectos a mejorar": buscar("podrian mejorarse"), "Comentarios": buscar("comentarios")}
        faltan = [k for k in ("Curso", "Calificación") if base[k] is None]
        if faltan:
            avisos.append(f"En la encuesta {periodo} no encuentro las columnas: {', '.join(faltan)}.")
            continue
        out = pd.DataFrame({k: (d[v] if v is not None else pd.Series([None] * len(d))) for k, v in base.items()})
        for frag, etiqueta, _dim in ENC_ITEMS:
            c = buscar(frag)
            out[etiqueta] = pd.to_numeric(d[c], errors="coerce") if c is not None else float("nan")
        out["Periodo"] = periodo
        partes.append(out)
    if not partes:
        return None, avisos, 0
    e = pd.concat(partes, ignore_index=True)
    e = e[e["Curso"].notna()].copy()
    for c in ["Correo", "Programa", "Curso", "Calificación", "Recomienda", "Aspectos a mejorar", "Comentarios"]:
        e[c] = e[c].map(lambda v: re.sub(r"\s+", " ", str(v)).strip() if pd.notna(v) else "")
    e["Correo"] = e["Correo"].str.lower()
    e["Programa"] = e["Programa"].replace("", "Sin información")
    e["Semestre"] = pd.to_numeric(e["Semestre"], errors="coerce").map(lambda v: "" if pd.isna(v) else str(int(v)))
    e["Fecha"] = pd.to_datetime(e["Fecha"], dayfirst=True, errors="coerce")
    canon_cal = {_clave(c): c for c in ENC_CALIF}
    e["Calificación"] = e["Calificación"].map(lambda v: canon_cal.get(_clave(v), v))
    e["Calificación (1-5)"] = e["Calificación"].map({c: i for i, c in enumerate(ENC_CALIF, 1)})
    canon_rec = {"si": "Sí", "tal vez": "Tal vez", "no": "No"}
    e["Recomienda"] = e["Recomienda"].map(lambda v: canon_rec.get(_clave(v), v))
    # Una respuesta por estudiante y curso en cada periodo: se conserva la última enviada
    antes = len(e)
    e["_k"] = e["Correo"].where(e["Correo"] != "", e.index.astype(str))
    e = e.sort_values("Fecha", kind="stable").drop_duplicates(["Periodo", "_k", "Curso"], keep="last")
    e = e.drop(columns="_k").sort_index()
    e["Promedio afirmaciones"] = e[ENC_LABELS].mean(axis=1)
    return e.reset_index(drop=True), avisos, antes - len(e)


def _color_likert(n: int) -> str:
    return {1: ROJO_NO, 2: _mezcla(T["superficie"], ROJO_NO, 0.6),
            3: _mezcla(T["superficie"], T["tinta_2"], 0.45),
            4: _mezcla(T["superficie"], VERDE_OK, 0.42), 5: VERDE_OK}[n]


def enc_calificacion(e: pd.DataFrame):
    if e.empty:
        return _vacio()
    c = e["Calificación"].value_counts().reindex(ENC_CALIF, fill_value=0)
    tot = c.sum()
    fig = go.Figure(go.Bar(
        x=[f"{k}<br>({i})" for i, k in enumerate(ENC_CALIF, 1)], y=c.values,
        marker=dict(color=[_color_likert(i) for i in range(1, 6)], cornerradius=4),
        text=[f"{v} ({v / tot:.0%})" if tot else "" for v in c.values], textposition="outside", cliponaxis=False,
        textfont=dict(color=TINTA_2), customdata=list(ENC_CALIF),
        hovertemplate="<b>%{customdata}</b><br>%{y} estudiantes<extra></extra>"))
    fig = _base(fig, 330)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(title_text="N.º de estudiantes", range=[0, c.max() * 1.18 if tot else 1])
    return fig


def enc_recomendacion(e: pd.DataFrame):
    c = e["Recomienda"].value_counts().reindex(ENC_RECOM, fill_value=0)
    if c.sum() == 0:
        return _vacio()
    fig = go.Figure(go.Pie(
        labels=c.index, values=c.values, hole=0.55, sort=False, direction="clockwise",
        marker=dict(colors=[VERDE_OK, "#e3a008", ROJO_NO], line=dict(color=T["superficie"], width=2)),
        textinfo="label+percent", textfont=dict(size=13),
        hovertemplate="<b>%{label}</b><br>%{value} estudiantes (%{percent})<extra></extra>"))
    fig = _base(fig, 330)
    fig.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
    return fig


def enc_likert(e: pd.DataFrame, dim: str | None):
    items = [x for x in ENC_ITEMS if not dim or x[2] == dim]
    if e.empty:
        return _vacio()
    filas = []
    for _f, lab, d in items:
        v = e[lab].dropna()
        n = len(v)
        filas.append((lab, d, n, [(v == k).sum() for k in range(1, 6)], v.mean() if n else None))
    filas = filas[::-1]                         # el primero arriba
    ys = [f[0] for f in filas]
    fig = go.Figure()
    for k in range(1, 6):
        fig.add_bar(y=ys, x=[f[3][k - 1] / f[2] if f[2] else 0 for f in filas], orientation="h", name=str(k),
                    marker=dict(color=_color_likert(k), line=dict(color=T["superficie"], width=1)),
                    customdata=[[f[3][k - 1], f[1]] for f in filas],
                    hovertemplate=f"<b>%{{y}}</b><br>%{{customdata[1]}}<br>Respuesta {k}: %{{x:.0%}} "
                                  f"(%{{customdata[0]}} estudiantes)<extra></extra>")
    fig.add_scatter(y=ys, x=[1.06] * len(ys), mode="text", text=[f"{f[4]:.2f}" if f[4] else "" for f in filas],
                    textfont=dict(color=TINTA, size=12), showlegend=False, hoverinfo="skip")
    fig = _base(fig, max(260, 34 * len(ys) + 90))
    fig.update_layout(barmode="stack", bargap=0.3, margin=dict(r=60),
                      legend=dict(title_text="Respuesta (1 = muy en desacuerdo, 5 = muy de acuerdo)  ",
                                  orientation="h", y=1.02, yanchor="bottom", x=0))
    fig.update_xaxes(tickformat=".0%", range=[0, 1.1], tickvals=[0, 0.25, 0.5, 0.75, 1], showgrid=False)
    fig.update_yaxes(showgrid=False, automargin=True)
    fig.add_annotation(x=1.06, y=1, yref="paper", yanchor="bottom", text="Prom.", showarrow=False,
                       font=dict(color=TINTA_2, size=11))
    return fig


def enc_dimensiones(e: pd.DataFrame):
    if e.empty:
        return _vacio()
    prom = [e[[x[1] for x in ENC_ITEMS if x[2] == d]].stack().mean() for d in ENC_DIMENSIONES]
    fig = go.Figure(go.Bar(
        x=ENC_DIMENSIONES, y=prom, marker=dict(color=PALETA[:4], cornerradius=4),
        text=[f"{p:.2f}" for p in prom], textposition="outside", cliponaxis=False, textfont=dict(color=TINTA),
        hovertemplate="<b>%{x}</b><br>Promedio: %{y:.2f} de 5<extra></extra>"))
    fig = _base(fig, 330)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(range=[0, 5.4], title_text="Promedio (1 a 5)")
    return fig


def enc_cursos(t: pd.DataFrame):
    if t.empty:
        return _vacio()
    d = t.sort_values("Promedio afirmaciones")
    colores = {"Clase Espejo": PALETA[0], "COIL": PALETA[1], "Profesor Visitante": PALETA[2]}
    fig = go.Figure()
    vistos = set()
    for _, r in d.iterrows():
        tipo = r["Tipo de actividad"]
        fig.add_bar(y=[r["Curso"]], x=[r["Promedio afirmaciones"]], orientation="h", name=tipo,
                    legendgroup=tipo, showlegend=tipo not in vistos,
                    marker=dict(color=colores.get(tipo, PALETA[5]), cornerradius=4),
                    text=f"{r['Promedio afirmaciones']:.2f}  (n={r['Encuestas']})", textposition="outside",
                    cliponaxis=False, textfont=dict(color=TINTA_2),
                    hovertemplate=f"<b>{r['Curso']}</b><br>{tipo} · {r['Periodo']}<br>Promedio: %{{x:.2f}} de 5"
                                  f"<br>Calificación general: {r['Calificación general']:.2f}<br>"
                                  f"{r['Encuestas']} encuestas<extra></extra>")
        vistos.add(tipo)
    fig = _base(fig, max(260, 30 * len(d) + 80))
    fig.update_layout(barmode="overlay", margin=dict(r=90))
    fig.update_xaxes(range=[0, 5], showgrid=False, title_text="Promedio de las 14 afirmaciones (1 a 5)")
    fig.update_yaxes(showgrid=False, automargin=True)
    return fig


_STOP = set("""a al algo algun alguna algunas algunos ante antes asi aun bien cada como con contra cual cuando de del
desde donde dos el ella ellas ello ellos en entre era es esa esas ese eso esos esta estaba estan estar este esto estos
fue fueron ha hay hubo la las le les lo los mas me mi mis mucho muy nada ni no nos nuestra nuestro o otra otro para
pero poco por porque puede que se sea sean ser si sin sobre solo su sus tal tambien tan te tener tiene todo todos
tu un una unas uno unos y ya yo mas menos hace hacer haya creo seria podria cosa cosas vez etc ninguno ninguna nada
todo bien ok ademas asimismo ser sido estaba estuvo fue""".split())


def enc_palabras(textos: pd.Series, top=20):
    from collections import Counter
    cnt, formas = Counter(), {}
    for t in textos.dropna():
        for w in re.findall(r"[a-záéíóúñü]+", str(t).lower()):
            k = _sin_tildes(w)
            if len(w) > 3 and k not in _STOP:
                cnt[k] += 1                        # «participación» y «participacion» cuentan juntas
                formas.setdefault(k, Counter())[w] += 1
    if not cnt:
        return _vacio("Sin respuestas abiertas para los filtros elegidos")
    c = pd.Series({formas[k].most_common(1)[0][0]: n for k, n in cnt.most_common(top)}).iloc[::-1]
    fig = go.Figure(go.Bar(x=c.values, y=c.index, orientation="h", marker=dict(color=T["acento"], cornerradius=4),
                           text=c.values, textposition="outside", cliponaxis=False, textfont=dict(color=TINTA_2),
                           hovertemplate="<b>%{y}</b><br>aparece %{x} veces<extra></extra>"))
    fig = _base(fig, max(260, 24 * len(c) + 40))
    fig.update_xaxes(showgrid=False, showticklabels=False)
    fig.update_yaxes(showgrid=False, automargin=True)
    return fig


ESCALA_AZUL = [[0, T["escala_s"][0]], [1, T["escala_s"][1]]]
ESCALA_NARANJA = [[0, T["escala_e"][0]], [1, T["escala_e"][1]]]
ESCALA_VERDE = [[0, T["escala_d"][0]], [1, T["escala_d"][1]]]

# ─────────────────────────────────────────────────────────────
# HOJAS DE RUTA DE INTERNACIONALIZACIÓN (transcritas de los Word de cada programa)
# Para actualizar el texto o las metas, edita este bloque.
# "medida" enlaza la estrategia con un dato que el dashboard ya calcula:
#   movilidad = estudiantes en movilidad saliente en el año · pct_curricula = % alumnos con
#   experiencias de internacionalización · cursos = cursos con clase espejo / COIL / prof. visitante
# ─────────────────────────────────────────────────────────────
_PILARES_UCSP = [
    ("Abiertos al mundo", "Conocimiento"),
    ("Interactuando con el mundo", "Experiencia"),
    ("Comprometidos con el mundo", "Propuesta / Innovación"),
]

RUTAS = {
    "ADM": dict(
        programa="Administración de Negocios",
        escuela="Administración de Negocios",
        info=[("Facultad", "Ciencias Económicas y Empresariales"),
              ("Escuela profesional", "Administración de Negocios"),
              ],
        perfil_intro=("La Escuela Profesional de Administración de Negocios de la Universidad Católica San Pablo "
                      "forma personas que en su desempeño profesional sean capaces de investigar, analizar, organizar, "
                      "planear, dirigir y ejecutar las actividades en las organizaciones profundizando en diversas áreas "
                      "del saber, teniendo así una mirada completa de la realidad, o que le permitirá juzgar las realidades "
                      "particulares desde una cosmovisión formada en diálogo fe – razón; tanto en el campo privado como en "
                      "el estatal, en el ámbito nacional e internacional; todo esto, con el propósito de servicio al bien común."),
        perfil_mision=("Formar profesionales íntegros en administración de empresas en Arequipa, en un ambiente de "
                       "respeto y exigencia académica, humanística y ética."),
        perfil_lista_titulo="Quienes deciden estudiar Administración de Negocios poseen las siguientes características:",
        perfil_lista=[
            "Una personalidad y competencias profesionales basadas en valores éticos y en el consciente ejercicio de "
            "virtudes como la justicia y la prudencia, indispensables para el desempeño de su profesión y para su "
            "despliegue personal.",
            "Tiene conocimientos sólidos y específicos sobre gestión y análisis de datos para la toma de decisiones.",
            "Muestra capacidad de emprendimiento y flexibilidad ante los cambios.",
            "Es persistente en el logro de objetivos.",
            "Tiene profunda conciencia social y respeto por el medio ambiente y la persona humana.",
            "Tiene liderazgo y la capacidad de trabajar en equipo.",
        ],
        fortalezas=[
            "Experiencia previa en clases espejo y COIL (aunque no sistematizada).",
            "Perfil de carrera con enfoque en gestión, liderazgo y toma de decisiones, fácilmente internacionalizable.",
            "Existencia de redes académicas potenciales (ej. CLADEA, convenios UCSP).",
            "Interés de docentes en colaboración internacional.",
        ],
        oportunidades=[
            "Débil institucionalización de experiencias internacionales (COIL, clases espejo).",
            "Falta de estrategia clara de internacionalización por cursos.",
            "Oportunidad de potenciar cursos dictados en inglés o bilingües.",
            "Capacitación en metodologías de internacionalización a los docentes.",
        ],
        objetivos=[
            "Fortalecer la dimensión internacional del proceso formativo mediante la incorporación de contenidos, "
            "metodologías y experiencias internacionales en áreas como gestión y estrategia, marketing, finanzas, "
            "emprendimiento, gobierno de personas, promoviendo competencias globales en entornos empresariales.",
            "Desarrollar alianzas estratégicas con universidades y organizaciones internacionales para impulsar la "
            "cooperación académica, investigación aplicada y actualización en tendencias globales de negocios.",
            "Incrementar la participación de estudiantes y docentes en actividades como clases espejo, COIL, movilidad "
            "académica, prácticas internacionales y proyectos colaborativos.",
        ],
        estrategias=[
            (1, "Meso", "Definición de cursos con enfoque global e intercultural en los cuales se incorporen casos y metodologías internacionales y IFRS.",
             "# cursos con enfoque global e intercultural", ["2", "3", "4"], "Dirección de Escuela", "Requiere capacitación docente", None),
            (1, "Meso", "Implementar COIL y clases espejo en cursos clave (marketing, estrategia, RRHH, finanzas).",
             "# de cursos diseñados para experiencias de internacionalización (COIL, clases espejo, profesor visitante)",
             ["20", "25", "30"], "Líder Internacionalización", "Priorizar cursos núcleo", "cursos"),
            (1, "Meso", "Incorporar cursos al programa de bilingüismo institucional.",
             "# de cursos dentro del programa de bilingüismo", ["2", "3", "4"], "Dirección de Escuela", "Enfoque progresivo", None),
            (1, "Meso", "Formación docente para internacionalización (capacitaciones en COIL, metodologías globales, inglés académico).",
             "% de docentes capacitados", ["25%", "40%", "60%"], "Líder Internacionalización", "Clave para sostenibilidad", None),
            (2, "Meso", "Diseñar y consolidar alianzas estratégicas con universidades extranjeras.",
             "# de alianzas estratégicas ejecutadas", ["3", "4", "5"], "Dirección de Escuela", "Priorizar LATAM + Europa", None),
            (2, "Meso", "Incorporar docentes internacionales en actividades académicas (clases, seminarios, investigación).",
             "# de docentes internacionales participantes", ["3", "5", "7"], "Líder Internacionalización", "Puede ser virtual", None),
            (3, "Meso", "Diseñar e implementar un sistema estructurado de difusión y acceso a oportunidades de internacionalización para estudiantes.",
             "# de estudiantes que participaron en movilidad internacional saliente", ["10", "12", "14"],
             "Líder Internacionalización", "Uso de canales digitales", "movilidad"),
            (3, "Meso", "Optimizar procesos de internacionalización.",
             "% de satisfacción de estudiantes sobre información y procesos", ["70%", "80%", "90%"],
             "Líder Internacionalización", "Medición con encuestas", None),
            (3, "Micro", "Implementar experiencias COIL, clases espejo y otras experiencias internacionales en cursos definidos.",
             "% de estudiantes con experiencias de internacionalización (clases espejo, COIL, profesor visitante)",
             ["30%", "40%", "50%"], "Líder de Internacionalización DCEE", "", "pct_curricula"),
            (3, "Meso", "Diseñar e implementar un sistema estructurado de difusión y acceso a oportunidades de internacionalización para profesores.",
             "# de docentes que participó de movilidad docente / pasantías / misiones académicas", ["1", "2", "3"],
             "Líder Internacionalización", "Incentivar participación", None),
            (3, "Micro", "Desarrollar investigaciones colaborativas internacionales en gestión y negocios.",
             "# de investigaciones internacionales realizadas", ["1", "2", "3"],
             "Líder Internacionalización / Investigación DCEE", "Vincular con redes", None),
        ],
    ),
    "CONT": dict(
        programa="Contabilidad",
        escuela="Contabilidad",
        info=[("Facultad", "Ciencias Económicas y Empresariales"),
              ("Escuela profesional", "Contabilidad"),
              ],
        perfil_intro=("La Escuela Profesional de Contabilidad de la Universidad Católica San Pablo forma personas que en su "
                      "desempeño profesional son capaces de identificar, analizar, medir y controlar la información de "
                      "carácter contable, financiero y tributario en las organizaciones. Así, permiten a quienes toman "
                      "decisiones, considerar los diversos factores y riesgos que conlleva la gestión económica empresarial "
                      "en el marco de su servicio al bien común."),
        perfil_mision="",
        perfil_lista_titulo="El profesional en Contabilidad posee las siguientes características:",
        perfil_lista=[
            "Posee una personalidad y una competencia profesional basadas en virtudes como la justicia y la prudencia, y "
            "en el consciente ejercicio de la profesión, anteponiendo el valor de la fe pública de la información en el "
            "contexto del bien común.",
            "Tiene conocimientos específicos y profundos sobre contabilidad financiera, auditoría, y tributación.",
            "Está preparado para el análisis de datos y manejo de lenguajes de programación abordando de manera "
            "responsable los desafíos organizacionales.",
            "Tiene sólidos conocimientos en finanzas.",
            "Posee capacidad de cooperación, comunicación asertiva, proactividad y compromiso con el aprendizaje "
            "constante y reflexivo.",
            "Muestra dominio del sistema tributario nacional no solo en lo que respecta a su cumplimiento, sino también a "
            "las alternativas que este ofrece para la toma de decisiones, mediante una adecuada planificación tributaria "
            "nacional e internacional.",
            "Está preparado para sistematizar y analizar información financiera, económica y legal para la planificación, "
            "el control, la evaluación y la toma de decisiones, por medio de la destreza en el conocimiento y el manejo de "
            "herramientas, y la apertura a un marco mayor de conocimientos y saberes.",
        ],
        fortalezas=[
            "Profesores en empresas globales importantes.",
            "Experiencia previa en clases espejo, COIL y profesores visitantes.",
            "Redes académicas internacionales: miembro y en proceso de acreditación con ACBSP y pertenencia a CLADEA.",
        ],
        oportunidades=[
            "Baja movilidad estudiantil, tanto entrante como saliente.",
            "Poca producción en investigación.",
            "Débil consolidación de convenios internacionales.",
            "Baja disponibilidad de financiamiento para movilidad por parte de estudiantes.",
            "Falta de bilingüismo en el plan de formación.",
        ],
        objetivos=[
            "Fortalecer la dimensión internacional del proceso formativo de la Carrera Profesional de Contabilidad mediante "
            "la integración sistemática de experiencias académicas internacionales e interculturales en el currículo, "
            "promoviendo el desarrollo de competencias globales en contabilidad, auditoría, tributación y finanzas, con "
            "énfasis en normas internacionales (IFRS), herramientas digitales y principios éticos.",
            "Impulsar la vinculación académica del programa con universidades, docentes y entornos profesionales "
            "internacionales, mediante el desarrollo de alianzas estratégicas sostenibles que favorezcan la cooperación, "
            "la investigación conjunta, la innovación y la actualización disciplinar en contabilidad, tributación, "
            "auditoría y finanzas.",
            "Promover la participación progresiva de estudiantes y docentes en actividades de internacionalización, tales "
            "como clases espejo, COIL, movilidad académica, investigación colaborativa y eventos internacionales, "
            "incrementando su exposición a contextos globales y fortaleciendo su perfil académico y profesional.",
        ],
        estrategias=[
            (1, "Meso", "Definición de cursos con enfoque global e intercultural en los cuales se incorporen casos y metodologías internacionales y IFRS.",
             "# cursos con enfoque global e intercultural", ["2", "3", "4"], "Dirección de Escuela", "Requiere capacitación docente", None),
            (1, "Micro", "Implementar COIL y clases espejo en cursos clave (marketing, estrategia, RRHH, finanzas).",
             "# de cursos diseñados para experiencias de internacionalización (COIL, clases espejo, profesor visitante)",
             ["5", "7", "10"], "Líder de Internacionalización DCEE", "Priorizar cursos núcleo", "cursos"),
            (1, "Meso", "Incorporación de cursos al programa de bilingüismo institucional.",
             "# cursos dentro del programa de bilingüismo", ["3", "4", "5"], "Dirección de Escuela", "Enfoque progresivo", None),
            (1, "Micro", "Formación docente para internacionalización (capacitaciones en COIL, metodologías globales, inglés académico).",
             "% de docentes capacitados", ["25%", "40%", "60%"], "Líder de Internacionalización DCEE", "Clave para sostenibilidad", None),
            (2, "Meso", "Diseñar y consolidar alianzas estratégicas con universidades extranjeras.",
             "# alianzas estratégicas ejecutadas", ["3", "4", "5"], "Dirección de Escuela", "Priorizar LATAM + Europa", None),
            (2, "Meso", "Incorporar docentes internacionales en actividades académicas (clases, seminarios, investigación).",
             "# docentes internacionales", ["3", "5", "7"], "Líder de Internacionalización DCEE", "Puede ser virtual", None),
            (3, "Meso", "Diseñar e implementar un sistema estructurado de difusión y acceso a oportunidades de internacionalización para estudiantes.",
             "# de estudiantes que participó de movilidad internacional", ["2", "3", "4"],
             "Líder de Internacionalización DCEE", "Uso de canales digitales", "movilidad"),
            (3, "Meso", "Optimizar procesos de internacionalización.",
             "% satisfacción de estudiantes sobre información y procesos de internacionalización", ["70%", "80%", "90%"],
             "Líder de Internacionalización DCEE", "Medición con encuestas", None),
            (3, "Micro", "Implementar experiencias COIL, clases espejo y otras experiencias internacionales en cursos definidos.",
             "% de estudiantes con experiencias de internacionalización (clases espejo, COIL, profesor visitante)",
             ["30%", "40%", "50%"], "Líder de Internacionalización DCEE", "", "pct_curricula"),
            (3, "Meso", "Diseñar e implementar un sistema estructurado de difusión y acceso a oportunidades de internacionalización para profesores.",
             "# de docentes que participó de movilidad docente / pasantías / misiones académicas", ["1", "2", "3"],
             "Líder de Internacionalización DCEE", "Incentivar participación", None),
            (3, "Micro", "Desarrollar investigaciones colaborativas internacionales.",
             "# de investigaciones internacionales realizadas", ["1", "2", "3"],
             "Líder Internacionalización / Investigación DCEE", "Vincular con redes", None),
        ],
    ),
}


# ─────────────────────────────────────────────────────────────
# INTERFAZ
# ─────────────────────────────────────────────────────────────
def periodos(pre):
    """Periodos como botones: se puede marcar cualquier combinación (sin marcar ninguno = todos)."""
    return ui.div(
        ui.div(ui.tags.label("Periodos", class_="control-label"),
               ui.div(ui.input_action_link(f"{pre}_per_actual", "Actual"), " · ",
                      ui.input_action_link(f"{pre}_per_todos", "Todos"), " · ",
                      ui.input_action_link(f"{pre}_per_ninguno", "Ninguno"), class_="per-acciones"),
               class_="d-flex justify-content-between align-items-baseline"),
        ui.input_checkbox_group(f"{pre}_per", None, choices=[], inline=True),
        class_="per-botones",
    )


def multi(id_, etiqueta):
    return ui.input_selectize(id_, etiqueta, choices=[], multiple=True,
                              options={"placeholder": "Todos", "plugins": ["remove_button"]})


def nota(texto):
    """Leyenda corta visible dentro de una tarjeta de indicador."""
    return ui.p(texto, class_="kpi-nota")


def kpi(titulo, id_, texto=None, nota_id=None):
    """Tarjeta de indicador: valor + (nota dinámica) + leyenda fija de cómo se calcula."""
    extra = []
    if nota_id:
        extra.append(ui.div(ui.output_text(nota_id, inline=True), class_="kpi-dinamica"))
    if texto:
        extra.append(nota(texto))
    return ui.value_box(titulo, ui.output_text(id_), *extra)


def tarjeta(titulo, salida, texto=None):
    """Gráfico o tabla con su leyenda al pie (fuente y cálculo)."""
    hijos = [ui.card_header(titulo), salida]
    if texto:
        hijos.append(ui.card_footer(texto, class_="leyenda"))
    return ui.card(*hijos, full_screen=True)


def fuente(*partes):
    """Recuadro al inicio de cada subpestaña: de dónde salen los datos."""
    return ui.div(ui.strong("Fuente de los datos: "), *partes, class_="alert alert-light border small mb-3")


panel_saliente = ui.nav_panel(
    "Movilidad saliente",
    ui.layout_sidebar(
        ui.sidebar(
            periodos("s"),
            multi("s_esc", "Esc. Prof. UCSP"),
            multi("s_dur", "Modalidad (duración)"),
            multi("s_for", "Modalidad (presencial/virtual)"),
            multi("s_con", "Concepto"),
            multi("s_pais", "País"),
            multi("s_uni", "Universidad de destino"),
            ui.input_action_button("s_reset", "Limpiar filtros", class_="btn-outline-secondary btn-sm"),
            width=290,
        ),
        fuente("archivo «Consolidado de Movilidad Estudiantil SALIENTE y ENTRANTE», pestaña MOVILIDAD SALIENTE. "
               "Cada fila de esa base es un estudiante UCSP que realizó una movilidad en un periodo académico. "
               "Al final está el detalle por estudiante (apellidos, nombres y correo). Los filtros de la izquierda se aplican a todos los indicadores, "
               "gráficos y tablas de esta pestaña."),
        ui.layout_column_wrap(
            kpi("Estudiantes UCSP en movilidad", "s_kpi_total",
                "Número de movilidades registradas. Un estudiante que salió en dos periodos cuenta dos veces."),
            kpi("Países de destino", "s_kpi_paises", "Países distintos a los que fueron los estudiantes."),
            kpi("Universidades de destino", "s_kpi_unis", "Universidades de destino distintas."),
            kpi("Movilidad presencial", "s_kpi_pres",
                "% de movilidades en modalidad Presencial (el resto es Virtual)."),
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
            "Número de movilidades en cada periodo académico (columna Per. Acad., llevada al formato AAAA-01/AAAA-02). "
            "Con el selector, cada barra se divide por la categoría elegida.",
        ),
        ui.layout_columns(
            tarjeta("Destinos en el mundo", ui.output_ui("s_g_mapa"),
                    "Color más intenso = más movilidades hacia ese país."),
            tarjeta("Estudiantes por país de destino", ui.output_ui("s_g_pais"),
                    "Número de movilidades por país de destino."),
            col_widths=(7, 5),
        ),
        ui.layout_columns(
            tarjeta("Top 15 universidades de destino", ui.output_ui("s_g_uni"),
                    "Las 15 universidades que recibieron más movilidades con los filtros aplicados."),
            ui.div(
                tarjeta("Por escuela profesional", ui.output_ui("s_g_esc"),
                        "Movilidades según la escuela del estudiante (Esc. Prof. UCSP)."),
                tarjeta("Por concepto", ui.output_ui("s_g_con"),
                        "Movilidades según la columna Concepto (intercambio, conferencia, etc.)."),
                tarjeta("Por modalidad (duración)", ui.output_ui("s_g_dur"),
                        "Movilidades según la duración registrada (Larga / Corta / Sin información)."),
            ),
            col_widths=(7, 5),
        ),
        tarjeta("Detalle por universidad de destino", ui.output_data_frame("s_tabla"),
                "Una fila por universidad: número de movilidades, primer y último periodo con movilidad, y convenios "
                "con los que se realizaron. Se puede filtrar escribiendo bajo cada columna."),
        tarjeta(
            ui.div(ui.span("Detalle por estudiante"),
                   ui.download_button("s_descargar_est", "Descargar (CSV)", class_="btn-sm btn-outline-secondary ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_data_frame("s_tabla_est"),
            "Una fila por movilidad, con los filtros aplicados. Se puede buscar escribiendo bajo cada columna y descargar en CSV.",
        ),
    ),
)

panel_entrante = ui.nav_panel(
    "Movilidad entrante",
    ui.layout_sidebar(
        ui.sidebar(
            periodos("e"),
            multi("e_car", "Carrera"),
            multi("e_pais", "País de origen"),
            multi("e_uni", "Universidad de origen"),
            multi("e_conv", "Convenio"),
            ui.input_action_button("e_reset", "Limpiar filtros", class_="btn-outline-secondary btn-sm"),
            width=290,
        ),
        fuente("archivo «Consolidado de Movilidad Estudiantil SALIENTE y ENTRANTE», pestaña MOVILIDAD ENTRANTE. "
               "Cada fila es un estudiante de otra universidad que estudió en la UCSP en un periodo. "
               "Al final está el detalle por estudiante (nombre y correo). Los filtros de la izquierda se aplican a toda esta pestaña."),
        ui.layout_column_wrap(
            kpi("Estudiantes visitantes", "e_kpi_total",
                "Número de estudiantes visitantes registrados en los periodos elegidos."),
            kpi("Países de origen", "e_kpi_paises", "Países distintos de donde vinieron."),
            kpi("Universidades de origen", "e_kpi_unis", "Universidades de origen distintas."),
            kpi("Periodos con movilidad", "e_kpi_per",
                "Periodos académicos con al menos un estudiante visitante."),
            width=1 / 4, fill=False,
        ),
        tarjeta(
            ui.div(ui.span("Evolución por periodo académico"),
                   ui.div(ui.input_select("e_por", None, width="200px", choices={
                       "": "Sin desagregar", "Carrera": "por Carrera", "País": "por País"}),
                          class_="ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_ui("e_g_periodo"),
            "Número de estudiantes visitantes por periodo académico. Con el selector se divide por carrera o país.",
        ),
        ui.layout_columns(
            tarjeta("Países de origen en el mundo", ui.output_ui("e_g_mapa"),
                    "Color más intenso = más estudiantes visitantes de ese país."),
            tarjeta("Estudiantes por país de origen", ui.output_ui("e_g_pais"),
                    "Número de estudiantes visitantes por país de origen."),
            col_widths=(7, 5),
        ),
        ui.layout_columns(
            tarjeta("Universidades de origen", ui.output_ui("e_g_uni"),
                    "Número de estudiantes visitantes por universidad de origen."),
            ui.div(
                tarjeta("Por carrera", ui.output_ui("e_g_car"),
                        "Carrera de la UCSP en la que estudiaron."),
                tarjeta("Por convenio", ui.output_ui("e_g_conv"),
                        "Convenio o red bajo el que llegaron."),
            ),
            col_widths=(7, 5),
        ),
        tarjeta("Detalle por universidad de origen", ui.output_data_frame("e_tabla"),
                "Una fila por universidad: número de estudiantes, primer y último periodo, y carreras en las que "
                "estudiaron. Se puede filtrar escribiendo bajo cada columna."),
        tarjeta(
            ui.div(ui.span("Detalle por estudiante"),
                   ui.download_button("e_descargar_est", "Descargar (CSV)", class_="btn-sm btn-outline-secondary ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_data_frame("e_tabla_est"),
            "Una fila por estudiante visitante en cada periodo, con los filtros aplicados. Se puede buscar escribiendo bajo cada columna y descargar en CSV.",
        ),
    ),
)

panel_curricula = ui.nav_panel(
    "Internacionalización de la Currícula",
    ui.output_ui("d_aviso"),
    ui.layout_sidebar(
        ui.sidebar(
            periodos("d"),
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
        fuente("archivo «BASE GENERAL DE MOVILIDAD DOCENTE», pestaña Consoli. Cada fila es una actividad "
               "internacional de un docente UCSP registrada para una carrera (ADM o CONT); una actividad para ambas "
               "carreras aparece en dos filas. No se usan correos, evidencias ni enlaces de encuestas."),
        ui.layout_column_wrap(
            kpi("Docentes UCSP participantes", "d_kpi_doc",
                "Docentes UCSP distintos con al menos una actividad."),
            kpi("% de docentes que participan", "d_kpi_doc_pct",
                "Docentes UCSP participantes ÷ docentes de la Facultad en esos periodos (o de la carrera, si filtras "
                "una). Con varios periodos, cada docente cuenta una sola vez, tanto arriba como abajo. Información "
                "proporcionada por el coordinador administrativo de la facultad.",
                "d_kpi_doc_pct_nota"),
            kpi("Actividades totales", "d_kpi_ind",
                "Clases espejo + COIL + profesores visitantes + otras actividades. En profesor visitante cuenta cada "
                "par académico (una sesión con dos visitantes suma dos)."),
            kpi("Clases espejo", "d_kpi_ce", "Clases espejo distintas (compartida ADM-CONT = 1)."),
            kpi("COIL", "d_kpi_coil", "COIL distintos (compartido ADM-CONT = 1)."),
            kpi("Profesores visitantes", "d_kpi_pv", "Cada académico visitante cuenta en cada actividad en la que "
                "participó: si una actividad tuvo dos pares académicos, suma dos.", "d_kpi_pv_nota"),
            kpi("Otras actividades", "d_kpi_otras",
                "Actividad internacional, postulación, congresos, etc. (todo lo que no es clase espejo, COIL ni "
                "profesor visitante)."),
            kpi("Alumnos participantes", "d_kpi_alu",
                "Suma de N° alumnos ADM + CONT de cada actividad (una vez por actividad)."),
            kpi("Universidades socias", "d_kpi_uni", "Universidades contraparte distintas."),
            width=1 / 3, fill=False,
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
            "Actividades distintas por periodo (columna Semestre). En profesor visitante cuenta cada par académico "
            "(una sesión con dos visitantes suma dos). Al desagregar por carrera, una actividad compartida por ADM "
            "y CONT se cuenta en ambas (igual que en el Resumen de Actividades).",
        ),
        tarjeta("Resumen de actividades por carrera y periodo", ui.output_data_frame("d_resumen"),
                "Mismo cálculo que la pestaña 'Resumen Actividades' de la base docente: número de filas de Consoli "
                "por carrera, tipo y periodo. La fila TOTAL suma Clase Espejo + COIL + Profesor Visitante."),
        ui.layout_columns(
            tarjeta("Países socios", ui.output_ui("d_g_mapa"),
                    "Color más intenso = más actividades distintas con universidades de ese país."),
            tarjeta("Actividades por país socio", ui.output_ui("d_g_pais"),
                    "Actividades distintas por país socio (no se muestran 'Sin información' ni 'No aplica')."),
            col_widths=(7, 5),
        ),
        ui.layout_columns(
            tarjeta("Top 15 universidades contraparte", ui.output_ui("d_g_uni"),
                    "Las 15 universidades con más actividades distintas."),
            tarjeta("Docentes UCSP con más actividades (top 15)", ui.output_ui("d_g_prof"),
                    "Los 15 docentes UCSP con más actividades distintas (columna Profesor UCSP)."),
            col_widths=(6, 6),
        ),
        ui.layout_columns(
            tarjeta("Por tipo de actividad", ui.output_ui("d_g_tipo"),
                    "Actividades distintas por tipo (se unifican mayúsculas: 'Clase espejo' = 'Clase Espejo')."),
            tarjeta("Por línea del curso", ui.output_ui("d_g_lin"),
                    "Actividades distintas por línea del curso (las 12 con más actividades)."),
            col_widths=(6, 6),
        ),
        ui.layout_columns(
            tarjeta("Por modalidad", ui.output_ui("d_g_mod"),
                    "Actividades distintas según modalidad (Virtual / Presencial)."),
            tarjeta("Por dictado", ui.output_ui("d_g_dic"),
                    "Actividades distintas según la columna Dictado de Consoli (Bilateral / Unilateral)."),
            col_widths=(6, 6),
        ),
        tarjeta(
            ui.div(ui.span("Detalle de actividades"),
                   ui.download_button("d_descargar", "Descargar (CSV)", class_="btn-sm btn-outline-secondary ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_data_frame("d_detalle"),
            "Una fila por actividad. Si una actividad estaba registrada para ADM y CONT, aparece una sola vez y la "
            "columna Carreras indica ambas. Se puede filtrar escribiendo bajo cada columna y descargar en CSV.",
        ),
    ),
)


panel_curr_alumnos = ui.nav_panel(
    "Internacionalización de la Currícula",
    ui.output_ui("c_aviso"),
    ui.layout_sidebar(
        ui.sidebar(
            periodos("c"),
            multi("c_esc", "Escuela profesional"),
            ui.input_checkbox_group("c_tipo", "Actividades que cuentan para el indicador",
                                    choices=TIPOS_CURRICULA, selected=TIPOS_CURRICULA),
            ui.input_radio_buttons("c_modo", "Al elegir varios periodos, contar…", choices={
                "unicos": "Alumnos únicos en todo el rango",
                "semestre": "Sumando cada semestre (como la macro)"}, selected="unicos"),
            ui.input_action_button("c_reset", "Limpiar filtros", class_="btn-outline-secondary btn-sm"),
            width=290,
        ),
        fuente("archivo «CONSULTA_INDICADOR_INTERNACIONALIZACION_CURRICULA». BASE_GENERAL: una fila por alumno, "
               "curso y grupo en cada periodo; el tipo de actividad de cada curso-grupo viene de la base docente "
               "(Consoli). MATRICULADOS: alumnos matriculados por escuela y periodo según el Portal de Transparencia "
               "UCSP. Al final está el detalle por alumno, con su código y nombre."),
        ui.layout_column_wrap(
            kpi("% de alumnos con actividad internacional", "c_kpi_pct",
                "Alumnos con actividad ÷ alumnos matriculados (tarjetas de la derecha).", "c_kpi_pct_nota"),
            kpi("Alumnos con actividad internacional", "c_kpi_num",
                "Alumnos que llevaron al menos un curso-grupo con una actividad de los tipos marcados.",
                "c_kpi_num_nota"),
            kpi("Alumnos matriculados (denominador)", "c_kpi_den",
                "Un periodo: Transparencia UCSP. Varios periodos con alumnos únicos: alumnos distintos de la base.",
                "c_kpi_den_nota"),
            width=1 / 3, fill=False,
        ),
        ui.layout_column_wrap(
            kpi("Alumnos en clases espejo", "c_kpi_ce",
                "Alumnos distintos con al menos una clase espejo.", "c_kpi_ce_nota"),
            kpi("Alumnos en COIL", "c_kpi_coil",
                "Alumnos distintos con al menos un COIL.", "c_kpi_coil_nota"),
            kpi("Alumnos con profesor visitante", "c_kpi_pv",
                "Alumnos distintos con al menos una sesión de profesor visitante.", "c_kpi_pv_nota"),
            width=1 / 3, fill=False,
        ),
        ui.div(
            ui.strong("¿Cómo se calcula? "),
            "En un solo periodo: alumnos únicos que participaron en al menos una actividad internacional "
            "(en cualquiera de sus cursos y grupos) ÷ alumnos matriculados según el Portal de Transparencia UCSP. "
            "En varios periodos, con 'Alumnos únicos en todo el rango': cada alumno cuenta una sola vez aunque haya "
            "participado en varios semestres, y el denominador son los alumnos distintos que aparecen en la base "
            "en ese rango (Transparencia solo publica totales por semestre y no permite identificar alumnos "
            "repetidos). Con 'Sumando cada semestre' se suman los resultados de cada periodo (alumno-semestre), "
            "como en la macro. Un alumno con más de un tipo de actividad aparece en cada tipo, pero en el "
            "indicador cuenta una vez.",
            class_="alert alert-light border small mb-3",
        ),
        tarjeta("% de alumnos con actividad internacional por periodo", ui.output_ui("c_g_pct"),
                "Para cada periodo y escuela: alumnos únicos con actividad ÷ matriculados de Transparencia "
                "(si falta ese dato, alumnos de la base). Pasa el mouse por una barra para ver el número de alumnos."),
        tarjeta("Alumnos por tipo de actividad y periodo", ui.output_ui("c_g_tipo"),
                "Alumnos distintos con cada tipo de actividad en cada periodo. Un alumno puede figurar en más de un tipo."),
        tarjeta("Detalle por periodo", ui.output_data_frame("c_tabla_per"),
                "Mismo detalle que la macro. 'En base' = alumnos distintos de la escuela en BASE_GENERAL (referencia; "
                "solo se usa como denominador si falta el dato de Transparencia). Las columnas por tipo son alumnos distintos."),
        ui.layout_columns(
            tarjeta("Cursos con más alumnos participantes (top 15)", ui.output_ui("c_g_curso"),
                    "Alumnos distintos que tuvieron una actividad internacional en ese curso (todos sus grupos) "
                    "en los periodos elegidos."),
            tarjeta("Participaciones por línea del curso", ui.output_ui("c_g_linea"),
                    "Participación = un alumno en un curso-grupo con actividad internacional. Un alumno con "
                    "actividad en dos cursos suma dos participaciones."),
            col_widths=(6, 6),
        ),
        tarjeta(
            ui.div(ui.span("Detalle por curso y grupo"),
                   ui.download_button("c_descargar", "Descargar (CSV)", class_="btn-sm btn-outline-secondary ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_data_frame("c_tabla_grupo"),
            "Una fila por periodo, escuela, curso, grupo y tipo de actividad, con el número de alumnos de esa escuela "
            "en ese grupo. El listado de alumnos está en «Detalle por alumno».",
        ),
        tarjeta(
            ui.div(ui.span("Detalle por alumno"),
                   ui.download_button("c_descargar_alu", "Descargar (CSV)", class_="btn-sm btn-outline-secondary ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_data_frame("c_tabla_alu"),
            "Una fila por alumno con actividad internacional (de los tipos marcados) en los periodos elegidos: periodos, número de cursos-grupo con actividad, tipos y cursos. Se puede buscar escribiendo bajo cada columna y descargar en CSV.",
        ),
    ),
)

panel_satisfaccion = ui.nav_panel(
    "Satisfacción con Intern. Currícula",
    ui.output_ui("q_aviso"),
    ui.layout_sidebar(
        ui.sidebar(
            periodos("q"),
            multi("q_prog", "Programa profesional"),
            multi("q_tipo", "Tipo de actividad"),
            multi("q_curso", "Curso"),
            multi("q_sem", "Semestre del curso"),
            ui.input_action_button("q_reset", "Limpiar filtros", class_="btn-outline-secondary btn-sm"),
            width=290,
        ),
        fuente("encuestas de satisfacción de los alumnos que participaron en actividades de internacionalización de "
               "la currícula (clases espejo, COIL, etc.), una hoja por periodo. El tipo de actividad de cada curso se "
               "toma de la base docente (Consoli) según el curso y el periodo. Si un alumno respondió dos veces por el "
               "mismo curso, se cuenta solo su última respuesta."),
        ui.layout_column_wrap(
            kpi("Encuestas respondidas", "q_kpi_n", "Una respuesta por alumno y curso.", "q_kpi_n_nota"),
            kpi("Calificación general", "q_kpi_cal",
                "Promedio de «¿Cómo calificarías esta experiencia?»: Deficiente = 1, Regular = 2, Buena = 3, "
                "Muy Buena = 4, Excelente = 5.", "q_kpi_cal_nota"),
            kpi("Recomendarían la actividad", "q_kpi_rec", "% que respondió «Sí» a «¿Recomendarías este tipo de "
                "actividades a otros estudiantes?».", "q_kpi_rec_nota"),
            kpi("Nivel de acuerdo promedio", "q_kpi_prom",
                "Promedio de las 14 afirmaciones (1 = muy en desacuerdo, 5 = muy de acuerdo).", "q_kpi_prom_nota"),
            width=1 / 4, fill=False,
        ),
        ui.layout_columns(
            tarjeta("Calificación general de la experiencia", ui.output_ui("q_g_cal"),
                    "Número de alumnos según cómo calificaron la experiencia en general. Entre paréntesis, el valor "
                    "que se usa para el promedio."),
            tarjeta("¿Recomendarían este tipo de actividades?", ui.output_ui("q_g_rec"),
                    "% de alumnos según su respuesta."),
            col_widths=(7, 5),
        ),
        tarjeta(
            ui.div(ui.span("Nivel de acuerdo con cada afirmación"),
                   ui.div(ui.input_select("q_dim", None, width="230px",
                                          choices={"": "Todas las dimensiones", **{d: d for d in ENC_DIMENSIONES}}),
                          class_="ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_ui("q_g_likert"),
            "Cada barra suma 100% de las respuestas a esa afirmación; los colores van de 1 (rojo, muy en desacuerdo) "
            "a 5 (verde, muy de acuerdo). El número a la derecha es el promedio. Pasa el mouse para ver cuántos "
            "alumnos eligieron cada opción.",
        ),
        ui.layout_columns(
            tarjeta("Promedio por dimensión", ui.output_ui("q_g_dim"),
                    "Promedio de las afirmaciones de cada dimensión: Aprendizaje (4), Impacto intercultural (4), "
                    "Logística y soporte (3) y Rol docente (3)."),
            tarjeta("Promedio por curso", ui.output_ui("q_g_curso"),
                    "Promedio de las 14 afirmaciones de cada curso, con el número de encuestas (n). El color indica "
                    "el tipo de actividad."),
            col_widths=(5, 7),
        ),
        tarjeta(
            ui.div(ui.span("Resultados por curso"),
                   ui.download_button("q_descargar_cursos", "Descargar (CSV)", class_="btn-sm btn-outline-secondary ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_data_frame("q_t_cursos"),
            "Una fila por curso y periodo. «% de acuerdo» = % de respuestas en 4 o 5 entre las 14 afirmaciones.",
        ),
        tarjeta(
            ui.div(ui.span("Palabras más repetidas en las respuestas abiertas"),
                   ui.div(ui.input_radio_buttons("q_campo", None, inline=True, choices={
                       "Aspectos a mejorar": "Aspectos a mejorar", "Comentarios": "Comentarios y sugerencias"}),
                          class_="ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_ui("q_g_palabras"),
            "Las 20 palabras que más aparecen (sin artículos, preposiciones ni palabras muy cortas).",
        ),
        tarjeta(
            ui.div(ui.span("Respuestas abiertas"),
                   ui.download_button("q_descargar_resp", "Descargar (CSV)", class_="btn-sm btn-outline-secondary ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_data_frame("q_t_resp"),
            "Alumnos que escribieron algo en «¿Qué aspectos podrían mejorarse?» o en «Comentarios o sugerencias». "
            "Se puede buscar escribiendo bajo cada columna y descargar en CSV (la descarga incluye todas las respuestas).",
        ),
    ),
)

panel_companygame = ui.nav_panel(
    "Torneo CompanyGame",
    ui.output_ui("cg_aviso"),
    ui.layout_sidebar(
        ui.sidebar(
            ui.input_checkbox_group("cg_cat", "Categorías", choices=CG_CATS, selected=CG_CATS),
            ui.input_select("cg_ed", "Edición para ver en detalle", choices=[]),
            ui.p("Las categorías se aplican a toda la pestaña. La edición elegida solo cambia la sección "
                 "«Detalle de la edición».", class_="kpi-nota"),
            ui.input_action_button("cg_reset", "Limpiar filtros", class_="btn-outline-secondary btn-sm"),
            width=290,
        ),
        fuente("base «CompanyGame_base_unificada», armada con los informes oficiales del Torneo ACBSP–CompanyGame "
               "(PDF de competencias 2024 y 2025, Informe Final 2024) y los archivos de seguimiento Torneo 2022, "
               "2023, 2024 y 2025. El detalle de la edición incluye el listado de estudiantes con nombre, correo y "
               "código (este último solo existe en 2024). La UCSP participa como Facultad de Ciencias Económicas y Empresariales, con estudiantes de "
               "Administración de Negocios y Contabilidad. Las categorías del torneo (Administración, Finanzas y "
               "Contabilidad, Marketing) son áreas de competencia, no carreras: un estudiante de cualquier carrera "
               "puede competir en cualquier categoría."),
        ui.h5("Evolución edición a edición", class_="sec-titulo mt-1 mb-3"),
        ui.layout_column_wrap(
            kpi("Ediciones con participación UCSP", "cg_k_ed", "Ediciones del torneo con equipos UCSP inscritos.",
                "cg_k_ed_nota"),
            kpi("Equipos inscritos en la última edición", "cg_k_eq",
                "Equipos UCSP inscritos en las categorías elegidas.", "cg_k_eq_nota"),
            kpi("Estudiantes en la última edición", "cg_k_est",
                "Estudiantes UCSP distintos en los listados de la edición.", "cg_k_est_nota"),
            kpi("Mejor puesto entre instituciones", "cg_k_best",
                "Mejor posición de la UCSP en el ranking de instituciones de una categoría.", "cg_k_best_nota"),
            width=1 / 4, fill=False,
        ),
        ui.layout_columns(
            tarjeta("Equipos UCSP por edición", ui.output_ui("cg_g_part"),
                    "Inscritos = equipos registrados; activos = equipos que tomaron decisiones en el simulador; "
                    "clasificados = equipos que superaron la fase clasificatoria. Totales de todas las categorías, "
                    "según el historial de participación de los informes oficiales."),
            tarjeta("Tasa de clasificación: UCSP vs. torneo", ui.output_ui("cg_g_clas"),
                    "Equipos clasificados ÷ equipos inscritos. La línea punteada es el mismo cálculo para todas las "
                    "instituciones del torneo. Todas las categorías."),
            col_widths=(6, 6),
        ),
        ui.layout_columns(
            tarjeta("Puesto de la UCSP en el ranking de instituciones", ui.output_ui("cg_g_pos"),
                    "Posición de la UCSP en el ranking indexado de cada categoría (1 = primer lugar; el eje está "
                    "invertido, así que subir es mejorar). Pasa el mouse para ver cuántas instituciones competían. "
                    "2022 no tiene posición publicada."),
            tarjeta(
                ui.div(ui.span("Estudiantes UCSP por edición"),
                       ui.div(ui.input_select("cg_est_por", None, width="210px", choices={
                           "Programa / carrera": "por carrera", "Categoría": "por categoría del torneo"}),
                              class_="ms-auto"),
                       class_="d-flex align-items-center gap-2"),
                ui.output_ui("cg_g_est"),
                "Estudiantes distintos de los equipos inscritos oficialmente en cada edición (en 2025 no se cuentan "
                "los grupos que no se inscribieron o no confirmaron). La categoría del torneo no es la carrera: "
                "estudiantes de Administración de Negocios y de Contabilidad pueden competir en cualquier "
                "categoría. La carrera es la que figura en cada archivo (2025 revisado por la Facultad; en 2024 no hubo "
                "estudiantes de Contabilidad). 2024 corresponde al seguimiento interno (Torneo 2024.xlsx)."),
            col_widths=(6, 6),
        ),
        ui.layout_columns(
            tarjeta("Avance de los equipos por hito", ui.output_ui("cg_g_hitos"),
                    "% de equipos UCSP que cumplió cada hito, sobre los equipos con dato. Ronda: 2022 decisión del "
                    "periodo; 2023 y 2024 decisión tomada; 2025 cuestionario de la ronda. 2024 solo tiene seguimiento "
                    "hasta la ronda 3 y 2025 no registra video final."),
            tarjeta("Competencias de los equipos clasificados", ui.output_ui("cg_g_comp"),
                    "Promedio, entre las seis competencias evaluadas, del % de equipos clasificados en nivel "
                    "Destacado o Satisfactorio. Solo existe evaluación en 2024 y 2025. Administración 2024 tuvo "
                    "2 equipos evaluados."),
            col_widths=(7, 5),
        ),
        ui.h5(ui.output_text("cg_titulo_ed", inline=True), class_="sec-titulo mt-4 mb-3"),
        ui.layout_column_wrap(
            kpi("Equipos inscritos", "cg_d_eq", None, "cg_d_eq_nota"),
            kpi("Equipos clasificados", "cg_d_cla", None, "cg_d_cla_nota"),
            kpi("Estudiantes", "cg_d_est", "Estudiantes distintos en el listado de la edición.", "cg_d_est_nota"),
            kpi("Entregaron informe final", "cg_d_inf", None, "cg_d_inf_nota"),
            width=1 / 4, fill=False,
        ),
        tarjeta("Resultados de la UCSP por categoría", ui.output_data_frame("cg_t_cat"),
                "Datos de los informes oficiales. Puesto = posición de la UCSP en el ranking indexado de instituciones. "
                "Ranking final medio e indexado: puntaje de 0 a 1000. Celdas vacías = dato no publicado."),
        ui.output_ui("cg_fila_equipos"),
        ui.output_ui("cg_oficial_2024"),
        ui.output_ui("cg_comp_ed"),
        tarjeta(
            ui.div(ui.span("Detalle por equipo"),
                   ui.download_button("cg_descargar", "Descargar (CSV)", class_="btn-sm btn-outline-secondary ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_data_frame("cg_t_eq"),
            "Una fila por equipo UCSP de la edición: integrantes, hitos y puestos en el simulador. Se puede filtrar "
            "escribiendo bajo cada columna y descargar en CSV.",
        ),
        tarjeta(
            ui.div(ui.span("Estudiantes de la edición"),
                   ui.download_button("cg_descargar_est", "Descargar (CSV)", class_="btn-sm btn-outline-secondary ms-auto"),
                   class_="d-flex align-items-center gap-2"),
            ui.output_data_frame("cg_t_est"),
            "Estudiantes de los equipos inscritos en la edición elegida. El código de alumno solo figura en el archivo de 2024. Se puede buscar escribiendo bajo cada columna y descargar en CSV.",
        ),
    ),
)

panel_docentes = ui.nav_panel(
    "Indicadores de Docentes",
    # Aquí se pueden agregar más subpestañas de docentes junto a panel_curricula
    ui.navset_underline(panel_curricula, id="sub_docentes"),
)

# ---------- INICIO: Presentación y Hojas de ruta ----------
def _ul(items, clase=""):
    return ui.tags.ul(*[ui.tags.li(ui.span(class_="li-ico"), ui.span(t)) for t in items],
                      class_=f"lista-ico {clase}")


def _seccion(titulo, *hijos, subtitulo=None):
    cab = [ui.h4(titulo, class_="sec-titulo")]
    if subtitulo:
        cab.append(ui.p(subtitulo, class_="sec-sub"))
    return ui.div(*cab, *hijos, class_="seccion")


def _tarjeta_seccion(ruta, titulo, texto):
    return ui.div(
        ui.div(ruta, class_="sc-ruta"),
        ui.h5(titulo, class_="sc-titulo"),
        ui.p(texto, class_="sc-texto"),
        class_="sc-card",
    )


panel_presentacion = ui.nav_panel(
    "Presentación",
    ui.div(
        ui.div(
            ui.div("Universidad Católica San Pablo · Facultad de Ciencias Económicas y Empresariales", class_="hero-kicker"),
            ui.h1("Internacionalización FCEE", class_="hero-titulo"),
            ui.p("Dashboard de indicadores de internacionalización de las escuelas profesionales de "
                 "Administración de Negocios y Contabilidad: movilidad estudiantil, internacionalización de la "
                 "currícula y actividades internacionales de los docentes, en un solo lugar y con datos que se "
                 "actualizan automáticamente.", class_="hero-texto"),
            ui.div(ui.span("Alumnos", class_="hero-chip"), ui.span("Docentes", class_="hero-chip"),
                   ui.span("Hojas de ruta 2027–2029", class_="hero-chip"), ui.span("Datos en línea", class_="hero-chip"),
                   class_="hero-chips"),
            class_="hero",
        ),
        _seccion(
            "¿Para qué sirve este dashboard?",
            ui.div(
                ui.div(ui.h5("Medir"),
                       ui.p("Reúne en indicadores claros la información de movilidad, currícula y actividades "
                            "docentes que antes estaba en varias bases y hojas de cálculo."), class_="pq-card"),
                ui.div(ui.h5("Dar seguimiento"),
                       ui.p("Permite comparar los resultados con las metas de las hojas de ruta de "
                            "internacionalización de cada programa."), class_="pq-card"),
                ui.div(ui.h5("Explorar"),
                       ui.p("Con los filtros se puede ver cualquier periodo, escuela, país, universidad, docente "
                            "o tipo de actividad, y descargar el detalle."), class_="pq-card"),
                ui.div(ui.h5("Compartir"),
                       ui.p("Ofrece a directores y docentes una misma fuente de información, siempre actualizada "
                            "y con el detalle por estudiante para hacer seguimiento."), class_="pq-card"),
                class_="pq-grid",
            ),
        ),
        _seccion(
            "¿Qué encontrarás en cada pestaña?",
            ui.div(
                _tarjeta_seccion("Inicio", "Hojas de ruta",
                                 "Diagnóstico, objetivos, estrategias y metas 2027–2029 de internacionalización de "
                                 "Administración de Negocios y de Contabilidad, con el avance actual de los "
                                 "indicadores que el dashboard puede medir."),
                _tarjeta_seccion("Indicadores de Alumnos", "Movilidad saliente",
                                 "Estudiantes UCSP que realizaron intercambio: evolución por periodo, países y "
                                 "universidades de destino, modalidad y concepto."),
                _tarjeta_seccion("Indicadores de Alumnos", "Movilidad entrante",
                                 "Estudiantes de otras universidades que estudiaron en la UCSP: países, "
                                 "universidades de origen, carreras y convenios."),
                _tarjeta_seccion("Indicadores de Alumnos", "Internacionalización de la Currícula",
                                 "% de alumnos que participaron en clases espejo, COIL o con profesores visitantes "
                                 "respecto de los matriculados, por periodo y escuela."),
                _tarjeta_seccion("Indicadores de Docentes", "Internacionalización de la Currícula",
                                 "Actividades internacionales de los docentes: clases espejo, COIL, profesores "
                                 "visitantes, universidades socias y detalle de cada actividad."),
                class_="sc-grid",
            ),
        ),
        _seccion(
            "Cómo usarlo",
            ui.div(
                ui.div(ui.strong("Filtros"), ui.span(" — en el panel izquierdo de cada pestaña: periodos, "
                                                     "escuela, país, etc. Se aplican a todo lo que ves en esa pestaña. Cada pestaña abre "
                                                     "en el semestre en curso; haz clic en los periodos que quieras sumar (o «Todos» para el histórico)."), class_="tip"),
                ui.div(ui.strong("Gráficos"), ui.span(" — pasa el mouse sobre una barra o país para ver el valor exacto; "
                                                      "con el botón de ampliar (esquina inferior derecha) se ven a pantalla completa."), class_="tip"),
                ui.div(ui.strong("Notas en gris"), ui.span(" — explican de dónde salen los datos y cómo se calcula "
                                                           "cada indicador."), class_="tip"),
                ui.div(ui.strong("Descargar"), ui.span(" — las tablas de detalle se pueden filtrar y descargar en CSV."), class_="tip"),
                ui.div(ui.strong("Actualizar"), ui.span(" — los datos se leen de las bases en Google Drive cada 10 minutos; "
                                                        "el botón «Actualizar datos» fuerza la lectura."), class_="tip"),
                class_="tips",
            ),
        ),
        ui.div(
            ui.div("SV", class_="autor-avatar"),
            ui.div(
                ui.div("Desarrollado por", class_="autor-kicker"),
                ui.div("Sebastián David Villalba Bouroncle", class_="autor-nombre"),
                ui.div("Profesor Tiempo Completo · Facultad de Ciencias Económicas y Empresariales", class_="autor-cargo"),
                ui.div("Universidad Católica San Pablo · Arequipa, Perú", class_="autor-cargo"),
            ),
            class_="autor",
        ),
        class_="inicio-wrap",
    ),
)


def panel_ruta(k):
    R = RUTAS[k]
    n_med = sum(1 for e in R["estrategias"] if e[7])
    n_meso = sum(1 for e in R["estrategias"] if e[1] == "Meso")
    pid = k.lower()
    return ui.nav_panel(
        f"Hoja de Ruta {R['programa']}",
        ui.div(
            ui.div(
                ui.div("Ruta de Internacionalización · Metas 2027 – 2029", class_="hero-kicker"),
                ui.h1(f"Programa Profesional de {R['programa']}", class_="hero-titulo"),
                ui.div(*[ui.span(ui.span(f"{a}: ", class_="chip-k"), b, class_="hero-chip") for a, b in R["info"]],
                       class_="hero-chips"),
                class_="hero",
            ),
            ui.div(
                ui.div(ui.div(str(len(R["objetivos"])), class_="mini-num"), ui.div("objetivos", class_="mini-lbl"), class_="mini"),
                ui.div(ui.div(str(len(R["estrategias"])), class_="mini-num"), ui.div("estrategias", class_="mini-lbl"), class_="mini"),
                ui.div(ui.div(f"{n_meso} / {len(R['estrategias']) - n_meso}", class_="mini-num"),
                       ui.div("nivel meso / micro", class_="mini-lbl"), class_="mini"),
                ui.div(ui.div(str(n_med), class_="mini-num"),
                       ui.div("metas medidas en vivo por el dashboard", class_="mini-lbl"), class_="mini"),
                class_="mini-grid",
            ),
            _seccion(
                "Perfil global",
                ui.layout_columns(
                    ui.div(
                        ui.h5("Perfil de egreso del programa"),
                        ui.p(R["perfil_intro"]),
                        ui.p(ui.em(R["perfil_mision"])) if R["perfil_mision"] else None,
                        ui.p(ui.strong(R["perfil_lista_titulo"])),
                        _ul(R["perfil_lista"], "lista-perfil"),
                        class_="bloque",
                    ),
                    ui.div(
                        ui.h5("Perfil global UCSP"),
                        *[ui.div(ui.div(t, class_="pilar-t"), ui.div(sub, class_="pilar-s"), class_="pilar")
                          for t, sub in _PILARES_UCSP],
                        class_="bloque",
                    ),
                    col_widths=(8, 4),
                ),
            ),
            _seccion(
                "Diagnóstico de internacionalización",
                ui.layout_columns(
                    ui.div(ui.h5("Fortalezas"), _ul(R["fortalezas"], "lista-ok"), class_="bloque bloque-ok"),
                    ui.div(ui.h5("Oportunidades de mejora"), _ul(R["oportunidades"], "lista-warn"),
                           class_="bloque bloque-warn"),
                    col_widths=(6, 6),
                ),
            ),
            _seccion(
                "Objetivos de internacionalización del programa",
                ui.div(*[ui.div(ui.div(str(i + 1), class_="obj-num"), ui.p(o), class_="obj-card")
                         for i, o in enumerate(R["objetivos"])], class_="obj-grid"),
            ),
            _seccion(
                "Estrategias y metas",
                ui.div(
                    ui.input_radio_buttons(f"hr_{pid}_obj", "Objetivo", inline=True,
                                           choices={"0": "Todos", "1": "Obj. 1", "2": "Obj. 2", "3": "Obj. 3"}),
                    ui.input_radio_buttons(f"hr_{pid}_niv", "Nivel", inline=True,
                                           choices={"": "Todos", "Meso": "Meso", "Micro": "Micro"}),
                    ui.input_checkbox(f"hr_{pid}_med", "Solo metas medidas por el dashboard", False),
                    class_="filtros-ruta",
                ),
                ui.output_ui(f"hr_{pid}_estr"),
                ui.p("Las metas son anuales: cada meta se compara solo con lo logrado en ese mismo año, sin "
                     "acumular años anteriores. En las estrategias medidas por el dashboard, «Logrado» se calcula en "
                     "vivo: estudiantes de la escuela en movilidad saliente en el año; % de alumnos con experiencias "
                     "internacionales en el año (alumnos únicos del año ÷ alumnos distintos de la base en el año; si "
                     "solo hay un semestre, el % de ese semestre sobre los matriculados de Transparencia); y cursos "
                     "distintos con clase espejo, COIL o profesor visitante en el año. «Parcial» indica un año en curso "
                     "o con un solo semestre registrado. La «Referencia» muestra el último año previo a 2027, solo "
                     "como punto de partida.", class_="leyenda-suelta"),
                subtitulo="Filtra por objetivo o nivel. Cada tarjeta muestra el indicador, las metas por año y el responsable.",
            ),
            ui.p(f"Fuente: documento «Ruta de Internacionalización del Programa Profesional de {R['programa']}».",
                 class_="leyenda-suelta"),
            class_="inicio-wrap",
        ),
    )


panel_inicio = ui.nav_panel(
    "Inicio",
    ui.navset_underline(panel_presentacion, panel_ruta("ADM"), panel_ruta("CONT"), id="sub_inicio"),
)

app_ui = ui.page_navbar(
    panel_inicio,
    ui.nav_panel(
        "Indicadores de Alumnos",
        ui.navset_underline(panel_saliente, panel_entrante, panel_curr_alumnos, panel_satisfaccion, panel_companygame, id="sub_alumnos"),
    ),
    panel_docentes,
    ui.nav_spacer(),
    ui.nav_control(ui.input_action_button("recargar", "Actualizar datos",
                                          class_="btn-sm btn-light")),
    title="Internacionalización FCEE",
    window_title="Internacionalización FCEE",
    footer=ui.div(ui.output_text("estado"), class_="text-muted small px-4 py-2"),
    fillable=False,
    header=ui.TagList(
        ui.output_ui("aviso"),
        ui.head_content(
            ui.tags.meta(name="robots", content="noindex, nofollow"),
            ui.tags.script(src="plotlyjs/plotly.min.js"),
            ui.tags.script(f"document.documentElement.setAttribute('data-bs-theme', '{T['modo']}');"),
        ),
        ui.tags.style(f"""
        body {{ background:{T['fondo']}; color:{T['tinta']}; }}
        .card, .bslib-value-box, .bslib-sidebar-layout > .sidebar {{ background:{T['superficie']} !important; }}
        .bslib-sidebar-layout {{ background:{T['superficie']}; }}
        .bslib-value-box {{ border-top: 3px solid {T['acento']} !important; }}
        .bslib-value-box .value-box-value {{ font-size: 2rem; font-weight: 600; color:{T['tinta']}; }}
        .bslib-value-box .value-box-title {{ font-size: .85rem; color:{T['tinta_2']}; }}
        .card-header {{ font-weight: 600; background: transparent; color:{T['tinta']}; }}
        .navbar {{ background: {T['barra']} !important; border-bottom: 1px solid {T['grilla']}; }}
        .navbar .nav-link, .navbar-brand {{ color: {T['barra_texto']} !important; }}
        .navbar .nav-link.active {{ border-bottom: 2px solid {T['acento'] if T['barra'] in ('#ffffff',) else T['barra_texto']}; }}
        .navbar-brand {{ font-weight: 600; }}
        .navbar .btn {{ border:1px solid {T['grilla']}; }}
        #sub_inicio, #sub_alumnos, #sub_docentes {{ padding: .75rem 1rem 0; background:{T['superficie']}; border-bottom:1px solid {T['grilla']}; }}
        #sub_inicio .nav-link, #sub_alumnos .nav-link, #sub_docentes .nav-link {{ color:{T['tinta_2']} !important; font-weight:500; }}
        #sub_inicio .nav-link.active, #sub_alumnos .nav-link.active, #sub_docentes .nav-link.active {{ color:{T['tinta']} !important; border-bottom-color:{T['acento']}; }}
        .card-header .form-group {{ margin-bottom: 0; }}
        /* ---- Pantalla de clave ---- */
        .modal-backdrop.show {{ opacity: 1; background:{T['fondo']}; }}
        .clave-caja {{ padding: .75rem .5rem .25rem; }}
        .clave-titulo {{ font-size: 1.25rem; font-weight: 700; color:{T['tinta']}; }}
        .clave-sub {{ color:{T['tinta_2']}; font-size: .9rem; margin: .25rem 0 1rem; }}
        .clave-error {{ color:#e66767; font-size: .85rem; margin-top: .5rem; }}
        /* ---- Periodos como botones ---- */
        .per-botones {{ margin-bottom: 1rem; }}
        .per-botones .control-label {{ margin-bottom: .35rem; }}
        .per-acciones {{ font-size: .78rem; }}
        .per-acciones a {{ color:{T['acento']}; text-decoration: none; }}
        .per-botones .shiny-options-group {{ display:flex !important; flex-wrap:wrap; gap:.3rem; justify-content:flex-start; }}
        .per-botones label.checkbox-inline {{ margin:0 !important; padding:0 !important; width:auto !important; }}
        .per-botones label.checkbox-inline input {{ position:absolute; opacity:0; pointer-events:none; }}
        .per-botones label.checkbox-inline span {{ display:inline-block; padding:.25rem .55rem; border-radius:999px;
                                          cursor:pointer; font-size:.8rem; border:1px solid {T['grilla']};
                                          color:{T['tinta_2']}; background:{T['superficie']}; user-select:none;
                                          transition: all .12s ease; }}
        .per-botones label.checkbox-inline span:hover {{ border-color:{T['acento']}; color:{T['tinta']}; }}
        .per-botones label.checkbox-inline input:checked + span {{ background:{T['acento']}; border-color:{T['acento']};
                                                                   color:#fff; }}
        .kpi-nota {{ font-size: .72rem; color:{T['nota_texto']}; background:{T['nota_fondo']};
                     border-radius: 6px; padding: .35rem .5rem; margin: .5rem 0 0; line-height: 1.25; }}
        .kpi-dinamica {{ font-size: .8rem; color:{T['tinta']}; font-weight: 500; }}
        .card-footer.leyenda {{ font-size: .78rem; color:{T['nota_texto']}; background:{T['nota_fondo']};
                                border-top: 1px solid {T['grilla']}; padding-right: 2.75rem; }}
        .alert-light {{ background:{T['nota_fondo']} !important; color:{T['nota_texto']};
                       border: none !important; border-left: 3px solid {T['acento']} !important; }}
        .alert-light strong {{ color:{T['tinta']}; }}
        .btn-outline-secondary {{ color:{T['tinta_2']}; border-color:{T['grilla']}; }}
        .btn-outline-secondary:hover {{ background:{T['nota_fondo']}; color:{T['tinta']}; }}
        .form-check-input:checked {{ background-color:{T['acento']}; border-color:{T['acento']}; }}
        /* ---- Inicio ---- */
        .inicio-wrap {{ max-width: 1280px; margin: 0 auto; padding: 1.25rem 1rem 2rem; }}
        .hero {{ border-radius: 18px; padding: 2.2rem 2.4rem; color:#fff; margin-bottom: 1.5rem;
                 background: radial-gradient(circle at 85% 15%, rgba(255,255,255,.18), transparent 40%),
                             linear-gradient(135deg, {T['acento']}, color-mix(in srgb, {T['acento']} 35%, #000)); }}
        .hero-kicker {{ text-transform: uppercase; letter-spacing: .08em; font-size: .78rem; opacity: .85; }}
        .hero-titulo {{ font-size: 2.4rem; font-weight: 700; margin: .4rem 0 .6rem; color:#fff; }}
        .hero-texto {{ font-size: 1.05rem; max-width: 820px; opacity: .95; }}
        .hero-chips {{ display:flex; flex-wrap:wrap; gap:.5rem; margin-top: 1rem; }}
        .hero-chip {{ background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.25);
                      border-radius: 999px; padding: .3rem .8rem; font-size: .85rem; }}
        .chip-k {{ opacity: .75; }}
        .seccion {{ margin: 1.75rem 0; }}
        .sec-titulo {{ font-weight: 700; margin-bottom: .25rem; color:{T['tinta']}; }}
        .sec-sub {{ color:{T['tinta_2']}; font-size: .9rem; margin-bottom: .9rem; }}
        .pq-grid, .sc-grid, .obj-grid {{ display:grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); margin-top:.75rem; }}
        .pq-card, .sc-card, .obj-card, .bloque, .estr-card, .mini {{ background:{T['superficie']}; border:1px solid {T['grilla']};
                     border-radius: 14px; padding: 1.1rem 1.2rem; }}
        .pq-card h5, .sc-titulo, .bloque h5 {{ font-weight: 650; color:{T['tinta']}; }}
        .pq-card p, .sc-texto, .obj-card p, .bloque p, .lista-ico li {{ color:{T['tinta_2']}; font-size: .92rem; }}
        .pq-ico, .sc-ico {{ font-size: 1.8rem; margin-bottom: .4rem; }}
        .sc-card {{ border-top: 3px solid {T['acento']}; transition: transform .15s ease; }}
        .sc-card:hover, .pq-card:hover, .estr-card:hover {{ transform: translateY(-3px); }}
        .sc-ruta {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; color:{T['acento']}; font-weight: 600; }}
        .tips {{ display:grid; gap:.6rem; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); margin-top:.6rem; }}
        .tip {{ background:{T['nota_fondo']}; color:{T['nota_texto']}; border-radius: 10px; padding: .7rem .9rem; font-size: .88rem; }}
        .tip strong {{ color:{T['tinta']}; }}
        .autor {{ display:flex; align-items:center; gap: 1.1rem; margin-top: 2rem; padding: 1.2rem 1.4rem;
                  border-radius: 16px; background:{T['superficie']}; border:1px solid {T['grilla']}; border-left: 4px solid {T['acento']}; }}
        .autor-avatar {{ width: 64px; height: 64px; border-radius: 50%; display:flex; align-items:center; justify-content:center;
                         font-weight: 700; font-size: 1.3rem; color:#fff; background:{T['acento']}; flex: none; }}
        .autor-kicker {{ font-size: .75rem; text-transform: uppercase; letter-spacing: .06em; color:{T['tinta_2']}; }}
        .autor-nombre {{ font-size: 1.2rem; font-weight: 700; color:{T['tinta']}; }}
        .autor-cargo {{ font-size: .9rem; color:{T['tinta_2']}; }}
        .mini-grid {{ display:grid; gap: .8rem; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }}
        .mini {{ text-align:center; padding: .9rem; }}
        .mini-num {{ font-size: 1.8rem; font-weight: 700; color:{T['acento']}; }}
        .mini-lbl {{ font-size: .82rem; color:{T['tinta_2']}; }}
        .lista-ico {{ list-style: none; padding-left: 0; margin: 0; }}
        .lista-ico li {{ display:flex; gap:.6rem; margin-bottom: .55rem; line-height: 1.4; }}
        .li-ico {{ flex: none; width: 7px; height: 7px; border-radius: 50%; margin-top: .5rem; background:{T['acento']}; }}
        .lista-ok .li-ico {{ background:#2fbf71; }}
        .lista-warn .li-ico {{ background:#e3a008; }}
        .bloque-ok {{ border-top: 3px solid #2fbf71; }}
        .bloque-warn {{ border-top: 3px solid #e3a008; }}
        .pilar {{ display:flex; flex-direction:column; gap:.1rem; padding:.75rem; border-radius: 12px;
                  background:{T['nota_fondo']}; margin-bottom:.6rem; }}
        .pilar-t {{ font-weight: 650; color:{T['tinta']}; }}
        .pilar-s {{ font-size: .82rem; color:{T['tinta_2']}; }}
        .obj-card {{ display:flex; gap: .9rem; align-items:flex-start; }}
        .obj-num {{ flex:none; width: 2.4rem; height: 2.4rem; border-radius: 50%; background:{T['acento']}; color:#fff;
                    display:flex; align-items:center; justify-content:center; font-weight: 700; font-size: 1.1rem; }}
        .filtros-ruta {{ display:flex; flex-wrap:wrap; gap: 1.5rem; align-items:flex-end; padding: .8rem 1rem;
                         background:{T['superficie']}; border:1px solid {T['grilla']}; border-radius: 12px; margin-bottom: 1rem; }}
        .filtros-ruta .form-group, .filtros-ruta .shiny-input-container {{ margin-bottom: 0; width:auto; }}
        .estr-grid {{ display:grid; gap: 1rem; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); }}
        .estr-card {{ display:flex; flex-direction:column; gap:.6rem; transition: transform .15s ease; }}
        .estr-top {{ display:flex; flex-wrap:wrap; gap:.4rem; align-items:center; }}
        .tag {{ font-size: .72rem; font-weight: 600; border-radius: 999px; padding: .15rem .6rem; }}
        .tag-obj {{ background:{T['acento']}; color:#fff; }}
        .tag-niv {{ border:1px solid {T['grilla']}; color:{T['tinta_2']}; }}
        .tag-med {{ background:#2fbf71; color:#0b2b1b; }}
        .estr-texto {{ font-weight: 600; color:{T['tinta']}; margin:0; }}
        .estr-ind {{ font-size: .85rem; color:{T['tinta_2']}; }}
        .metas {{ display:grid; grid-template-columns: repeat(3, 1fr); gap:.5rem; }}
        .meta {{ background:{T['nota_fondo']}; border-radius: 10px; padding: .45rem .6rem; }}
        .meta-anio {{ font-size: .72rem; color:{T['tinta_2']}; }}
        .meta-val {{ font-size: 1.15rem; font-weight: 700; color:{T['tinta']}; }}
        .meta-barra {{ height: 6px; border-radius: 4px; background:{T['grilla']}; margin-top:.3rem; overflow:hidden; }}
        .meta-barra > div {{ height: 100%; border-radius: 4px; background:{T['acento']}; }}
        .meta-real {{ font-size: .72rem; margin-top: .35rem; color:{T['tinta_2']}; }}
        .meta-real.ok {{ color:#2fbf71; font-weight: 600; }}
        .meta-real.no {{ color:#e3a008; font-weight: 600; }}
        .meta-real.parcial {{ color:{T['tinta']}; }}
        .meta-ok {{ box-shadow: inset 0 0 0 1px #2fbf71; }}
        .avance {{ border-radius: 10px; padding: .55rem .7rem; border: 1px dashed #2fbf71; font-size: .85rem; color:{T['tinta']}; }}
        .avance-barra {{ height: 8px; border-radius: 4px; background:{T['grilla']}; margin-top:.35rem; overflow:hidden; }}
        .avance-barra > div {{ height:100%; background:#2fbf71; border-radius: 4px; }}
        .estr-pie {{ display:flex; justify-content:space-between; gap:.5rem; flex-wrap:wrap; font-size: .8rem; color:{T['tinta_2']};
                     border-top: 1px solid {T['grilla']}; padding-top: .5rem; margin-top:auto; }}
        .leyenda-suelta {{ font-size: .78rem; color:{T['nota_texto']}; background:{T['nota_fondo']}; border-radius: 10px;
                           padding: .55rem .8rem; margin-top: 1rem; }}
        #q_t_resp td {{ vertical-align: top; }}
        #q_t_resp td:nth-child(4), #q_t_resp td:nth-child(5) {{ min-width: 340px; white-space: normal; }}
        #d_detalle td, #c_tabla_grupo td, #c_tabla_per td, #cg_t_eq td, #cg_t_cat td, #s_tabla_est td, #e_tabla_est td, #c_tabla_alu td, #cg_t_est td, #q_t_cursos td {{ white-space: nowrap; max-width: 420px; overflow: hidden; text-overflow: ellipsis; }}
    """)),
)

# ─────────────────────────────────────────────────────────────
# SERVIDOR
# ─────────────────────────────────────────────────────────────
def _periodos(df):
    """Periodos válidos (AAAA-SS) ordenados."""
    return sorted(p for p in df["Periodo"].unique() if re.fullmatch(r"\d{4}-\d{2}", str(p)))


def _periodo_actual() -> str:
    """Semestre en curso según la fecha de hoy: enero–julio = AAAA-01, agosto–diciembre = AAAA-02."""
    hoy = datetime.now()
    return f"{hoy.year}-{'01' if hoy.month <= 7 else '02'}"


def _periodo_inicial(per: list) -> str:
    """Periodo con el que abre cada pestaña: el último ya iniciado (no los futuros, p. ej. movilidades
    programadas para el próximo año). Si la base aún no tiene el semestre en curso, el más reciente que tenga."""
    hasta_hoy = [p for p in per if p <= _periodo_actual()]
    return hasta_hoy[-1] if hasta_hoy else per[-1]


def _filtrar(df, periodos_sel, filtros: dict):
    d = df
    if periodos_sel:                                      # sin periodos marcados = todos
        d = d[d["Periodo"].isin(list(periodos_sel))]
    for col, sel in filtros.items():
        if sel:
            d = d[d[col].isin(sel)]
    return d


def _orden(df, cols):
    """Orden fijo de categorías (por frecuencia en toda la base) para que cada una conserve su color."""
    return {c: df[c].value_counts().index.tolist() for c in cols}


def server(input, output, session):

    error = reactive.value(None)

    # ----- Acceso con clave: hasta ingresarla no se carga ningún dato -----
    autenticado = reactive.value(not CLAVE)
    intentos = {"n": 0}

    def _pedir_clave(msg=None):
        ui.modal_show(ui.modal(
            ui.div(
                ui.div("Internacionalización FCEE", class_="clave-titulo"),
                ui.p("Ingresa la clave para ver el dashboard.", class_="clave-sub"),
                ui.input_password("clave", None, placeholder="Clave", width="100%"),
                ui.div(msg, class_="clave-error") if msg else None,
                ui.input_action_button("entrar", "Entrar", class_="btn-primary w-100 mt-3"),
                ui.tags.script("""
                    setTimeout(function(){
                      var c = document.getElementById('clave'); if (!c) return; c.focus();
                      c.addEventListener('keyup', function(e){
                        if (e.key === 'Enter') { Shiny.setInputValue('clave', c.value, {priority:'event'});
                                                 document.getElementById('entrar').click(); }
                      });
                    }, 300);"""),
                class_="clave-caja",
            ),
            title=None, footer=None, easy_close=False, size="s", fade=False,
        ))

    if CLAVE:
        _pedir_clave()

    @reactive.effect
    @reactive.event(input.entrar)
    def _():
        if hmac.compare_digest(str(input.clave() or "").encode(), CLAVE.encode()):
            autenticado.set(True)
            ui.modal_remove()
        else:
            intentos["n"] += 1
            time.sleep(min(intentos["n"], 5))            # cada intento fallido espera un poco más
            ui.modal_remove()
            _pedir_clave("Clave incorrecta. Inténtalo de nuevo.")

    @reactive.calc
    def datos():
        req(autenticado())
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
            actual = [p for p in input[f"{pre}_per"]() if p in per]
            sel = [_periodo_inicial(per)] if limpiar else actual
            ui.update_checkbox_group(f"{pre}_per", choices=per[::-1], selected=sel, inline=True)

    primera_vez = {"s": True, "d": True, "c": True}

    # Atajos de los botones de periodos: Actual / Todos / Ninguno
    def _atajos_periodos(pre, base):
        @reactive.effect
        @reactive.event(input[f"{pre}_per_actual"])
        def _():
            per = _periodos(base())
            if per:
                ui.update_checkbox_group(f"{pre}_per", selected=[_periodo_inicial(per)])

        @reactive.effect
        @reactive.event(input[f"{pre}_per_todos"])
        def _():
            ui.update_checkbox_group(f"{pre}_per", selected=_periodos(base()))

        @reactive.effect
        @reactive.event(input[f"{pre}_per_ninguno"])
        def _():
            ui.update_checkbox_group(f"{pre}_per", selected=[])

    _atajos_periodos("s", lambda: sal())
    _atajos_periodos("e", lambda: ent())
    _atajos_periodos("c", lambda: cur()[0])
    _atajos_periodos("d", lambda: doc())
    _atajos_periodos("q", lambda: enc())

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
        return _filtrar(sal(), input.s_per(), {col: input[id_]() for id_, col in FILTROS_S.items()})

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

    # ----- Detalles por estudiante -----
    def _cols(df, cols):
        return df[[c for c in cols if c in df.columns]].copy()

    def _s_est():
        d = s_f()
        cols = ["Periodo", "Apellidos", "Nombres", "Correo", "Esc. Prof. UCSP", "Estado", "Concepto", "Duración",
                "Formato", "Universidad de destino", "País", "Convenio", "Beca"]
        t = _cols(d, cols).rename(columns={"Esc. Prof. UCSP": "Programa profesional"})
        orden = [c for c in ["Periodo", "Apellidos", "Nombres"] if c in t.columns]
        return t.sort_values(orden, ascending=[False] + [True] * (len(orden) - 1), kind="stable").fillna("")

    @render.data_frame
    def s_tabla_est():
        return render.DataGrid(_s_est(), filters=True, width="100%", height="460px")

    @render.download(filename=lambda: f"movilidad_saliente_estudiantes_{datetime.now():%Y%m%d}.csv")
    def s_descargar_est():
        yield _s_est().to_csv(index=False, sep=";").encode("utf-8-sig")

    def _e_est():
        d = e_f()
        cols = ["Periodo", "Nombres", "Correos", "Carrera", "Universidad de Origen", "País", "Convenio"]
        t = _cols(d, cols).rename(columns={"Correos": "Correo", "Carrera": "Carrera en la UCSP"})
        orden = [c for c in ["Periodo", "Nombres"] if c in t.columns]
        return t.sort_values(orden, ascending=[False] + [True] * (len(orden) - 1), kind="stable").fillna("")

    @render.data_frame
    def e_tabla_est():
        return render.DataGrid(_e_est(), filters=True, width="100%", height="460px")

    @render.download(filename=lambda: f"movilidad_entrante_estudiantes_{datetime.now():%Y%m%d}.csv")
    def e_descargar_est():
        yield _e_est().to_csv(index=False, sep=";").encode("utf-8-sig")

    def _c_alumnos():
        a = _act_filtrada()
        cols = ["Código", "Alumno", "Programa profesional", "Periodos", "Cursos-grupo con actividad",
                "Tipos de actividad", "Cursos"]
        if a.empty:
            return pd.DataFrame(columns=cols)
        tipos = list(input.c_tipo()) or TIPOS_CURRICULA
        def unir(sr):
            return ", ".join(sorted(set(x for x in sr if x)))
        g = a.groupby("ID")
        t = pd.DataFrame({
            "Código": g["Código"].first(),
            "Alumno": g["Alumno"].first(),
            "Programa profesional": g["Escuela"].agg(unir),
            "Periodos": g["Periodo"].agg(lambda sr: ", ".join(sorted(set(sr)))),
            "Cursos-grupo con actividad": g.apply(lambda x: x[["Periodo", "Curso", "Grupo"]].drop_duplicates().shape[0]),
            "Tipos de actividad": g.apply(lambda x: ", ".join(k for k in tipos if x[k].any())),
            "Cursos": g["Curso"].agg(unir),
        }).reset_index(drop=True)
        return t.sort_values(["Programa profesional", "Alumno"], kind="stable")

    @render.data_frame
    def c_tabla_alu():
        return render.DataGrid(_c_alumnos(), filters=True, width="100%", height="460px")

    @render.download(filename=lambda: f"curricula_alumnos_detalle_{datetime.now():%Y%m%d}.csv")
    def c_descargar_alu():
        yield _c_alumnos().to_csv(index=False, sep=";").encode("utf-8-sig")

    # ============ INICIO ============
    def _num(v):
        return float(str(v).replace("%", "").strip())

    def _valores_anuales(k, medida):
        """Valor logrado en cada año calendario: {año: (valor, texto, parcial)}.
        Las metas de las hojas de ruta son anuales, así que cada año se mide por separado (no se acumula).
        'parcial' = año en curso o con un solo semestre registrado."""
        esc = RUTAS[k]["escuela"]
        anio_hoy = datetime.now().year
        res = {}
        try:
            if medida == "movilidad":
                s_ = sal()
                s_ = s_[(s_["Esc. Prof. UCSP"] == esc) & s_["Año"].notna()]
                for y, g in s_.groupby(s_["Año"].astype(int)):
                    n = len(g)
                    res[y] = (n, f"{n}", y >= anio_hoy)
            elif medida == "pct_curricula":
                base, mat = cur()
                b = base[(base["Escuela"] == esc) & base["Periodo"].str.match(r"^\d{4}-\d{2}$")]
                for y, g in b.groupby(b["Periodo"].str[:4].astype(int)):
                    pers = sorted(g["Periodo"].unique())
                    if len(pers) >= 2:      # año completo: alumnos únicos del año ÷ alumnos distintos del año
                        pct = g.loc[g[TIPOS_CURRICULA].any(axis=1), "ID"].nunique() / max(g["ID"].nunique(), 1)
                    else:                   # un solo semestre: % de ese semestre (denominador Transparencia)
                        r = resumen_curricula(g, mat)
                        pct = r["Con actividad"].sum() / max(r["Matriculados"].sum(), 1)
                    res[y] = (pct * 100, f"{pct:.1%}", y >= anio_hoy or len(pers) < 2)
            elif medida == "cursos":
                d = doc()
                d = d[(d["Carrera"] == esc) & d["Tipo"].isin(TIPOS_INDICADOR)
                      & d["Periodo"].str.match(r"^\d{4}-\d{2}$") & ~d["Curso"].isin(["Sin información", "No aplica"])]
                for y, g in d.groupby(d["Periodo"].str[:4].astype(int)):
                    n = int(g["Curso"].nunique())
                    res[y] = (n, f"{n}", y >= anio_hoy or g["Periodo"].nunique() < 2)
        except Exception:
            return {}
        return res

    _UNIDAD = {"movilidad": "estudiantes en movilidad saliente",
               "pct_curricula": "de alumnos con experiencias internacionales",
               "cursos": "cursos con clase espejo, COIL o profesor visitante"}

    def _estrategias(k):
        R = RUTAS[k]
        pid = k.lower()
        obj = input[f"hr_{pid}_obj"]()
        niv = input[f"hr_{pid}_niv"]()
        solo_med = input[f"hr_{pid}_med"]()
        tarjetas = []
        for (o, nivel, texto, indicador, metas, resp, obs, medida) in R["estrategias"]:
            if obj not in ("0", "", None) and str(o) != obj:
                continue
            if niv and nivel != niv:
                continue
            if solo_med and not medida:
                continue
            nums = [_num(m) for m in metas]
            tope = max(nums) or 1
            vals = _valores_anuales(k, medida) if medida else {}
            bloques_meta = []
            for i, (m, v) in enumerate(zip(metas, nums)):
                anio = 2027 + i
                logrado = None
                clase = "meta"
                if medida:
                    if anio in vals:
                        valor, txt, parcial = vals[anio]
                        if parcial:
                            logrado = ui.div(f"Logrado: {txt} (parcial)", class_="meta-real parcial")
                        elif valor >= v:
                            logrado = ui.div(f"Logrado: {txt} · cumplida", class_="meta-real ok")
                            clase = "meta meta-ok"
                        else:
                            logrado = ui.div(f"Logrado: {txt} · no cumplida", class_="meta-real no")
                    else:
                        logrado = ui.div("Logrado: sin datos aún", class_="meta-real")
                bloques_meta.append(ui.div(
                    ui.div(f"Meta {anio}", class_="meta-anio"), ui.div(m, class_="meta-val"),
                    ui.div(ui.div(style=f"width:{v / tope * 100:.0f}%"), class_="meta-barra"),
                    logrado, class_=clase))
            tags = [ui.span(f"Objetivo {o}", class_="tag tag-obj"), ui.span(f"Nivel {nivel}", class_="tag tag-niv")]
            referencia = None
            if medida:
                tags.append(ui.span("Medido en el dashboard", class_="tag tag-med"))
                previos = sorted(y for y in vals if y < 2027)
                if previos:
                    y = previos[-1]
                    _, txt, parcial = vals[y]
                    referencia = ui.div(
                        ui.strong(f"Referencia {y}: "), f"{txt} {_UNIDAD[medida]}",
                        " (año incompleto)" if parcial else "",
                        ". Solo como punto de partida; no se compara con las metas.",
                        class_="avance")
            tarjetas.append(ui.div(
                ui.div(*tags, class_="estr-top"),
                ui.p(texto, class_="estr-texto"),
                ui.div(ui.strong("Indicador: "), indicador, class_="estr-ind"),
                ui.div(*bloques_meta, class_="metas"),
                referencia,
                ui.div(ui.span(ui.strong("Responsable: "), resp),
                       ui.span(ui.strong("Observaciones: "), obs) if obs else None, class_="estr-pie"),
                class_="estr-card",
            ))
        if not tarjetas:
            return ui.p("No hay estrategias con esos filtros.", class_="sec-sub")
        return ui.div(*tarjetas, class_="estr-grid")

    @render.ui
    def hr_adm_estr(): return _estrategias("ADM")
    @render.ui
    def hr_cont_estr(): return _estrategias("CONT")

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
        ui.update_radio_buttons("c_modo", selected="unicos")

    @reactive.calc
    def c_base():
        base, _m = cur()
        return _filtrar(base, input.c_per(),
                        {col: input[id_]() for id_, col in FILTROS_C.items()})

    @reactive.calc
    def c_res():
        tipos = list(input.c_tipo()) or TIPOS_CURRICULA
        return resumen_curricula(c_base(), cur()[1], tipos)

    @reactive.calc
    def c_ind():
        """Valores de las tarjetas según el modo de conteo."""
        r = c_res()
        tipos_sel = list(input.c_tipo()) or TIPOS_CURRICULA
        varios = r["Periodo"].nunique() > 1
        if varios and input.c_modo() == "unicos":
            b = c_base()
            num = int(b.loc[b[tipos_sel].any(axis=1), "ID"].nunique())
            den = int(b["ID"].nunique())
            por_tipo = {t: int(b.loc[b[t], "ID"].nunique()) for t in TIPOS_CURRICULA}
            return dict(num=num, den=den, tipos=por_tipo,
                        nota_pct=f"Acumulado de {r['Periodo'].nunique()} periodos (alumnos únicos)",
                        nota_num="Cada alumno cuenta una vez en todo el rango",
                        nota_den="Alumnos distintos en la base durante el rango")
        respaldo = (r["Fuente"] != "Transparencia UCSP").any()
        return dict(num=int(r["Con actividad"].sum()), den=int(r["Matriculados"].sum()),
                    tipos={t: int(r[t].sum()) for t in TIPOS_CURRICULA},
                    nota_pct=("Periodo único" if not varios else
                              f"{r['Periodo'].nunique()} periodos sumados (alumno-semestre)"),
                    nota_num="Alumnos únicos por periodo",
                    nota_den=("Incluye respaldo de la base en algún periodo" if respaldo
                              else "Fuente: Transparencia UCSP" + (" (sumada por semestre)" if varios else "")))

    def _pct(n):
        den = c_ind()["den"]
        return f"{n / den:.1%}" if den else "—"

    @render.text
    def c_kpi_pct(): return _pct(c_ind()["num"])
    @render.text
    def c_kpi_pct_nota(): return c_ind()["nota_pct"]
    @render.text
    def c_kpi_num(): return f"{c_ind()['num']:,}"
    @render.text
    def c_kpi_num_nota(): return c_ind()["nota_num"]
    @render.text
    def c_kpi_den(): return f"{c_ind()['den']:,}"
    @render.text
    def c_kpi_den_nota(): return c_ind()["nota_den"]
    @render.text
    def c_kpi_ce(): return f"{c_ind()['tipos']['Clase Espejo']:,}"
    @render.text
    def c_kpi_ce_nota(): return f"{_pct(c_ind()['tipos']['Clase Espejo'])} del denominador"
    @render.text
    def c_kpi_coil(): return f"{c_ind()['tipos']['COIL']:,}"
    @render.text
    def c_kpi_coil_nota(): return f"{_pct(c_ind()['tipos']['COIL'])} del denominador"
    @render.text
    def c_kpi_pv(): return f"{c_ind()['tipos']['Profesor Visitante']:,}"
    @render.text
    def c_kpi_pv_nota(): return f"{_pct(c_ind()['tipos']['Profesor Visitante'])} del denominador"

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
        return _filtrar(doc(), input.d_per(),
                        {col: input[id_]() for id_, col in FILTROS_D.items()})

    @reactive.calc
    def d_act():
        return actividades_unicas(d_filas())

    def _n_tipo(tipos):
        a = d_act()
        return f"{int(a['Tipo'].isin(tipos).sum()):,}"

    @render.text
    def d_kpi_ind():
        a = d_act()
        return f"{int((a['Tipo'] != 'Profesor Visitante').sum()) + _n_pv():,}"
    @render.text
    def d_kpi_ce(): return _n_tipo(["Clase Espejo"])
    @render.text
    def d_kpi_coil(): return _n_tipo(["COIL"])
    def _n_pv() -> int:
        """Profesores visitantes: cada par académico de cada actividad cuenta uno (ver cargar_docentes)."""
        return int((d_act()["Tipo"] == "Profesor Visitante").sum())

    @render.text
    def d_kpi_pv(): return f"{_n_pv():,}"
    @render.text
    def d_kpi_pv_nota():
        f = d_filas()
        f = f[f["Tipo"] == "Profesor Visitante"]
        p = f["Par académico"]
        n = p[~p.isin(["", "N.A.", "No aplica"])].str.strip().str.lower().nunique()
        act = len(f.drop_duplicates(["Periodo", "Profesor UCSP", "Universidad", "Descripción", "Fecha"]))
        return (f"{act} sesion{'es' if act != 1 else ''} · {n} académico{'s' if n != 1 else ''} "
                f"distinto{'s' if n != 1 else ''}")
    @render.text
    def d_kpi_otras():
        a = d_act()
        return f"{int((~a['Tipo'].isin(TIPOS_INDICADOR)).sum()):,}"
    @render.text
    def d_kpi_doc():
        p = d_act()["Profesor UCSP"]
        return str(p[~p.isin(["Sin información", "No aplica"])].nunique())
    def _doc_pct():
        """Docentes distintos que participaron ÷ docentes distintos de la Facultad en los periodos elegidos."""
        f = d_filas()
        f = f[~f["Profesor UCSP"].isin(["Sin información", "No aplica"])]
        car = list(input.d_car())
        quien = car[0] if len(car) == 1 and car[0] in ("Administración de Negocios", "Contabilidad") else "Facultad"
        periodos = sorted(set(input.d_per()) or set(_periodos(doc())))
        con = [p for p in periodos if p in DOCENTES_FACULTAD_IDS]
        sin = [p for p in periodos if p not in DOCENTES_FACULTAD_IDS]
        n = f.loc[f["Periodo"].isin(con), "Profesor UCSP"].str.strip().str.lower().nunique()
        total = set()
        for p in con:
            listas = DOCENTES_FACULTAD_IDS[p]
            total |= set(listas[quien]) if quien != "Facultad" else set().union(*listas.values())
        return n, len(total), con, sin, quien

    @render.text
    def d_kpi_doc_pct():
        n, den, *_ = _doc_pct()
        return f"{n / den:.0%}" if den else "–"

    @render.text
    def d_kpi_doc_pct_nota():
        n, den, con, sin, quien = _doc_pct()
        base = "de la Facultad" if quien == "Facultad" else f"de {quien}"
        if not con:
            return "Sin total de docentes para los periodos elegidos"
        if len(con) == 1:
            txt = f"{n} de {den} docentes {base} ({con[0]})"
        else:
            txt = f"{n} de {den} docentes distintos {base} en {len(con)} periodos"
        if sin:
            txt += (f" · {len(sin)} periodos sin total de docentes (no se incluyen)" if len(sin) > 2
                    else f" · sin total de docentes: {', '.join(sin)} (no se incluye{'n' if len(sin) > 1 else ''})")
        return txt

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
                    "style": {"font-weight": "600", "background-color": "rgba(127,127,127,.12)"}}]
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

    # ============ SATISFACCIÓN CON LA INTERNACIONALIZACIÓN DE LA CURRÍCULA ============
    @reactive.calc
    def enc_datos():
        req(autenticado())
        input.recargar()
        reactive.invalidate_later(MINUTOS_RECARGA * 60)
        try:
            return cargar_encuestas()
        except Exception as ex:
            print("ERROR encuestas:", repr(ex))
            return None, [f"No se pudieron leer las encuestas: {ex}"], 0

    @reactive.calc
    def enc():
        e, _a, _d = enc_datos()
        req(e is not None)
        e = e.copy()
        # Tipo de actividad del curso según la base docente (mismo curso y periodo)
        tipos = {}
        r = datos()
        dd = r[2] if r is not None else None
        if dd is not None and not dd.empty:
            for (per, cur), g in dd.groupby(["Periodo", "Curso"]):
                t = sorted(set(g["Tipo"]) & set(TIPOS_CURRICULA))
                if t:
                    tipos[(per, _clave(cur))] = ", ".join(t)
        e["Tipo de actividad"] = [tipos.get((p, _clave(c)), "Sin información") for p, c in zip(e["Periodo"], e["Curso"])]
        return e

    @render.ui
    def q_aviso():
        e, avisos, _d = enc_datos()
        if avisos:
            return ui.div(" ".join(avisos), class_="alert alert-warning m-3")

    FILTROS_Q = {"q_prog": "Programa", "q_tipo": "Tipo de actividad", "q_curso": "Curso", "q_sem": "Semestre"}
    primera_q = {"v": True}

    @reactive.effect
    def _():
        e = enc()
        with reactive.isolate():
            _poblar(e, FILTROS_Q, "q", limpiar=primera_q["v"])
        primera_q["v"] = False

    @reactive.effect
    @reactive.event(input.q_reset)
    def _():
        _poblar(enc(), FILTROS_Q, "q", limpiar=True)

    @reactive.calc
    def q_f():
        return _filtrar(enc(), input.q_per(), {col: input[id_]() for id_, col in FILTROS_Q.items()})

    @render.text
    def q_kpi_n(): return f"{len(q_f()):,}"

    @render.text
    def q_kpi_n_nota():
        e = q_f()
        dup = enc_datos()[2]
        extra = f" · {dup} respuestas repetidas no se cuentan" if dup else ""
        return f"{e['Curso'].nunique()} cursos evaluados{extra}"

    @render.text
    def q_kpi_cal():
        v = q_f()["Calificación (1-5)"].mean()
        return "–" if pd.isna(v) else f"{v:.2f}"

    @render.text
    def q_kpi_cal_nota():
        e = q_f()
        n = len(e)
        if not n:
            return ""
        top = e["Calificación"].isin(["Muy Buena", "Excelente"]).sum()
        return f"{top / n:.0%} la calificó como Muy Buena o Excelente"

    @render.text
    def q_kpi_rec():
        e = q_f()
        return "–" if e.empty else f"{(e['Recomienda'] == 'Sí').mean():.0%}"

    @render.text
    def q_kpi_rec_nota():
        e = q_f()
        if e.empty:
            return ""
        return f"Tal vez: {(e['Recomienda'] == 'Tal vez').mean():.0%} · No: {(e['Recomienda'] == 'No').mean():.0%}"

    @render.text
    def q_kpi_prom():
        v = q_f()[ENC_LABELS].stack().mean()
        return "–" if pd.isna(v) else f"{v:.2f}"

    @render.text
    def q_kpi_prom_nota():
        v = q_f()[ENC_LABELS].stack()
        return "" if v.empty else f"{(v >= 4).mean():.0%} de las respuestas en 4 o 5"

    @render.ui
    def q_g_cal(): return _html(enc_calificacion(q_f()))

    @render.ui
    def q_g_rec(): return _html(enc_recomendacion(q_f()))

    @render.ui
    def q_g_likert(): return _html(enc_likert(q_f(), input.q_dim() or None))

    @render.ui
    def q_g_dim(): return _html(enc_dimensiones(q_f()))

    def _q_cursos():
        e = q_f()
        cols = ["Periodo", "Curso", "Tipo de actividad", "Encuestas", "Promedio afirmaciones", "Calificación general",
                "% recomienda", "% de acuerdo"] + ENC_DIMENSIONES
        if e.empty:
            return pd.DataFrame(columns=cols)
        filas = []
        for (per, cur, tipo), g in e.groupby(["Periodo", "Curso", "Tipo de actividad"]):
            v = g[ENC_LABELS].stack()
            fila = {"Periodo": per, "Curso": cur, "Tipo de actividad": tipo, "Encuestas": len(g),
                    "Promedio afirmaciones": v.mean(), "Calificación general": g["Calificación (1-5)"].mean(),
                    "% recomienda": (g["Recomienda"] == "Sí").mean(), "% de acuerdo": (v >= 4).mean()}
            for d in ENC_DIMENSIONES:
                fila[d] = g[[x[1] for x in ENC_ITEMS if x[2] == d]].stack().mean()
            filas.append(fila)
        return pd.DataFrame(filas)[cols]

    @render.ui
    def q_g_curso(): return _html(enc_cursos(_q_cursos()))

    def _q_cursos_tabla():
        t = _q_cursos().sort_values(["Periodo", "Promedio afirmaciones"], ascending=[False, False])
        for c in ["Promedio afirmaciones", "Calificación general"] + ENC_DIMENSIONES:
            t[c] = t[c].map(lambda v: "" if pd.isna(v) else round(v, 2))
        for c in ["% recomienda", "% de acuerdo"]:
            t[c] = t[c].map(lambda v: "" if pd.isna(v) else f"{v:.0%}")
        return t

    @render.data_frame
    def q_t_cursos():
        return render.DataGrid(_q_cursos_tabla(), filters=True, width="100%", height="380px")

    @render.download(filename=lambda: f"satisfaccion_por_curso_{datetime.now():%Y%m%d}.csv")
    def q_descargar_cursos():
        yield _q_cursos_tabla().to_csv(index=False, sep=";").encode("utf-8-sig")

    def _q_texto_util(v):
        t = re.sub(r"[^a-záéíóúñü]", "", str(v).lower())
        return len(t) >= 3

    @render.ui
    def q_g_palabras():
        e = q_f()
        campo = input.q_campo() or "Aspectos a mejorar"
        return _html(enc_palabras(e.loc[e[campo].map(_q_texto_util), campo]))

    def _q_resp(solo_texto=True):
        e = q_f()
        if solo_texto:
            e = e[e["Aspectos a mejorar"].map(_q_texto_util) | e["Comentarios"].map(_q_texto_util)]
        cols = ["Curso", "Calificación", "Recomienda", "Aspectos a mejorar", "Comentarios", "Correo", "Programa",
                "Semestre", "Tipo de actividad", "Periodo"]
        return e[cols].rename(columns={"Programa": "Programa profesional", "Semestre": "Semestre del curso"}) \
                      .sort_values(["Periodo", "Curso"], ascending=[False, True], kind="stable") \
                      .rename(columns={"Recomienda": "¿Recomendaría?"})

    @render.data_frame
    def q_t_resp():
        return render.DataGrid(_q_resp(), filters=True, width="100%", height="520px")

    @render.download(filename=lambda: f"satisfaccion_respuestas_{datetime.now():%Y%m%d}.csv")
    def q_descargar_resp():
        e = q_f()
        cols = ["Periodo", "Fecha", "Correo", "Programa", "Curso", "Tipo de actividad", "Semestre"] + ENC_LABELS + \
               ["Calificación", "Recomienda", "Aspectos a mejorar", "Comentarios"]
        yield e[cols].to_csv(index=False, sep=";").encode("utf-8-sig")

    # ============ TORNEO COMPANYGAME ============
    cg_error = reactive.value(None)

    @reactive.calc
    def cg_datos():
        req(autenticado())
        input.recargar()
        reactive.invalidate_later(MINUTOS_RECARGA * 60)
        try:
            d = cargar_companygame()
            cg_error.set(None)
            return d
        except Exception as e:                    # un problema aquí no afecta al resto del dashboard
            print("ERROR CompanyGame:", repr(e))
            cg_error.set(str(e))
            return None

    def cg():
        r = cg_datos()
        req(r is not None)
        return r[0]

    @render.ui
    def cg_aviso():
        cg_datos()
        if cg_error():
            return ui.div(ui.strong("No se pudo leer la base CompanyGame. "), cg_error(),
                          " Revisa que la hoja siga compartida como 'Cualquier persona con el enlace → Lector'.",
                          class_="alert alert-warning m-3")

    def _cg_anios():
        return sorted(cg()["UCSP_EDICIONES"]["Año"].unique().tolist())

    @reactive.effect
    def _():
        anios = _cg_anios()
        with reactive.isolate():
            act = input.cg_ed()
        sel = act if act and int(act) in anios else str(anios[-1])
        ui.update_select("cg_ed", choices=[str(a) for a in reversed(anios)], selected=sel)

    @reactive.effect
    @reactive.event(input.cg_reset)
    def _():
        ui.update_checkbox_group("cg_cat", selected=CG_CATS)
        ui.update_select("cg_ed", selected=str(_cg_anios()[-1]))

    def cg_cats():
        return list(input.cg_cat()) or CG_CATS

    def cg_todas():
        return set(cg_cats()) == set(CG_CATS)

    def cg_anio():
        a = input.cg_ed()
        req(a)
        return int(a)

    def _cg_eq_cat(anio, col):
        """Suma por categorías elegidas (UCSP_CATEGORIAS); None si falta algún dato."""
        c = cg()["UCSP_CATEGORIAS"]
        s = c[(c["Año"] == anio) & c["Categoría"].isin(cg_cats())][col]
        return None if s.empty or s.isna().any() else int(s.sum())

    def _cg_inscritos(anio):
        if cg_todas():
            e = cg()["UCSP_EDICIONES"]
            v = e.loc[e["Año"] == anio, "Equipos inscritos"]
            return None if v.empty or pd.isna(v.iloc[0]) else int(v.iloc[0])
        return _cg_eq_cat(anio, "Equipos inscritos UCSP")

    # ----- Evolución -----
    @render.text
    def cg_k_ed():
        return str(len(_cg_anios()))

    @render.text
    def cg_k_ed_nota():
        a = _cg_anios()
        return f"{a[0]}–{a[-1]}"

    @render.text
    def cg_k_eq():
        v = _cg_inscritos(_cg_anios()[-1])
        return "s/d" if v is None else str(v)

    @render.text
    def cg_k_eq_nota():
        a = _cg_anios()
        v, w = _cg_inscritos(a[-1]), _cg_inscritos(a[-2]) if len(a) > 1 else None
        if v is None or not w:
            return f"Edición {a[-1]}"
        return f"Edición {a[-1]} · {v / w - 1:+.0%} vs. {a[-2]} ({w})"

    def _cg_est(anio):
        p = cg()["PARTICIPANTES"]
        return p[(p["Año"] == anio) & p["Categoría"].isin(cg_cats())]["ID estudiante"].nunique()

    @render.text
    def cg_k_est():
        return str(_cg_est(_cg_anios()[-1]))

    @render.text
    def cg_k_est_nota():
        p = cg()["PARTICIPANTES"]
        p = p[p["Categoría"].isin(cg_cats())]
        rep = p.groupby("ID estudiante")["Año"].nunique()
        return f"{p['ID estudiante'].nunique()} en total desde {_cg_anios()[0]} · {int((rep > 1).sum())} participaron más de una vez"

    def _cg_mejor():
        c = cg()["UCSP_CATEGORIAS"]
        c = c[c["Categoría"].isin(cg_cats())].dropna(subset=["Posición UCSP (ranking indexado)"])
        if c.empty:
            return None
        return c.sort_values(["Posición UCSP (ranking indexado)", "Año"]).iloc[0]

    @render.text
    def cg_k_best():
        m = _cg_mejor()
        return "–" if m is None else _ordinal(m["Posición UCSP (ranking indexado)"])

    @render.text
    def cg_k_best_nota():
        m = _cg_mejor()
        if m is None:
            return "Sin posiciones publicadas"
        inst = "" if pd.isna(m["Instituciones en la categoría"]) else f" de {int(m['Instituciones en la categoría'])}"
        return f"{m['Categoría']} {m['Año']}{inst}"

    @render.ui
    def cg_g_part():
        return _html(cg_participacion(cg()["UCSP_EDICIONES"].sort_values("Año")))

    @render.ui
    def cg_g_clas():
        return _html(cg_clasificacion(cg()["UCSP_EDICIONES"].sort_values("Año")))

    @render.ui
    def cg_g_pos():
        return _html(cg_posiciones(cg()["UCSP_CATEGORIAS"], cg_cats()))

    @render.ui
    def cg_g_est():
        return _html(cg_estudiantes(cg()["PARTICIPANTES"], cg_cats(), input.cg_est_por() or "Programa / carrera"))

    @render.ui
    def cg_g_hitos():
        return _html(cg_hitos_evolucion(cg()["EQUIPOS_HITOS"], cg_cats()))

    @render.ui
    def cg_g_comp():
        return _html(cg_competencias(cg()["COMPETENCIAS"], cg_cats()))

    # ----- Detalle de la edición -----
    @render.text
    def cg_titulo_ed():
        return f"Detalle de la edición {cg_anio()}"

    @render.text
    def cg_d_eq():
        v = _cg_inscritos(cg_anio())
        return "s/d" if v is None else str(v)

    @render.text
    def cg_d_eq_nota():
        a = cg_anio()
        g = cg()["TORNEO_GLOBAL"]
        tot = g.loc[g["Año"] == a, "Equipos inscritos"]
        if cg_todas() and not tot.empty and not pd.isna(tot.iloc[0]):
            v = _cg_inscritos(a) or 0
            return f"{v / tot.iloc[0]:.1%} de los {int(tot.iloc[0])} equipos del torneo"
        return "Categorías elegidas" if not cg_todas() else ""

    def _cg_clasif(a):
        if cg_todas():
            e = cg()["UCSP_EDICIONES"]
            v = e.loc[e["Año"] == a, "Equipos clasificados"]
            return None if v.empty or pd.isna(v.iloc[0]) else int(v.iloc[0])
        return _cg_eq_cat(a, "Equipos clasificados UCSP")

    @render.text
    def cg_d_cla():
        v = _cg_clasif(cg_anio())
        return "s/d" if v is None else str(v)

    @render.text
    def cg_d_cla_nota():
        a = cg_anio()
        v, n = _cg_clasif(a), _cg_inscritos(a)
        if v is None or not n:
            return "Sin dato por categoría para esta edición"
        txt = f"{v / n:.0%} de los inscritos"
        if cg_todas():
            e = cg()["UCSP_EDICIONES"]
            t = e.loc[e["Año"] == a, "Clasificados / inscritos del torneo"]
            if not t.empty and not pd.isna(t.iloc[0]):
                txt += f" · torneo: {t.iloc[0]:.0%}"
        return txt

    @render.text
    def cg_d_est():
        return str(_cg_est(cg_anio()))

    @render.text
    def cg_d_est_nota():
        a = cg_anio()
        p = cg()["PARTICIPANTES"]
        p = p[(p["Año"] == a) & p["Categoría"].isin(cg_cats())]
        rep = int((p["Repite (ya participó antes)"] == "Sí").sum())
        car = p["Programa / carrera"].value_counts()
        txt = " · ".join(f"{'Adm. de Negocios' if k == 'Administración de Negocios' else k}: {v}" for k, v in car.items())
        extra = " · listado del seguimiento interno" if a == 2024 else ""
        return f"{txt} · {rep} ya habían participado antes{extra}"

    def _cg_informe(a):
        """(entregaron, equipos, fuente) del informe final."""
        if a == 2024:
            e = cg()["EQUIPOS_2024"]
            e = e[e["Categoría"].isin(cg_cats())]
            return int((e["Entregó informe final"] == "Sí").sum()), len(e), "informe oficial 2024"
        h = cg()["EQUIPOS_HITOS"]
        h = h[(h["Año"] == a) & h["Categoría"].isin(cg_cats())]
        con = h[h["Informe final"].isin(["Sí", "No"])]
        return int((con["Informe final"] == "Sí").sum()), len(con), "seguimiento de la edición"

    @render.text
    def cg_d_inf():
        si, n, _f = _cg_informe(cg_anio())
        return "s/d" if not n else f"{si / n:.0%}"

    @render.text
    def cg_d_inf_nota():
        si, n, f = _cg_informe(cg_anio())
        return "Sin dato" if not n else f"{si} de {n} equipos · {f}"

    @render.data_frame
    def cg_t_cat():
        c = cg()["UCSP_CATEGORIAS"]
        c = c[(c["Año"] == cg_anio()) & c["Categoría"].isin(cg_cats())].copy()
        def ent(v):
            return "" if pd.isna(v) else int(v)
        def dec(v):
            return "" if pd.isna(v) else f"{v:,.2f}"
        t = pd.DataFrame({
            "Categoría": c["Categoría"],
            "Equipos inscritos": c["Equipos inscritos UCSP"].map(ent),
            "Equipos clasificados": c["Equipos clasificados UCSP"].map(ent),
            "Puesto UCSP": c["Posición UCSP (ranking indexado)"].map(lambda v: "" if pd.isna(v) else _ordinal(v)),
            "Instituciones": c["Instituciones en la categoría"].map(ent),
            "Países": c["Países en la categoría"].map(ent),
            "Ranking final medio": c["Ranking final medio UCSP (de 1000)"].map(dec),
            "Ranking indexado": c["Ranking indexado UCSP"].map(dec),
            "Equipos en el torneo": c["Equipos inscritos en el torneo (categoría)"].map(ent),
            "Nota": c["Nota"].fillna(""),
        })
        t = t.loc[:, [k for k in t.columns if k == "Categoría" or (t[k].astype(str) != "").any()]]
        return render.DataGrid(t, width="100%")

    def _cg_hitos_ed():
        h = cg()["EQUIPOS_HITOS"]
        return h[(h["Año"] == cg_anio()) & h["Categoría"].isin(cg_cats())]

    @render.ui
    def cg_g_mapa():
        return _html(cg_mapa_hitos(_cg_hitos_ed()))

    @render.ui
    def cg_g_rondas():
        r = cg()["RANKING_RONDAS"]
        return _html(cg_rondas(r[(r["Año"] == cg_anio()) & r["Categoría"].isin(cg_cats())]))

    @render.ui
    def cg_g_comp_ed():
        c = cg()["COMPETENCIAS"]
        return _html(cg_competencias_detalle(c[(c["Año"] == cg_anio()) & c["Categoría"].isin(cg_cats())]))

    @render.ui
    def cg_fila_equipos():
        mapa_ = tarjeta("Hitos cumplidos por cada equipo", ui.output_ui("cg_g_mapa"),
                        "Sí / No por equipo y hito; s/d = la fuente no tiene ese dato. En 2025 solo se muestran los "
                        "27 equipos inscritos oficialmente.")
        r = cg()["RANKING_RONDAS"]
        r = r[(r["Año"] == cg_anio()) & r["Categoría"].isin(cg_cats())]
        hay = not r.dropna(subset=["Ranking ronda 1", "Ranking ronda 2", "Ranking ronda 3", "Ranking ronda 4"],
                           how="all").empty
        if not hay:
            return mapa_
        nota_r = " Esta edición llega hasta la ronda 3." if cg_anio() == 2024 else ""
        return ui.layout_columns(
            mapa_,
            tarjeta("Puesto de cada equipo en el simulador, ronda a ronda", ui.output_ui("cg_g_rondas"),
                    "Ranking de cada equipo entre todos los equipos de su categoría en el torneo (1 = mejor; eje "
                    "invertido, así que subir es mejorar)." + nota_r),
            col_widths=(6, 6))

    @render.ui
    def cg_comp_ed():
        c = cg()["COMPETENCIAS"]
        if c[(c["Año"] == cg_anio()) & c["Categoría"].isin(cg_cats())].empty:
            return None
        return tarjeta("Perfil competencial de los equipos clasificados", ui.output_ui("cg_g_comp_ed"),
                       "% de equipos clasificados de la UCSP en cada nivel, por competencia y categoría (informe "
                       "oficial). Valores leídos de los gráficos del informe.")

    @render.ui
    def cg_oficial_2024():
        if cg_anio() != 2024:
            return None
        return tarjeta("Resultados oficiales por equipo 2024 (informe ACBSP)", ui.output_data_frame("cg_t_2024"),
                       "Tabla del informe oficial 2024: 16 equipos con nombres E57_. No coinciden con los 13 equipos "
                       "del seguimiento interno de la tabla de hitos (Torneo 2024.xlsx), por eso se muestran por "
                       "separado. Puesto = posición del equipo en su categoría (0 = no clasificó).")

    @render.data_frame
    def cg_t_2024():
        e = cg()["EQUIPOS_2024"]
        e = e[e["Categoría"].isin(cg_cats())].copy()
        cols = {"Categoría": "Categoría", "Equipo": "Equipo", "Posición (0 = no clasificó)": "Puesto",
                "Ranking final (máx. 1000)": "Ranking final (/1000)", "Valor de la compañía (máx. 650)": "Valor compañía (/650)",
                "Plan de acción (máx. 100)": "Plan de acción (/100)", "Informe final (máx. 150)": "Informe final (/150)",
                "Cuestionarios (máx. 100)": "Cuestionarios (/100)", "Alcance total %": "Alcance total %",
                "Tiempo total (min)": "Tiempo en simulador (min)", "Estado": "Estado"}
        t = e[[c for c in cols if c in e.columns]].rename(columns=cols)
        for c in t.columns:
            if pd.api.types.is_numeric_dtype(t[c]):
                t[c] = t[c].map(lambda v: "" if pd.isna(v) else (int(v) if float(v).is_integer() else round(v, 2)))
        t = t.sort_values(["Categoría", "Estado", "Puesto"], key=lambda s: s.map(lambda v: (v == 0, v)) if s.name == "Puesto" else s)
        return render.DataGrid(t, filters=True, width="100%", height="420px")

    def _cg_tabla_eq():
        h = _cg_hitos_ed()
        r = cg()["RANKING_RONDAS"]
        r = r[r["Año"] == cg_anio()][["Equipo", "Ranking ronda 1", "Ranking ronda 2", "Ranking ronda 3",
                                       "Ranking ronda 4", "Mejor ranking", "Puntaje fase clasificatoria (2024)",
                                       "Valor final de la compañía (2022)"]]
        t = h.merge(r, on="Equipo", how="left")
        cols = ["Categoría", "Curso", "Equipo", "Integrantes"] + CG_HITOS + ["Rondas completadas (de 4)",
                "Ranking ronda 1", "Ranking ronda 2", "Ranking ronda 3", "Ranking ronda 4", "Mejor ranking",
                "Puntaje fase clasificatoria (2024)", "Valor final de la compañía (2022)"]
        t = t[cols]
        t = t.loc[:, [c for c in t.columns if not (t[c].isna().all())]]
        for c in t.columns:
            if pd.api.types.is_numeric_dtype(t[c]):
                t[c] = t[c].map(lambda v: "" if pd.isna(v) else int(v))
        return t.rename(columns=lambda c: c.replace("Ranking ronda", "Puesto ronda"))

    @render.data_frame
    def cg_t_eq():
        return render.DataGrid(_cg_tabla_eq(), filters=True, width="100%", height="420px")

    @render.download(filename=lambda: f"companygame_equipos_{input.cg_ed()}.csv")
    def cg_descargar():
        yield _cg_tabla_eq().to_csv(index=False, sep=";").encode("utf-8-sig")

    def _cg_est_tabla():
        p = cg()["PARTICIPANTES"]
        p = p[(p["Año"] == cg_anio()) & p["Categoría"].isin(cg_cats())]
        cols = {"Nombre": "Nombre", "Correo": "Correo", "Código de alumno": "Código", "Programa / carrera": "Carrera",
                "Categoría": "Categoría", "Curso": "Curso", "Equipo": "Equipo",
                "Repite (ya participó antes)": "Ya participó antes"}
        t = p[[c for c in cols if c in p.columns]].rename(columns=cols).fillna("")
        return t.sort_values(["Categoría", "Equipo", "Nombre"] if "Nombre" in t.columns else ["Categoría", "Equipo"],
                             kind="stable")

    @render.data_frame
    def cg_t_est():
        return render.DataGrid(_cg_est_tabla(), filters=True, width="100%", height="460px")

    @render.download(filename=lambda: f"companygame_estudiantes_{input.cg_ed()}.csv")
    def cg_descargar_est():
        yield _cg_est_tabla().to_csv(index=False, sep=";").encode("utf-8-sig")

    # ============ ENTRANTE ============
    @reactive.calc
    def e_f():
        return _filtrar(ent(), input.e_per(), {col: input[id_]() for id_, col in FILTROS_E.items()})

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
