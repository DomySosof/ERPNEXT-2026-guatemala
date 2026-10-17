#!/usr/bin/env bash
# =============================================================================
#  estados-financieros.sh
#  Atajo de escritorio: genera los estados financieros y los libros contables
#  (Libro Diario y Libro Mayor) y los copia a ./salidas. Todo el trabajo ocurre
#  dentro del contenedor 'backend'.
#
#  Uso:
#      ./scripts/estados-financieros.sh            # ejercicio fiscal actual
#      ./scripts/estados-financieros.sh 2026       # ejercicio fiscal indicado
# =============================================================================
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_SH="$SCRIPT_DIR/../install.sh"

[ -x "$INSTALL_SH" ] || { echo "No encuentro $INSTALL_SH" >&2; exit 1; }

exec "$INSTALL_SH" reports "$@"
