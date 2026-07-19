from scripts.evaluation.finalize_second_filter_labels import final_decision


def row(content: str, notice: int = 3, topic: str = "요구사항") -> dict[str, str]:
    return {
        "content": content,
        "notice_relevance": str(notice),
        "l_topic": topic,
        "dense_rank": "1",
        "bm25_rank": "1",
        "rrf_rank": "1",
    }


def test_direct_rag_requirement_is_grade_three() -> None:
    decision = final_decision(
        row("요구사항 상세설명 RAG 기반 내부 문서 지식 검색과 LLM 질의응답 서비스를 구축한다.")
    )
    assert decision.grade == 3


def test_notice_grade_caps_chunk_grade() -> None:
    decision = final_decision(
        row("RAG 기반 내부 문서 검색과 LLM 자연어 질의응답 서비스를 구축한다.", notice=2)
    )
    assert decision.grade == 2


def test_generic_security_clause_is_zero_even_with_system_word() -> None:
    decision = final_decision(
        row("보안 요구사항 정보시스템 구축 운영 지침과 개인정보 암호화 기준을 준수해야 한다.")
    )
    assert decision.grade == 0


def test_integrated_data_dashboard_is_grade_two() -> None:
    decision = final_decision(
        row("기관 데이터를 통합 분석하여 의사결정 지원 대시보드를 구축하고 데이터 연계를 자동화한다.")
    )
    assert decision.grade == 2


def test_retrieval_rank_does_not_change_final_grade() -> None:
    high_rank = row("일반 교육 일정과 산출물 제출 방법을 설명한다.")
    low_rank = dict(high_rank, dense_rank="100", bm25_rank="100", rrf_rank="100")
    assert final_decision(high_rank).grade == final_decision(low_rank).grade == 0


def test_irrelevant_notice_forces_zero() -> None:
    decision = final_decision(
        row("RAG 기반 LLM 질의응답 서비스를 구축한다.", notice=0)
    )
    assert decision.grade == 0


def test_ai_infrastructure_is_adjacent_grade_two() -> None:
    decision = final_decision(
        row("AI 서버 구성 요구사항 상세설명 LLM 학습과 RAG 임베딩용 GPU 서버를 구축한다.")
    )
    assert decision.grade == 2


def test_current_equipment_inventory_is_not_core_match() -> None:
    decision = final_decision(
        row("서버명 모델 네트워크 운영체계 DB 서버와 RAG 운영 서버의 현재 사양 목록", topic="개요")
    )
    assert decision.grade <= 1


def test_contract_overview_does_not_inherit_notice_relevance() -> None:
    decision = final_decision(
        row("사업 기간은 계약일로부터 6개월이며 계약 방법은 제한경쟁입찰로 한다.", topic="개요")
    )
    assert decision.grade == 0


def test_ai_meeting_minutes_is_adjacent_grade_two() -> None:
    decision = final_decision(
        row("요구사항 명칭 AI 회의록 시스템 요구사항 상세설명 음성 전사와 회의 요약 기능을 구현한다.")
    )
    assert decision.grade == 2


def test_negated_integration_does_not_get_grade_two() -> None:
    decision = final_decision(
        row("환불자를 관리하며 합격자통합관리시스템 연계 제외 대상은 직접 입력한다.")
    )
    assert decision.grade <= 1


def test_substantive_generic_function_requirement_is_grade_one() -> None:
    decision = final_decision(
        row("기능요구사항 상세설명 환불 대상 정보를 입력, 수정, 삭제하고 엑셀로 내려받는 관리 화면을 구현한다.", notice=2)
    )
    assert decision.grade == 1
