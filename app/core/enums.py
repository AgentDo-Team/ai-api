import enum

# BidNotice 관련
# 공고 파싱 상태
class ParseStatus(str, enum.Enum):
    PENDING = "PENDING"  # 파싱 완료, 청킹 대기 중
    CHUNKED = "CHUNKED"  # 청킹 및 벡터 DB 저장 완료
    EMBEDDED = "EMBEDDED" # 임베딩 완료
    ERROR = "ERROR"      # 파싱 또는 처리 중 에러 발생

# CompanyProfile 관련
# 기업 규모
class CompanyScale(str, enum.Enum):
    LARGE = "LARGE"
    MIDDLE = "MIDDLE"
    SMALL = "SMALL"

    @property
    def description(self) -> str:
        mapping = {
            "LARGE": "대기업",
            "MIDDLE": "중견기업",
            "SMALL": "중소기업",
        }
        return mapping.get(self.value, "")

# 기업신용평가등급
class CreditRating(str, enum.Enum):
    AAA = "AAA"
    AA_PLUS = "AA+"
    AA_ZERO = "AA0"
    AA_MINUS = "AA-"
    A_PLUS = "A+"
    A_ZERO = "A0"
    A_MINUS = "A-"
    BBB_PLUS = "BBB+"
    BBB_ZERO = "BBB0"
    BBB_MINUS = "BBB-"
    BB_PLUS = "BB+"
    BB_ZERO = "BB0"
    BB_MINUS = "BB-"
    B_PLUS = "B+"
    B_ZERO = "B0"
    B_MINUS = "B-"
    CCC_PLUS = "CCC+"

    @property
    def description(self) -> str:
        # 신용등급은 값 자체가 설명이므로 그대로 반환합니다.
        return self.value

# sp등급
class SpGrade(str, enum.Enum):
    GRADE_3 = "3"
    GRADE_2 = "2"
    GRADE_1 = "1"

    @property
    def description(self) -> str:
        mapping = {
            "3": "SP인증 3등급/CMMI·SPICE 4~5",
            "2": "SP인증 2등급/CMMI·SPICE 2~3",
            "1": "SP인증 1등급",
        }
        return mapping.get(self.value, "")
    

# BidNotice 관련
# 도메인 분류코드 (나라장터 품목분류번호). 멤버명은 코드값 그 자체(키), value는 프론트
# 표시용 한글명. 코드가 숫자로 시작해 class 본문 문법(식별자)으로는 못 쓰므로 함수형
# Enum 생성 방식을 쓴다. 시스템 내부(BidNotice.procurement_clsfc_no 등 DB 컬럼)에서는
# 코드 문자열 그대로 다루다가, 조회 시 ProcurementCategory[code].value 로 한글명을 얻는다.
ProcurementCategory = enum.Enum(
    "ProcurementCategory",
    {
        "81111513": "클라우드서비스",
        "81111595": "클라우드지원서비스",
        "81111596": "클라우드융합서비스",
        "81111594": "생성형AI업무지원서비스",
        "81111599": "정보시스템개발서비스",
        "81111598": "패키지소프트웨어개발및도입서비스",
        "81112002": "데이터서비스",
        "80101507": "정보화전략계획서비스",
        "80101698": "정보화프로젝트관리서비스(PMO)",
        "81111799": "정보인프라구축서비스",
        "81111801": "컴퓨터네트워크또는인터넷보안서비스",
        "81111809": "컴퓨터시스템설치",
        "81111708": "정보통신설계용역",
        "81151699": "공간정보DB구축서비스",
        "81111899": "정보시스템유지관리서비스",
        "81112399": "전산장비유지관리서비스",
        "81112299": "소프트웨어유지및지원서비스",
        "81111811": "운영위탁서비스",
        "81112199": "인터넷지원개발서비스",
        "80141619": "고객센터운영서비스",
    },
    type=str,
)


# ChatMessage의 role

# SearchSet의 status