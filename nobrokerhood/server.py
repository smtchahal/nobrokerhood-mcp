"""
NoBrokerHood MCP server — exposes gate pre-approval as MCP tools.

Call ``build_server()`` for a plain stdio server (the common case — spawned as
a subprocess by Claude Desktop / Code), or pass MCPServer constructor kwargs
(``token_verifier``, ``auth``, ...) to self-host with your own authorization
layer in front. Transport-level options (``host``, ``port``,
``streamable_http_path``, ``stateless_http``, ...) are no longer accepted
here — pass them to ``.run(transport=..., **kwargs)`` on the returned server
instead (see mcp 2.0's migration guide).

Rule: never write to stdout in stdio mode — it corrupts the JSON-RPC framing.
All logging goes to stderr only.
"""

import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Literal

from mcp.server.mcpserver import MCPServer

from nobrokerhood import KNOWN_COMPANIES, NobrokerhoodClient, pick_fields
from nobrokerhood.exceptions import NobrokerhoodError

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(levelname)s %(name)s: %(message)s",
)

_IST = timezone(timedelta(hours=5, minutes=30))

_EXPECTED_TOP_FIELDS = ("startDate", "endDate", "startTime", "endTime", "createdOn")
_EXPECTED_VISITOR_FIELDS = ("expectedInTime", "expectedOutTime")
_VISIT_TOP_FIELDS = (
    "createdOn",
    "lastUpdatedOn",
    "inTime",
    "outTime",
    "expectedInTime",
    "expectedOutTime",
    "approvedOn",
    "stayOverReminderTime",
)
_APARTMENT_DATE_FIELDS = ("leaseStartDate", "leaseEndDate")


def _ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=_IST).isoformat()


def _enrich_visits_list(visits: list) -> None:
    """Add *_iso companions for top-level unix-ms timestamps in a visit list."""
    for visit in visits:
        if not isinstance(visit, dict):
            continue
        for field in _VISIT_TOP_FIELDS:
            if isinstance(visit.get(field), int):
                visit[f"{field}_iso"] = _ms_to_iso(visit[field])


def _enrich_pending(result: dict) -> dict:
    """Add *_iso companions for every unix-ms timestamp in list_expected results."""
    pending = result.get("data", {}).get("pending")
    if not isinstance(pending, list):
        return result
    for visit in pending:
        if not isinstance(visit, dict):
            continue
        for field in _EXPECTED_TOP_FIELDS:
            if isinstance(visit.get(field), int):
                visit[f"{field}_iso"] = _ms_to_iso(visit[field])
        visitor = visit.get("visitor")
        if isinstance(visitor, dict):
            for field in _EXPECTED_VISITOR_FIELDS:
                if isinstance(visitor.get(field), int):
                    visitor[f"{field}_iso"] = _ms_to_iso(visitor[field])
    return result


def _enrich_visits(result: dict) -> dict:
    """Add *_iso companions for top-level unix-ms timestamps in list_visits results."""
    data = result.get("data", {})
    for category in ("current", "expired", "denied", "pending"):
        visits = data.get(category)
        if isinstance(visits, list):
            _enrich_visits_list(visits)
    return result


def _enrich_profile(result: dict) -> dict:
    """Add *_iso companions for lease date timestamps in get_user_multiprofile_info."""
    for apt_entry in result.get("data", {}).get("apartments", []):
        apt = apt_entry.get("apartment")
        if not isinstance(apt, dict):
            continue
        for field in _APARTMENT_DATE_FIELDS:
            if isinstance(apt.get(field), int):
                apt[f"{field}_iso"] = _ms_to_iso(apt[field])
    return result


# ── Client singleton ──────────────────────────────────────────────────────────

_client: NobrokerhoodClient | None = None


def _get_client() -> NobrokerhoodClient:
    """Lazy singleton — fails with a clean error if .env is incomplete."""
    global _client
    if _client is None:
        _client = NobrokerhoodClient()
    return _client


# ── Tools ─────────────────────────────────────────────────────────────────────


def pre_approve(
    company: str,
    apartment_id: str,
    duration_hours: float | None = None,
    in_time: str | None = None,
    out_time: str | None = None,
    vehicle_type: Literal["FOUR_WHEELER", "TWO_WHEELER"] = "FOUR_WHEELER",
    visitor_name: str = "",
    visitor_phone: str = "",
    fields: list[str] | None = None,
) -> dict:
    """Pre-approve a delivery or visitor at the society gate via NoBrokerHood.

    Use this whenever the user wants to let a delivery in: "pre-approve zepto",
    "let the dominos guy in for 4 hours", "approve amazon till midnight".
    "Pre-approve for the day" means until midnight (23:59) of the current day.

    Call get_user_multiprofile_info first to obtain the apartment_id if not
    already known; skip if the user explicitly provided it.

    Args:
      company: Brand name, e.g. "Zepto", "Blinkit", "Dominos", "Amazon".
        Case/space/hyphen insensitive. ~100 brands have built-in defaults; see
        the `known_companies` tool for the full list. Unknown brands default
        to a 1-hour window.
      apartment_id: The apartment ID to pre-approve the visit for. Fetch from
        get_user_multiprofile_info → data.apartments.apartment.id.
      duration_hours: Override the per-company default window length (in hours).
        Ignored when out_time is provided.
      in_time: ISO-8601 start time (e.g. "2026-04-11T14:30"). IST assumed.
        Defaults to now.
      out_time: ISO-8601 end time (e.g. "2026-04-11T23:59"). IST assumed.
        Takes precedence over duration_hours (precedence: out_time >
        duration_hours > company default). Use this for "pre-approve for the
        day" by computing today's 23:59 in ISO-8601.
      vehicle_type: FOUR_WHEELER (default) or TWO_WHEELER.
      visitor_name: Usually blank for deliveries.
      visitor_phone: Usually blank for deliveries.
      fields: Dot-notation paths to filter the response. Omit to return everything.

    Returns the raw API response dict. On success, the visit ID is a string at
    response["data"][0] (data is a list; element 0 is the visit ID).
    """
    try:
        result = _get_client().pre_approve(
            company=company,
            apartment_id=apartment_id,
            duration_hours=duration_hours,
            in_time=datetime.fromisoformat(in_time) if in_time else None,
            out_time=datetime.fromisoformat(out_time) if out_time else None,
            vehicle_type=vehicle_type,
            visitor_name=visitor_name,
            visitor_phone=visitor_phone,
        )
        return pick_fields(result, fields)
    except (OSError, NobrokerhoodError, ValueError) as e:
        raise RuntimeError(f"pre_approve failed: {e}") from e


def cancel_visit(
    visit_id: str,
    apartment_id: str,
    fields: list[str] | None = None,
) -> dict:
    """Cancel a previously pre-approved visit by its visit ID.

    Use this when the user wants to cancel a delivery approval they no longer need.
    The visit_id is at response["data"][0] from the pre_approve call.

    Call get_user_multiprofile_info first to obtain the apartment_id if not
    already known; skip if the user explicitly provided it.

    Args:
      visit_id: The visit ID string returned when the visit was created.
      apartment_id: The apartment ID the visit belongs to. Fetch from
        get_user_multiprofile_info → data.apartments.apartment.id.
      fields: Dot-notation paths to filter the response. Omit to return everything.

    Returns the raw API response dict on success.
    """
    try:
        result = _get_client().cancel_visit(visit_id, apartment_id=apartment_id)
        return pick_fields(result, fields)
    except (OSError, NobrokerhoodError) as e:
        raise RuntimeError(f"cancel_visit failed: {e}") from e


def list_expected(
    apartment_id: str,
    page: int = 1,
    page_size: int = 5,
    sort_order: Literal["asc", "desc"] = "asc",
    fields: list[str] | None = None,
) -> dict:
    """List pre-approved deliveries that are currently pending arrival.

    These are the user's active pre-approvals at their apartment.

    Use this when the user asks about pre-approved deliveries that haven't
    arrived yet: "what have I pre-approved?", "show my pending deliveries",
    "what deliveries am I expecting?", "did I approve anything?",
    "list my approvals". Do NOT use for historical/past gate activity — use
    list_visits for that.

    Call get_user_multiprofile_info first to obtain the apartment_id if not
    already known; skip if the user explicitly provided it.

    Args:
      apartment_id: The apartment ID to list visits for. Fetch from
        get_user_multiprofile_info → data.apartments.apartment.id.
      page: Page number, 1-indexed. Default 1.
      page_size: Number of results per page. Default 5.
      sort_order: "asc" (soonest first, default) or "desc" (latest first).
      fields: Dot-notation paths to filter the response. Omit to return everything.

    Returns the raw API response dict containing a list of pre-approved visits
    awaiting arrival, each with a visit ID, company name, and time window.
    """
    try:
        result = _get_client().list_expected(
            apartment_id=apartment_id,
            page=page,
            page_size=page_size,
            sort_order=sort_order,
        )
        return pick_fields(_enrich_pending(result), fields)
    except (OSError, NobrokerhoodError) as e:
        raise RuntimeError(f"list_expected failed: {e}") from e


def list_visits(
    apartment_id: str,
    page: int = 1,
    page_size: int = 10,
    fields: list[str] | None = None,
) -> dict:
    """List current, past (expired), and denied visits for an apartment.

    Use this when the user asks about gate activity (current, historical, or
    denied): "who's at the gate?", "who came today?", "show past visitors",
    "any denied entries?", "who visited recently?", "what deliveries came in?",
    "what deliveries are coming today?". Do NOT use for pending pre-approvals
    that haven't arrived — use list_expected for that.

    Returns all categories in one call. Each category is a separate list:
      - data.current:  visitors presently at the gate (checked in, not yet out)
      - data.expired:  completed past visits (checked in and checked out)
      - data.denied:   entry attempts that were denied at the gate
      - data.pending:  pre-approved visits not yet arrived (overlaps with list_expected)

    Each visit entry includes: company, visitor name/phone, inTime, outTime,
    gate name, approvedBy, approvalType, visitorType, and approval status.
    Company is at the top-level ``company`` field and also at
    ``visitorProfile.company``.

    Call get_user_multiprofile_info first to obtain the apartment_id if not
    already known. Skip if the user explicitly provided it.

    Args:
      apartment_id: The apartment ID to list visits for. Fetch from
        get_user_multiprofile_info → data.apartments.apartment.id.
      page: Page number, 1-indexed. Default 1. Applies to all lists.
      page_size: Number of results per page. Default 10.
      fields: Dot-notation paths to filter the response. Strongly recommended —
        omitting returns all four categories with full visitor data, which is
        large. Use fields to fetch only what the query needs:
          ["data.current"] → who's at the gate right now
          ["data.expired"] → today's completed visits
          ["data.current", "data.expired"] → active + past visits
          ["data.expired.company", "data.expired.inTime"] → company + entry time
          ["data.currentTotal", "data.expiredTotal", "data.deniedTotal"] → counts only
        Omit only if the user explicitly wants everything.

    Returns the raw API response dict.
    """
    try:
        result = _get_client().list_visits(
            apartment_id=apartment_id,
            page=page,
            page_size=page_size,
        )
        return pick_fields(_enrich_visits(result), fields)
    except (OSError, NobrokerhoodError) as e:
        raise RuntimeError(f"list_visits failed: {e}") from e


def get_user_multiprofile_info(fields: list[str] | None = None) -> dict:
    """Fetch the authenticated user's multiprofile information.

    Use this when the user asks about their profile, apartments, family members,
    society details, or pass codes: "what apartments do I have?", "show my profile",
    "who are my family members?", "what's my pass code?", "which societies am I in?".

    Also use this FIRST whenever another tool needs an apartment_id — unless
    the user explicitly provided the apartment_id, in which case use it directly.
    Call with fields=["data.apartments.apartment.id", "data.apartments.apartment.name",
    "data.apartments.apartment.displayName", "data.apartments.apartment.buildingName"]
    to identify the right apartment before proceeding. If exactly one apartment is
    returned, use its ID immediately without asking the user to confirm. If multiple
    apartments are returned, match the user's input against all of: name (full
    apartment name), displayName (short label), and buildingName (tower/block name)
    — the user may refer to any of these.

    Args:
      fields: Dot-notation paths to include in the response. Always specify
        fields to avoid fetching the full profile (which includes family,
        notification settings, and other data rarely needed). Omit only if
        the user explicitly asks for their complete profile information.
        Examples:
        - ["data.apartments.apartment.id", "data.apartments.apartment.name",
          "data.apartments.apartment.displayName",
          "data.apartments.apartment.buildingName"]
          → compact apartment list for matching and obtaining an apartment_id
        - ["data.user.person.name", "data.user.person.phone"]
          → just the primary user's contact info
        - ["data.passCodes"] → just the pass codes map

    Returns the raw API response dict containing:
      - user: primary user details (name, email, phone, photo)
      - family: list of family members registered under the account
      - apartments: all apartments the user has access to, each with apartment
        details, area/block info, society info, ownership type (OWNER/TENANT),
        and residency tag
      - passCodes: map of apartmentId → entry pass code
      - notifcationSettings: all notification toggle states
      - hasMultipleProfile: whether the user has profiles across multiple apartments
    """
    try:
        result = _get_client().get_user_multiprofile_info()
        return pick_fields(_enrich_profile(result), fields)
    except (OSError, NobrokerhoodError) as e:
        raise RuntimeError(f"get_user_multiprofile_info failed: {e}") from e


def known_companies() -> dict:
    """Return the list of delivery brands with built-in default approval windows.

    Use this when the user asks "what companies do you know?", "which brands are
    supported?", or before calling pre_approve with an unfamiliar name.

    Returns a dict with a "companies" key containing a sorted list of brand names.
    """
    return {"companies": sorted(KNOWN_COMPANIES.keys())}


_TOOLS = (
    pre_approve,
    cancel_visit,
    list_expected,
    list_visits,
    get_user_multiprofile_info,
    known_companies,
)


def register_tools(mcp: MCPServer) -> None:
    """Register all NoBrokerHood tools on an existing MCPServer instance."""
    for fn in _TOOLS:
        mcp.tool()(fn)


def build_server(**mcpserver_kwargs) -> MCPServer:
    """Build an MCPServer with all NoBrokerHood tools registered.

    Pass no arguments for a plain stdio server. Pass MCPServer constructor
    kwargs (``token_verifier``, ``auth``, ...) to self-host with your own
    authorization layer in front — this function does not implement or assume
    any particular auth scheme. Transport-level options (``host``, ``port``,
    ``streamable_http_path``, ``stateless_http``, ...) belong on
    ``.run(transport=..., **kwargs)`` instead, not here.
    """
    mcp = MCPServer("nobrokerhood", **mcpserver_kwargs)
    register_tools(mcp)
    return mcp


def main() -> None:
    """Entry point for the ``nobrokerhood-mcp`` console script (stdio transport)."""
    build_server().run()


if __name__ == "__main__":
    main()
