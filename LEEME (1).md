# Dashboard de Movilidad Estudiantil UCSP

## Probarlo en tu computadora (Spyder / Anaconda)

1. Abre **Anaconda Prompt** (o la terminal) y entra a esta carpeta:
   `cd ruta\a\dashboard_movilidad`
2. Instala las librerías (solo la primera vez):
   `pip install -r requirements.txt`
3. Ejecuta la app:
   `shiny run app.py --reload`
4. Abre en el navegador: http://127.0.0.1:8000

Puedes editar `app.py` en Spyder; con `--reload` el dashboard se actualiza al guardar.

## Conexión con Google Drive

La app descarga la hoja directamente de Drive (ID ya configurado en `app.py`).
Para que funcione, la hoja debe estar compartida como
**"Cualquier persona con el enlace → Lector"**.

Si prefieres que la hoja siga siendo privada (contiene nombres y correos de alumnos):
1. Crea una cuenta de servicio en Google Cloud y descarga su JSON de credenciales.
2. Comparte la hoja con el correo de esa cuenta (como "Lector").
3. Define la variable de entorno `GOOGLE_SERVICE_ACCOUNT_JSON` con el contenido del JSON
   (en Connect Cloud: *Settings → Variables*, marcándola como secreta).

Opcional: si pones una copia en `data/base.xlsx`, la app la usa cuando no hay conexión.
No la subas a un repositorio público.

## Publicarlo en línea (Posit Connect Cloud, gratis)

1. Sube `app.py` y `requirements.txt` a un repositorio de GitHub.
2. Entra a https://connect.posit.cloud, elige **Publish → Shiny**, selecciona el repositorio
   y `app.py` como archivo principal.
3. Comparte el enlace que te da. Cada vez que actualices la hoja en Drive,
   el dashboard mostrará los datos nuevos (recarga sola cada 10 minutos o con el botón
   "Actualizar datos").

## Notas sobre los datos

- Los detalles por estudiante muestran nombres, correos y códigos (decisión de la Facultad). El dashboard es público y no lo indexan los buscadores.
- "Per. Acad." se normaliza a AAAA-01 / AAAA-02 (aunque Excel lo haya convertido a fecha).
- Se quitan espacios sobrantes ("Contabilidad " = "Contabilidad").
- Las dos columnas "Modalidad" se renombran a **Duración** (Larga/Corta) y **Formato** (Presencial/Virtual).
- Si agregas un país nuevo que no aparece en el mapa, añádelo al diccionario `ISO3` de `app.py`.

## Fórmulas de la hoja del dashboard (solo IMPORTRANGE simples, sin CHOOSECOLS)

Google a veces no calcula un IMPORTRANGE anidado dentro de otra función cuando el dashboard lee la hoja.
Por eso cada pestaña usa varios IMPORTRANGE simples, uno al lado del otro, que traen solo las columnas permitidas.

MOVILIDAD SALIENTE: A1 `=IMPORTRANGE("1CXiqec_6Wwf6nKs92cHKbLnzdjr3f3J1D0B3IdnYqFk"; "'MOVILIDAD SALIENTE'!A:D")` · E1 `=IMPORTRANGE("1CXiqec_6Wwf6nKs92cHKbLnzdjr3f3J1D0B3IdnYqFk"; "'MOVILIDAD SALIENTE'!H:M")` · K1 (apellidos, nombres, correo) `=IMPORTRANGE("1CXiqec_6Wwf6nKs92cHKbLnzdjr3f3J1D0B3IdnYqFk"; "'MOVILIDAD SALIENTE'!E:G")`

MOVILIDAD ENTRANTE: A1 `=IMPORTRANGE("1CXiqec_6Wwf6nKs92cHKbLnzdjr3f3J1D0B3IdnYqFk"; "'MOVILIDAD ENTRANTE'!B:F")` · F1 (nombres) `=IMPORTRANGE("1CXiqec_6Wwf6nKs92cHKbLnzdjr3f3J1D0B3IdnYqFk"; "'MOVILIDAD ENTRANTE'!A:A")` · G1 (correos) `=IMPORTRANGE("1CXiqec_6Wwf6nKs92cHKbLnzdjr3f3J1D0B3IdnYqFk"; "'MOVILIDAD ENTRANTE'!G:G")`

ACTIVIDADES DOCENTES (ID 1TNSt9S9XteACFZPCk_uvU7JByFZpR9CXNpgEP7kKTaM, pestaña Consoli):
A1 B:F · F1 H:O · N1 Q:Q · O1 S:S · P1 W:X

CURRICULA DE ALUMNOS: en la base de currícula (privada) agrega en BASE_GENERAL la columna K "ID_ALUMNO" con
K2 `=ARRAYFORMULA(IF(C2:C=""; ""; XMATCH(C2:C; UNIQUE(C2:C))))`. En el dashboard (ID 1jkxaMtOO2IloDOdX8m0xCRYL8xgUgMXpanf6JeUKuJo):
A1 BASE_GENERAL!A:B · C1 BASE_GENERAL!E:H · G1 BASE_GENERAL!J:K · I1 (código y nombre) BASE_GENERAL!C:D

MATRICULADOS: A1 `=IMPORTRANGE("1jkxaMtOO2IloDOdX8m0xCRYL8xgUgMXpanf6JeUKuJo"; "MATRICULADOS!A1:C500")`


## Torneo CompanyGame (Indicadores de Alumnos → Torneo CompanyGame)

Lee una hoja aparte: «CompanyGame_base_unificada» (ID en `CG_SHEET_ID` de `app.py`), compartida como
**"Cualquier persona con el enlace → Lector"**. Usa las pestañas UCSP_EDICIONES, UCSP_CATEGORIAS, TORNEO_GLOBAL,
EQUIPOS_HITOS, RANKING_RONDAS, PARTICIPANTES, COMPETENCIAS, EQUIPOS_2024 y EQUIPOS_2025, con los encabezados en la fila 3.
Para agregar una edición nueva (p. ej. 2026), añade sus filas en esas pestañas manteniendo los mismos encabezados:
el dashboard la muestra sola. Si esta hoja falla, solo esa subpestaña muestra un aviso; el resto sigue funcionando.

## Satisfacción con Intern. Currícula (Indicadores de Alumnos)

Cada periodo es una hoja de Google con las respuestas del formulario (la primera pestaña), compartida como
**"Cualquier persona con el enlace → Lector"**. Para agregar un periodo, en `app.py` busca `ENCUESTAS_SATISFACCION`
y añade una línea con el periodo y el ID de la hoja (lo que va entre `/d/` y `/edit` en el enlace):

    ENCUESTAS_SATISFACCION = {
        "2026-01": "1ylMidkIzk3KhwI_hek8XEvs7SIDUQ8t6PvPnrNJgg9Y",
        "2026-02": "ID_DE_LA_HOJA_2026-02",
    }

Las columnas se reconocen por su texto (no importa el orden), así que el formulario debe mantener las mismas preguntas.
El tipo de actividad de cada curso (clase espejo, COIL…) se toma de la base docente según el curso y el periodo.
Si un alumno respondió dos veces por el mismo curso, se cuenta su última respuesta.

## % de docentes que participan (Indicadores de Docentes)

El denominador son los docentes de la Facultad en los periodos elegidos (información proporcionada por el coordinador
administrativo de la facultad). En `app.py`, `DOCENTES_FACULTAD_IDS` guarda, por periodo y escuela, un código anónimo
de 8 caracteres por docente, generado a partir de su DNI (no contiene nombres, DNI ni correos). Así, al elegir varios
periodos, cada docente cuenta una sola vez, tanto entre los participantes como en el total.
Para agregar un periodo nuevo, pásale a Claude la lista de docentes de ese periodo (mismo formato del Excel).
Los periodos sin lista no entran en el cálculo (la tarjeta lo indica).

## Filtro de periodos

En cada pestaña los periodos son botones: se puede marcar cualquier combinación. «Actual» deja solo el semestre en
curso, «Todos» marca el histórico y «Ninguno» los desmarca (sin ninguno marcado se muestran todos).

## Clave de acceso

El dashboard pide una clave al abrirse si existe la variable `DASH_CLAVE`. Para activarla en Connect Cloud:
abre el contenido → Settings (engranaje) → Variables → agrega `DASH_CLAVE` con la clave, márcala como secreta y
vuelve a publicar. Para cambiar la clave, edita el valor de la variable. No escribas la clave en `app.py`, porque el
repositorio es público. Sin la variable (por ejemplo, al probar en tu computadora) el dashboard no pide clave.
