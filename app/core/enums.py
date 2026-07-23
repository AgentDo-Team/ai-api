import enum

class ParseStatus(str, enum.Enum):
    PENDING = "PENDING" 
    CHUNKED = "CHUNKED"  
    EMBEDDED = "EMBEDDED"
    ERROR = "ERROR"     

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
        return self.value

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

class SearchSetStatus(str, enum.Enum):
    ONGOING_SECOND_FILTER = "ongoing_second_filter"  
    ONGOING_THIRD_FILTER = "ongoing_third_filter"  
    COMPLETED = "completed"  
    FAILED = "failed" 
    ONGOING_REPORT_GENERATION = "ongoing_report_generation"  
 
