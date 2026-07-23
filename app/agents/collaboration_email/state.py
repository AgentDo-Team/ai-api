from __future__ import annotations

from typing import TypedDict


class CollaborationEmailState(TypedDict, total=False):

    company_id: int
    partner_id: int
    bid_notice_id: int
    gap_description: str

    to: str
    subject: str
    body: str

    approved: bool
    status: str
    sent_result: dict
