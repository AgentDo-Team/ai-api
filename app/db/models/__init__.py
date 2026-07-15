"""SQLModel ORM 모델 정의.

이 모듈을 import 하면 모든 테이블이 SQLModel.metadata 에 등록된다.
스키마 생성(create_all) 전에 반드시 import 되어야 한다.
"""

from app.db.models.analysis import AnalysisResult, ChatMessage
from app.db.models.bid import BidNotice, Chunk
from app.db.models.company import Company, CompanyProfile, CompanyProject
from app.db.models.reference import EvalCriteriaReference
from app.db.models.search import DomainCode, HardFilter, SearchSet

__all__ = [
    "Company",
    "CompanyProfile",
    "CompanyProject",
    "SearchSet",
    "HardFilter",
    "DomainCode",
    "BidNotice",
    "Chunk",
    "AnalysisResult",
    "ChatMessage",
    "EvalCriteriaReference",
]
