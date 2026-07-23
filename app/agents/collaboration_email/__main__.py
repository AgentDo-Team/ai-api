from __future__ import annotations

import asyncio
import logging

from langgraph.types import Command

from app.agents.collaboration_email.graph import build_collaboration_email_graph

# 검증 대상 입력 (DB 에 존재하는 id 로 바꿔서 실행)
SAMPLE_COMPANY_ID = 1
SAMPLE_PARTNER_ID = 1
SAMPLE_BID_NOTICE_ID = 1
SAMPLE_GAP = "공고가 요구하는 대규모 공공 클라우드 전환 구축 실적이 회사에 없음"

# True 로 바꾸면 승인 → 실제 Gmail 발송까지 진행한다.
APPROVE = False


async def main() -> None:
    graph = build_collaboration_email_graph()
    config = {"configurable": {"thread_id": "collab-email-demo"}}

    # 1) compose → human_review 에서 interrupt 로 멈춘다.
    result = await graph.ainvoke(
        {
            "company_id": SAMPLE_COMPANY_ID,
            "partner_id": SAMPLE_PARTNER_ID,
            "bid_notice_id": SAMPLE_BID_NOTICE_ID,
            "gap_description": SAMPLE_GAP,
        },
        config=config,
    )

    interrupts = result.get("__interrupt__")
    if not interrupts:
        print("interrupt 없이 종료됨:", result)
        return

    payload = interrupts[0].value
    draft = payload["draft"]
    print("\n" + "=" * 60)
    print("협업 제안 메일 초안 (HITL 검수)")
    print("=" * 60)
    print(f"수신자: {draft['to']}")
    print(f"제목  : {draft['subject']}")
    print(f"본문  :\n{draft['body']}")
    print("=" * 60)
    print(f"안내: {payload['message']}")

    # 2) 승인/취소로 재개한다. (프론트에서는 이 값을 사용자 선택으로 받는다)
    final = await graph.ainvoke(Command(resume={"approved": APPROVE}), config=config)

    print("\n최종 상태:", final.get("status"))
    if final.get("status") == "sent":
        print("Gmail message id:", final.get("sent_result", {}).get("id"))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
