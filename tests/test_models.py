from datetime import datetime, timedelta

from nobrokerhood.companies import COMPANY_DISPLAY_NAMES, KNOWN_COMPANIES
from nobrokerhood.models import VisitorInfo, VisitRequest


class TestVisitorInfo:
    def test_to_api_dict(self):
        v = VisitorInfo(company="Zepto", name="John", phone="1234567890")
        d = v.to_api_dict()
        assert d == {
            "company": "Zepto",
            "name": "John",
            "phone": "1234567890",
            "pickup": "false",
        }

    def test_to_api_dict_pickup_true(self):
        v = VisitorInfo(company="Amazon", pickup=True)
        assert v.to_api_dict()["pickup"] == "true"


class TestVisitRequest:
    def test_expected_out(self):
        t = datetime(2026, 4, 16, 10, 0)
        req = VisitRequest(
            visitor=VisitorInfo(company="Zepto"),
            expected_in=t,
            duration_hours=2.0,
        )
        assert req.expected_out == t + timedelta(hours=2)

    def test_format_time(self):
        t = datetime(2026, 4, 16, 9, 5)
        req = VisitRequest(
            visitor=VisitorInfo(company="Zepto"),
            expected_in=t,
        )
        assert req.format_time(t) == "16/04/2026 09:05"


class TestCompanyData:
    def test_all_known_companies_have_display_names(self):
        missing = set(KNOWN_COMPANIES) - set(COMPANY_DISPLAY_NAMES)
        assert not missing, (
            f"KNOWN_COMPANIES keys missing from COMPANY_DISPLAY_NAMES: {missing}"
        )

    def test_known_companies_values_are_valid(self):
        for key, val in KNOWN_COMPANIES.items():
            assert val is None or isinstance(val, int | float | str), (
                f"KNOWN_COMPANIES[{key!r}] has unexpected type: {type(val)}"
            )
