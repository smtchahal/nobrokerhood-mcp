from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class VisitorInfo:
    company: str
    name: str = ""
    phone: str = ""
    pickup: bool = False

    def to_api_dict(self) -> dict:
        return {
            "company": self.company,
            "name": self.name,
            "phone": self.phone,
            "pickup": str(self.pickup).lower(),
        }


@dataclass
class VisitRequest:
    visitor: VisitorInfo
    expected_in: datetime
    duration_hours: float = 1.0
    is_private: bool = True
    no_of_visits_in_day: int = 1
    vehicle_type: str = "FOUR_WHEELER"
    visitor_type: str = "DELIVERY"

    @property
    def expected_out(self) -> datetime:
        return self.expected_in + timedelta(hours=self.duration_hours)

    def format_time(self, dt: datetime) -> str:
        """Returns time in the format the API expects: DD/MM/YYYY HH:MM"""
        return dt.strftime("%d/%m/%Y %H:%M")
