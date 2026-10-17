#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
estados_financieros.py
======================
Genera el paquete completo de estados financieros de una empresa ERPNext y lo
exporta a HTML / CSV / XLSX en un solo paso:

    01  Balance General                    (Estado de Situación Financiera)
    02  Estado de Resultados               (Pérdidas y Ganancias)
    03  Balance Financiero                 (Balanza de Comprobación)
    04  Estado de Flujo de Efectivo
    05  Estado de Cambios en el Patrimonio Neto  (formato matricial NIC 1)
    05b Estado de Cambios en el Patrimonio Neto  (plantilla nativa ERPNext)
    06  Libro Diario                       (formato Guatemala, partidas con folio)
    07  Libro Mayor                        (formato Guatemala, saldo corriente)

Uso (lo hace 'install.sh reports'):

    docker compose exec -T backend bench --site <sitio> console \
        < scripts/estados_financieros.py

Parámetros por variables de entorno:
    EF_SITE, EF_COMPANY, EF_FISCAL_YEAR, EF_OUTDIR, LD_FOLIO_INICIO
"""

import csv
import html
import os
import sys
from datetime import date

# --------------------------------------------------------------------------
# Bootstrap
# --------------------------------------------------------------------------


def _bootstrap():
    import frappe

    already = getattr(frappe.local, "site", None) and getattr(frappe.local, "db", None)
    if already:
        return frappe

    site = os.environ.get("EF_SITE") or os.environ.get("ERP_SITE") or (
        sys.argv[1] if len(sys.argv) > 1 else None
    )
    sites_path = os.environ.get("ERP_SITES_PATH", "/home/frappe/frappe-bench/sites")
    frappe.init(site=site, sites_path=sites_path)
    frappe.connect()
    return frappe


frappe = _bootstrap()

from frappe.utils import add_days, cstr, flt, getdate  # noqa: E402

frappe.set_user("Administrator")
frappe.flags.ignore_permissions = True

SENTINEL = "ERP_FINANCIAL_STATEMENTS_OK"
OUTDIR = os.environ.get("EF_OUTDIR") or "/home/frappe/frappe-bench/sites/_estados_financieros"

# Rellenados en main(); usados por _emit() para el encabezado de cada archivo.
SUBTITLE = ""


# --------------------------------------------------------------------------
# Contexto (empresa y ejercicio)
# --------------------------------------------------------------------------


def resolve_company():
    name = os.environ.get("EF_COMPANY")
    if name and frappe.db.exists("Company", name):
        return name
    if name:
        found = frappe.db.get_value("Company", {"company_name": name}, "name")
        if found:
            return found
    name = frappe.defaults.get_global_default("company")
    if name and frappe.db.exists("Company", name):
        return name
    companies = frappe.get_all("Company", pluck="name", limit=1)
    if not companies:
        raise SystemExit(
            "No hay ninguna empresa todavía.\n"
            "  1) Abre el navegador en el sitio y crea tu empresa con el asistente\n"
            "     (País: Guatemala, Moneda: GTQ, plan: Guatemala - Cuentas).\n"
            "  2) Ejecuta:  ./install.sh contabilidad\n"
            "  3) Vuelve a intentar:  ./install.sh reports"
        )
    return companies[0]


def resolve_fiscal_year(company, label=None):
    from erpnext.accounts.utils import get_fiscal_year

    fy = None
    if label:
        fy = get_fiscal_year(
            fiscal_year=label, company=company, as_dict=True, raise_on_missing=False
        )
    if not fy:
        fy = get_fiscal_year(
            date=date.today(), company=company, as_dict=True, raise_on_missing=False
        )
    if not fy:
        fys = frappe.get_all(
            "Fiscal Year",
            fields=["name", "year_start_date", "year_end_date"],
            order_by="year_start_date desc",
            limit=1,
        )
        if not fys:
            raise SystemExit("No hay años fiscales definidos. Ejecuta setup_accounting.py.")
        fy = frappe._dict(fys[0])
    return fy


def d2s(value):
    return getdate(value).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# Ejecución de reportes
# --------------------------------------------------------------------------


def run_report(report_name, filters):
    from frappe.desk.query_report import run

    out = run(report_name, filters=dict(filters))
    if not isinstance(out, dict):
        return [], []
    return out.get("columns") or [], out.get("result") or []


def fin_filters(company, from_date, to_date, fy, **extra):
    filters = frappe._dict(
        {
            "company": company,
            "filter_based_on": "Date Range",
            "period_start_date": d2s(from_date),
            "period_end_date": d2s(to_date),
            "from_fiscal_year": fy,
            "to_fiscal_year": fy,
            "periodicity": "Yearly",
            "accumulated_values": 1,
            "include_default_book_entries": 1,
            "selected_view": "Report",
            "show_zero_values": 1,
            "show_account_details": "Summary",
        }
    )
    filters.update(extra)
    return filters


# --------------------------------------------------------------------------
# Exportación
# --------------------------------------------------------------------------


def fmt_value(value, column):
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, (int, float)):
        fieldtype = (column or {}).get("fieldtype")
        if fieldtype == "Int":
            return str(int(flt(value, 0)))
        if fieldtype == "Percent":
            return f"{flt(value, 2):.2f}%"
        return f"{flt(value, 2):,.2f}"
    return cstr(value)


def write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([c.get("label") or c.get("fieldname") for c in columns])
        for row in rows:
            writer.writerow([fmt_value(row.get(c.get("fieldname")), c) for c in columns])


def write_html(path, title, subtitle, columns, rows, note=""):
    heads = "".join(
        f"<th>{html.escape(cstr(c.get('label') or c.get('fieldname')))}</th>" for c in columns
    )
    body = []
    for row in rows:
        cells = []
        for idx, col in enumerate(columns):
            value = row.get(col.get("fieldname"))
            text = fmt_value(value, col)
            cls = ""
            if isinstance(value, (int, float)) and not isinstance(value, bool) and flt(value) < 0:
                cls = ' class="neg"'
            if idx == 0:
                cells.append(f"<td{cls}>{html.escape(text)}</td>")
            else:
                cells.append(f'<td class="num"{cls}>{html.escape(text)}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")

    doc = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
 body {{ font-family: -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; margin:32px; color:#1f272e; }}
 h1 {{ font-size:20px; margin:0 0 4px; }}
 .sub {{ color:#687178; font-size:13px; margin-bottom:18px; }}
 table {{ border-collapse:collapse; width:100%; font-size:13px; }}
 th,td {{ border-bottom:1px solid #e2e8ed; padding:7px 10px; }}
 th {{ background:#f6f8fa; text-align:left; font-weight:600; }}
 td.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
 tr:hover td {{ background:#fafbfc; }}
 .neg {{ color:#b4302a; }}
 .note {{ margin-top:18px; color:#687178; font-size:12px; }}
</style></head><body>
<h1>{html.escape(title)}</h1>
<div class="sub">{html.escape(subtitle)}</div>
<table><thead><tr>{heads}</tr></thead><tbody>{''.join(body)}</tbody></table>
<div class="note">{html.escape(note)}</div>
</body></html>"""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(doc)


def write_xlsx(path, sheets):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except Exception:  # noqa: BLE001
        return False

    workbook = Workbook()
    workbook.remove(workbook.active)
    head_fill = PatternFill("solid", fgColor="F6F8FA")
    for name, columns, rows in sheets:
        sheet = workbook.create_sheet(title=name[:31])
        sheet.append([c.get("label") or c.get("fieldname") for c in columns])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = head_fill
        for row in rows:
            sheet.append([row.get(c.get("fieldname")) for c in columns])
        for idx, col in enumerate(columns, start=1):
            if col.get("fieldtype") in ("Currency", "Float", "Int", "Percent"):
                for column_cells in sheet.iter_cols(min_col=idx, max_col=idx, min_row=2):
                    for cell in column_cells:
                        if type(cell.value) in (int, float):
                            cell.number_format = "#,##0.00"
                            cell.alignment = Alignment(horizontal="right")
        sheet.column_dimensions["A"].width = 52
        for idx in range(2, len(columns) + 1):
            sheet.column_dimensions[sheet.cell(row=1, column=idx).column_letter].width = 18
    workbook.save(path)
    return True


# --------------------------------------------------------------------------
# Estado de Cambios en el Patrimonio (matriz por cuenta) - NIC 1
# --------------------------------------------------------------------------


def _balances(company, accounts, date_from=None, date_to=None):
    """Saldo (crédito - débito) por cuenta. Positivo = saldo acreedor."""
    if not accounts:
        return {}
    where = "company=%(company)s and is_cancelled=0 and account in %(accounts)s"
    params = {"company": company, "accounts": tuple(accounts)}
    if date_from and date_to:
        where += " and posting_date between %(from)s and %(to)s"
        params["from"] = d2s(date_from)
        params["to"] = d2s(date_to)
    elif date_to:
        where += " and posting_date <= %(to)s"
        params["to"] = d2s(date_to)
    rows = frappe.db.sql(
        f"""select account, sum(debit) as debit, sum(credit) as credit
            from `tabGL Entry` where {where} group by account""",
        params,
        as_dict=True,
    )
    return {r.account: flt(r.credit) - flt(r.debit) for r in rows}


def _root_balances(company, as_of):
    """Saldo (débito - crédito) acumulado por naturaleza (root_type)."""
    rows = frappe.db.sql(
        """select root_type, sum(debit) - sum(credit) as bal
           from `tabGL Entry`
           where company=%s and is_cancelled=0 and posting_date <= %s
           group by root_type""",
        (company, d2s(as_of)),
        as_dict=True,
    )
    return {r.root_type: flt(r.bal) for r in rows}


def accounting_check(company, as_of):
    """Cuadre contable real: A + G = P + PN + I  (en términos débito-crédito).

    Suma algebraica de todos los movimientos por naturaleza. Si las partidas
    están correctamente clasificadas y el libro cuadra, el resultado es 0.
    """
    bal = _root_balances(company, as_of)
    return sum(bal.values())


def equity_statement(company, from_date, to_date):
    """Devuelve (columns, rows, resultado) con el ECPN matricial (NIC 1)."""
    accounts = frappe.db.sql(
        """select name, account_name, account_number from `tabAccount`
           where company=%s and root_type='Equity' and is_group=0 and disabled=0
           order by ifnull(account_number,''), account_name""",
        company,
        as_dict=True,
    )
    pl_accounts = frappe.db.sql_list(
        """select name from `tabAccount`
           where company=%s and root_type in ('Income','Expense') and is_group=0 and disabled=0""",
        company,
    )

    names = [a.name for a in accounts]
    opening_date = add_days(d2s(from_date), -1)
    opening = _balances(company, names, date_to=opening_date)
    movement = _balances(company, names, date_from=from_date, date_to=to_date)
    pl_movement = _balances(company, pl_accounts, date_from=from_date, date_to=to_date)

    resultado = sum(pl_movement.values())

    columns = [{"fieldname": "concepto", "label": "Concepto", "fieldtype": "Data", "width": 320}]
    for acc in accounts:
        columns.append(
            {
                "fieldname": f"acc_{acc.name}",
                "label": (f"{acc.account_number} " if acc.account_number else "")
                + (acc.account_name or acc.name),
                "fieldtype": "Currency",
                "width": 160,
            }
        )
    columns.append(
        {"fieldname": "resultado", "label": "Resultado del Ejercicio", "fieldtype": "Currency", "width": 170}
    )
    columns.append(
        {"fieldname": "total", "label": "TOTAL PATRIMONIO", "fieldtype": "Currency", "width": 180}
    )

    def total_of(source):
        return sum(source.get(a.name, 0.0) for a in accounts)

    rows = []
    # Saldo inicial
    row = {"concepto": "Saldo inicial del patrimonio", "resultado": 0.0}
    for acc in accounts:
        row[f"acc_{acc.name}"] = opening.get(acc.name, 0.0)
    row["total"] = total_of(opening)
    rows.append(row)

    # Movimientos del período
    row = {"concepto": "Movimientos del período (aportes, reservas, distribuciones)", "resultado": resultado}
    for acc in accounts:
        row[f"acc_{acc.name}"] = movement.get(acc.name, 0.0)
    row["total"] = total_of(movement) + resultado
    rows.append(row)

    # Saldo final
    row = {"concepto": "SALDO FINAL DEL PATRIMONIO NETO", "resultado": resultado}
    for acc in accounts:
        row[f"acc_{acc.name}"] = opening.get(acc.name, 0.0) + movement.get(acc.name, 0.0)
    row["total"] = total_of(opening) + total_of(movement) + resultado
    rows.append(row)

    return columns, rows, resultado


# --------------------------------------------------------------------------
# Libro Diario y Libro Mayor (formato Guatemala)
# --------------------------------------------------------------------------
# En Guatemala el Libro Diario es el registro cronológico de las partidas
# (asientos) con sus cuentas al Debe y al Haber, numeradas por folio y con la
# leyenda "Sumas iguales" en cada partida. El Libro Mayor es el traslado de esas
# partidas a cada cuenta, con su saldo corriente.

LD_COLUMNS = [
    {"fieldname": "folio", "label": "Folio", "fieldtype": "Int", "width": 70},
    {"fieldname": "fecha", "label": "Fecha", "fieldtype": "Data", "width": 100},
    {"fieldname": "documento", "label": "Documento", "fieldtype": "Data", "width": 210},
    {"fieldname": "codigo", "label": "Código", "fieldtype": "Data", "width": 110},
    {"fieldname": "cuenta", "label": "Cuenta", "fieldtype": "Data", "width": 260},
    {"fieldname": "descripcion", "label": "Descripción", "fieldtype": "Data", "width": 320},
    {"fieldname": "debe", "label": "Debe", "fieldtype": "Currency", "width": 130},
    {"fieldname": "haber", "label": "Haber", "fieldtype": "Currency", "width": 130},
]

LM_COLUMNS = [
    {"fieldname": "codigo", "label": "Código", "fieldtype": "Data", "width": 110},
    {"fieldname": "cuenta", "label": "Cuenta", "fieldtype": "Data", "width": 240},
    {"fieldname": "fecha", "label": "Fecha", "fieldtype": "Data", "width": 100},
    {"fieldname": "documento", "label": "Documento", "fieldtype": "Data", "width": 200},
    {"fieldname": "descripcion", "label": "Descripción", "fieldtype": "Data", "width": 300},
    {"fieldname": "debe", "label": "Debe", "fieldtype": "Currency", "width": 130},
    {"fieldname": "haber", "label": "Haber", "fieldtype": "Currency", "width": 130},
    {"fieldname": "saldo", "label": "Saldo", "fieldtype": "Currency", "width": 130},
]

_LIBRO_CSS = """
 body { font-family: -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; margin:28px; color:#1f272e; }
 h1 { font-size:20px; margin:0 0 2px; text-align:center; letter-spacing:.06em; }
 h2 { font-size:15px; margin:16px 0 6px; }
 .ident { text-align:center; font-size:13px; color:#333; line-height:1.5; margin-bottom:14px; }
 .ident b { font-size:15px; }
 .period { text-align:center; font-size:13px; color:#687178; margin-bottom:18px; }
 .asiento { margin:0 0 14px; page-break-inside:avoid; }
 .ahead { display:flex; gap:14px; flex-wrap:wrap; align-items:baseline; background:#f6f8fa;
          border:1px solid #e2e8ed; border-bottom:none; padding:6px 10px; font-size:12.5px; }
 .ahead .folio { font-weight:700; }
 table { border-collapse:collapse; width:100%; font-size:12.5px; }
 th,td { border:1px solid #e2e8ed; padding:5px 8px; }
 th { background:#fafbfc; text-align:left; font-weight:600; }
 td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
 td.cod { width:110px; color:#4c5560; }
 tfoot td { font-weight:600; background:#fcfdfe; }
 .totales { margin-top:18px; }
 .totales th, .totales td { font-size:13px; }
 .note { margin-top:16px; color:#687178; font-size:11.5px; }
 .acc-head { background:#f2f5f7; font-weight:600; }
 @media print { body { margin:12mm; } .asiento { page-break-inside:avoid; } }
"""


def company_identity(company):
    info = frappe.db.get_value(
        "Company", company, ["company_name", "tax_id", "default_currency"], as_dict=True
    ) or frappe._dict()
    return {
        "name": info.get("company_name") or company,
        "tax_id": info.get("tax_id") or "",
        "currency": info.get("default_currency") or "",
    }


def _gl_rows(company, from_date, to_date):
    return frappe.db.sql(
        """
        select
            g.posting_date,
            g.voucher_type,
            g.voucher_no,
            g.account,
            ifnull(a.account_number, '') as account_number,
            ifnull(a.account_name, g.account) as account_name,
            ifnull(a.root_type, '') as root_type,
            ifnull(g.remarks, '') as remarks,
            ifnull(g.is_opening, 'No') as is_opening,
            g.debit,
            g.credit
        from `tabGL Entry` g
        left join `tabAccount` a on a.name = g.account
        where g.company = %(company)s
          and ifnull(g.is_cancelled, 0) = 0
          and g.posting_date between %(from_date)s and %(to_date)s
        order by g.posting_date, g.creation, g.name
        """,
        {"company": company, "from_date": d2s(from_date), "to_date": d2s(to_date)},
        as_dict=True,
    )


# -------------------------------- Libro Diario ----------------------------


def build_libro_diario(company, from_date, to_date, folio_inicio=1):
    """Agrupa los movimientos en partidas (asientos) cronológicas y las numera.

    Se recorre el libro mayor en orden cronológico y se agrupa por documento de
    origen. Si por alguna razón las líneas de un mismo documento no quedaran
    juntas, el diccionario las vuelve a unir sin perder el orden de aparición.
    """
    asientos = {}
    for row in _gl_rows(company, from_date, to_date):
        key = (row.posting_date, row.voucher_type, row.voucher_no)
        asiento = asientos.get(key)
        if asiento is None:
            asiento = asientos[key] = {
                "key": key,
                "fecha": row.posting_date,
                "voucher_type": row.voucher_type,
                "voucher_no": row.voucher_no,
                "lines": [],
                "debe": 0.0,
                "haber": 0.0,
            }
        asiento["lines"].append(row)
        asiento["debe"] += flt(row.debit)
        asiento["haber"] += flt(row.credit)

    # Los dict conservan el orden de inserción: las partidas quedan en el orden
    # cronológico en que se registraron (igual que el reporte de ERPNext).
    ordered = list(asientos.values())
    for i, asiento in enumerate(ordered, start=folio_inicio):
        asiento["folio"] = i
    return ordered


def libro_diario_flat(asientos):
    out = []
    for asiento in asientos:
        doc = f"{asiento['voucher_type']} {asiento['voucher_no']}".strip()
        fecha = getdate(asiento["fecha"]).strftime("%d/%m/%Y")
        for row in asiento["lines"]:
            out.append(
                {
                    "folio": asiento["folio"],
                    "fecha": fecha,
                    "documento": doc,
                    "codigo": row.account_number,
                    "cuenta": row.account_name,
                    "descripcion": row.remarks,
                    "debe": flt(row.debit),
                    "haber": flt(row.credit),
                }
            )
    return out


def write_libro_diario_html(path, company, from_date, to_date, asientos):
    ident = company_identity(company)
    nit = f" · NIT: {html.escape(cstr(ident['tax_id']))}" if ident["tax_id"] else ""
    blocks = []
    total_debe = total_haber = 0.0
    for asiento in asientos:
        lines = "".join(
            "<tr>"
            f'<td class="cod">{html.escape(cstr(r.account_number))}</td>'
            f"<td>{html.escape(cstr(r.account_name))}</td>"
            f"<td>{html.escape(cstr(r.remarks))}</td>"
            f'<td class="num">{flt(r.debit):,.2f}</td>'
            f'<td class="num">{flt(r.credit):,.2f}</td>'
            "</tr>"
            for r in asiento["lines"]
        )
        total_debe += asiento["debe"]
        total_haber += asiento["haber"]
        blocks.append(
            f"""<div class="asiento">
 <div class="ahead">
   <span class="folio">Folio {asiento['folio']}</span>
   <span><b>Asiento No. {asiento['folio']}</b></span>
   <span>Fecha: {getdate(asiento['fecha']).strftime('%d/%m/%Y')}</span>
   <span>Documento: {html.escape(cstr(asiento['voucher_type']))} {html.escape(cstr(asiento['voucher_no']))}</span>
 </div>
 <table>
  <thead><tr><th>Código</th><th>Cuenta</th><th>Descripción</th><th class="num">Debe</th><th class="num">Haber</th></tr></thead>
  <tbody>{lines}</tbody>
  <tfoot><tr><td colspan="3">Sumas iguales</td>
    <td class="num">{asiento['debe']:,.2f}</td><td class="num">{asiento['haber']:,.2f}</td></tr></tfoot>
 </table>
</div>"""
        )

    cuadre = total_debe - total_haber
    estado = "CUADRA" if abs(cuadre) < 0.01 else "NO CUADRA"
    doc = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Libro Diario</title>
<style>{_LIBRO_CSS}</style></head><body>
<h1>LIBRO DIARIO</h1>
<div class="ident">
 <b>{html.escape(cstr(ident['name']))}</b>{nit}<br>
 Moneda: {html.escape(cstr(ident['currency']))}
</div>
<div class="period">Del {getdate(from_date).strftime('%d/%m/%Y')} al {getdate(to_date).strftime('%d/%m/%Y')}
 · {len(asientos)} partidas</div>
{''.join(blocks)}
<table class="totales">
 <thead><tr><th colspan="3">TOTALES DEL PERÍODO</th><th class="num">Debe</th><th class="num">Haber</th></tr></thead>
 <tbody><tr><td colspan="3">Sumas iguales del libro ({estado})</td>
   <td class="num">{total_debe:,.2f}</td><td class="num">{total_haber:,.2f}</td></tr></tbody>
</table>
<div class="note">Generado automáticamente por scripts/estados_financieros.py ·
 Diferencia Debe - Haber: {cuadre:,.2f}</div>
</body></html>"""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(doc)


# -------------------------------- Libro Mayor -----------------------------


def _opening_by_account(company, from_date):
    rows = frappe.db.sql(
        """select g.account, sum(g.debit) - sum(g.credit) as bal
           from `tabGL Entry` g
           where g.company = %(company)s and ifnull(g.is_cancelled, 0) = 0
             and g.posting_date < %(from_date)s
           group by g.account""",
        {"company": company, "from_date": d2s(from_date)},
        as_dict=True,
    )
    return {r.account: flt(r.bal) for r in rows}


def build_libro_mayor(company, from_date, to_date):
    """Traslada las partidas a cada cuenta, con saldo inicial, movimientos y saldo final."""
    opening = _opening_by_account(company, from_date)
    accounts = {}
    for row in _gl_rows(company, from_date, to_date):
        acc = accounts.get(row.account)
        if acc is None:
            acc = accounts[row.account] = {
                "account": row.account,
                "account_number": row.account_number,
                "account_name": row.account_name,
                "root_type": row.root_type,
                "lines": [],
                "debe": 0.0,
                "haber": 0.0,
            }
        acc["lines"].append(row)
        acc["debe"] += flt(row.debit)
        acc["haber"] += flt(row.credit)

    for account, saldo in opening.items():
        if account in accounts or abs(flt(saldo)) < 0.005:
            continue
        info = frappe.db.get_value(
            "Account", account, ["account_number", "account_name", "root_type"], as_dict=True
        ) or frappe._dict()
        accounts[account] = {
            "account": account,
            "account_number": info.get("account_number") or "",
            "account_name": info.get("account_name") or account,
            "root_type": info.get("root_type") or "",
            "lines": [],
            "debe": 0.0,
            "haber": 0.0,
        }

    result = []
    for account in sorted(
        accounts, key=lambda a: (accounts[a]["account_number"] or "", accounts[a]["account_name"] or "")
    ):
        acc = accounts[account]
        running = acc["saldo_inicial"] = flt(opening.get(account, 0.0))
        for row in acc["lines"]:
            running += flt(row.debit) - flt(row.credit)
            row["saldo"] = running
        acc["saldo_final"] = running
        result.append(acc)
    return result


def libro_mayor_flat(accounts):
    out = []
    for acc in accounts:
        base = {
            "codigo": acc["account_number"],
            "cuenta": acc["account_name"],
        }
        out.append({**base, "fecha": "", "documento": "", "descripcion": "Saldo inicial",
                    "debe": "", "haber": "", "saldo": acc["saldo_inicial"]})
        for row in acc["lines"]:
            out.append(
                {
                    **base,
                    "fecha": getdate(row.posting_date).strftime("%d/%m/%Y"),
                    "documento": f"{row.voucher_type} {row.voucher_no}".strip(),
                    "descripcion": row.remarks,
                    "debe": flt(row.debit),
                    "haber": flt(row.credit),
                    "saldo": row.saldo,
                }
            )
        out.append({**base, "fecha": "", "documento": "", "descripcion": "Totales del período",
                    "debe": acc["debe"], "haber": acc["haber"], "saldo": acc["saldo_final"]})
    return out


def write_libro_mayor_html(path, company, from_date, to_date, accounts):
    ident = company_identity(company)
    nit = f" · NIT: {html.escape(cstr(ident['tax_id']))}" if ident["tax_id"] else ""
    blocks = []
    tot_debe = tot_haber = 0.0
    for acc in accounts:
        rows = [
            "<tr>"
            '<td colspan="3" class="acc-head">Saldo inicial</td>'
            f'<td class="num"></td><td class="num"></td>'
            f'<td class="num">{acc["saldo_inicial"]:,.2f}</td>'
            "</tr>"
        ]
        for row in acc["lines"]:
            rows.append(
                "<tr>"
                f'<td>{getdate(row.posting_date).strftime("%d/%m/%Y")}</td>'
                f'<td>{html.escape(cstr(row.voucher_type))} {html.escape(cstr(row.voucher_no))}</td>'
                f"<td>{html.escape(cstr(row.remarks))}</td>"
                f'<td class="num">{flt(row.debit):,.2f}</td>'
                f'<td class="num">{flt(row.credit):,.2f}</td>'
                f'<td class="num">{flt(row.saldo):,.2f}</td>'
                "</tr>"
            )
        tot_debe += acc["debe"]
        tot_haber += acc["haber"]
        rows.append(
            "<tr>"
            '<td colspan="3" style="font-weight:600">Totales del período</td>'
            f'<td class="num" style="font-weight:600">{acc["debe"]:,.2f}</td>'
            f'<td class="num" style="font-weight:600">{acc["haber"]:,.2f}</td>'
            f'<td class="num" style="font-weight:600">{acc["saldo_final"]:,.2f}</td>'
            "</tr>"
        )
        blocks.append(
            f"""<div class="asiento">
 <h2>{html.escape(cstr(acc['account_number']))} {html.escape(cstr(acc['account_name']))}</h2>
 <table>
  <thead><tr><th>Fecha</th><th>Documento</th><th>Descripción</th>
    <th class="num">Debe</th><th class="num">Haber</th><th class="num">Saldo</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
 </table>
</div>"""
        )

    doc = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Libro Mayor</title>
<style>{_LIBRO_CSS}</style></head><body>
<h1>LIBRO MAYOR</h1>
<div class="ident"><b>{html.escape(cstr(ident['name']))}</b>{nit}<br>
 Moneda: {html.escape(cstr(ident['currency']))}</div>
<div class="period">Del {getdate(from_date).strftime('%d/%m/%Y')} al {getdate(to_date).strftime('%d/%m/%Y')}
 · {len(accounts)} cuentas</div>
{''.join(blocks)}
<table class="totales">
 <thead><tr><th colspan="3">TOTALES DEL PERÍODO</th><th class="num">Debe</th><th class="num">Haber</th><th class="num"></th></tr></thead>
 <tbody><tr><td colspan="3">Sumas iguales del libro</td>
  <td class="num">{tot_debe:,.2f}</td><td class="num">{tot_haber:,.2f}</td><td class="num"></td></tr></tbody>
</table>
<div class="note">Generado automáticamente por scripts/estados_financieros.py ·
 Diferencia Debe - Haber: {tot_debe - tot_haber:,.2f}</div>
</body></html>"""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(doc)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def _emit(slug, title, columns, rows, note=""):
    if not columns:
        print(f"  ! {title}: sin datos/columnas")
        return
    write_csv(os.path.join(OUTDIR, f"{slug}.csv"), columns, rows)
    write_html(os.path.join(OUTDIR, f"{slug}.html"), title, SUBTITLE, columns, rows, note)
    print(f"  ✔ {title}  ({len(rows)} filas)")


def _safe_report(report, filters, slug, title, note=""):
    """Ejecuta un reporte; si falla, avisa pero no interrumpe el resto."""
    try:
        cols, rows = run_report(report, filters)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! {title}: no se pudo ejecutar '{report}' ({exc})")
        return [], []
    _emit(slug, title, cols, rows, note)
    return cols, rows


def main():
    global SUBTITLE

    company = resolve_company()
    fy_doc = resolve_fiscal_year(company, os.environ.get("EF_FISCAL_YEAR"))
    fy = fy_doc.name
    from_date = fy_doc.year_start_date
    to_date = fy_doc.year_end_date

    currency = frappe.get_cached_value("Company", company, "default_currency")
    SUBTITLE = (
        f"{company} · ejercicio fiscal {fy} · {getdate(from_date)} a {getdate(to_date)}"
        f" · moneda {currency}"
    )
    note = "Generado automáticamente por scripts/estados_financieros.py"

    os.makedirs(OUTDIR, exist_ok=True)
    sheets = []
    summary = []

    print("=" * 90)
    print(" ESTADOS FINANCIEROS COMPLETOS")
    print(f" {SUBTITLE}")
    print("=" * 90)

    # ---- 1. Balance General -------------------------------------------------
    cols, rows = _safe_report(
        "Balance Sheet",
        fin_filters(company, from_date, to_date, fy),
        "01-balance-general",
        "Balance General (Estado de Situación Financiera)",
        note,
    )
    if rows:
        sheets.append(("Balance General", cols, rows))
        summary.append(("Total activo", _pick_total(rows, "Total Assets", "Total Activo")))
        summary.append(("Total pasivo", _pick_total(rows, "Total Liabilities", "Total Pasivo")))
        summary.append(("Total patrimonio", _pick_total(rows, "Total Equity", "Total Patrimonio")))

    # ---- 2. Estado de Resultados -------------------------------------------
    cols, rows = _safe_report(
        "Profit and Loss Statement",
        fin_filters(company, from_date, to_date, fy, accumulated_values=0),
        "02-estado-resultados",
        "Estado de Resultados",
        note,
    )
    if rows:
        sheets.append(("Estado de Resultados", cols, rows))
        summary.append(
            (
                "Utilidad / (Pérdida) neta",
                _pick_total(rows, "Profit for the year", "Net Profit", "Total", "Utilidad"),
            )
        )

    # ---- 3. Balance Financiero (Balanza de Comprobación) -------------------
    tb_filters = frappe._dict(
        {
            "company": company,
            "fiscal_year": fy,
            "from_date": d2s(from_date),
            "to_date": d2s(to_date),
            "period_start_date": d2s(from_date),
            "period_end_date": d2s(to_date),
            "filter_based_on": "Fiscal Year",
            "periodicity": "Yearly",
            "with_period_closing_entry_for_opening": 1,
            "with_period_closing_entry_for_current_period": 1,
            "show_zero_values": 0,
            "show_unclosed_fy_pl_balances": 1,
            "include_default_book_entries": 1,
            "show_net_values": 1,
            "show_group_accounts": 1,
        }
    )
    cols, rows = _safe_report(
        "Trial Balance",
        tb_filters,
        "03-balance-financiero",
        "Balance Financiero (Balanza de Comprobación)",
        note,
    )
    if rows:
        sheets.append(("Balanza de Comprobacion", cols, rows))

    # ---- 4. Estado de Flujo de Efectivo ------------------------------------
    cols, rows = _safe_report(
        "Cash Flow",
        fin_filters(
            company,
            from_date,
            to_date,
            fy,
            show_opening_and_closing_balance=1,
            show_account_details="Summary",
        ),
        "04-flujo-efectivo",
        "Estado de Flujo de Efectivo",
        note,
    )
    if rows:
        sheets.append(("Flujo de Efectivo", cols, rows))
        summary.append(
            (
                "Flujo neto del período",
                _pick_total(rows, "Net Cash", "Net Cash Flow", "Net Change in Cash"),
            )
        )

    # ---- 5. Estado de Cambios en el Patrimonio (matriz) --------------------
    try:
        cols, rows, resultado = equity_statement(company, from_date, to_date)
        control = accounting_check(company, to_date)
        _emit(
            "05-estado-patrimonio",
            "Estado de Cambios en el Patrimonio Neto (NIC 1)",
            cols,
            rows,
            note=f"{note} · Cuadre contable del libro (debe ser 0): {flt(control, 2):,.2f}",
        )
        sheets.append(("Patrimonio Neto", cols, rows))
        summary.append(("Resultado del ejercicio (según mayor)", resultado))
        summary.append(("Cuadre contable del libro (debe ser 0)", control))
    except Exception as exc:  # noqa: BLE001
        print(f"  ! No se pudo construir el ECPN matricial: {exc}")

    # ---- 5b. Plantilla nativa ERPNext (Custom Financial Statement) ---------
    template = "Estado de Cambios en el Patrimonio Neto (NIC 1)"
    if frappe.db.exists("Financial Report Template", template):
        _safe_report(
            "Custom Financial Statement",
            fin_filters(company, from_date, to_date, fy, report_template=template),
            "05b-estado-patrimonio-plantilla",
            "Estado de Cambios en el Patrimonio Neto (plantilla ERPNext)",
            note,
        )
    else:
        print("  ! La plantilla ECPN no existe (ejecuta setup_accounting.py)")

    # ---- 6. Libro Diario (Guatemala) ---------------------------------------
    try:
        folio_inicio = int(os.environ.get("LD_FOLIO_INICIO") or 1)
    except ValueError:
        folio_inicio = 1
    try:
        asientos = build_libro_diario(company, from_date, to_date, folio_inicio)
        ld_rows = libro_diario_flat(asientos)
        write_libro_diario_html(
            os.path.join(OUTDIR, "06-libro-diario.html"), company, from_date, to_date, asientos
        )
        write_csv(os.path.join(OUTDIR, "06-libro-diario.csv"), LD_COLUMNS, ld_rows)
        print(f"  ✔ Libro Diario  ({len(asientos)} partidas, {len(ld_rows)} líneas)")
        if ld_rows:
            sheets.append(("Libro Diario", LD_COLUMNS, ld_rows))
        ld_debe = sum(flt(a["debe"]) for a in asientos)
        ld_haber = sum(flt(a["haber"]) for a in asientos)
        summary.append(("Libro Diario · total Debe", ld_debe))
        summary.append(("Libro Diario · total Haber", ld_haber))
        summary.append(("Libro Diario · diferencia (debe ser 0)", ld_debe - ld_haber))
    except Exception as exc:  # noqa: BLE001
        print(f"  ! No se pudo construir el Libro Diario: {exc}")

    # ---- 7. Libro Mayor (Guatemala) ----------------------------------------
    try:
        mayor = build_libro_mayor(company, from_date, to_date)
        lm_rows = libro_mayor_flat(mayor)
        write_libro_mayor_html(
            os.path.join(OUTDIR, "07-libro-mayor.html"), company, from_date, to_date, mayor
        )
        write_csv(os.path.join(OUTDIR, "07-libro-mayor.csv"), LM_COLUMNS, lm_rows)
        print(f"  ✔ Libro Mayor  ({len(mayor)} cuentas, {len(lm_rows)} líneas)")
        if lm_rows:
            sheets.append(("Libro Mayor", LM_COLUMNS, lm_rows))
    except Exception as exc:  # noqa: BLE001
        print(f"  ! No se pudo construir el Libro Mayor: {exc}")

    # ---- índice + xlsx ------------------------------------------------------
    _write_index(SUBTITLE)
    if sheets and write_xlsx(os.path.join(OUTDIR, "estados-financieros.xlsx"), sheets):
        print("  ✔ estados-financieros.xlsx")

    print("-" * 90)
    for label, value in summary:
        if value is None:
            continue
        print(f" {label[:58]:<58} {flt(value, 2):>18,.2f}")
    print("-" * 90)
    print(f" Archivos en: {OUTDIR}")
    print(f"{SENTINEL} {company} {fy}")
    return 0


def _pick_total(rows, *labels):
    """Busca una fila de total por su etiqueta y devuelve su importe."""
    meta_keys = {
        "indent",
        "is_group",
        "is_total_row",
        "has_value",
        "warn_if_negative",
        "account_name",
    }

    def norm(text):
        return "".join(ch for ch in cstr(text).lower() if ch.isalnum())

    wanted = [norm(label) for label in labels]
    for row in rows or []:
        label = ""
        for key in ("account", "acc_name", "account_name", "label"):
            if row.get(key):
                label = cstr(row.get(key))
                break
        name = norm(label)
        if not name or not any(w == name or w in name for w in wanted):
            continue
        for key in ("total", "closing_credit", "closing_debit", "balance"):
            value = row.get(key)
            if type(value) in (int, float):
                return value
        numbers = [
            v
            for k, v in row.items()
            if k not in meta_keys and type(v) in (int, float)
        ]
        if numbers:
            return numbers[-1]
    return None


def _write_index(subtitle):
    entries = [
        ("01-balance-general.html", "Balance General"),
        ("02-estado-resultados.html", "Estado de Resultados"),
        ("03-balance-financiero.html", "Balance Financiero (Balanza)"),
        ("04-flujo-efectivo.html", "Estado de Flujo de Efectivo"),
        ("05-estado-patrimonio.html", "Estado de Cambios en el Patrimonio Neto"),
        ("05b-estado-patrimonio-plantilla.html", "ECPN (plantilla ERPNext)"),
        ("06-libro-diario.html", "Libro Diario (Guatemala)"),
        ("07-libro-mayor.html", "Libro Mayor (Guatemala)"),
    ]
    files = [(h, t) for h, t in entries if os.path.exists(os.path.join(OUTDIR, h))]
    libros = [(h, t) for h, t in files if h[:2] in ("06", "07")]
    estados = [(h, t) for h, t in files if h[:2] not in ("06", "07")]

    def items(pairs):
        return "".join(
            f'<li><a href="{html.escape(h)}">{html.escape(t)}</a> '
            f'(<a href="{html.escape(h.replace(".html", ".csv"))}">csv</a>)</li>'
            for h, t in pairs
        )

    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Estados financieros</title>
<style>body{{font-family:-apple-system,"Segoe UI",Roboto,Arial,sans-serif;margin:32px;color:#1f272e}}
li{{margin:6px 0}} .sub{{color:#687178;font-size:13px}} h2{{font-size:15px;margin:18px 0 6px}}</style>
</head><body>
<h1>Estados financieros y libros contables</h1><div class="sub">{html.escape(subtitle)}</div>
<h2>Estados financieros</h2><ul>{items(estados)}</ul>
<h2>Libros contables (Guatemala)</h2><ul>{items(libros)}</ul>
<p><a href="estados-financieros.xlsx">Descargar todo en Excel (estados-financieros.xlsx)</a></p>
</body></html>"""
    with open(os.path.join(OUTDIR, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(doc)


if __name__ == "__main__":
    try:
        main()
    except Exception as _exc:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        print(f"ERROR: {_exc}")
        raise SystemExit(1)
