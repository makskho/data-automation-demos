"""Command line: export-products, update, export-postings, warehouses.

Exit codes: 0 done, 1 the API rejected something or failed, 2 the input is not acceptable
(bad sheet, missing keys, bad arguments) and nothing was sent.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from .client import OzonClient
from .errors import ApiError, SheetError
from .fake import FakeOzon
from .plan import build_plan, render_diff, render_issues, render_table, validate
from .sheets import read_edit_sheet, write_postings, write_products
from .transport import DEFAULT_BASE_URL, HttpTransport, RetryingTransport, Transport


def load_env_file(path: str | Path) -> None:
    """Read KEY=VALUE lines into os.environ (existing variables win). No dependency needed."""
    file = Path(path)
    if not file.is_file():
        return
    for raw in file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ozon_sync", description="Ozon Seller API <-> Excel")
    parser.add_argument("--demo", action="store_true", help="работать на встроенных синтетических данных, без ключей и сети")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=argparse.SUPPRESS)
    parser.add_argument("--env-file", default=".env", help="файл с OZON_CLIENT_ID и OZON_API_KEY (по умолчанию .env)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("export-products", help="выгрузить товары с ценами и остатками в .xlsx")
    p.add_argument("-o", "--output", default="out/products.xlsx")
    p.add_argument("--visibility", default="ALL", help="фильтр /v3/product/list (по умолчанию ALL)")

    p = sub.add_parser("update", help="обновить цены и остатки из .xlsx (по умолчанию dry-run)")
    p.add_argument("file", help="файл, выгруженный export-products и отредактированный")
    p.add_argument("--apply", action="store_true", help="реально отправить изменения (без флага только показать)")
    p.add_argument("--warehouse-id", type=int, help="склад FBS для остатков (список: команда warehouses)")
    p.add_argument("--skip-invalid", action="store_true", help="пропустить строки с ошибками и обработать остальные")
    p.add_argument("--allow-big-change", action="store_true", help="разрешить изменение цены больше чем на 50%%")

    p = sub.add_parser("export-postings", help="выгрузить отправления FBS за период в .xlsx")
    p.add_argument("--from", dest="date_from", required=True, type=_parse_date, help="первый день, ГГГГ-ММ-ДД")
    p.add_argument("--to", dest="date_to", required=True, type=_parse_date, help="последний день включительно")
    p.add_argument("--status", help="например awaiting_packaging, delivering, delivered, cancelled")
    p.add_argument("--utc-offset", type=float, default=3.0, help="часовой пояс продавца, часов от UTC (Москва = 3)")
    p.add_argument("-o", "--output", default="out/postings.xlsx")

    sub.add_parser("warehouses", help="показать склады продавца (warehouse_id)")
    return parser


def _parse_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"ожидается дата ГГГГ-ММ-ДД, получено «{text}»") from None


def day_window(first: date, last: date, utc_offset_hours: float) -> tuple[datetime, datetime]:
    """[first 00:00:00.000, last 23:59:59.999] in the seller's timezone, as aware datetimes."""
    tz = timezone(timedelta(hours=utc_offset_hours))
    since = datetime(first.year, first.month, first.day, tzinfo=tz)
    end = datetime(last.year, last.month, last.day, tzinfo=tz) + timedelta(days=1) - timedelta(milliseconds=1)
    return since, end


def _make_transport(args: argparse.Namespace) -> Transport:
    if args.demo:
        return FakeOzon()
    load_env_file(args.env_file)
    client_id, api_key = os.environ.get("OZON_CLIENT_ID", ""), os.environ.get("OZON_API_KEY", "")
    if not client_id or not api_key:
        raise SystemExit(_err("нужны OZON_CLIENT_ID и OZON_API_KEY (переменные окружения или файл .env), либо запустите с --demo"))
    http = HttpTransport(client_id, api_key, args.base_url)
    return RetryingTransport(http, on_retry=_report_retry)


def _err(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def _report_retry(path: str, attempt: int, delay: float, exc: ApiError) -> None:
    print(f"  {path}: HTTP {exc.status}, повтор {attempt} через {delay:g} с", file=sys.stderr)


def main(argv: Sequence[str] | None = None, transport: Transport | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        client = OzonClient(transport if transport is not None else _make_transport(args))
        handler = {
            "export-products": _export_products,
            "update": _update,
            "export-postings": _export_postings,
            "warehouses": _warehouses,
        }[args.command]
        return handler(client, args)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    except SheetError as exc:
        return _err(f"Ошибка файла: {exc}")
    except ApiError as exc:
        return _err(f"Ошибка API: {exc}")


def _export_products(client: OzonClient, args: argparse.Namespace) -> int:
    catalog = client.fetch_catalog(args.visibility)
    path = write_products(args.output, catalog)
    print(f"Товаров: {len(catalog)}. Файл: {path}")
    return 0


def _warehouses(client: OzonClient, args: argparse.Namespace) -> int:
    rows = [(w.get("warehouse_id"), w.get("name"), w.get("status")) for w in client.list_warehouses()]
    print(render_table(["warehouse_id", "Название", "Статус"], rows))
    return 0


def _export_postings(client: OzonClient, args: argparse.Namespace) -> int:
    if args.date_to < args.date_from:
        return _err("--to раньше --from")
    since, to = day_window(args.date_from, args.date_to, args.utc_offset)
    postings = client.list_postings(since, to, args.status)
    path = write_postings(args.output, postings, args.utc_offset)
    lines = sum(len(p.lines) for p in postings)
    print(f"Период {args.date_from} .. {args.date_to} (UTC{args.utc_offset:+g}). Отправлений: {len(postings)}, строк товаров: {lines}. Файл: {path}")
    return 0


def _update(client: OzonClient, args: argparse.Namespace) -> int:
    rows = read_edit_sheet(args.file)
    catalog = client.fetch_catalog()
    valid, issues = validate(rows, catalog)
    if issues:
        print(f"Строк с ошибками в таблице: {len({i.row_no for i in issues})}")
        print(render_issues(issues))
        if not args.skip_invalid:
            print("\nНичего не отправлено. Исправьте файл или запустите с --skip-invalid.")
            return 2
        print(f"\n--skip-invalid: эти строки пропущены, обрабатываем остальные ({len(valid)}).\n")

    plan = build_plan(valid, catalog)
    print(render_diff(plan))
    print(
        f"\nСтрок без изменений: {plan.unchanged_rows}. К отправке: цены — {len(plan.price_updates)} товаров, "
        f"остатки — {len(plan.stock_updates)} товаров."
    )
    if not args.apply:
        print("Режим dry-run: ничего не отправлено. Добавьте --apply, чтобы применить.")
        return 0
    if not plan.price_updates and not plan.stock_updates:
        return 0
    if plan.warnings and not args.allow_big_change:
        print("Есть изменения цены больше 50% (помечены «!»). Проверьте их или добавьте --allow-big-change. Ничего не отправлено.")
        return 2

    warehouse_id = args.warehouse_id
    if plan.stock_updates and warehouse_id is None:
        warehouses = client.list_warehouses()
        if len(warehouses) != 1:
            print("Для остатков укажите --warehouse-id. Склады:")
            print(render_table(["warehouse_id", "Название"], [(w.get("warehouse_id"), w.get("name")) for w in warehouses]))
            return 2
        warehouse_id = int(warehouses[0]["warehouse_id"])
        print(f"Склад не указан, он один: {warehouse_id}.")

    results = []
    if plan.price_updates:
        results += [("цена", r) for r in client.update_prices(plan.price_updates)]
    if plan.stock_updates:
        results += [("остаток", r) for r in client.update_stocks(plan.stock_updates, int(warehouse_id))]
    failed = [(kind, r) for kind, r in results if not r.ok]
    print(f"\nОтправлено: {len(results)}, успешно: {len(results) - len(failed)}, с ошибкой: {len(failed)}.")
    for kind, r in failed:
        print(f"  {r.offer_id} ({kind}): {'; '.join(r.errors) or 'ошибка'}")
    return 1 if failed else 0
