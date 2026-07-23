from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from app.agents.recommendation_search.state import WeaknessSearchResult


class CollaborationAgentState(TypedDict, total=False):

    
    company_id: int
    search_set_id: int
    bid_notice_id: int

    
    weaknesses: list[str]
    can_resolve: bool
    gap_description: str
    judge_reason: str
    branch: str

    
    partner_id: int
    to: str
    subject: str
    body: str
    approved: bool
    status: str
    sent_result: dict

    
    search_results: Annotated[list[WeaknessSearchResult], operator.add]
    report: str
