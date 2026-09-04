#!/usr/bin/env python3
"""
nbh — Nobrokerhood gate management CLI

Usage examples:
  nbh pre-approve zepto
  nbh pre-approve dominos --hours 4
  nbh pre-approve amazon --in "25/04/2026 14:00" --vehicle TWO_WHEELER
  nbh cancel <visit-id>
  nbh list
  nbh register-device
"""

import argparse
import json
import logging
import sys
from datetime import datetime

from nobrokerhood import KNOWN_COMPANIES, NobrokerhoodClient, pick_fields
from nobrokerhood.exceptions import NobrokerhoodError

logger = logging.getLogger(__name__)


def _parse_datetime(value: str, flag: str, *, default_time: str) -> datetime:
    """Parse DD/MM/YYYY or DD/MM/YYYY HH:MM; missing time defaults to default_time."""
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if fmt == "%d/%m/%Y":
                h, m = map(int, default_time.split(":"))
                dt = dt.replace(hour=h, minute=m)
            return dt
        except ValueError:
            continue
    logger.error("%s must be DD/MM/YYYY or DD/MM/YYYY HH:MM", flag)
    sys.exit(1)


def cmd_pre_approve(client: NobrokerhoodClient, args: argparse.Namespace) -> None:
    in_time = None
    if args.in_time:
        in_time = _parse_datetime(args.in_time, "--in", default_time="00:00")

    out_time = None
    if args.out_time:
        out_time = _parse_datetime(args.out_time, "--out", default_time="23:59")

    try:
        result = client.pre_approve(
            company=args.company,
            apartment_id=args.apartment_id,
            duration_hours=args.hours,
            in_time=in_time,
            out_time=out_time,
            vehicle_type=args.vehicle,
            visitor_name=args.name or "",
            visitor_phone=args.phone or "",
        )
    except ValueError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    _print_result(result, args.fields)


def cmd_cancel(client: NobrokerhoodClient, args: argparse.Namespace) -> None:
    result = client.cancel_visit(args.visit_id, apartment_id=args.apartment_id)
    _print_result(result, args.fields)


def cmd_list(client: NobrokerhoodClient, args: argparse.Namespace) -> None:
    result = client.list_expected(
        apartment_id=args.apartment_id,
        page=args.page,
        page_size=args.page_size,
        sort_order=args.sort,
    )
    _print_result(result, args.fields)


def cmd_visits(client: NobrokerhoodClient, args: argparse.Namespace) -> None:
    result = client.list_visits(
        apartment_id=args.apartment_id,
        page=args.page,
        page_size=args.page_size,
    )
    _print_result(result, args.fields)


def cmd_register_device(client: NobrokerhoodClient, args: argparse.Namespace) -> None:
    result = client.register_device(apartment_id=args.apartment_id)
    _print_result(result, args.fields)


def cmd_home(client: NobrokerhoodClient, args: argparse.Namespace) -> None:
    result = client.get_home_content(apartment_id=args.apartment_id)
    _print_result(result, args.fields)


def cmd_user_info(client: NobrokerhoodClient, args: argparse.Namespace) -> None:
    result = client.get_user_multiprofile_info()
    _print_result(result, args.fields)


def _print_result(data: dict, fields: list[str] | None = None) -> None:
    print(json.dumps(pick_fields(data, fields), indent=2, ensure_ascii=False))


def _add_fields_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--fields",
        nargs="+",
        default=None,
        metavar="PATH",
        help=(
            "Dot-notation paths to include in the response, e.g. "
            "--fields data.apartments.apartment.id data.apartments.apartment.name. "
            "Omit to return the full response."
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nbh",
        description="Nobrokerhood gate management CLI",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help=(
            "Increase log verbosity. "
            "-v shows INFO (request/response summary), "
            "-vv shows DEBUG (exact request and response bodies)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- pre-approve ----
    pa = sub.add_parser("pre-approve", help="Pre-approve a delivery")
    pa.add_argument(
        "company",
        help=f"Delivery company (e.g. zepto, blinkit, dominos), or 'any' to admit "
        f"deliveries from any/every brand under one approval window. "
        f"Known companies with default windows: {', '.join(KNOWN_COMPANIES)}",
    )
    pa.add_argument(
        "--apartment-id",
        required=True,
        dest="apartment_id",
        metavar="ID",
        help="Apartment ID (fetch via: nbh user-info)",
    )
    window = pa.add_mutually_exclusive_group()
    window.add_argument(
        "--hours",
        type=float,
        default=None,
        metavar="N",
        help="Duration of the approval window in hours (overrides per-company default)",
    )
    window.add_argument(
        "--out",
        dest="out_time",
        default=None,
        metavar="DD/MM/YYYY[HH:MM]",
        help="Window end time; date-only defaults to 23:59. "
        "Use with --in for a multi-day range.",
    )
    pa.add_argument(
        "--in",
        dest="in_time",
        default=None,
        metavar="DD/MM/YYYY[HH:MM]",
        help="Window start time; date-only defaults to 00:00 (default: now)",
    )
    pa.add_argument(
        "--vehicle",
        default="FOUR_WHEELER",
        choices=["FOUR_WHEELER", "TWO_WHEELER"],
        help="Vehicle type (default: FOUR_WHEELER)",
    )
    pa.add_argument("--name", default="", help="Visitor name")
    pa.add_argument("--phone", default="", help="Visitor phone")
    _add_fields_arg(pa)

    # ---- cancel ----
    ca = sub.add_parser("cancel", help="Cancel a pre-approved visit")
    ca.add_argument("visit_id", help="Visit ID to cancel")
    ca.add_argument(
        "--apartment-id",
        required=True,
        dest="apartment_id",
        metavar="ID",
        help="Apartment ID (fetch via: nbh user-info)",
    )
    _add_fields_arg(ca)

    # ---- list ----
    ls = sub.add_parser("list", help="List upcoming expected visits")
    ls.add_argument(
        "--apartment-id",
        required=True,
        dest="apartment_id",
        metavar="ID",
        help="Apartment ID (fetch via: nbh user-info)",
    )
    ls.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    ls.add_argument(
        "--page-size",
        type=int,
        default=5,
        dest="page_size",
        help="Results per page (default: 5)",
    )
    ls.add_argument(
        "--sort",
        default="asc",
        choices=["asc", "desc"],
        help="Sort order (default: asc)",
    )
    _add_fields_arg(ls)

    # ---- visits ----
    vs = sub.add_parser(
        "visits",
        help="List current, past, and denied visits for an apartment",
    )
    vs.add_argument(
        "--apartment-id",
        required=True,
        dest="apartment_id",
        metavar="ID",
        help="Apartment ID (fetch via: nbh user-info)",
    )
    vs.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    vs.add_argument(
        "--page-size",
        type=int,
        default=10,
        dest="page_size",
        help="Results per page (default: 10)",
    )
    _add_fields_arg(vs)

    # ---- register-device ----
    rd = sub.add_parser("register-device", help="Register/refresh device with the API")
    rd.add_argument(
        "--apartment-id",
        required=True,
        dest="apartment_id",
        metavar="ID",
        help="Apartment ID (fetch via: nbh user-info)",
    )
    _add_fields_arg(rd)

    # ---- home ----
    ho = sub.add_parser("home", help="Fetch home-screen content")
    ho.add_argument(
        "--apartment-id",
        required=True,
        dest="apartment_id",
        metavar="ID",
        help="Apartment ID (fetch via: nbh user-info)",
    )
    _add_fields_arg(ho)

    # ---- user-info ----
    ui = sub.add_parser(
        "user-info",
        help="Fetch user multiprofile info (apartments, family, pass codes)",
    )
    _add_fields_arg(ui)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    log_level = {0: logging.WARNING, 1: logging.INFO}.get(args.verbose, logging.DEBUG)
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        client = NobrokerhoodClient()
    except OSError as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(1)

    handlers = {
        "pre-approve": cmd_pre_approve,
        "cancel": cmd_cancel,
        "list": cmd_list,
        "visits": cmd_visits,
        "register-device": cmd_register_device,
        "home": cmd_home,
        "user-info": cmd_user_info,
    }

    try:
        handlers[args.command](client, args)
    except NobrokerhoodError as exc:
        body = getattr(exc, "response_body", None)
        if body is not None:
            print(json.dumps(body, indent=2, ensure_ascii=False))
        logger.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
