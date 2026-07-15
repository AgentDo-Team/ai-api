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
# 도메인 분류코드
# class ProcurementCategory(str, enum.Enum):
#     CLOUD_SERVICE = "81111513"
#     CLOUD_SUPPORT = "81111595"
#     CLOUD_CONVERGENCE = "81111596"
#     GEN_AI_SUPPORT = "81111594"
#     IS_DEV = "81111599"
#     PKG_SW_DEV = "81111598"
#     DATA_SERVICE = "81112002"
#     ISP_SERVICE = "80101507"
#     PMO_SERVICE = "80101698"
#     INFRA_BUILD = "81111799"
#     NETWORK_SECURITY = "81111801"
#     SYS_INSTALL = "81111809"
#     COMM_DESIGN = "81111708"
#     SPATIAL_DB = "81151699"
#     IS_MAINTENANCE = "81111899"
#     HW_MAINTENANCE = "81112399"
#     SW_MAINTENANCE = "81112299"
#     OPER_TRUST = "81111811"
#     WEB_SUPPORT = "81112199"
#     CS_OPER = "80141619"

#     @property
#     def description(self) -> str:
#         mapping = {
#             "81111513": "클라우드서비스",
#             "81111595": "클라우드지원서비스",
#             "81111596": "클라우드융합서비스",
#             "81111594": "생성형AI업무지원서비스",
#             "81111599": "정보시스템개발서비스",
#             "81111598": "패키지소프트웨어개발및도입서비스",
#             "81112002": "데이터서비스",
#             "80101507": "정보화전략계획서비스",
#             "80101698": "정보화프로젝트관리서비스(PMO)",
#             "81111799": "정보인프라구축서비스",
#             "81111801": "컴퓨터네트워크또는인터넷보안서비스",
#             "81111809": "컴퓨터시스템설치",
#             "81111708": "정보통신설계용역",
#             "81151699": "공간정보DB구축서비스",
#             "81111899": "정보시스템유지관리서비스",
#             "81112399": "전산장비유지관리서비스",
#             "81112299": "소프트웨어유지및지원서비스",
#             "81111811": "운영위탁서비스",
#             "81112199": "인터넷지원개발서비스",
#             "80141619": "고객센터운영서비스",
#         }
#         return mapping.get(self.value, "알 수 없는 분류")
    
# ChatMessage의 role

# SearchSet의 status