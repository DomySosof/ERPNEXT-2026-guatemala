# ERPNext v16 en Docker — Contabilidad Guatemala 🇬🇹

Instala **ERPNext v16 completo dentro de Docker**, con la contabilidad lista para
Guatemala: plan de cuentas (*Guatemala - Cuentas*), moneda **GTQ**, los **5 estados
financieros** y los **libros contables Libro Diario y Libro Mayor**.

En tu máquina **no se instala nada** (ni Python, ni Node, ni MariaDB, ni `bench`):
todo vive en contenedores y volúmenes Docker. El sitio queda **limpio, sin
empresas ni datos de prueba**: la empresa la creas tú con el asistente web.

> **No necesitas saber de programación.** Es copiar y pegar 3 comandos en una
> terminal. La **primera vez tarda 10–20 minutos** (descarga las imágenes); las
> siguientes arranca en segundos. Nada de lo que hagas aquí borra tus datos.

### Instalación en 4 pasos

```bash
./install.sh                 # 1) deja ERPNext funcionando (sitio limpio)
# 2) creas TU empresa en el navegador (asistente de ERPNext)
./install.sh contabilidad    # 3) prepara la contabilidad guatemalteca
./install.sh reports         # 4) (opcional) estados y libros en ./salidas/
```

¿Es tu primera vez con Docker o con la terminal? Ve directo a la
**[instalación paso a paso](#3-instalación-paso-a-paso)**.

---

## Índice

1. [Qué incluye](#1-qué-incluye)
2. [Requisitos](#2-requisitos)
3. [Instalación paso a paso](#3-instalación-paso-a-paso)
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
* El reporte en pantalla **Balance de Saldos (Guatemala)**: una fila por cuenta
  con su *saldo inicial*, *debe*, *haber* y *saldo final*, con fila de totales.
  Es el vistazo rápido para comprobar que el libro cuadra.
* Un **Excel con todas las hojas** (estados + libros): `estados-financieros.xlsx`.
* Un `index.html` con el resumen y enlaces a todo.

Los 4 reportes dedicados (ECPN, Libro Diario, Libro Mayor y Balance de Saldos)
son **Query Reports** propios, de sólo lectura, y quedan enlazados en:

* la sección **Reportes** de la barra lateral de *Contabilidad*, y
* la tarjeta **Financial Statements** del espacio **Accounting**.

Se pueden **ver, imprimir y exportar a Excel/CSV directamente desde ERPNext**
(botón **⋯ › Export** y **Imprimir**). Los **Libros Diario y Mayor** traen sus
propios **subtotales por asiento y por cuenta** (y su fila de total general), de
modo que no dependen de ejecutar ningún script.

Todos los archivos HTML (estados y libros) usan un **diseño unificado**:
encabezado con los datos de la empresa, tarjetas de resumen con los totales
principales, tablas con filas de total resaltadas y, en los libros, un panel
final con el **estado del libro** (`CUADRA` / `NO CUADRA`).

---

## 2. Requisitos

Antes de empezar necesitas **una sola cosa instalada en tu computadora: Docker**.

| Qué | Detalle |
|---|---|
| **Docker** | Docker Desktop (Windows/macOS) o Docker Engine + Compose v2 (Linux). Es lo único que hay que instalar: incluye todo lo demás. |
| **RAM** | ~4 GB libres (mejor 6–8 GB para trabajar cómodo). |
| **Disco** | ~6–8 GB libres (imágenes + datos). |
| **Puerto libre** | El **8080**. Si está ocupado, se cambia en `.env` (ver [sección 9](#9-configuración-env)). |
| **Internet** | Sólo la primera vez, para descargar las imágenes. |
| **Terminal** | La de tu sistema. En Windows se usa **Git Bash** o **WSL** (ver abajo). |

### Instalar Docker (elige tu sistema)

* **Windows 10/11** → descarga **Docker Desktop** desde
  <https://www.docker.com/products/docker-desktop/> e instálalo. Si te pregunta,
  acepta usar **WSL 2**. Ábrelo y espera a que diga **“Engine running”**.
* **macOS** → descarga **Docker Desktop** desde
  <https://www.docker.com/products/docker-desktop/> (elige *Apple Silicon* o
  *Intel* según tu Mac), instálalo y ábrelo.
* **Linux (Ubuntu / Debian / Fedora…)** → instala **Docker Engine + Compose v2**:
  <https://docs.docker.com/engine/install/>

> **Windows: usa una terminal tipo bash.** Los comandos de esta guía son de bash.
> Instala [Git for Windows](https://git-scm.com/download/win) y abre **Git Bash**
> (menú Inicio ▸ *Git Bash*), o usa **Ubuntu (WSL 2)**. En *PowerShell* o *CMD* no
> funcionan `./install.sh` ni los demás scripts.

### Comprobar que Docker quedó bien

Abre la terminal y pega estos tres comandos:

```bash
docker --version
docker compose version
docker run --rm hello-world
```

Los tres deben responder **sin error**. El último imprime un saludo: eso confirma
que Docker está funcionando.

### Si te pide `sudo` (sólo Linux)

Para no escribir `sudo` cada vez, agrega tu usuario al grupo `docker` y luego
**cierra la sesión y vuelve a entrar** (o reinicia):

```bash
sudo usermod -aG docker "$USER"
```

Después, `docker run --rm hello-world` debe funcionar **sin** `sudo`.

---

## 3. Instalación paso a paso

Sigue los pasos en orden. En cada bloque, **copia y pega** el comando en la
terminal y pulsa **Enter**.

### Paso 0 — Abre la terminal

* **Windows** → **Git Bash** (menú Inicio ▸ *Git Bash*). No uses PowerShell.
* **macOS** → **Terminal** (Aplicaciones ▸ Utilidades ▸ Terminal).
* **Linux** → tu terminal habitual.

### Paso 1 — Descarga el proyecto

**Opción A — con Git (recomendado):**

```bash
git clone <URL-del-repositorio> erpnext-gt
cd erpnext-gt
```

**Opción B — sin Git:** en la página del repositorio pulsa el botón verde
**Code ▸ Download ZIP**, descomprime el archivo y entra a la carpeta:

```bash
cd ruta/a/la/carpeta/descomprimida
```

> Truco: escribe `cd ` (con un espacio al final), **arrastra la carpeta** a la
> ventana de la terminal —se pega la ruta sola— y pulsa Enter.

### Paso 2 — (Sólo la primera vez) dale permiso de ejecución

```bash
chmod +x install.sh scripts/*.sh
```

> Si este comando diera error, no pasa nada: en los pasos siguientes usa
> `bash install.sh` en lugar de `./install.sh`.

### Paso 3 — Instala ERPNext

```bash
./install.sh
```

Descarga las imágenes, levanta los servicios y crea el sitio. **La primera vez
tarda entre 10 y 20 minutos** (unos 5 en las siguientes). Al terminar verás algo
así:

```
✔ ¡Instalación terminada! El sitio quedó limpio (sin empresas ni datos de prueba).

 1) Crea tu empresa con el asistente web
    Abre http://localhost:8080 y entra como Administrator
    Contraseña: XxXxXxXxXxXxXxXx
```

> **Anota esa contraseña.** También queda guardada en el archivo **`.env`**
> (ábrelo con cualquier editor de texto y busca `SITE_ADMIN_PASSWORD`). Si
> prefieres una propia, escríbela ahí **antes** de ejecutar este paso.

### Paso 4 — Crea tu empresa en el navegador

Abre **<http://localhost:8080>** y entra como **Administrator** con esa contraseña.
ERPNext abre su asistente: ahí creas **tu** empresa con tus datos reales (el
instalador no crea ninguna). Los campos importantes están en la
[sección 4](#4-crear-tu-empresa-con-el-asistente).

### Paso 5 — Prepara la contabilidad guatemalteca

Cuando termines el asistente, vuelve a la terminal y ejecuta:

```bash
./install.sh contabilidad
```

Esto corrige el catálogo de Guatemala, deja el plan de cuentas en la
**nomenclatura base**, crea tus ejercicios fiscales y agrega los reportes
(Libro Diario, Libro Mayor, Balance de Saldos) dentro de ERPNext.

### Paso 6 — (Opcional) Genera los estados y libros en archivos

```bash
./install.sh reports 2026
```

Quedan en la carpeta **`salidas/`** (HTML imprimible, CSV y un Excel). Si aparecen
en ceros es normal: todavía no registras asientos → mira la
[sección 10](#10-tu-primer-asiento-apertura-contable).

### ¿Cómo sé que quedó bien?

* `./install.sh status` muestra los servicios en estado **Up**.
* **<http://localhost:8080>** abre el escritorio de ERPNext.
* Dentro de ERPNext, en **Cuentas ▸ Reportes**, aparecen *Libro Diario
  (Guatemala)*, *Libro Mayor (Guatemala)* y *Balance de Saldos (Guatemala)*.

### En el día a día

* **Apagar** (sin perder nada): `./install.sh stop` · **Encender**: `./install.sh up`.
* Apagar o reiniciar la computadora **no borra nada**: los datos viven en Docker.
* La instalación es **idempotente**: puedes repetir cualquier paso sin miedo; nada
  se duplica y nunca se crean empresas ni datos de prueba.

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

> **Plan de cuentas mínimo (por defecto).** El catálogo *Guatemala - Cuentas*
> trae cientos de cuentas. Con `ERP_MINIMAL_CHART=1` (lo normal),
> `./install.sh contabilidad` lo reduce a la **nomenclatura base**: las 7 cuentas
> raíz, numeradas del 1 al 7, **más sus encabezados principales** (21 cuentas en
> total), de modo que los estados conserven su estructura sin arrastrar el resto
> de subcuentas:
>
> | # | Raíz | Encabezados que conserva |
> |---|---|---|
> | 1 | Activos | Activo Corriente · No Corriente |
> | 2 | Pasivos | Pasivo Corriente · Pasivo No Corriente |
> | 3 | Patrimonio | Capital · Resultados del Ejercicio · Utilidades Retenidas |
> | 4 | Ingresos | Productos · Servicios |
> | 5 | Costos | Costo de Ventas · Costos Incluidos en la Valuación · Merma o Ajuste de Inventario |
> | 6 | Gastos | *(sólo la raíz)* |
> | 7 | Otros Gastos y Productos Financieros | Otros Gastos · Otros Ingresos |
>
> Así tú armas tus propias subcuentas donde las necesites. Es **seguro**: sólo se
> aplica si la empresa todavía **no tiene asientos**; si ya registraste
> movimientos, el plan se deja intacto. Para conservar el catálogo completo pon
> `ERP_MINIMAL_CHART=0` en `.env` y vuelve a ejecutar `./install.sh contabilidad`
> (antes de registrar asientos). Puedes agregar o quitar encabezados editando la
> lista `MINIMAL_CHART_HEADERS` en `scripts/setup_accounting.py`.

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
4. **Deja el plan de cuentas mínimo** (con `ERP_MINIMAL_CHART=1`, por defecto):
   borra el resto del catálogo y conserva la **nomenclatura base**: las 7 raíces
   (`1 Activos` … `7 Otros Gastos y Productos Financieros`) **más sus encabezados**
   (Activo Corriente, No Corriente, Pasivo Corriente/No Corriente, Capital,
   Resultados del Ejercicio, Utilidades Retenidas, Productos, Servicios, Costo de
   Ventas, Costos Incluidos en la Valuación, Merma o Ajuste de Inventario, Otros
   Gastos y Otros Ingresos), 21 cuentas en total, de modo que tú armes tus
   propias subcuentas. Sólo se aplica si la empresa no tiene asientos.
   Con `ERP_MINIMAL_CHART=0` en su lugar **completa el catálogo** con lo que le
   falta y ERPNext necesita: cuenta con `account_type = Equity`, depreciación
   acumulada, gasto por depreciación, cuenta real de redondeo y
   `account_type = Income Account` en los ingresos.
5. **Asigna Account Categories** (el motor NIIF de v16) a las cuentas por reglas,
   para que también funcionen las plantillas NIIF *(sólo con el catálogo completo)*.
6. **Fija los valores por defecto de la empresa** (ingresos, gastos, por cobrar,
   por pagar, banco/efectivo, redondeo) y aplica `ERP_PERPETUAL_INVENTORY`.
7. **Crea los años fiscales** indicados en `FISCAL_YEARS`.
8. **Crea / actualiza la plantilla** `Financial Report Template` del **ECPN
   (NIC 1)**.
9. **Crea los 4 reportes propios** (ECPN, Libro Diario, Libro Mayor y Balance de
   Saldos) y los enlaza en la barra lateral y el espacio de Contabilidad.
10. **Verifica** que todos los reportes existan (9 en total).

Si lo ejecutas **antes** de crear tu empresa, no falla: crea la plantilla y los
reportes (que sirven para cualquier empresa) y te recuerda qué falta.

Salida típica (con el plan mínimo):

```
Sitio: frontend
País: Guatemala · Moneda: GTQ
Plan de cuentas: nomenclatura base de Guatemala (raíces 1 a 7 + encabezados)
· Empresa: AtiTur, R.L.
  · Datos maestros de ERPNext: ya estaban listos
  ✔ 'Patrimonio' marcada como Patrimonio (Equity)
  · Valores por defecto de cuenta liberados (14 campos)
  · Plan de cuentas reducido a la nomenclatura base (21 cuentas = 7 raíces + encabezados; 100 eliminadas)
  + Año fiscal 2025 (2025-01-01 → 2025-12-31)
· Reporte creado: Libro Diario (Guatemala)
· Reporte creado: Libro Mayor (Guatemala)
· Reporte creado: Balance de Saldos (Guatemala)
· 9 reportes verificados correctamente
ERP_ACCOUNTING_SETUP_OK company_configured
```

---

## 6. Libro Diario y Libro Mayor (formato Guatemala)

Se ven **dentro de ERPNext** (Cuentas › Reportes › *Libro Diario (Guatemala)* /
*Libro Mayor (Guatemala)*) y también se pueden generar **como archivo** (HTML
imprimible + CSV), en orden cronológico y en GTQ.

* **Libro Diario** — registro cronológico de las **partidas (asientos)**. Cada
  partida lleva su **folio**, la fecha, el documento de origen (`Journal Entry`,
  factura, etc.) y sus cuentas al **Debe** y al **Haber**. Al pie de **cada
  asiento** aparece su fila **«Sumas iguales asiento N»** (el subtotal *Debe =
  Haber* de ese asiento), y al final la fila **«TOTAL DEL PERÍODO»** con la suma
  de todas las partidas (el cuadre *Debe − Haber*, que debe ser `0.00`). Esas
  filas las calcula la propia consulta, así que se ven igual en pantalla, al
  imprimir y al exportar.
* **Libro Mayor** — el **traslado** de esas partidas a cada cuenta, en orden de
  código. Cada cuenta se abre con su fila **«Saldo inicial»**, siguen sus
  movimientos con el **saldo corriente** (débito positivo) y cierra con la fila
  **«Suma del período»** (total *Debe*, total *Haber* y **saldo final** de esa
  cuenta). Al pie, **«TOTAL GENERAL»** suma los saldos finales: debe dar `0.00`
  si el libro cuadra. El archivo añade además un panel **Balance de saldos** y el
  **estado del libro** (`CUADRA` / `NO CUADRA`).
* **Balance de Saldos (Guatemala)** — reporte propio, una fila por cuenta con su
  *saldo inicial*, *debe*, *haber* y *saldo final*, con fila de **totales**. Es
  la vista rápida para comprobar que el libro cuadra: el total del Debe debe
  igualar al del Haber y la suma de los saldos finales debe dar `0.00`.

**Ver, imprimir y exportar desde ERPNext (sin ejecutar ningún script).** Abre el
reporte, ajusta **Empresa / Desde / Hasta** y usa la barra de la derecha:

* **⋯ › Export** → descarga el reporte en **Excel** o **CSV** tal como se ve.
* **Imprimir** (o `Ctrl+P`) → vista de impresión lista para **PDF**.

Las filas de subtotal y de total van en **negrita** para que resalten. No hace
falta usar `./scripts/estados-financieros.sh`; ese atajo sólo sirve para dejar
copias `HTML`/`XLSX` en `./salidas/` con el diseño «bonito» del reporte.

Detalles:

* Filtros: **Empresa** (obligatorio), **Desde** y **Hasta** (por defecto, el año
  fiscal en curso).
* URLs directas:
  * `http://localhost:8080/app/query-report/Libro%20Diario%20(Guatemala)`
  * `http://localhost:8080/app/query-report/Libro%20Mayor%20(Guatemala)`
  * `http://localhost:8080/app/query-report/Balance%20de%20Saldos%20(Guatemala)`
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
├── estados-financieros.xlsx            # todas las hojas + «Resumen y cuadre»
└── salida-<año>.txt                    # log de la generación
```

Todos los `.html` comparten el mismo **diseño** (encabezado con los datos de la
empresa, tarjetas de totales y filas de total resaltadas) y se imprimen a PDF con
`Ctrl+P` desde el navegador. El Excel incluye una hoja **«Resumen y cuadre»** con
los totales de control (Balance General, resultado, cuadre del libro, diferencia
del Libro Diario y suma de saldos finales del Libro Mayor).

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
| `ERP_MINIMAL_CHART` | `1` | `1` conserva la **nomenclatura base** (7 raíces 1…7 + sus encabezados, 21 cuentas) y borra el resto de subcuentas; `0` conserva el catálogo completo *Guatemala - Cuentas*. |
| `FISCAL_YEAR_START_MONTH` | `1` | Mes de inicio del ejercicio (1 = enero). |
| `FISCAL_YEARS` | `2025,2026,2027` | Ejercicios fiscales que se crean. |
| `LD_FOLIO_INICIO` | *(vacío → 1)* | Primer folio del **Libro Diario**. |
| `SITE_ADMIN_PASSWORD` | *(vacío)* | Se genera al azar si queda vacío. |
| `DB_ROOT_PASSWORD` | *(vacío)* | Se genera al azar si queda vacío. |

Consulta la configuración efectiva con `./install.sh env`.

> `.env` está en `.gitignore`: **nunca** se sube a GitHub (contiene contraseñas).

---

## 10. Tu primer asiento: apertura contable

Con el **plan de cuentas mínimo** el sitio arranca con la nomenclatura base (las
7 raíces y sus encabezados: Activo Corriente, Pasivo No Corriente, Capital,
Productos, Costo de Ventas, etc.). Antes de registrar movimientos, crea las
subcuentas que necesites como hijas de esos encabezados: **Contabilidad › Plan de
cuentas**, elige la cuenta (p. ej. `Activo Corriente`) y pulsa **Add Child** (una
cuenta como `1101 Caja`). Para que los estados salgan con datos, aparte de la
cuenta de resultados también conviene definir las **cuentas por defecto de la
empresa** (*Company › Default Accounts*: por cobrar, por pagar, banco/efectivo,
ingresos y gastos).

Luego registra tu **asiento de apertura** con los saldos con los que arrancas:

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

y revisa `salidas/06-libro-diario.html` (partidas con folio y «sumas iguales»),
`salidas/07-libro-mayor.html` (balance de saldos y **saldo final** por cuenta, con
el estado `CUADRA` / `NO CUADRA`) y el reporte en pantalla **Balance de Saldos
(Guatemala)**.

Si el total de *Debe − Haber* del Libro Diario no es `0.00`, o la suma de los
saldos finales del Libro Mayor no da `0.00`, hay un asiento descuadrado: revisa el
Balance Financiero (Balanza de Comprobación).

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
arrastrar datos de otra instalación (cada quien crea su empresa). Los pasos son
**exactamente los mismos** de la [sección 3](#3-instalación-paso-a-paso); en
resumen:

```bash
git clone <URL-del-repositorio> erpnext-gt
cd erpnext-gt
chmod +x install.sh scripts/*.sh

./install.sh                 # 1) deja el sitio limpio funcionando
# 2) crea tu empresa en el navegador (http://localhost:8080)
./install.sh contabilidad    # 3) prepara la contabilidad guatemalteca
./install.sh reports 2026    # 4) (opcional) estados y libros en ./salidas/
```

> La otra computadora también necesita **Docker instalado** (ver
> [sección 2](#2-requisitos)). Si el **puerto 8080** ya está ocupado ahí, cámbialo
> en `.env` (`HTTP_PORT=8081`) antes de ejecutar `./install.sh`.

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

**Errores típicos de la primera vez**

* **`docker: command not found`** → Docker no está instalado (o la terminal se
  abrió antes de instalarlo). Cierra y vuelve a abrir la terminal. Si sigue,
  instálalo (sección [2](#2-requisitos)).
* **`Cannot connect to the Docker daemon`** → Docker está instalado pero **no está
  corriendo**. Abre **Docker Desktop** (Windows/macOS) y espera a *“Engine
  running”*, o en Linux: `sudo systemctl start docker`.
* **`permission denied ... ./install.sh`** → dale permiso de ejecución
  (`chmod +x install.sh scripts/*.sh`) o ejecútalo con `bash install.sh`.
* **`./install.sh: No such file or directory`** → no estás en la carpeta del
  proyecto. Entra con `cd ruta/a/la/carpeta` (paso 1) y verifica con `ls` que
  aparezca `install.sh`.
* **`./install.sh` no hace nada en Windows** → estás en *PowerShell* o *CMD*. Usa
  **Git Bash** o **Ubuntu (WSL)** (sección [2](#2-requisitos)).
* **`No se encontró 'docker compose'`** → te falta el plugin *Compose v2*;
  actualiza Docker Desktop / reinstala Docker Engine reciente.

**Durante o después de la instalación**

* **El puerto 8080 está ocupado** → cambia `HTTP_PORT` en `.env` (p. ej.
  `HTTP_PORT=8081`) y ejecuta `./install.sh up`; la URL pasa a ser
  `http://localhost:8081`.
* **"El sitio no responde"** → revisa los logs: `./install.sh logs create-site`
  o `./install.sh logs backend`.
* **Agregué los reportes pero no aparecen** → haz *recarga forzada* en el
  navegador (`Ctrl + Shift + R`).
* **Los estados salen en ceros** → es normal si aún no registras asientos.
  Empieza con un asiento de apertura (sección 10).
* **No aparecen los reportes *Libro Diario (Guatemala)* / *Libro Mayor (Guatemala)***
  → todavía no ejecutaste `./install.sh contabilidad`. Recuerda hacer *recarga
  forzada* en el navegador (`Ctrl + Shift + R`).
* **¿Cómo imprimo o exporto un libro a Excel sin usar la terminal?** → abre el
  reporte en ERPNext (Cuentas › Reportes), ajusta *Desde/Hasta* y usa **⋯ ›
  Export** (Excel/CSV) o **Imprimir** (`Ctrl+P`). Las filas de subtotal por
  asiento/cuenta y la de total general ya vienen incluidas. Si actualizaste el
  proyecto, vuelve a ejecutar `./install.sh contabilidad` para refrescar los
  reportes.
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
  (folio, partida, Debe, Haber, «sumas iguales»). En pantalla incluyen los
  subtotales **por asiento** (Diario) y **por cuenta** (Mayor) más el total del
  período, y se pueden imprimir o exportar a Excel/CSV desde ERPNext. Para el
  archivo con el diseño «bonito» puedes usar `./install.sh reports`. La
  numeración de folios es consecutiva dentro del período; para un libro
  legalizado puedes ajustar el inicio con `LD_FOLIO_INICIO`.
* El proyecto **no crea empresas ni datos de ejemplo**, y **no incluye**
  facturación electrónica (FEL) ni regímenes fiscales específicos.
