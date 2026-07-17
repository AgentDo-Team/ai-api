# app/db/models/__init__.py
# 명시적으로 모델들을 하나씩 다 불러옵니다.
from app.db.models.proposal_drafts import ProposalDraft
from app.db.models import BidNotice, Chunk, Company, SearchSet, AnalysisResult, HardFilter

# 이제 SQLModel이 이 모듈들을 읽을 때 자동으로 명부에 등록합니다.
__all__ = ["BidNotice", "Chunk", "Company", "SearchSet", "AnalysisResult", "ProposalDraft", "HardFilter"]