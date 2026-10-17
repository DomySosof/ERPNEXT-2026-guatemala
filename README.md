# ERPNext v16 en Docker — Contabilidad Guatemala 🇬🇹

Instala **ERPNext v16 completo dentro de Docker**, con la contabilidad lista para
Guatemala: plan de cuentas (*Guatemala - Cuentas*), moneda **GTQ**, los **5 estados
financieros** y los **libros contables Libro Diario y Libro Mayor**.

En tu máquina **no se instala nada** (ni Python, ni Node, ni MariaDB, ni `bench`):
todo vive en contenedores y volúmenes Docker. El sitio queda **limpio, sin
empresas ni datos de prueba**: la empresa la creas tú con el asistente web.

```
./install.sh                 # 1) deja ERPNext funcionando (sitio limpio)
# 2) creas TU empresa en el navegador (asistente de ERPNext)
./install.sh contabilidad    # 3) prepara la contabilidad guatemalteca
./install.sh reports         # 4) genera los estados y libros en ./salidas/
```

---

## Índice

1. [Qué incluye](#1-qué-incluye)
2. [Requisitos](#2-requisitos)
3. [Instalación rápida](#3-instalación-rápida)
4. [Crear tu empresa con el asistente](#4-crear-tu-empresa-con-el-asistente)
5. [Qué hace `./install.sh contabilidad`](#5-qué-hace-installsh-contabilidad)
6. [Libro Diario y Libro Mayor (formato Guatemala)](#6-libro-diario-y-libro-mayor-formato-guatemala)
7. [Archivos generados](#7-archivos-generados)
8. [Comandos disponibles](#8-comandos-disponibles)
9. [Configuración (`.env`)](#9-configuración-env)
10. [Tu primer asiento: apertura contable](#10-tu-primer-asiento-apertura-contable)
11. [Respaldos y restauración](#11-respaldos-y-restauración)
12. [Actualizar / desinstalar](#12-actualizar--desinstalar)
13. [Instalarlo en otra computadora](#13-instalarlo-en-otra-computadora)
14. [Estructura del proyecto](#14-estructura-del-proyecto)
15. [Solución de problemas](#15-solución-de-problemas)
16. [Notas y alcance](#16-notas-y-alcance)

---

## 1. Qué incluye

| # | Estado financiero / libro | Dónde verlo en ERPNext | Archivo generado |
|---|---|---|---|
| 1 | **Balance General** (Estado de Situación Financiera) | Cuentas › Balance Sheet | `01-balance-general.html/.csv` |
| 2 | **Estado de Resultados** (Pérdidas y Ganancias) | Cuentas › Profit and Loss Statement | `02-estado-resultados.html/.csv` |
| 3 | **Balance Financiero** (Balanza de Comprobación) | Cuentas › Trial Balance | `03-balance-financiero.html/.csv` |
| 4 | **Estado de Flujo de Efectivo** | Cuentas › Cash Flow | `04-flujo-efectivo.html/.csv` |
| 5 | **Estado de Cambios en el Patrimonio Neto** (NIC 1) | Cuentas › Custom Financial Statement | `05-estado-patrimonio.html/.csv` |
| 6 | **Libro Diario** (formato Guatemala) | Cuentas › Reportes › *Libro Diario (Guatemala)* | `06-libro-diario.html/.csv` |
| 7 | **Libro Mayor** (formato Guatemala) | Cuentas › Reportes › *Libro Mayor (Guatemala)* | `07-libro-mayor.html/.csv` |

Además:

* Una versión **nativa** del ECPN (plantilla `Financial Report Template`) para
  imprimir desde ERPNext: `05b-estado-patrimonio-plantilla`.
* Un **Excel con todas las hojas** (estados + libros): `estados-financieros.xlsx`.
* Un `index.html` con el resumen y enlaces a todo.

Los 3 reportes dedicados (ECPN, Libro Diario y Libro Mayor) son **Query Reports**
propios, de sólo lectura, y quedan enlazados en:

* la sección **Reportes** de la barra lateral de *Contabilidad*, y
* la tarjeta **Financial Statements** del espacio **Accounting**.

---

## 2. Requisitos

* **Docker Engine** + **Docker Compose v2** (`docker compose`)
  → <https://docs.docker.com/engine/install/>
* El usuario debe poder ejecutar `docker` sin `sudo` (grupo `docker`).
* ~4 GB de RAM disponibles y ~6 GB de disco.
* Un solo puerto libre: **8080** por defecto (configurable).

---

## 3. Instalación rápida

```bash
# 1) Instalar: descarga las imágenes, levanta el stack y crea el sitio (limpio)
./install.sh

# 2) Abrir el navegador en http://localhost:8080
#    Usuario: Administrator
#    Contraseña: la que se imprime al final de la instalación (o en .env)

# 3) Ya con tu empresa creada (ver sección 4), preparar la contabilidad
./install.sh contabilidad

# 4) Opcional: generar los estados y libros como archivos en ./salidas/
./install.sh reports
```

La instalación es **idempotente**: puedes volver a ejecutar cualquier paso sin
miedo. Nada se duplica y nunca se crean empresas ni datos de prueba.

> Si `reports` todavía sale en ceros, es normal: un ERPNext recién instalado no
> tiene asientos. Mira la [sección 10](#10-tu-primer-asiento-apertura-contable).

---

## 4. Crear tu empresa con el asistente

Al abrir **http://localhost:8080** por primera vez, ERPNext muestra su asistente.
Es ahí donde creas **tu** empresa (el instalador no crea ninguna). Usa tus datos
reales; lo importante para que todo funcione:

| Campo del asistente | Valor |
|---|---|
| **País** | `Guatemala` |
| **Moneda** | `GTQ` |
| **Plan de cuentas** (Chart of Accounts) | `Guatemala - Cuentas` |
| **Nombre de la empresa** | Tu razón social real |
| **Abreviatura** | 2–5 letras (p. ej. `ARL`) |
| **Ejercicio fiscal** | del 1 de enero al 31 de diciembre |

> El plan de cuentas **no se puede cambiar después**, así que revisa que diga
> `Guatemala - Cuentas` antes de continuar.

Cuando termines el asistente, vuelve a la terminal y ejecuta:

```bash
./install.sh contabilidad
```

---

## 5. Qué hace `./install.sh contabilidad`

Lo ejecuta `scripts/setup_accounting.py`. Es **idempotente** y **no crea
empresas**: detecta la tuya y la ajusta.

1. **Detecta tu empresa** (la única del sitio, o la indicada en `COMPANY_NAME`)
   y avisa si el país o la moneda no coinciden con `Guatemala` / `GTQ`.
2. **Se asegura de que estén los datos maestros base** (grupos de artículos,
   territorios, unidades de medida, tipos de almacén...). Si ya existen —lo
   normal, porque los crea el asistente— **no los toca**.
3. **Corrige un error del catálogo de Guatemala**: la cuenta raíz *Patrimonio*
   viene con naturaleza **Activo** en lugar de **Patrimonio (Equity)**. Eso
   rompería el Balance General, la sección de financiación del flujo de efectivo
   y el ECPN. El script la reclasifica (y cualquier otra raíz equivalente).
4. **Completa lo que al catálogo le falta** y ERPNext necesita: cuenta con
   `account_type = Equity`, depreciación acumulada, gasto por depreciación y una
   cuenta real de redondeo; además asigna `account_type = Income Account` a las
   cuentas de ingreso.
5. **Asigna Account Categories** (el motor NIIF de v16) a las cuentas por reglas,
   para que también funcionen las plantillas NIIF.
6. **Fija los valores por defecto de la empresa** (ingresos, gastos, por cobrar,
   por pagar, banco/efectivo, redondeo) y aplica `ERP_PERPETUAL_INVENTORY`.
7. **Crea los años fiscales** indicados en `FISCAL_YEARS`.
8. **Crea / actualiza la plantilla** `Financial Report Template` del **ECPN
   (NIC 1)**.
9. **Crea los 3 reportes propios** y los enlaza en la barra lateral y el espacio
   de Contabilidad.
10. **Verifica** que todos los reportes existan (8 en total).

Si lo ejecutas **antes** de crear tu empresa, no falla: crea la plantilla y los
reportes (que sirven para cualquier empresa) y te recuerda qué falta.

Salida típica:

```
Sitio: frontend
País: Guatemala · Moneda: GTQ
· Empresa: AtiTur, R.L.
  · Datos maestros de ERPNext: ya estaban listos
  ✔ 'Patrimonio' marcada como Patrimonio (Equity)
  ✔ Categorías NIIF asignadas a 50 cuentas
  · Valores por defecto de la empresa: enable_perpetual_inventory
  + Año fiscal 2025 (2025-01-01 → 2025-12-31)
· Reporte creado: Libro Diario (Guatemala)
· Reporte creado: Libro Mayor (Guatemala)
· 8 reportes verificados correctamente
ERP_ACCOUNTING_SETUP_OK company_configured
```

---

## 6. Libro Diario y Libro Mayor (formato Guatemala)

Se generan **en pantalla** (reportes de ERPNext) y **como archivo** (HTML
imprimible + CSV), en orden cronológico y en GTQ.

* **Libro Diario** — registro cronológico de las **partidas (asientos)**. Cada
  partida lleva su **folio**, la fecha, el documento de origen (`Journal Entry`,
  factura, etc.) y sus cuentas al **Debe** y al **Haber**, con la leyenda
  **«Sumas iguales»** al pie de cada asiento y los totales del período al final
  (con el cuadre *Debe − Haber*, que debe ser `0.00`).
* **Libro Mayor** — el **traslado** de esas partidas a cada cuenta, en orden de
  código, con **saldo inicial**, movimientos y **saldo corriente** (débito
  positivo).

Detalles:

* Filtros: **Empresa** (obligatorio), **Desde** y **Hasta** (por defecto, el año
  fiscal en curso).
* URLs directas:
  * `http://localhost:8080/app/query-report/Libro%20Diario%20(Guatemala)`
  * `http://localhost:8080/app/query-report/Libro%20Mayor%20(Guatemala)`
  * `http://localhost:8080/app/query-report/Estado%20de%20Cambios%20en%20el%20Patrimonio%20Neto`

> **Folios.** El folio empieza en 1. Para continuar la numeración de un libro ya
> emitido, pon `LD_FOLIO_INICIO=251` en `.env` y vuelve a ejecutar
> `./install.sh reports`. El orden de los folios es idéntico en pantalla y en el
> archivo.

El **ECPN** también existe como reporte propio: muestra cada cuenta de patrimonio
con *saldo inicial*, *movimientos del período* y *saldo final*, más una fila con
el **resultado del ejercicio** y una fila de **Total** (patrimonio neto al
cierre).

---

## 7. Archivos generados

`./install.sh reports [año]` deja todo en la carpeta **`./salidas/`**:

```
salidas/
├── index.html                          # resumen con enlaces a todo
├── 01-balance-general.html / .csv
├── 02-estado-resultados.html / .csv
├── 03-balance-financiero.html / .csv
├── 04-flujo-efectivo.html / .csv
├── 05-estado-patrimonio.html / .csv
├── 05b-estado-patrimonio-plantilla...  # versión nativa del ECPN
├── 06-libro-diario.html / .csv
├── 07-libro-mayor.html / .csv
├── estados-financieros.xlsx            # todas las hojas en un Excel
└── salida-<año>.txt                    # log de la generación
```

Los `.html` se imprimen a PDF con `Ctrl+P` desde el navegador.

---

## 8. Comandos disponibles

```bash
./install.sh                 # instala / reanuda la instalación (por defecto)
./install.sh up              # levanta el stack
./install.sh stop            # detiene los contenedores (conserva los datos)
./install.sh restart         # reinicia
./install.sh status          # estado de los servicios
./install.sh logs [servicio] # ver logs (por defecto: backend)
./install.sh shell [servicio]# terminal dentro de un contenedor
./install.sh console         # consola Python de Frappe (sitio activo)
./install.sh contabilidad    # prepara la contabilidad guatemalteca
./install.sh reports [año]   # genera los estados y libros en ./salidas/
./install.sh backup          # respalda base de datos + archivos -> ./respaldos/
./install.sh restore <arch>  # restaura un respaldo .sql.gz
./install.sh update          # actualiza a la versión indicada en .env
./install.sh env             # muestra la configuración activa
./install.sh destroy         # ELIMINA contenedores, volúmenes y TODOS los datos
./install.sh help            # ayuda
```

Flags: `--no-pull` (no descargar imágenes) y `-y` / `--yes` (no preguntar).

Atajo para los estados: `./scripts/estados-financieros.sh [año]`.

---

## 9. Configuración (`.env`)

La instalación crea un archivo **`.env`** a partir de `.env.example`. Puedes
editarlo cuando quieras: las variables de contabilidad se leen al ejecutar
`./install.sh contabilidad`.

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `ERPNEXT_VERSION` | `v16.51.1` | Versión de la imagen `frappe/erpnext`. |
| `HTTP_PORT` | `8080` | Único puerto publicado en el host. |
| `SITE_NAME` | `frontend` | Nombre interno del sitio. |
| `COUNTRY` | `Guatemala` | Determina el plan de cuentas. |
| `CURRENCY` | `GTQ` | Moneda funcional de la empresa. |
| `COMPANY_NAME` | *(vacío)* | **Déjalo vacío**: se detecta la empresa del sitio. Sólo llénalo si tienes varias empresas. |
| `COMPANY_ABBR` | *(vacío)* | Sólo aplica junto con `COMPANY_NAME`. |
| `ERP_PERPETUAL_INVENTORY` | `0` | `0` apaga el inventario perpetuo (recomendado al empezar), `1` lo enciende. |
| `FISCAL_YEAR_START_MONTH` | `1` | Mes de inicio del ejercicio (1 = enero). |
| `FISCAL_YEARS` | `2025,2026,2027` | Ejercicios fiscales que se crean. |
| `LD_FOLIO_INICIO` | *(vacío → 1)* | Primer folio del **Libro Diario**. |
| `SITE_ADMIN_PASSWORD` | *(vacío)* | Se genera al azar si queda vacío. |
| `DB_ROOT_PASSWORD` | *(vacío)* | Se genera al azar si queda vacío. |

Consulta la configuración efectiva con `./install.sh env`.

> `.env` está en `.gitignore`: **nunca** se sube a GitHub (contiene contraseñas).

---

## 10. Tu primer asiento: apertura contable

Para que los estados dejen de salir en ceros, registra tu **asiento de apertura**
con los saldos con los que arrancas:

1. **Contabilidad › Journal Entry › New**.
2. Fecha: el inicio de tu ejercicio.
3. Agrega una línea por cuenta:

   | Cuenta | Debe | Haber |
   |---|---|---|
   | `1101` Caja / `1102` Banco | 50,000 | |
   | `1201` ... (cuentas por cobrar, inventario…) | … | |
   | `3101` Capital | | 50,000 |

4. Verifica que **Debe = Haber** y guarda (**Submit**).

Después, en cada período:

```bash
./install.sh reports 2026
```

y revisa `salidas/06-libro-diario.html` (partidas con folio y «sumas iguales») y
`salidas/07-libro-mayor.html` (saldos por cuenta).

Si el total de *Debe − Haber* del Libro Diario no es `0.00`, hay un asiento
descuadrado: revisa el Balance Financiero (Balanza de Comprobación).

---

## 11. Respaldos y restauración

```bash
./install.sh backup                               # crea un respaldo en ./respaldos/
./install.sh restore respaldos/<archivo>.sql.gz   # restaura (SOBRESCRIBE la base de datos)
```

`backup` ejecuta `bench backup --with-files` y copia a `./respaldos/` el juego más
reciente, con la fecha de creación como prefijo:

```
respaldos/20261017-022800-...-frontend-database.sql.gz        # base de datos  ← esto se restaura
respaldos/20261017-022800-...-frontend-files.tar              # archivos adjuntos públicos
respaldos/20261017-022800-...-frontend-private-files.tar      # archivos adjuntos privados
respaldos/20261017-022800-...-frontend-site_config_backup.json
```

`restore` espera el **`.sql.gz`** (la base de datos) y te pide escribir `SI` para
confirmar; con `-y` no pregunta:

```bash
./install.sh restore respaldos/20261017-022800-...-frontend-database.sql.gz
./install.sh -y restore respaldos/20261017-022800-...-frontend-database.sql.gz
```

Los respaldos también quedan dentro del volumen `sites` del contenedor `backend`
(carpeta `sites/<sitio>/private/backups`).

---

## 12. Actualizar / desinstalar

```bash
# Cambia ERPNEXT_VERSION en .env y luego (te pide escribir SI para confirmar):
./install.sh update

# Elimina TODO (contenedores + volúmenes + datos). Te pide escribir BORRAR:
./install.sh destroy
```

`update` descarga la nueva imagen, levanta el stack, espera al sitio y ejecuta
`bench migrate`.

`destroy` no borra este directorio: sólo quedan los archivos de texto del
proyecto. Tu máquina no conserva nada de ERPNext.

---

## 13. Instalarlo en otra computadora

El proyecto está pensado para **clonarse y correr en cualquier máquina** sin
arrastrar datos de otra instalación (cada quien crea su empresa).

```bash
git clone <URL-del-repositorio> erpnext-gt
cd erpnext-gt

./install.sh                 # sitio limpio
# ... crea tu empresa en el navegador ...
./install.sh contabilidad
./install.sh reports
```

El archivo `.env` **no viene** en el repositorio (está en `.gitignore`): el
instalador lo crea solo a partir de `.env.example`, generando contraseñas nuevas
al azar. Si quieres cambiar puerto, país, años fiscales, etc., edita
`.env.example` *antes* de clonar, o el `.env` que se genera.

Para hacer llegar un respaldo desde otra máquina:

```bash
# en la máquina origen
./install.sh backup
# copia el archivo ...-frontend-database.sql.gz a la otra máquina, y allá:
./install.sh restore respaldos/20261017-022800-...-frontend-database.sql.gz
```

> Ojo: `destroy` + `./install.sh` es la forma de empezar de cero. Si sólo quieres
> mover el sistema, usa `backup` / `restore`.

### Publicarlo en GitHub

El proyecto ya viene listo para subir (`.env`, `salidas/` y `respaldos/` están en
`.gitignore`, así que **no se suben** contraseñas ni datos generados):

```bash
cd /ruta/a/ERPNEXT
git init -b main
git add .
git commit -m "ERPNext v16 en Docker con contabilidad Guatemala (GTQ)"
git remote add origin https://github.com/<tu-usuario>/<tu-repo>.git
git push -u origin main
```

Si quieres publicarlo con otro nombre o en otra rama, cambia lo que haga falta.
Recuerda sacar **dos copias** del proyecto antes de subirlo si lo clonarás en más
de una computadora: cada instalación genera su propio `.env` y sus contraseñas.

---

## 14. Estructura del proyecto

```
.
├── install.sh                     # instalador + interfaz de línea de comandos
├── docker-compose.yml             # stack ERPNext v16 completo (11 servicios)
├── .env.example                   # plantilla de configuración
├── .gitignore                     # ignora .env, salidas/ y respaldos/
├── README.md
└── scripts/
    ├── setup_accounting.py        # reportes + libros + ejercicios + ajustes del catálogo
    ├── estados_financieros.py     # genera estados + Libro Diario/Mayor (HTML/CSV/XLSX)
    └── estados-financieros.sh     # atajo de escritorio para lo anterior

salidas/                           # (se crea) estados financieros generados
respaldos/                         # (se crea) respaldos de base de datos
```

Servicios del stack: `configurator`, `create-site`, `backend`, `frontend`
(nginx), `websocket`, `queue-short`, `queue-long`, `scheduler`, `redis-cache`,
`redis-queue` y `db` (MariaDB 11.8).

---

## 15. Solución de problemas

* **El puerto 8080 está ocupado** → cambia `HTTP_PORT` en `.env` y ejecuta
  `./install.sh up`.
* **"El sitio no responde"** → revisa los logs: `./install.sh logs create-site`
  o `./install.sh logs backend`.
* **Los estados salen en ceros** → es normal si aún no registras asientos.
  Empieza con un asiento de apertura (sección 10).
* **No aparecen los reportes *Libro Diario (Guatemala)* / *Libro Mayor (Guatemala)***
  → todavía no ejecutaste `./install.sh contabilidad`. Recuerda hacer *recarga
  forzada* en el navegador (`Ctrl + Shift + R`).
* **`reports` dice que no hay ninguna empresa** → crea tu empresa con el
  asistente web y luego ejecuta `./install.sh contabilidad`.
* **`Could not find Warehouse Type: Transit`** al crear la empresa → ejecuta
  `./install.sh contabilidad` (crea los datos maestros que falten, incluido ese
  tipo de almacén) y es idempotente.
* **`reports` no encuentra el ejercicio** → el año pedido no existe como *Fiscal
  Year*. Revisa `FISCAL_YEARS` en `.env` y vuelve a ejecutar
  `./install.sh contabilidad`.
* **`El sitio no responde con la app 'erpnext'`** → espera unos minutos (la
  primera vez descarga e inicializa mucho) y revisa
  `./install.sh logs create-site`.
* **Vi tracebacks de `NestedSetRecursionError` / "Document Insert Error"** → los
  imprime ERPNext al reinsertar registros de árboles (territorios, grupos de
  clientes...) que ya existen; los revierte solo y **no rompen nada**. Este
  proyecto ya no los provoca, pero el asistente de ERPNext puede imprimirlos.
* **Quiero empezar de cero** → `./install.sh destroy && ./install.sh`.

---

## 16. Notas y alcance

* Se instala la última versión estable de la familia v16
  (`frappe/erpnext:v16.51.1`). Si prefieres la línea LTS, usa `v15.123.0` en
  `ERPNEXT_VERSION`.
* El stack es de **un solo servidor** (no hay multi-tenant ni balanceador).
* Los 5 estados se apoyan en los **reportes clásicos** de ERPNext (que siguen
  existiendo en v16) para garantizar resultados, y se complementan con la
  plantilla nativa del ECPN.
* El **Libro Diario** y el **Libro Mayor** se construyen directamente desde los
  asientos contables (*GL Entry*), con las columnas que se usan en Guatemala
  (folio, partida, Debe, Haber, «sumas iguales»). La numeración de folios es
  consecutiva dentro del período; para un libro legalizado puedes ajustar el
  inicio con `LD_FOLIO_INICIO` y exportar a PDF (Ctrl+P) o a Excel/CSV.
* El proyecto **no crea empresas ni datos de ejemplo**, y **no incluye**
  facturación electrónica (FEL) ni regímenes fiscales específicos.
