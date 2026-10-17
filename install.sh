#!/usr/bin/env bash
# =============================================================================
#  install.sh - ERPNext v16 sobre Docker  (nada se instala en tu máquina)
#
#  Uso:                ./install.sh  ->  asistente web  ->  ./install.sh contabilidad
#
#  Comandos:
#     install (por defecto)  Instala / reanuda la instalación completa
#     up / start             Levanta el stack
#     stop                   Detiene los contenedores (conserva datos)
#     restart                Reinicia el stack
#     status                 Estado de los servicios
#     logs [servicio]        Ver logs (por defecto: backend)
#     shell [servicio]       Abrir una terminal dentro de un contenedor
#     console                Consola de Python de Frappe (sitio activo)
#     contabilidad           Configura la contabilidad guatemalteca (ejecútalo
#                            DESPUÉS de crear tu empresa con el asistente web)
#     reports [año]          Genera los estados financieros y los libros contables
#     backup                 Respalda base de datos + archivos
#     restore <archivo>      Restaura un respaldo .sql.gz
#     update                 Actualiza a la versión indicada en .env
#     destroy                ELIMINA contenedores + volúmenes (borra todo)
#     env                    Muestra la configuración activa
#     help                   Esta ayuda
#
#  Flags:
#     --no-pull              No descargar imágenes
#     --yes / -y             No preguntar nada
# =============================================================================
set -Eeuo pipefail

# ------------------------------------------------------------------ básicos --
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"
SENTINEL="ERP_ACCOUNTING_SETUP_OK"

if [ -t 1 ]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_BLUE=$'\033[34m'
else
  C_RESET=""; C_BOLD=""; C_DIM=""; C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""
fi

log()  { printf '%s\n' "${C_BLUE}▸${C_RESET} $*"; }
ok()   { printf '%s\n' "${C_GREEN}✔${C_RESET} $*"; }
warn() { printf '%s\n' "${C_YELLOW}!${C_RESET} $*" >&2; }
err()  { printf '%s\n' "${C_RED}✘${C_RESET} $*" >&2; }
die()  { err "$*"; exit 1; }
hr()   { printf '%s\n' "${C_DIM}------------------------------------------------------------------------${C_RESET}"; }

trap 'err "Falló en la línea $LINENO. Revisa: ./install.sh logs"' ERR

# ------------------------------------------------------------- argumentos --
COMMAND="install"
PULL=1
ASSUME_YES=0
EXTRA_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --no-pull)   PULL=0 ;;
    -y|--yes)    ASSUME_YES=1 ;;
    -h|--help)   COMMAND="help" ;;
    -*)          die "Opción desconocida: $1  (usa ./install.sh help)" ;;
    *)           if [ "$COMMAND" = "install" ] && [ ${#EXTRA_ARGS[@]} -eq 0 ] && \
                    [ "$1" != "install" ]; then
                   COMMAND="$1"
                 else
                   EXTRA_ARGS+=("$1")
                 fi ;;
  esac
  shift
done

# --------------------------------------------------------------- docker CLI --
if docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
else
  DC=()
fi
dc() { "${DC[@]}" --env-file "$ENV_FILE" -f "$SCRIPT_DIR/docker-compose.yml" "$@"; }

preflight() {
  command -v docker >/dev/null 2>&1 || die "Docker no está instalado. Instálalo desde https://docs.docker.com/engine/install/"
  if [ ${#DC[@]} -eq 0 ]; then
    die "No se encontró 'docker compose' ni 'docker-compose'. Instala el plugin Compose v2."
  fi
  docker info >/dev/null 2>&1 || die "El daemon de Docker no responde. ¿Está corriendo? (sudo systemctl start docker)"
  [ -d "$SCRIPTS_DIR" ] || die "Falta el directorio '$SCRIPTS_DIR'."
}

# ------------------------------------------------------ lectura de .env -----
# Se parsea el archivo a mano (no se hace 'source') para soportar valores con
# espacios, comas y acentos.
env_get() {
  local key="$1" line
  [ -f "$ENV_FILE" ] || return 0
  line="$(grep -E "^[[:space:]]*${key}=" "$ENV_FILE" | tail -n1 || true)"
  [ -n "$line" ] || return 0
  line="${line#*=}"
  line="$(printf '%s' "$line" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  case "$line" in
    \"*\") line="${line#\"}"; line="${line%\"}" ;;
    \'*\') line="${line#\'}"; line="${line%\'}" ;;
  esac
  printf '%s' "$line"
}

random_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | cut -c1-20
  else
    head -c 64 /dev/urandom | tr -dc 'A-Za-z0-9' | cut -c1-20
  fi
}

env_set() { # env_set KEY VALUE
  local key="$1" value="$2"
  if grep -qE "^[[:space:]]*${key}=" "$ENV_FILE"; then
    # reemplazo seguro (el valor puede contener '/')
    awk -v k="$key" -v v="$value" '
      $0 ~ "^[[:space:]]*"k"=" { print k"="v; next } { print }
    ' "$ENV_FILE" > "$ENV_FILE.tmp" && mv "$ENV_FILE.tmp" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

ensure_env() {
  if [ ! -f "$ENV_FILE" ]; then
    [ -f "$ENV_EXAMPLE" ] || die "Falta $ENV_EXAMPLE"
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    ok "Creado .env a partir de .env.example"
  fi

  local v
  v="$(env_get SITE_ADMIN_PASSWORD)";    [ -n "$v" ] || env_set SITE_ADMIN_PASSWORD "$(random_secret)"
  v="$(env_get DB_ROOT_PASSWORD)";       [ -n "$v" ] || env_set DB_ROOT_PASSWORD "$(random_secret)"
  # normalizaciones defensivas
  v="$(env_get ERPNEXT_VERSION)";        [ -n "$v" ] || env_set ERPNEXT_VERSION "v16.51.1"
  v="$(env_get SITE_NAME)";              [ -n "$v" ] || env_set SITE_NAME "frontend"
  v="$(env_get HTTP_PORT)";              [ -n "$v" ] || env_set HTTP_PORT "8080"
  v="$(env_get COUNTRY)";                [ -n "$v" ] || env_set COUNTRY "Guatemala"
  v="$(env_get CURRENCY)";               [ -n "$v" ] || env_set CURRENCY "GTQ"
  v="$(env_get FISCAL_YEARS)";           [ -n "$v" ] || env_set FISCAL_YEARS "$(date +%Y)"
  v="$(env_get ERP_PERPETUAL_INVENTORY)"; [ -n "$v" ] || env_set ERP_PERPETUAL_INVENTORY "0"
  v="$(env_get ERP_MINIMAL_CHART)";     [ -n "$v" ] || env_set ERP_MINIMAL_CHART "1"
}

load_config() {
  SITE_NAME="$(env_get SITE_NAME)";                     SITE_NAME="${SITE_NAME:-frontend}"
  HTTP_PORT="$(env_get HTTP_PORT)";                     HTTP_PORT="${HTTP_PORT:-8080}"
  ERPNEXT_VERSION="$(env_get ERPNEXT_VERSION)";         ERPNEXT_VERSION="${ERPNEXT_VERSION:-v16.51.1}"
  SITE_ADMIN_PASSWORD="$(env_get SITE_ADMIN_PASSWORD)"
  COMPANY_NAME="$(env_get COMPANY_NAME)"
  COMPANY_ABBR="$(env_get COMPANY_ABBR)"
  PERPETUAL_INVENTORY="$(env_get ERP_PERPETUAL_INVENTORY)"; PERPETUAL_INVENTORY="${PERPETUAL_INVENTORY:-0}"
  MINIMAL_CHART="$(env_get ERP_MINIMAL_CHART)"; MINIMAL_CHART="${MINIMAL_CHART:-1}"
  COUNTRY="$(env_get COUNTRY)"
  CURRENCY="$(env_get CURRENCY)"
  FISCAL_YEAR_START_MONTH="$(env_get FISCAL_YEAR_START_MONTH)"; FISCAL_YEAR_START_MONTH="${FISCAL_YEAR_START_MONTH:-1}"
  FISCAL_YEARS="$(env_get FISCAL_YEARS)"
  LD_FOLIO_INICIO="$(env_get LD_FOLIO_INICIO)"
}

# ----------------------------------------------------------- utilidades dc --
check_port() {
  local port="$1" proj
  command -v ss >/dev/null 2>&1 || return 0
  ss -ltn 2>/dev/null | grep -q ":${port} " || return 0

  # Si el puerto lo ocupa nuestro propio stack, no es un problema.
  proj="$(env_get COMPOSE_PROJECT_NAME)"; proj="${proj:-erpnext}"
  if docker ps --filter "publish=${port}" --format '{{.Names}}' 2>/dev/null | grep -q "^${proj}-"; then
    return 0
  fi

  warn "El puerto ${port} ya está en uso por otro programa. Cambia HTTP_PORT en .env si algo no funciona."
}

wait_for_create_site() {
  log "Esperando a que el contenedor 'create-site' termine (puede tardar varios minutos)..."
  local cid state i=0
  cid="$(dc ps -a -q create-site 2>/dev/null | head -n1 || true)"
  if [ -z "$cid" ]; then
    warn "No se encontró el contenedor create-site; continúo."
    return 0
  fi
  while :; do
    state="$(docker inspect -f '{{.State.Status}}:{{.State.ExitCode}}' "$cid" 2>/dev/null || echo unknown:1)"
    case "$state" in
      exited:0) ok "Sitio listo."; return 0 ;;
      exited:*)
        err "El contenedor create-site terminó con error (${state})."
        dc logs --tail=80 create-site || true
        return 1 ;;
      *)
        i=$((i + 1))
        if [ "$i" -gt 240 ]; then
          err "Timeout esperando la creación del sitio (20 min)."
          dc logs --tail=80 create-site || true
          return 1
        fi
        sleep 5 ;;
    esac
  done
}

site_ready() {
  dc exec -T backend bench --site "$SITE_NAME" list-apps 2>/dev/null | grep -q erpnext
}

# Ejecuta un script Python dentro del contenedor, en el contexto del sitio.
# IMPORTANTE: no se usa 'bench console' porque es IPython y ejecuta el script
# línea por línea (rompe funciones y 'return'). Se usa el intérprete Python del
# virtualenv del contenedor, que sí ejecuta el archivo como programa.
run_in_site() { # run_in_site <archivo.py> [VAR=valor ...]
  local script="$1"; shift
  local args=() out rc
  for kv in "$@"; do args+=(-e "$kv"); done

  out="$(mktemp)"
  local sentinel="${RUN_SENTINEL:-$SENTINEL}"

  # El script llega por stdin y se ejecuta con el python del venv ('-').
  #  -w: directorio de trabajo = bench (frappe usa rutas de log relativas ../logs)
  #  -e FRAPPE_STREAM_LOGGING=1: evita abrir archivos de log (los manda a stderr)
  #  bash -c (sin -l): no cargamos perfiles que puedan cambiar el directorio.
  rc=0
  dc exec -T "${args[@]}" -w /home/frappe/frappe-bench -e FRAPPE_STREAM_LOGGING=1 \
    backend bash -c \
    "if [ -x env/bin/python ]; then exec env/bin/python - '$SITE_NAME'; else exec python3 - '$SITE_NAME'; fi" \
    < "$script" >"$out" 2>&1 || rc=$?

  if [ "$rc" -eq 0 ] && grep -q "$sentinel" "$out"; then
    cat "$out"; rm -f "$out"; return 0
  fi

  err "No se pudo ejecutar $script dentro del contenedor."
  printf '%s\n' "${C_DIM}----- salida del contenedor -----${C_RESET}"
  cat "$out" || true
  rm -f "$out"
  return 1
}

# --------------------------------------------------------------- comandos --
cmd_install() {
  preflight
  ensure_env
  load_config
  check_port "$HTTP_PORT"

  hr
  printf '%s\n' "${C_BOLD} ERPNext ${ERPNEXT_VERSION} · Docker${C_RESET}"
  printf '%s\n' " Sitio        : ${SITE_NAME}"
  printf '%s\n' " URL          : http://localhost:${HTTP_PORT}"
  printf '%s\n' " Usuario      : Administrator"
  printf '%s\n' " País/moneda  : ${COUNTRY} · ${CURRENCY}"
  hr

  if [ "$PULL" -eq 1 ]; then
    log "Descargando imágenes (esto solo pasa la primera vez)..."
    dc pull --quiet || warn "No se pudieron precargar todas las imágenes; continuaré."
  fi

  log "Levantando los servicios..."
  dc up -d

  wait_for_create_site

  log "Verificando que el sitio responda..."
  local i=0
  until site_ready; do
    i=$((i + 1))
    if [ "$i" -gt 60 ]; then
      die "El sitio no responde con la app 'erpnext'. Revisa: ./install.sh logs backend"
    fi
    sleep 5
  done
  ok "Sitio operativo."

  hr
  ok "¡Instalación terminada! El sitio quedó limpio (sin empresas ni datos de prueba)."
  printf '%s\n' ""
  printf '%s\n' " ${C_BOLD}Siguientes 2 pasos:${C_RESET}"
  printf '%s\n' ""
  printf '%s\n' " ${C_BOLD}1) Crea tu empresa con el asistente web${C_RESET}"
  printf '%s\n' "    Abre ${C_BOLD}http://localhost:${HTTP_PORT}${C_RESET} y entra como ${C_BOLD}Administrator${C_RESET}"
  printf '%s\n' "    Contraseña: ${C_BOLD}${SITE_ADMIN_PASSWORD}${C_RESET}"
  printf '%s\n' "    El asistente te pedirá los datos de ${C_BOLD}tu${C_RESET} empresa. Usa:"
  printf '%s\n' "      · País            : ${COUNTRY}"
  printf '%s\n' "      · Moneda          : ${CURRENCY}"
  printf '%s\n' "      · Plan de cuentas : Guatemala - Cuentas"
  printf '%s\n' ""
  printf '%s\n' " ${C_BOLD}2) Prepara la contabilidad guatemalteca${C_RESET}"
  printf '%s\n' "    Cuando termines el asistente, vuelve aquí y ejecuta:"
  printf '%s\n' "      ${C_BOLD}./install.sh contabilidad${C_RESET}"
  printf '%s\n' "    ${C_DIM}Crea los reportes y los libros (Libro Diario y Libro Mayor), corrige el"
  printf '%s\n' "    catálogo de Guatemala y deja listos los ejercicios fiscales.${C_RESET}"
  printf '%s\n' ""
  printf '%s\n' " ${C_DIM}Para generar los estados en archivos: ./install.sh reports${C_RESET}"
  hr
}

cmd_up()      { preflight; ensure_env; load_config; dc up -d;              ok "Servicios levantados."; }
cmd_stop()    { preflight; ensure_env;            dc stop;                 ok "Servicios detenidos (los datos se conservan)."; }
cmd_restart() { preflight; ensure_env;            dc restart;              ok "Servicios reiniciados."; }
cmd_status()  { preflight; ensure_env;            dc ps; }
cmd_logs() {
  preflight; ensure_env
  local svc="${EXTRA_ARGS[0]:-backend}"
  dc logs -f --tail=200 "$svc"
}

cmd_shell() {
  preflight; ensure_env
  local svc="${EXTRA_ARGS[0]:-backend}"
  log "Abriendo bash en el contenedor '$svc'..."
  dc exec "$svc" bash
}

cmd_console() {
  preflight; ensure_env; load_config
  log "Consola de Frappe del sitio '$SITE_NAME'. Escribe exit() para salir."
  dc exec backend bench --site "$SITE_NAME" console
}

cmd_env() {
  ensure_env; load_config
  hr
  printf 'SITE_NAME        = %s\n' "$SITE_NAME"
  printf 'HTTP_PORT        = %s\n' "$HTTP_PORT"
  printf 'ERPNEXT_VERSION  = %s\n' "$ERPNEXT_VERSION"
  printf 'COMPANY_NAME     = %s\n' "${COMPANY_NAME:-(se detecta la empresa del sitio)}"
  printf 'COMPANY_ABBR     = %s\n' "${COMPANY_ABBR:-(no aplica)}"
  printf 'COUNTRY          = %s\n' "$COUNTRY"
  printf 'CURRENCY         = %s\n' "$CURRENCY"
  printf 'FISCAL_YEARS     = %s\n' "$FISCAL_YEARS"
  printf 'INV. PERPETUO    = %s\n' "$PERPETUAL_INVENTORY"
  printf 'PLAN MÍNIMO      = %s\n' "$MINIMAL_CHART"
  printf 'ADMIN_PASSWORD   = %s\n' "$SITE_ADMIN_PASSWORD"
  hr
  printf 'Archivo: %s\n' "$ENV_FILE"
}

cmd_contabilidad() {
  preflight; ensure_env; load_config
  log "Configurando la contabilidad guatemalteca (reportes, libros y catálogo)..."
  run_in_site "$SCRIPTS_DIR/setup_accounting.py" \
    "ERP_SITE=$SITE_NAME" \
    "ERP_COMPANY=$COMPANY_NAME" \
    "ERP_ABBR=$COMPANY_ABBR" \
    "ERP_COUNTRY=$COUNTRY" \
    "ERP_CURRENCY=$CURRENCY" \
    "ERP_FY_START_MONTH=$FISCAL_YEAR_START_MONTH" \
    "ERP_FISCAL_YEARS=$FISCAL_YEARS" \
    "ERP_PERPETUAL_INVENTORY=$PERPETUAL_INVENTORY" \
    "ERP_MINIMAL_CHART=$MINIMAL_CHART"
  ok "Contabilidad lista."
  printf '%s\n' "   ${C_DIM}Reportes en: Cuentas > Reportes (barra lateral), y en la tarjeta Financial Statements.${C_RESET}"
}

cmd_reports() {
  preflight; ensure_env; load_config
  local year="${EXTRA_ARGS[0]:-$(date +%Y)}"
  local outdir="$SCRIPT_DIR/salidas"
  mkdir -p "$outdir"

  log "Generando los estados financieros y los libros contables del ejercicio $year..."
  RUN_SENTINEL="ERP_FINANCIAL_STATEMENTS_OK" run_in_site "$SCRIPTS_DIR/estados_financieros.py" \
    "EF_SITE=$SITE_NAME" \
    "EF_COMPANY=$COMPANY_NAME" \
    "EF_FISCAL_YEAR=$year" \
    "LD_FOLIO_INICIO=${LD_FOLIO_INICIO:-1}" \
    | tee "$outdir/salida-$year.txt"

  log "Copiando archivos generados a ./salidas ..."
  dc cp "backend:/home/frappe/frappe-bench/sites/_estados_financieros/." "$outdir/" 2>/dev/null \
    || warn "No se pudieron copiar los archivos (¿se generó alguno?)."

  ok "Listo. Revisa: $outdir"
  ls -1 "$outdir" 2>/dev/null || true
}

cmd_backup() {
  preflight; ensure_env; load_config
  local outdir="$SCRIPT_DIR/respaldos"
  mkdir -p "$outdir"
  local stamp; stamp="$(date +%Y%m%d-%H%M%S)"

  log "Respaldando base de datos del sitio '$SITE_NAME'..."
  dc exec -T backend bench --site "$SITE_NAME" backup --with-files

  log "Copiando respaldos a ./respaldos ..."
  local tmp="$outdir/.tmp"
  rm -rf "$tmp"; mkdir -p "$tmp"
  dc cp "backend:/home/frappe/frappe-bench/sites/$SITE_NAME/private/backups/." "$tmp/"
  # nos quedamos con el juego más reciente
  local base; base="$(ls -1t "$tmp"/*.sql.gz 2>/dev/null | head -n1 | sed 's/\.sql\.gz$//')"
  if [ -n "$base" ]; then
    for f in "$base".*; do cp -f "$f" "$outdir/$stamp-$(basename "$f")"; done
  fi
  rm -rf "$tmp"
  ok "Respaldo en: $outdir"
  ls -1 "$outdir" | tail -n5
}

cmd_restore() {
  preflight; ensure_env; load_config
  local file="${EXTRA_ARGS[0]:-}"
  [ -n "$file" ] || die "Uso: ./install.sh restore <ruta/al/respaldo.sql.gz>"
  [ -f "$file" ] || die "No existe el archivo: $file"

  warn "Esto SOBRESCRIBE la base de datos del sitio '$SITE_NAME'."
  if [ "$ASSUME_YES" -ne 1 ]; then
    read -r -p "¿Continuar? (escribe SI): " ans
    [ "$ans" = "SI" ] || die "Cancelado."
  fi

  local name; name="$(basename "$file")"
  dc cp "$file" "backend:/tmp/$name"
  log "Restaurando $name ..."
  dc exec -T backend bench --site "$SITE_NAME" --force restore "/tmp/$name"
  dc exec -T backend bench --site "$SITE_NAME" migrate
  dc exec -T backend bench --site "$SITE_NAME" clear-cache
  dc restart backend queue-short queue-long scheduler websocket
  ok "Restauración completada."
}

cmd_update() {
  preflight; ensure_env; load_config
  warn "Actualizar es un cambio de versión de la imagen (${ERPNEXT_VERSION}). Haz un respaldo antes."
  if [ "$ASSUME_YES" -ne 1 ]; then
    read -r -p "¿Continuar? (escribe SI): " ans
    [ "$ans" = "SI" ] || die "Cancelado."
  fi
  dc pull
  dc up -d
  log "Ejecutando migraciones..."
  until site_ready; do sleep 5; done
  dc exec -T backend bench --site "$SITE_NAME" migrate
  dc restart backend queue-short queue-long scheduler websocket
  ok "Actualización terminada."
}

cmd_destroy() {
  preflight; ensure_env
  warn "Esto ELIMINA contenedores, volúmenes y TODOS los datos de ERPNext."
  if [ "$ASSUME_YES" -ne 1 ]; then
    read -r -p "Escribe BORRAR para confirmar: " ans
    [ "$ans" = "BORRAR" ] || die "Cancelado."
  fi
  dc down -v --remove-orphans
  ok "Todo eliminado. Tu máquina queda limpia (solo quedan estos archivos de texto)."
}

cmd_help() {
  sed -n '3,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# ------------------------------------------------------------------ main ---
case "$COMMAND" in
  install)            cmd_install ;;
  up|start)           cmd_up ;;
  stop)               cmd_stop ;;
  restart)            cmd_restart ;;
  status|ps)          cmd_status ;;
  logs|log)           cmd_logs ;;
  shell|bash)         cmd_shell ;;
  console)            cmd_console ;;
  env|config)         cmd_env ;;
  contabilidad|accounting|contable) cmd_contabilidad ;;
  reports|estados)    cmd_reports ;;
  backup)             cmd_backup ;;
  restore)            cmd_restore ;;
  update|upgrade)     cmd_update ;;
  destroy|uninstall)  cmd_destroy ;;
  help|-h|--help)     cmd_help ;;
  *)                  die "Comando desconocido: '$COMMAND'. Usa ./install.sh help" ;;
esac
