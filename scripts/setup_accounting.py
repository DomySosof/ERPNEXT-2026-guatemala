#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_accounting.py
===================
Deja la contabilidad lista para emitir los 5 estados financieros:

    1. Balance General
    2. Estado de Resultados
    3. Balance Financiero / Balanza de Comprobación
    4. Estado de Flujo de Efectivo
    5. Estado de Cambios en el Patrimonio Neto (NIC 1)   <-- plantilla propia

IMPORTANTE: este script NO crea la empresa. La empresa la creas tú desde el
asistente web de ERPNext (País = Guatemala, Moneda = GTQ, plan de cuentas
"Guatemala - Cuentas"). Así el sitio queda limpio, sin datos de ejemplo.

Qué hace:
    - Detecta la empresa ya creada (la tuya).
    - Prepara los datos maestros base que normalmente deja el asistente de
      ERPNext (grupos de artículos, territorios, UOM, tipos de almacén...).
      Sin esto, crear una empresa falla con
      "Could not find Warehouse Type: Transit".
    - Corrige el root_type del patrimonio (el catálogo de Guatemala lo trae
      mal: "Patrimonio" viene como Asset en lugar de Equity).
    - Normaliza account_type de cuentas clave y completa los valores por
      defecto de la empresa (cuenta de ingresos, gastos, redondeo, etc.).
    - Asigna Account Categories (motor NIIF de ERPNext v16).
    - Crea los años fiscales.
    - Crea / actualiza la plantilla "Estado de Cambios en el Patrimonio Neto".
    - Crea los reportes propios (Query Report en base de datos, visibles en la
      lista de reportes y con acceso directo en el espacio y la barra lateral):
        · Estado de Cambios en el Patrimonio Neto
        · Libro Diario (Guatemala)
        · Libro Mayor (Guatemala)
    - Verifica que los reportes existan.

Si todavía no existe ninguna empresa, sólo crea la plantilla y los reportes
(que valen para cualquier empresa) y te dice qué hacer a continuación.

Es idempotente: se puede ejecutar las veces que haga falta.

Uso (lo hace 'install.sh contabilidad'):

    docker compose exec -T -w /home/frappe/frappe-bench -e FRAPPE_STREAM_LOGGING=1 \
        backend env/bin/python - < scripts/setup_accounting.py

Parámetros por variables de entorno:
    ERP_COMPANY, ERP_COUNTRY, ERP_CURRENCY,
    ERP_FY_START_MONTH, ERP_FISCAL_YEARS, ERP_PERPETUAL_INVENTORY
    (ERP_COMPANY es opcional: si se deja vacío se usa la única empresa del sitio)
"""

import json
import os
import sys
from datetime import date, timedelta

# --------------------------------------------------------------------------
# 0. Bootstrap de Frappe (funciona con 'bench console' y con 'python -')
# --------------------------------------------------------------------------


def _bootstrap():
    import frappe

    already = getattr(frappe.local, "site", None) and getattr(frappe.local, "db", None)
    if already:
        return frappe

    site = os.environ.get("ERP_SITE") or (sys.argv[1] if len(sys.argv) > 1 else None)
    sites_path = os.environ.get("ERP_SITES_PATH", "/home/frappe/frappe-bench/sites")
    frappe.init(site=site, sites_path=sites_path)
    frappe.connect()
    return frappe


frappe = _bootstrap()

if not getattr(frappe.local, "site", None):
    raise SystemExit("No hay sitio activo: pasa --site <sitio> o define ERP_SITE.")

frappe.set_user("Administrator")
frappe.flags.ignore_permissions = True
frappe.flags.in_setup_accounting = True

SENTINEL = "ERP_ACCOUNTING_SETUP_OK"

CFG = {
    # Vacío = usar la empresa que exista en el sitio (la que creó el asistente).
    "company": os.environ.get("ERP_COMPANY") or "",
    "abbr": (os.environ.get("ERP_ABBR") or "").upper()[:5],
    "country": os.environ.get("ERP_COUNTRY") or "Guatemala",
    "currency": os.environ.get("ERP_CURRENCY") or "GTQ",
    "fy_start_month": int(os.environ.get("ERP_FY_START_MONTH") or 1),
    "perpetual_inventory": (os.environ.get("ERP_PERPETUAL_INVENTORY") or "0") not in (
        "",
        "0",
        "no",
        "false",
        "False",
    ),
    "fiscal_years": [
        y.strip()
        for y in (os.environ.get("ERP_FISCAL_YEARS") or str(date.today().year)).split(",")
        if y.strip()
    ],
}

ECPN_TEMPLATE_NAME = "Estado de Cambios en el Patrimonio Neto (NIC 1)"
EQUITY_REPORT_NAME = "Estado de Cambios en el Patrimonio Neto"
LIBRO_DIARIO_REPORT_NAME = "Libro Diario (Guatemala)"
LIBRO_MAYOR_REPORT_NAME = "Libro Mayor (Guatemala)"

FINANCIAL_REPORTS = [
    ("Balance Sheet", "Balance General / Estado de Situación Financiera"),
    ("Profit and Loss Statement", "Estado de Resultados"),
    ("Trial Balance", "Balance Financiero / Balanza de Comprobación"),
    ("Cash Flow", "Estado de Flujo de Efectivo"),
    ("Custom Financial Statement", "Estado de Cambios en el Patrimonio Neto (ECPN)"),
    (EQUITY_REPORT_NAME, "ECPN (reporte dedicado)"),
    (LIBRO_DIARIO_REPORT_NAME, "Libro Diario (Guatemala)"),
    (LIBRO_MAYOR_REPORT_NAME, "Libro Mayor (Guatemala)"),
]

LOG = []


def log(msg):
    LOG.append(msg)
    print(msg, flush=True)


def warn(msg):
    print(f"  ! {msg}", flush=True)


# --------------------------------------------------------------------------
# 0. Datos maestros que normalmente deja el asistente de ERPNext
# --------------------------------------------------------------------------
# Un sitio creado con 'bench new-site --install-app erpnext' NO pasa por el
# asistente web, así que le faltan datos maestros que el asistente sí crea
# (grupos de artículos, territorios, unidades de medida, tipos de fiesta...).
#
# El que rompe todo es el tipo de almacén "Transit": al crear la empresa,
# ERPNext crea los almacenes por defecto y el de "Goods In Transit" falla con
#     frappe.exceptions.LinkValidationError: Could not find Warehouse Type: Transit
#
# (En v16 el parche que lo creaba ya no se ejecuta: sólo corría si existía el
# campo 'Stock Entry.add_to_transit', que ya no existe.) Aquí ejecutamos el
# mismo paso que hace el asistente (install_fixtures.install) y, por si acaso,
# creamos el tipo de almacén a mano.

WAREHOUSE_TRANSIT = "Transit"


def ensure_warehouse_transit():
    """Crea el tipo de almacén 'Transit' si falta (lo usa 'Goods In Transit')."""
    if frappe.db.exists("Warehouse Type", WAREHOUSE_TRANSIT):
        return True
    try:
        doc = frappe.new_doc("Warehouse Type")
        doc.name = WAREHOUSE_TRANSIT
        doc.flags.ignore_permissions = True
        doc.insert()
        frappe.db.commit()
        log(f"  · Tipo de almacén '{WAREHOUSE_TRANSIT}' creado")
        return True
    except Exception as exc:  # noqa: BLE001
        warn(f"No se pudo crear el tipo de almacén '{WAREHOUSE_TRANSIT}': {exc}")
        try:
            frappe.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False


def fixtures_missing():
    """¿Faltan los datos maestros que crea el asistente de ERPNext?

    Se comprueban cosas que el asistente crea siempre y que no dependen del
    idioma del sitio (por eso contamos registros en lugar de buscar por nombre).
    """
    try:
        if not frappe.db.exists("Warehouse Type", WAREHOUSE_TRANSIT):
            return True
        for doctype in ("Item Group", "UOM", "Territory"):
            if not frappe.db.count(doctype):
                return True
    except Exception:  # noqa: BLE001
        return True
    return False


def ensure_erpnext_master_data(company=None):
    """Crea los datos maestros base SÓLO si faltan y ya existe una empresa.

    Importante: si ya existen (lo normal, porque el asistente web los crea),
    NO se vuelve a llamar a 'install_fixtures.install()'. Reinsertar registros
    de árboles (Territory, Customer Group, Supplier Group, Sales Person...) hace
    que ERPNext imprima tracebacks de 'NestedSetRecursionError' que asustan:
    son inofensivos (los revierte solo), pero mejor no provocarlos.

    Si todavía no hay empresa tampoco los creamos: los creará el asistente web,
    que es quien sabe hacerlo limpio.
    """
    if not fixtures_missing():
        log("  · Datos maestros de ERPNext: ya estaban listos")
    elif company:
        try:
            from erpnext.setup.setup_wizard.operations import install_fixtures

            install_fixtures.install(CFG["country"])
            frappe.db.commit()
            log("  · Datos maestros base de ERPNext creados (grupos, territorios, UOM...)")
        except Exception as exc:  # noqa: BLE001
            warn(f"No se pudieron preparar todos los datos maestros de ERPNext: {exc}")
            try:
                frappe.db.rollback()
            except Exception:  # noqa: BLE001
                pass
    else:
        log("  · Datos maestros de ERPNext: los creará el asistente web")

    # Red de seguridad: sin este tipo de almacén, crear/editar una empresa falla
    # con "Could not find Warehouse Type: Transit".
    ensure_warehouse_transit()


# --------------------------------------------------------------------------
# 1. Empresa (la crea el usuario en el asistente web de ERPNext)
# --------------------------------------------------------------------------


def find_company():
    """Devuelve la empresa a configurar, o None si el sitio todavía no tiene.

    Orden de búsqueda:
      1. ERP_COMPANY (por 'name' o por 'company_name').
      2. La única empresa del sitio (la que creaste con el asistente).
    """
    name = CFG["company"]
    if name:
        if frappe.db.exists("Company", name):
            return name
        found = frappe.db.get_value("Company", {"company_name": name}, "name")
        if found:
            return found
        warn(f"La empresa '{name}' (ERP_COMPANY) no existe todavía.")

    companies = frappe.get_all("Company", pluck="name", limit=3)
    if not companies:
        return None
    if len(companies) > 1:
        warn(
            "El sitio tiene más de una empresa; configura ERP_COMPANY en .env "
            "para indicar cuál se va a usar."
        )
    return companies[0]


def check_company_basics(company):
    """Avisa (sin romper nada) si la empresa no está en el país/moneda esperados."""
    data = frappe.db.get_value(
        "Company", company, ["company_name", "country", "default_currency"], as_dict=True
    ) or {}
    label = data.get("company_name") or company

    country = data.get("country") or ""
    if country and country.strip().lower() != CFG["country"].strip().lower():
        warn(
            f"La empresa '{label}' está configurada en '{country}', no en "
            f"'{CFG['country']}'. El plan de cuentas importado no se cambia solo; "
            "si no es lo que querías, borra el sitio y vuelve a empezar "
            "(./install.sh destroy)."
        )

    currency = data.get("default_currency") or ""
    if currency and currency.upper() != CFG["currency"].upper():
        warn(
            f"La moneda de '{label}' es {currency}, no {CFG['currency']}. "
            "Los estados saldrán en la moneda de la empresa."
        )

    if not frappe.db.count("Account", {"company": company}):
        warn(
            f"La empresa '{label}' no tiene plan de cuentas. Vuelve a crearla con el "
            "asistente (plan 'Guatemala - Cuentas')."
        )
    return label


def set_company_defaults(company):
    """Asegura los valores por defecto de la empresa y los de sesión."""
    frappe.defaults.set_global_default("company", company)
    try:
        frappe.defaults.set_user_default("company", company, user="Administrator")
    except Exception as exc:  # noqa: BLE001
        warn(f"No se pudo fijar la empresa por defecto del usuario: {exc}")

    doc = frappe.get_doc("Company", company)
    changed = {}

    def first_account(**filters):
        f = {"company": company, "is_group": 0, "disabled": 0}
        f.update(filters)
        return frappe.db.get_value("Account", f, "name")

    # Inventario perpetuo: por defecto se deja como está en .env
    # (ERP_PERPETUAL_INVENTORY=0 -> se apaga, que es lo que el asistente deja
    # encendido). Apagado, la contabilidad funciona igual sin exigir cuentas
    # de inventario configuradas.
    desired_perpetual = 1 if CFG["perpetual_inventory"] else 0
    if int(doc.enable_perpetual_inventory or 0) != desired_perpetual:
        changed["enable_perpetual_inventory"] = desired_perpetual

    def first_account(**filters):
        f = {"company": company, "is_group": 0, "disabled": 0}
        f.update(filters)
        return frappe.db.get_value("Account", f, "name")

    if not doc.default_income_account:
        changed["default_income_account"] = (
            first_account(account_category="Revenue from Operations")
            or first_account(account_type="Income Account")
            or first_account(root_type="Income")
        )
    if not doc.default_expense_account:
        changed["default_expense_account"] = first_account(account_type="Cost of Goods Sold") or first_account(
            root_type="Expense"
        )
    if not doc.default_receivable_account:
        changed["default_receivable_account"] = first_account(account_type="Receivable")
    if not doc.default_payable_account:
        changed["default_payable_account"] = first_account(account_type="Payable")
    if not doc.default_cash_account:
        changed["default_cash_account"] = first_account(account_type="Cash")
    if not doc.default_bank_account:
        changed["default_bank_account"] = first_account(account_type="Bank")
    if not doc.default_expense_account and not doc.get("default_expense_account"):
        changed["default_expense_account"] = first_account(root_type="Expense")

    for field, value in changed.items():
        # Ojo: 0 es un valor válido (p.ej. apagar el inventario perpetuo),
        # por eso no se puede usar 'if value:'.
        if value is None or value == "":
            continue
        frappe.db.set_value("Company", company, field, value, update_modified=False)

    if changed:
        frappe.db.commit()
        aplicados = [f for f, v in changed.items() if v is not None and v != ""]
        log(f"  · Valores por defecto de la empresa: {', '.join(aplicados)}")


# --------------------------------------------------------------------------
# 2. Corrección del árbol de cuentas
# --------------------------------------------------------------------------

# Cuentas raíz que deben ser patrimonio (Equity). El catálogo de Guatemala
# trae "Patrimonio" con root_type = "Asset", lo cual rompe Balance General,
# el flujo de efectivo (sección financiación) y el ECPN.
EQUITY_ROOT_NAMES = {
    "patrimonio",
    "patrimonio neto",
    "capital contable",
    "equity",
    "source of funds (equity)",
}
EQUITY_ROOT_NUMBERS = {"3", "3.0", "30", "300", "3000", "30000"}


def fix_equity_root_type(company):
    roots = frappe.db.sql(
        """select name, lft, rgt, root_type, account_number, account_name
           from `tabAccount` where company=%s and ifnull(parent_account,'')='' """,
        company,
        as_dict=True,
    )
    fixed = 0
    for root in roots:
        if root.root_type == "Equity":
            continue
        name = (root.account_name or "").strip().lower()
        number = (root.account_number or "").strip()
        if name in EQUITY_ROOT_NAMES or number in EQUITY_ROOT_NUMBERS:
            frappe.db.sql(
                """update `tabAccount`
                   set root_type='Equity', report_type='Balance Sheet'
                   where company=%s and lft>=%s and rgt<=%s""",
                (company, root.lft, root.rgt),
            )
            frappe.db.set_value(
                "Account", root.name, "account_type", "Equity", update_modified=False
            )
            fixed += 1
            log(f"  ✔ '{root.account_name}' marcada como Patrimonio (Equity)")

    if fixed:
        from frappe.utils.nestedset import rebuild_tree

        rebuild_tree("Account")
        frappe.clear_cache()
        frappe.db.commit()
    else:
        log("  · Árbol de patrimonio ya correcto")

    return fixed


# --------------------------------------------------------------------------
# 3. Cuentas auxiliares que el catálogo no trae
# --------------------------------------------------------------------------


def find_parent(company, by_name=None, by_number=None, account_types=None, root_type=None):
    """Busca una cuenta de grupo para usar como padre."""
    if by_name:
        name = frappe.db.get_value(
            "Account", {"company": company, "account_name": by_name, "is_group": 1}, "name"
        )
        if name:
            return name
    if by_number:
        for number in (by_number,) if isinstance(by_number, str) else by_number:
            name = frappe.db.get_value(
                "Account",
                {"company": company, "account_number": number, "is_group": 1},
                "name",
            )
            if name:
                return name
    filters = {"company": company, "is_group": 1, "disabled": 0}
    if account_types:
        filters["account_type"] = ["in", list(account_types)]
    if root_type:
        filters["root_type"] = root_type
    return frappe.db.get_value("Account", filters, "name")


def ensure_account(company, account_name, parent, account_type=None, number=None):
    """Crea una cuenta hoja si no existe. Devuelve su nombre o None."""
    existing = frappe.db.get_value(
        "Account", {"company": company, "account_name": account_name, "is_group": 0}, "name"
    )
    if existing:
        if account_type:
            frappe.db.set_value("Account", existing, "account_type", account_type, update_modified=False)
        return existing

    if not parent:
        warn(f"No hay cuenta padre para crear '{account_name}'")
        return None

    root_type = frappe.get_cached_value("Account", parent, "root_type")
    doc = frappe.new_doc("Account")
    doc.account_name = account_name
    doc.company = company
    doc.parent_account = parent
    doc.is_group = 0
    doc.root_type = root_type
    doc.report_type = "Balance Sheet" if root_type in ("Asset", "Liability", "Equity") else "Profit and Loss"
    doc.account_type = account_type
    doc.account_number = number
    doc.account_currency = frappe.get_cached_value("Company", company, "default_currency")
    doc.flags.ignore_permissions = True
    doc.flags.ignore_mandatory = True
    doc.insert()
    log(f"  + Cuenta creada: {account_name} ({account_type or 'sin tipo'})")
    return doc.name


def ensure_helper_accounts(company):
    """Redondeo, depreciación acumulada y cuenta de Equity: mínimos que el
    catálogo de Guatemala no define y que ERPNext necesita."""
    # 1) Cuenta con account_type = Equity (sección 'Financiación' del flujo de caja)
    has_equity = frappe.db.get_value(
        "Account", {"company": company, "account_type": "Equity", "is_group": 0}, "name"
    )
    if not has_equity:
        candidate = frappe.db.get_value(
            "Account", {"company": company, "account_name": "Capital", "is_group": 0}, "name"
        ) or frappe.db.get_value(
            "Account",
            {"company": company, "root_type": "Equity", "is_group": 0},
            "name",
            order_by="lft",
        )
        if candidate:
            frappe.db.set_value("Account", candidate, "account_type", "Equity", update_modified=False)
        else:
            parent = find_parent(company, root_type="Equity")
            ensure_account(company, "Capital Social", parent, account_type="Equity")

    # 2) Depreciación acumulada
    has_ad = frappe.db.get_value(
        "Account",
        {"company": company, "account_type": "Accumulated Depreciation", "is_group": 0},
        "name",
    )
    if not has_ad:
        parent = (
            find_parent(company, by_name="Activos Fijos")
            or find_parent(company, account_types=["Fixed Asset"], root_type="Asset")
            or find_parent(company, root_type="Asset")
        )
        ensure_account(company, "Depreciación Acumulada", parent, account_type="Accumulated Depreciation")
    ad_account = frappe.db.get_value(
        "Account",
        {"company": company, "account_type": "Accumulated Depreciation", "is_group": 0},
        "name",
    )
    if ad_account:
        frappe.db.set_value(
            "Company", company, "accumulated_depreciation_account", ad_account, update_modified=False
        )

    dep_expense = frappe.db.get_value(
        "Account", {"company": company, "account_type": "Depreciation", "is_group": 0}, "name"
    )
    if dep_expense:
        frappe.db.set_value(
            "Company", company, "depreciation_expense_account", dep_expense, update_modified=False
        )

    # 3) Cuenta de redondeo de verdad (el catálogo pone una provisión de crédito
    #    con account_type 'Round Off', que no es una cuenta de resultados).
    round_off = frappe.db.get_value(
        "Account",
        {"company": company, "account_name": "Ajustes por Redondeo", "is_group": 0},
        "name",
    )
    if not round_off:
        parent = (
            find_parent(company, by_name="Otros Gastos")
            or find_parent(company, by_name="Gastos Diversos")
            or find_parent(company, root_type="Expense")
        )
        round_off = ensure_account(company, "Ajustes por Redondeo", parent, account_type="Round Off")
    if round_off:
        frappe.db.set_value("Company", company, "round_off_account", round_off, update_modified=False)

    # 4) Cuentas de ingresos: el catálogo no les pone account_type
    income_leaves = frappe.get_all(
        "Account",
        filters={"company": company, "root_type": "Income", "is_group": 0, "account_type": ""},
        pluck="name",
        limit=5,
    )
    for acc in income_leaves:
        frappe.db.set_value("Account", acc, "account_type", "Income Account", update_modified=False)

    frappe.db.commit()


# --------------------------------------------------------------------------
# 4. Categorías de cuenta (motor NIIF de ERPNext v16)
# --------------------------------------------------------------------------

CATEGORY_BY_ACCOUNT_TYPE = {
    "Cash": "Cash and Cash Equivalents",
    "Bank": "Cash and Cash Equivalents",
    "Receivable": "Trade Receivables",
    "Payable": "Trade Payables",
    "Stock": "Stock Assets",
    "Stock Adjustment": "Cost of Goods Sold",
    "Cost of Goods Sold": "Cost of Goods Sold",
    "Expenses Included In Valuation": "Other Direct Costs",
    "Expenses Included In Asset Valuation": "Other Direct Costs",
    "Depreciation": "Operating Expenses",
    "Fixed Asset": "Tangible Assets",
    "Accumulated Depreciation": "Tangible Assets",
    "Capital Work in Progress": "Tangible Assets",
    "Round Off": "Operating Expenses",
    "Income Account": "Revenue from Operations",
    "Direct Income": "Revenue from Operations",
    "Indirect Income": "Other Operating Income",
    "Expense Account": "Operating Expenses",
    "Direct Expense": "Other Direct Costs",
    "Indirect Expense": "Operating Expenses",
}

CATEGORY_BY_ROOT = {
    "Income": "Revenue from Operations",
    "Expense": "Operating Expenses",
    "Equity": "Reserves and Surplus",
    "Asset": "Other Current Assets",
    "Liability": "Other Current Liabilities",
}


def assign_account_categories(company):
    categories = {
        d.name: (d.root_type or "")
        for d in frappe.get_all("Account Category", fields=["name", "root_type"])
    }
    if not categories:
        warn("No hay 'Account Category' definidas; se omite la categorización NIIF.")
        return 0

    accounts = frappe.get_all(
        "Account",
        filters={"company": company, "is_group": 0, "disabled": 0},
        fields=["name", "account_name", "account_type", "root_type", "account_category"],
    )

    assigned = 0
    for acc in accounts:
        if acc.account_category:
            continue

        name_low = (acc.account_name or "").lower()
        cat = None

        if acc.account_type == "Chargeable":
            cat = "Other Current Assets" if acc.root_type == "Asset" else "Other Payables"
        elif acc.root_type == "Equity":
            cat = "Share Capital" if ("capital" in name_low or "accion" in name_low) else "Reserves and Surplus"
        else:
            cat = CATEGORY_BY_ACCOUNT_TYPE.get(acc.account_type or "")

        if not cat:
            cat = CATEGORY_BY_ROOT.get(acc.root_type)

        if not cat or cat not in categories:
            continue
        # La categoría debe pertenecer al mismo root_type
        if categories[cat] and acc.root_type and categories[cat] != acc.root_type:
            continue

        frappe.db.set_value("Account", acc.name, "account_category", cat, update_modified=False)
        assigned += 1

    frappe.db.commit()
    log(f"  ✔ Categorías NIIF asignadas a {assigned} cuentas")
    return assigned


# --------------------------------------------------------------------------
# 5. Años fiscales
# --------------------------------------------------------------------------


def ensure_fiscal_years(company):
    from dateutil.relativedelta import relativedelta

    month = CFG["fy_start_month"] if 1 <= CFG["fy_start_month"] <= 12 else 1
    created = 0
    for raw in CFG["fiscal_years"]:
        try:
            year = int(raw)
        except ValueError:
            warn(f"Año fiscal inválido: {raw}")
            continue

        start = date(year, month, 1)
        end = start + relativedelta(years=1) - timedelta(days=1)
        name = str(year) if month == 1 else f"{year}-{year + 1}"

        if frappe.db.exists("Fiscal Year", name):
            continue

        doc = frappe.new_doc("Fiscal Year")
        doc.year = name
        doc.year_start_date = start
        doc.year_end_date = end
        doc.append("companies", {"company": company})
        doc.flags.ignore_permissions = True
        doc.insert()
        created += 1
        log(f"  + Año fiscal {name} ({start} → {end})")

    frappe.db.commit()
    if not created:
        log("  · Años fiscales ya existentes")


# --------------------------------------------------------------------------
# 6. Estado de Cambios en el Patrimonio Neto (plantilla propia)
# --------------------------------------------------------------------------


def _formula(obj):
    return json.dumps(obj, ensure_ascii=False)


def ecpn_rows():
    equity = ["root_type", "=", "Equity"]
    pnl = ["root_type", "in", ["Income", "Expense"]]

    def account_row(ref, display, balance_type, filters, **kw):
        row = {
            "reference_code": ref,
            "display_name": display,
            "indentation_level": kw.pop("indent", 1),
            "data_source": "Account Data",
            "balance_type": balance_type,
            "reverse_sign": kw.pop("reverse_sign", 1),
            "calculation_formula": _formula(filters),
        }
        row.update(kw)
        return row

    def calc_row(ref, display, formula, **kw):
        row = {
            "reference_code": ref,
            "display_name": display,
            "indentation_level": kw.pop("indent", 0),
            "data_source": "Calculated Amount",
            "calculation_formula": formula,
        }
        row.update(kw)
        return row

    def blank(display="", **kw):
        row = {"display_name": display, "indentation_level": 0, "data_source": "Blank Line"}
        row.update(kw)
        return row

    rows = [
        # ---- filas internas (no se muestran, alimentan las fórmulas) ----
        account_row("ECPN_EQ_OPEN", "Patrimonio al inicio (cuentas de patrimonio)", "Opening Balance", equity,
                    hidden_calculation=1),
        account_row("ECPN_EQ_CLOSE", "Patrimonio al cierre (cuentas de patrimonio)", "Closing Balance", equity,
                    hidden_calculation=1),
        account_row("ECPN_PL_OPEN", "Resultados anteriores no capitalizados", "Opening Balance", pnl,
                    hidden_calculation=1),
        account_row("ECPN_PL_CLOSE", "Resultados acumulados al cierre", "Closing Balance", pnl,
                    hidden_calculation=1),
        # ---- presentación ----
        blank("ESTADO DE CAMBIOS EN EL PATRIMONIO NETO", bold_text=1),
        blank(),
        blank("SALDO INICIAL", bold_text=1),
        calc_row("ECPN_INI_EQ", "Patrimonio al inicio del período", "ECPN_EQ_OPEN",
                 indent=1, hide_when_empty=1),
        calc_row("ECPN_INI_PL", "(+) Resultados de ejercicios anteriores no capitalizados", "ECPN_PL_OPEN",
                 indent=1, hide_when_empty=1),
        calc_row("ECPN_SALDO_INI", "= Saldo inicial total del patrimonio",
                 "ECPN_EQ_OPEN + ECPN_PL_OPEN", indent=1, bold_text=1),
        blank(),
        blank("VARIACIONES DEL PERÍODO", bold_text=1),
        calc_row("ECPN_VAR_EQ", "(+/-) Aportes, distribuciones y otras variaciones del patrimonio",
                 "ECPN_EQ_CLOSE - ECPN_EQ_OPEN", indent=1, hide_when_empty=1),
        calc_row("ECPN_VAR_RES", "(+/-) Resultado integral del ejercicio (utilidad / pérdida)",
                 "ECPN_PL_CLOSE - ECPN_PL_OPEN", indent=1, hide_when_empty=1),
        calc_row("ECPN_VAR_TOTAL", "= Total de variaciones del período",
                 "(ECPN_EQ_CLOSE - ECPN_EQ_OPEN) + (ECPN_PL_CLOSE - ECPN_PL_OPEN)", indent=1, bold_text=1),
        blank(),
        calc_row("ECPN_SALDO_FIN", "= SALDO FINAL DEL PATRIMONIO NETO",
                 "ECPN_SALDO_INI + ECPN_VAR_TOTAL", indent=0, bold_text=1),
        blank(),
        calc_row("ECPN_CUADRE", "Cuadre de control (debe ser 0)",
                 "ECPN_SALDO_FIN - (ECPN_EQ_CLOSE + ECPN_PL_CLOSE)", indent=0, italic_text=1,
                 hide_when_empty=1),
    ]
    return rows


def ensure_ecpn_template():
    payload = {
        "doctype": "Financial Report Template",
        "template_name": ECPN_TEMPLATE_NAME,
        "report_type": "Custom Financial Statement",
        "disabled": 0,
        "rows": ecpn_rows(),
    }

    if frappe.db.exists("Financial Report Template", ECPN_TEMPLATE_NAME):
        doc = frappe.get_doc("Financial Report Template", ECPN_TEMPLATE_NAME)
        doc.update(payload)
        doc.flags.ignore_permissions = True
        doc.save()
        log(f"· Plantilla actualizada: {ECPN_TEMPLATE_NAME}")
        return doc.name

    doc = frappe.get_doc(payload)
    doc.flags.ignore_permissions = True
    try:
        doc.insert()
    except Exception as exc:  # noqa: BLE001
        warn(f"Validación de la plantilla falló ({exc}); se inserta sin validar.")
        doc = frappe.get_doc(payload)
        doc.flags.ignore_permissions = True
        doc.flags.ignore_validate = True
        doc.insert()
    log(f"· Plantilla creada: {ECPN_TEMPLATE_NAME}")
    return doc.name


# --------------------------------------------------------------------------
# 6b. Reporte propio "Estado de Cambios en el Patrimonio Neto"
# --------------------------------------------------------------------------
# El ECPN no es un reporte estándar de ERPNext: se arma con la plantilla de
# arriba (reporte "Custom Financial Statement"). Para que además aparezca como
# un reporte propio en la lista y en el buscador, creamos aquí un Query Report
# (sólo SQL, se guarda en base de datos) que muestra las cuentas de patrimonio
# con su saldo inicial, los movimientos del período y el saldo final, más una
# fila con el resultado del ejercicio (utilidad / pérdida).

EQUITY_REPORT_COLUMNS = [
    {"fieldname": "cuenta", "label": "Concepto", "fieldtype": "Data", "width": 360},
    {"fieldname": "saldo_inicial", "label": "Saldo inicial", "fieldtype": "Currency", "width": 150},
    {"fieldname": "movimientos", "label": "Movimientos del período", "fieldtype": "Currency", "width": 190},
    {"fieldname": "saldo_final", "label": "Saldo final", "fieldtype": "Currency", "width": 150},
]

EQUITY_REPORT_QUERY = """
select t.cuenta, t.saldo_inicial, t.movimientos, t.saldo_final
from (
    select
        0 as orden,
        a.name as cuenta,
        sum(case when g.posting_date < %(from_date)s
                   or (g.is_opening = 'Yes' and g.posting_date <= %(to_date)s)
                 then g.credit - g.debit else 0 end) as saldo_inicial,
        sum(case when g.posting_date between %(from_date)s and %(to_date)s
                   and ifnull(g.is_opening, 'No') <> 'Yes'
                 then g.credit - g.debit else 0 end) as movimientos,
        sum(case when g.posting_date <= %(to_date)s
                 then g.credit - g.debit else 0 end) as saldo_final
    from `tabGL Entry` g
    inner join `tabAccount` a on a.name = g.account
    where g.company = %(company)s
      and ifnull(g.is_cancelled, 0) = 0
      and g.posting_date <= %(to_date)s
      and a.root_type = 'Equity'
      and a.is_group = 0
      and ifnull(a.disabled, 0) = 0
    group by a.name, a.account_number
    union all
    select
        1 as orden,
        'Resultado del ejercicio (utilidad / pérdida)' as cuenta,
        0 as saldo_inicial,
        sum(case when g.posting_date between %(from_date)s and %(to_date)s
                   and ifnull(g.is_opening, 'No') <> 'Yes'
                 then g.credit - g.debit else 0 end) as movimientos,
        sum(case when g.posting_date <= %(to_date)s
                 then g.credit - g.debit else 0 end) as saldo_final
    from `tabGL Entry` g
    inner join `tabAccount` a on a.name = g.account
    where g.company = %(company)s
      and ifnull(g.is_cancelled, 0) = 0
      and g.posting_date <= %(to_date)s
      and a.root_type in ('Income', 'Expense')
      and a.is_group = 0
      and ifnull(a.disabled, 0) = 0
) t
order by t.orden, t.cuenta
"""


def equity_report_filters(company):
    """Filtros del Query Report, con los valores por defecto del año fiscal."""
    start, end = None, None
    try:
        from erpnext.accounts.utils import get_fiscal_year

        fy = get_fiscal_year(date=date.today(), company=company, as_dict=True, raise_on_missing=False)
        if fy:
            start, end = fy["year_start_date"], fy["year_end_date"]
    except Exception:  # noqa: BLE001
        pass

    start = start or date(date.today().year, 1, 1)
    end = end or date(date.today().year, 12, 31)

    return [
        {
            "fieldname": "company",
            "label": "Empresa",
            "fieldtype": "Link",
            "options": "Company",
            "mandatory": 1,
            "default": company,
        },
        {"fieldname": "from_date", "label": "Desde", "fieldtype": "Date", "mandatory": 1, "default": str(start)},
        {"fieldname": "to_date", "label": "Hasta", "fieldtype": "Date", "mandatory": 1, "default": str(end)},
    ]


# --- Libro Diario (Guatemala) ---------------------------------------------
# Registro cronológico de las partidas: cada asiento lleva su folio, la fecha,
# el documento de origen y sus cuentas al Debe y al Haber.

LIBRO_DIARIO_COLUMNS = [
    {"fieldname": "folio", "label": "Folio", "fieldtype": "Int", "width": 70},
    {"fieldname": "fecha", "label": "Fecha", "fieldtype": "Date", "width": 100},
    {"fieldname": "documento", "label": "Documento", "fieldtype": "Data", "width": 200},
    {"fieldname": "codigo", "label": "Código", "fieldtype": "Data", "width": 110},
    {"fieldname": "cuenta", "label": "Cuenta", "fieldtype": "Data", "width": 260},
    {"fieldname": "descripcion", "label": "Descripción", "fieldtype": "Data", "width": 320},
    {"fieldname": "debe", "label": "Debe", "fieldtype": "Currency", "width": 130},
    {"fieldname": "haber", "label": "Haber", "fieldtype": "Currency", "width": 130},
]

LIBRO_DIARIO_QUERY = """
select t.folio, t.fecha, t.documento, t.codigo, t.cuenta, t.descripcion, t.debe, t.haber
from (
    select
        dense_rank() over (
            order by s.posting_date, s.voucher_creation, s.voucher_type, s.voucher_no
        ) as folio,
        s.posting_date,
        s.voucher_creation,
        s.voucher_type,
        s.voucher_no,
        s.line_creation,
        s.line_name,
        s.posting_date as fecha,
        s.documento,
        s.codigo,
        s.cuenta,
        s.descripcion,
        s.debe,
        s.haber
    from (
        select
            g.posting_date,
            g.voucher_type,
            g.voucher_no,
            g.creation as line_creation,
            g.name as line_name,
            min(g.creation) over (
                partition by g.posting_date, g.voucher_type, g.voucher_no
            ) as voucher_creation,
            concat(g.voucher_type, ' ', g.voucher_no) as documento,
            ifnull(a.account_number, '') as codigo,
            ifnull(a.account_name, g.account) as cuenta,
            ifnull(g.remarks, '') as descripcion,
            g.debit as debe,
            g.credit as haber
        from `tabGL Entry` g
        left join `tabAccount` a on a.name = g.account
        where g.company = %(company)s
          and ifnull(g.is_cancelled, 0) = 0
          and g.posting_date between %(from_date)s and %(to_date)s
    ) s
) t
order by t.posting_date, t.voucher_creation, t.voucher_type, t.voucher_no,
         t.line_creation, t.line_name
"""


# --- Libro Mayor (Guatemala) ----------------------------------------------
# Traslado de las partidas a cada cuenta, con el saldo corriente del período.

LIBRO_MAYOR_COLUMNS = [
    {"fieldname": "codigo", "label": "Código", "fieldtype": "Data", "width": 110},
    {"fieldname": "cuenta", "label": "Cuenta", "fieldtype": "Data", "width": 240},
    {"fieldname": "fecha", "label": "Fecha", "fieldtype": "Date", "width": 100},
    {"fieldname": "documento", "label": "Documento", "fieldtype": "Data", "width": 200},
    {"fieldname": "descripcion", "label": "Descripción", "fieldtype": "Data", "width": 300},
    {"fieldname": "debe", "label": "Debe", "fieldtype": "Currency", "width": 130},
    {"fieldname": "haber", "label": "Haber", "fieldtype": "Currency", "width": 130},
    {"fieldname": "saldo", "label": "Saldo del período", "fieldtype": "Currency", "width": 150},
]

LIBRO_MAYOR_QUERY = """
select t.codigo, t.cuenta, t.fecha, t.documento, t.descripcion, t.debe, t.haber, t.saldo
from (
    select
        g.account as cuenta_id,
        ifnull(a.account_number, '') as codigo,
        ifnull(a.account_name, g.account) as cuenta,
        g.posting_date as fecha,
        g.creation as orden_creacion,
        g.name as orden_nombre,
        concat(g.voucher_type, ' ', g.voucher_no) as documento,
        ifnull(g.remarks, '') as descripcion,
        g.debit as debe,
        g.credit as haber,
        sum(g.debit - g.credit) over (
            partition by g.account
            order by g.posting_date, g.creation, g.name
            rows between unbounded preceding and current row
        ) as saldo
    from `tabGL Entry` g
    left join `tabAccount` a on a.name = g.account
    where g.company = %(company)s
      and ifnull(g.is_cancelled, 0) = 0
      and g.posting_date between %(from_date)s and %(to_date)s
) t
order by t.codigo, t.cuenta, t.cuenta_id, t.fecha, t.orden_creacion, t.orden_nombre
"""


def libro_report_filters(company):
    """Mismos filtros (empresa + rango de fechas) que el resto de reportes."""
    return equity_report_filters(company)


def ensure_query_report(name, query, columns, filters, add_total_row=1):
    """Crea o actualiza un Query Report (sólo SQL, se guarda en base de datos)."""
    payload = {
        "ref_doctype": "GL Entry",
        "report_type": "Query Report",
        "is_standard": "No",
        "add_total_row": add_total_row,
        "disabled": 0,
        "query": query,
    }

    def _fill(doc):
        doc.set("columns", [])
        doc.set("filters", [])
        for column in columns:
            doc.append("columns", dict(column))
        for flt in filters:
            doc.append("filters", dict(flt))
        return doc

    if frappe.db.exists("Report", name):
        doc = _fill(frappe.get_doc("Report", name))
        doc.update(payload)
        doc.flags.ignore_permissions = True
        doc.save()
        log(f"· Reporte actualizado: {name}")
        return doc.name

    doc = _fill(frappe.get_doc({"doctype": "Report", "report_name": name, **payload}))
    doc.flags.ignore_permissions = True
    try:
        doc.insert()
    except Exception as exc:  # noqa: BLE001
        warn(f"Validación de '{name}' falló ({exc}); se inserta sin validar.")
        doc = _fill(frappe.get_doc({"doctype": "Report", "report_name": name, **payload}))
        doc.flags.ignore_permissions = True
        doc.flags.ignore_validate = True
        doc.insert()
    log(f"· Reporte creado: {name}")
    return doc.name


def ensure_equity_report(company):
    return ensure_query_report(
        EQUITY_REPORT_NAME,
        EQUITY_REPORT_QUERY,
        EQUITY_REPORT_COLUMNS,
        equity_report_filters(company),
    )


def ensure_libro_diario_report(company):
    # 'add_total_row' se omite: la primera columna es el folio (no tiene sentido sumarla).
    return ensure_query_report(
        LIBRO_DIARIO_REPORT_NAME,
        LIBRO_DIARIO_QUERY,
        LIBRO_DIARIO_COLUMNS,
        libro_report_filters(company),
        add_total_row=0,
    )


def ensure_libro_mayor_report(company):
    return ensure_query_report(
        LIBRO_MAYOR_REPORT_NAME,
        LIBRO_MAYOR_QUERY,
        LIBRO_MAYOR_COLUMNS,
        libro_report_filters(company),
    )


# Reportes dedicados que además se enlazan en el espacio y la barra lateral.
DEDICATED_REPORTS = [
    (EQUITY_REPORT_NAME, ensure_equity_report),
    (LIBRO_DIARIO_REPORT_NAME, ensure_libro_diario_report),
    (LIBRO_MAYOR_REPORT_NAME, ensure_libro_mayor_report),
]


def ensure_dedicated_reports(company):
    """Crea/actualiza los reportes dedicados, uno por uno y con commit propio."""
    created = []
    for name, builder in DEDICATED_REPORTS:
        try:
            created.append(builder(company))
        except Exception as exc:  # noqa: BLE001
            warn(f"No se pudo crear el reporte '{name}': {exc}")
            try:
                frappe.db.rollback()
            except Exception:  # noqa: BLE001
                pass
        frappe.db.commit()
    return created


# --------------------------------------------------------------------------
# 6c. Acceso directo en el espacio "Accounting"
# --------------------------------------------------------------------------
# Metemos los reportes dedicados (patrimonio, libro diario, libro mayor) en la
# tarjeta "Financial Statements" del espacio de Contabilidad y en la sección
# "Reports" de la barra lateral, para que queden a la vista sin buscarlos.

WORKSPACE_NAME = "Accounting"
WORKSPACE_CARD = "Financial Statements"

SIDEBAR_NAME = "Accounts"
SIDEBAR_SECTION = "Reports"


def _only_valid_fields(doctype, row):
    """Descarta campos que no existan en la versión instalada del doctype."""
    try:
        valid = {field.fieldname for field in frappe.get_meta(doctype).fields}
    except Exception:  # noqa: BLE001
        return row
    return {key: value for key, value in row.items() if key in valid}


def workspace_link_row(name):
    """Fila de acceso directo, sólo con los campos que existan en esta versión."""
    row = {
        "type": "Link",
        "label": name,
        "link_type": "Report",
        "link_to": name,
        "is_query_report": 1,
        "onboard": 0,
        "hidden": 0,
        "link_count": 0,
        "report_ref_doctype": "GL Entry",
    }
    return _only_valid_fields("Workspace Link", row)


def ensure_workspace_links(names):
    if not frappe.db.exists("Workspace", WORKSPACE_NAME):
        warn(f"No existe el espacio '{WORKSPACE_NAME}'; se omite el acceso directo.")
        return None

    try:
        doc = frappe.get_doc("Workspace", WORKSPACE_NAME)
        links = doc.get("links") or []

        present = {link.link_to for link in links if link.link_type == "Report"}
        pending = [name for name in names if name not in present]
        if not pending:
            log("· Accesos directos ya presentes en el espacio Accounting")
            return doc.name

        # Localizar el final de la tarjeta destino.
        card_idx, insert_at = None, None
        for i, link in enumerate(links):
            if link.type == "Card Break":
                if card_idx is not None:
                    break
                if (link.label or "").strip() == WORKSPACE_CARD:
                    card_idx, insert_at = i, i + 1
            elif card_idx is not None:
                insert_at = i + 1

        if insert_at is None:
            warn(f"No se encontró la tarjeta '{WORKSPACE_CARD}'; se agregan al final.")
            insert_at = len(links)

        for offset, name in enumerate(pending):
            doc.append("links", workspace_link_row(name))
            new_row = doc.get("links").pop()
            doc.get("links").insert(insert_at + offset, new_row)
        for i, link in enumerate(doc.get("links"), start=1):
            link.idx = i

        if card_idx is not None:
            doc.get("links")[card_idx].link_count = (
                doc.get("links")[card_idx].link_count or 0
            ) + len(pending)

        doc.flags.ignore_permissions = True
        doc.save()
        for name in pending:
            log(f"· Acceso directo agregado en Accounting > {WORKSPACE_CARD}: {name}")
        return doc.name
    except Exception as exc:  # noqa: BLE001
        warn(f"No se pudo agregar el acceso directo en el espacio Accounting: {exc}")
        try:
            frappe.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


# --------------------------------------------------------------------------
# 6d. Acceso directo en la barra lateral de Contabilidad
# --------------------------------------------------------------------------


def sidebar_item_row(name):
    row = {
        "type": "Link",
        "label": name,
        "link_type": "Report",
        "link_to": name,
        "child": 1,
        "collapsible": 0,
        "indent": 0,
        "hidden": 0,
        "open_in_new_tab": 0,
        "show_arrow": 0,
    }
    return _only_valid_fields("Sidebar Item", row)


def ensure_sidebar_items(names):
    """Agrega los reportes a la sección 'Reportes' de la barra lateral de Accounts.

    Es 'best effort': si la versión instalada no tiene el doctype Sidebar, o el sitio
    bloquea la edición directa de barras laterales estándar, se avisa y se continúa.
    """
    try:
        if not frappe.db.exists("DocType", "Sidebar"):
            return None
        if not frappe.db.exists("Sidebar", SIDEBAR_NAME):
            warn(f"No existe la barra lateral '{SIDEBAR_NAME}'; se omite el acceso directo.")
            return None

        doc = frappe.get_doc("Sidebar", SIDEBAR_NAME)
        items = doc.get("items") or []

        present = {item.link_to for item in items if item.link_type == "Report"}
        pending = [name for name in names if name not in present]
        if not pending:
            log("· Reportes ya presentes en la barra lateral de Contabilidad")
            return doc.name

        section_idx, insert_at = None, None
        for i, item in enumerate(items):
            if item.type == "Section Break":
                if section_idx is not None:
                    break
                if (item.label or "").strip() == SIDEBAR_SECTION:
                    section_idx, insert_at = i, i + 1
            elif section_idx is not None:
                insert_at = i + 1

        if insert_at is None:
            warn(f"No se encontró la sección '{SIDEBAR_SECTION}'; se agregan al final.")
            insert_at = len(items)

        for offset, name in enumerate(pending):
            doc.append("items", sidebar_item_row(name))
            new_row = doc.get("items").pop()
            doc.get("items").insert(insert_at + offset, new_row)
        for i, item in enumerate(doc.get("items"), start=1):
            item.idx = i

        doc.flags.ignore_permissions = True
        # Las barras laterales estándar sólo se dejan editar en modo desarrollador o
        # durante install/migrate/patch; usamos la bandera 'in_patch' para esta escritura.
        previous = frappe.flags.get("in_patch")
        frappe.flags.in_patch = True
        try:
            doc.save()
        finally:
            frappe.flags.in_patch = previous

        for name in pending:
            log(f"· Acceso directo agregado en la barra lateral de Contabilidad > {SIDEBAR_SECTION}: {name}")
        return doc.name
    except Exception as exc:  # noqa: BLE001
        warn(f"No se pudo agregar los reportes a la barra lateral: {exc}")
        try:
            frappe.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


# --------------------------------------------------------------------------
# 7. Verificación
# --------------------------------------------------------------------------


def verify_reports():
    missing = []
    for report, label in FINANCIAL_REPORTS:
        if not frappe.db.exists("Report", report):
            missing.append(report)
    if missing:
        warn(f"Reportes no encontrados: {', '.join(missing)}")
    else:
        log(f"· {len(FINANCIAL_REPORTS)} reportes verificados correctamente")
    return missing


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main():
    frappe.flags.ignore_permissions = True
    print("=" * 78)
    print(" CONFIGURACIÓN CONTABLE - ERPNext")
    print("=" * 78)
    log(f"Sitio: {frappe.local.site}")
    log(f"País: {CFG['country']} · Moneda: {CFG['currency']}")

    company = find_company()
    if company:
        log(f"· Empresa: {check_company_basics(company)}")

    ensure_erpnext_master_data(company)

    if company:
        fix_equity_root_type(company)
        ensure_helper_accounts(company)
        assign_account_categories(company)
        set_company_defaults(company)
        ensure_fiscal_years(company)
    else:
        warn("Todavía no hay ninguna empresa en el sitio.")

    ensure_ecpn_template()
    frappe.db.commit()

    # Los reportes valen para cualquier empresa; si aún no hay, el filtro queda
    # vacío y se completa al volver a ejecutar este script.
    ensure_dedicated_reports(company or "")
    frappe.db.commit()

    report_names = [name for name, _ in DEDICATED_REPORTS]
    ensure_workspace_links(report_names)
    frappe.db.commit()
    ensure_sidebar_items(report_names)
    verify_reports()

    frappe.db.commit()
    frappe.clear_cache()

    print("-" * 78)
    if company:
        print(f" Cuentas totales : {frappe.db.count('Account', {'company': company})}")
        print(
            f" Años fiscales   : "
            f"{', '.join(frappe.get_all('Fiscal Year', pluck='name', order_by='name'))}"
        )
    else:
        print(" Cuentas totales : (sin empresa todavía)")
    print("-" * 78)
    print()
    print(" Estado                              | Reporte en ERPNext")
    print(" ------------------------------------+-----------------------------------------")
    for report, titulo in FINANCIAL_REPORTS:
        print(f" {titulo[:35]:<35} | {report}")
    print()
    print(f"Plantilla ECPN: {ECPN_TEMPLATE_NAME}")

    if not company:
        print()
        print("=" * 78)
        print(" FALTA CREAR LA EMPRESA (el sitio quedó limpio a propósito)")
        print("=" * 78)
        print(" 1) Abre el navegador en el sitio y entra como Administrator.")
        print(" 2) Completa el asistente con tus datos reales:")
        print(f"      · País              : {CFG['country']}")
        print(f"      · Moneda            : {CFG['currency']}")
        print("      · Plan de cuentas   : Guatemala - Cuentas")
        print(" 3) Vuelve a la terminal y ejecuta:")
        print("      ./install.sh contabilidad")
        print("=" * 78)

    print(f"{SENTINEL} {'company_configured' if company else 'no_company'}")
    return 0


if __name__ == "__main__":
    try:
        _rc = main()
    except Exception as _exc:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        try:
            frappe.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        print(f"ERROR: {_exc}")
        raise SystemExit(1)
