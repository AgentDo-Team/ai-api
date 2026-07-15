from dataclasses import dataclass, field, asdict
from pydantic import BaseModel, Field
from typing import List, Literal


@dataclass
class ParseResult:
    source: str
    fmt: str = ""
    status: str = "ok"
    markdown: str = ""
    table_count: int = 0
    char_count: int = 0

class ExtractedHeader(BaseModel):
    exact_header: str = Field(
        description="목차에 기재된 정확한 헤더명 (페이지 번호나 점(......)은 제외한 순수 텍스트, 예: '1. 제안요청 개요')"
    )
    l_topic: Literal["개요", "요구사항", "평가기준", "기타"] = Field(
        description="분류된 대분류명"
    )
    s_topic: str = Field(
        description="헤더의 의미를 분석하여 생성한 대표 소분류명"
    )

class DocumentStructure(BaseModel):
    headers: List[ExtractedHeader] = Field(
        description="문서 목차에 등장하는 상위 헤더 목록 (서식, 붙임 등 부록 제외)"
    )