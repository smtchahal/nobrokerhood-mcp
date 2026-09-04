"""
NobrokerhoodClient — thin wrapper around the Nobrokerhood gate management API.

All credentials are read from environment variables (see .env.example).
"""

import json
import logging
import os
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests

from .companies import COMPANY_DISPLAY_NAMES, KNOWN_COMPANIES, MIDNIGHT
from .exceptions import APIError, AuthError
from .models import VisitorInfo, VisitRequest

# The API server runs in IST (GMT+0530). We must use IST for the current time
# rather than datetime.now(), which returns the local/container clock. When
# running inside Docker (which defaults to UTC), datetime.now() would produce a
# time ~5.5 hours behind IST, causing visits to be created with an already-
# expired window — they silently succeed (HTTP 200, sts=1) but never appear in
# the guard's app.
_IST = timezone(timedelta(hours=5, minutes=30))

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.nobrokerhood.com"


class NobrokerhoodClient:
    """
    Client for the Nobrokerhood resident app API.

    Required environment variables:
        NBH_USER_ID       — your resident user ID
        NBH_SOCIETY_ID    — your society ID
        NBH_DEVICE_ID     — registered device UUID
        NBH_REMEMBER_ME   — value of the remember-me auth cookie
        NBH_JSESSIONID    — value of the JSESSIONID auth cookie
        NBH_CITY_ID       — your city identifier

    Optional:
        NBH_APP_VERSION   — app version header (default: 691)
    """

    def __init__(self) -> None:
        self._user_id = _require_env("NBH_USER_ID")
        self._society_id = _require_env("NBH_SOCIETY_ID")
        self._device_id = _require_env("NBH_DEVICE_ID")
        self._remember_me = _require_env("NBH_REMEMBER_ME")
        self._jsessionid = _require_env("NBH_JSESSIONID")
        self._city_id = _require_env("NBH_CITY_ID")
        self._app_version = os.environ.get("NBH_APP_VERSION", "691")

        self._session = requests.Session()
        self._session.headers.update(self._common_headers())
        cookies = {
            "remember-me": self._remember_me,
            "JSESSIONID": self._jsessionid,
        }
        # Optional analytics cookies — present in captured app traffic.
        # Set NBH_GA, NBH_GA_SESSION, NBH_GCL_AU to match the original requests.
        if ga := os.environ.get("NBH_GA"):
            cookies["_ga"] = ga
        if ga_session := os.environ.get("NBH_GA_SESSION"):
            cookies["_ga_XCR3CRK12Z"] = ga_session
        if gcl_au := os.environ.get("NBH_GCL_AU"):
            cookies["_gcl_au"] = gcl_au
        self._session.cookies.update(cookies)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def pre_approve(
        self,
        company: str,
        *,
        apartment_id: str,
        duration_hours: float | None = None,
        in_time: datetime | None = None,
        out_time: datetime | None = None,
        vehicle_type: str = "FOUR_WHEELER",
        visitor_name: str = "",
        visitor_phone: str = "",
    ) -> dict:
        """
        Pre-approve a delivery from *company*.

        Args:
            company:        Delivery company name, e.g. "Zepto", "Dominos", or
                            the literal "Any" to admit deliveries from any/
                            every brand under one approval window — this is
                            not a validation shortcut, it's the exact value
                            the resident app itself sends for its built-in
                            "any company" option.
            duration_hours: How long the window stays open.  Defaults to the
                            known default for the company, or 1 hour.
            in_time:        When the window opens.  Defaults to now (rounded
                            to the current minute).
            vehicle_type:   "FOUR_WHEELER" or "TWO_WHEELER".
            visitor_name:   Visitor name (usually left blank for deliveries).
            visitor_phone:  Visitor phone (usually left blank for deliveries).

        Returns:
            Parsed JSON response from the API.
        """
        key = (
            company.lower()
            .replace(" ", "")
            .replace("-", "")
            .replace("_", "")
            .replace("'", "")
        )
        # Resolve to the canonical display name the API expects (e.g. "Blinkit"
        # not "blinkit") so it renders correctly in the guard's app.
        display_name = COMPANY_DISPLAY_NAMES.get(key, company)

        if in_time is None:
            in_time = datetime.now(_IST).replace(second=0, microsecond=0, tzinfo=None)

        if out_time is not None:
            # Explicit end time overrides --hours and per-company defaults.
            duration_hours = (out_time - in_time).total_seconds() / 3600
            if duration_hours <= 0:
                raise ValueError("--out must be after --in (or after now).")
        elif duration_hours is None:
            looked_up = KNOWN_COMPANIES.get(key)
            if looked_up is None and key not in KNOWN_COMPANIES:
                # Completely unknown company — default to 1 hour
                looked_up = 1.0
            if looked_up is None:
                raise ValueError(
                    f"'{company}' has no default approval duration. "
                    "Please supply an explicit duration_hours."
                )
            duration_hours = looked_up

        if duration_hours is MIDNIGHT or duration_hours == MIDNIGHT:
            midnight = in_time.replace(hour=23, minute=59, second=0, microsecond=0)
            duration_hours = (midnight - in_time).total_seconds() / 3600

        req = VisitRequest(
            visitor=VisitorInfo(
                company=display_name,
                name=visitor_name,
                phone=visitor_phone,
            ),
            expected_in=in_time,
            duration_hours=duration_hours,
            vehicle_type=vehicle_type,
        )

        payload = {
            "apartmentId": apartment_id,
            "expectedInTime": req.format_time(req.expected_in),
            "expectedOutTime": req.format_time(req.expected_out),
            "isPrivate": str(req.is_private).lower(),
            "noOfVisitsInaDay": str(req.no_of_visits_in_day),
            "vehicleType": req.vehicle_type,
            "visitorInfo": json.dumps(
                [req.visitor.to_api_dict()], separators=(",", ":")
            ),
            "visitorType": req.visitor_type,
        }
        return self._post(
            "/api/v1/secured/visit/request",
            data=payload,
            content_type="application/x-www-form-urlencoded",
            extra_headers={"apartmentId": apartment_id},
        )

    def cancel_visit(self, visit_id: str, *, apartment_id: str) -> dict:
        """
        Cancel a pre-approved visit.

        Args:
            visit_id:     The visit ID returned when the visit was created.
            apartment_id: The apartment ID the visit belongs to.

        Returns:
            Parsed JSON response from the API.
        """
        return self._post(
            "/api/v1/secured/visit/update",
            data={"status": "0", "visitId": visit_id},
            content_type="application/x-www-form-urlencoded",
            extra_headers={"apartmentId": apartment_id},
        )

    def list_expected(
        self,
        *,
        apartment_id: str,
        page: int = 1,
        page_size: int = 5,
        sort_order: str = "asc",
    ) -> dict:
        """
        List upcoming / expected visits.

        Args:
            apartment_id: The apartment ID to list visits for.
            page:         Page number (1-indexed).
            page_size:    Results per page.
            sort_order:   "asc" or "desc".

        Returns:
            Parsed JSON response from the API.
        """
        params = {
            "apartmentId": apartment_id,
            "page": page,
            "pageSize": page_size,
            "societyId": self._society_id,
            "sortOrder": sort_order,
        }
        return self._get(
            "/api/v3/secured/visit/all/expected",
            params=params,
            extra_headers={"apartmentId": apartment_id},
        )

    def list_visits(
        self,
        *,
        apartment_id: str,
        page: int = 1,
        page_size: int = 10,
    ) -> dict:
        """
        List all visits for an apartment: current (at gate), expired (past), and denied.

        Args:
            apartment_id: The apartment ID to list visits for.
            page:         Page number (1-indexed). Applies to all three lists.
            page_size:    Results per page.

        Returns:
            Parsed JSON response from the API. The ``data`` key contains:
              - current:        visitors presently at the gate
              - currentTotal:   total count
              - expired:        completed past visits
              - expiredTotal:   total count
              - denied:         denied entry attempts
              - deniedTotal:    total count
              - pending:        pre-approved visits not yet arrived
              - pendingTotal:   total count
              - *VisitRatings:  rating prompts for each category
        """
        params = {
            "apartmentId": apartment_id,
            "societyId": self._society_id,
            "page": page,
            "pageSize": page_size,
        }
        return self._get(
            "/api/v2/secured/visit/all",
            params=params,
            extra_headers={"apartmentId": apartment_id},
        )

    def register_device(
        self,
        *,
        apartment_id: str,
        model: str = "iPhone18,2",
        os_sdk: str = "26.4",
        product: str = "APPLE",
        device_type: str = "IPHONE",
    ) -> dict:
        """
        Register (or re-register) the device with the API.

        Usually only needed once; the defaults match the original curl.
        """
        return self._post(
            "/api/v1/device-info/android/register",
            data={
                "appVersion": self._app_version,
                "deviceId": self._device_id,
                "model": model,
                "osSdk": os_sdk,
                "product": product,
                "trackId": self._device_id,
                "type": device_type,
            },
            content_type="application/x-www-form-urlencoded",
            extra_headers={"apartmentId": apartment_id},
        )

    def get_user_multiprofile_info(self) -> dict:
        """
        Fetch the authenticated user's multiprofile information.

        Returns user details, family members, all apartments the user has
        access to (with ownership type), notification settings, pass codes,
        and other profile-related configuration.

        Returns:
            Parsed JSON response from the API.
        """
        return self._get(f"/api/v2/user/secured/multiprofile/info/{self._user_id}")

    def get_home_content(
        self, *, apartment_id: str, screen: str = "NewHoodHomeViewController"
    ) -> dict:
        """
        Fetch home-screen content / jacket data.

        Args:
            apartment_id: The apartment ID to fetch home content for.
            screen:       The screen identifier passed to the jacket endpoint.

        Returns:
            Parsed JSON response from the API.
        """
        body = {
            "sP": screen,
            "uId": self._user_id,
            "business": "HOOD",
            "typeToAudienceIdsMap": {
                "APARTMENT": [apartment_id],
                "SOCIETY": [self._society_id],
                "CITY": [os.environ.get("NBH_CITY_AUDIENCE_ID", "")],
                "COUNTRY": ["IN"],
            },
            "isAdmin": False,
        }
        return self._post(
            "/api/v1/jacket/get",
            json=body,
            extra_headers={"apartmentId": apartment_id},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _common_headers(self) -> dict:
        return {
            "Host": "www.nobrokerhood.com",
            "appId": "RESIDENT",
            "Accept": "*/*",
            "userId": self._user_id,
            "appVersion": self._app_version,
            "Accept-Language": "en-IN,en;q=0.9",
            "tenant": "RESIDENT",
            "cityId": self._city_id,
            "deviceId": self._device_id,
            "societyId": self._society_id,
            "User-Agent": "APPLE-iPhone18,2-iOS-26.4-6.9.1",
            "Connection": "keep-alive",
        }

    def _post(
        self,
        path: str,
        *,
        data: dict | None = None,
        json: dict | None = None,
        content_type: str | None = None,
        extra_headers: dict | None = None,
    ) -> dict:
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        if extra_headers:
            headers.update(extra_headers)
        # Pre-encode form data to match the app's wire format:
        # slashes unencoded (safe for DD/MM/YYYY dates), spaces as %20 not +.
        body = (
            urllib.parse.urlencode(data, safe="/", quote_via=urllib.parse.quote)
            if data is not None and content_type == "application/x-www-form-urlencoded"
            else data
        )
        resp = self._session.post(
            _BASE_URL + path, data=body, json=json, headers=headers
        )
        return self._handle(resp)

    def _get(
        self,
        path: str,
        *,
        params: dict | None = None,
        extra_headers: dict | None = None,
    ) -> dict:
        resp = self._session.get(_BASE_URL + path, params=params, headers=extra_headers)
        return self._handle(resp)

    @staticmethod
    def _handle(resp: requests.Response) -> dict:
        req = resp.request
        logger.debug(
            "Request: %s %s\nHeaders: %s\nBody: %s",
            req.method,
            req.url,
            dict(req.headers),
            req.body,
        )
        logger.debug(
            "Response: %s\nHeaders: %s\nBody: %s",
            resp.status_code,
            dict(resp.headers),
            resp.text,
        )
        logger.info("%s %s → %s", req.method, req.url, resp.status_code)

        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text}

        if resp.status_code in (401, 403):
            raise AuthError(
                "Authentication failed — check NBH_REMEMBER_ME and NBH_JSESSIONID. "
                f"HTTP {resp.status_code}",
                response_body=body,
            )
        if not resp.ok:
            raise APIError(resp.status_code, resp.text[:200], response_body=body)
        return body


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise OSError(
            f"Required environment variable '{name}' is not set. "
            "See .env.example for a full list of required variables."
        )
    return value
