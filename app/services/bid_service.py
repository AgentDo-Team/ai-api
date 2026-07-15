import re
import time
from datetime import datetime, timedelta
from pathlib import Path
import requests
import time


from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.db.models.bid import BidNotice, ParseStatus
from app.db.repositories.bid_respository import BidNoticeRepository
from app.rag.loaders.kordoc_loader import parse_file, resolve_kordoc_cmd
from app.utils.file_utils import get_priority
from app.clients.g2b_client import fetch_page

class BidService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.bid_repo = BidNoticeRepository(session)

    def collect_bids(self, days_back=7):
        """API 데이터를 수집하고 정형 데이터를 추출합니다."""
        SERVICE_KEY = "18dbc10d66b4f8764dcc5ada60ebe8550b7232c4a4883480afd6c24d8c5aed78"
        BASE_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc"
        
        SI_domain_codes = [
            '81111513', '81111595', '81111596', '81111594', '81111599', '81111598', 
            '81112002', '80101507', '80101698', '81111799', '81111801', '81111809', 
            '81111708', '81151699', '81111899', '81112399', '81112299', '81111811', 
            '81112199', '80141619'
        ]

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        bgn_dt = start_date.strftime("%Y%m%d0000")
        end_dt = end_date.strftime("%Y%m%d2359")

        print(f"📡 [1단계] 나라장터 API 공고 수집 시작 ({bgn_dt} ~ {end_dt})...")
        raw_items = []
        
        with requests.Session() as session:
            page_no = 1
            while True:
                try:
                    data = fetch_page(session, BASE_URL, SERVICE_KEY, bgn_dt, end_dt, page_no)
                    items = data.get('response', {}).get('body', {}).get('items', [])
                    if not items: break
                    raw_items.extend(items)
                    
                    total_count = data.get('response', {}).get('body', {}).get('totalCount', 0)
                    if len(raw_items) >= total_count: break
                    page_no += 1
                    time.sleep(0.1)
                except Exception as e:
                    print(f"API 에러: {e}")
                    break

        filtered_results = []
        seen = set()
        
        def parse_dt(dt_str):
            try:
                return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S") if dt_str else None
            except:
                return None

        for item in raw_items:
            bid_no = item.get('bidNtceNo')
            clsfc_no = item.get('pubPrcrmntClsfcNo')
            
            if bid_no in seen or clsfc_no not in SI_domain_codes:
                continue
                
            seen.add(bid_no)
            
            rfp_candidates = []
            for i in range(1, 21):
                file_nm = item.get(f"ntceSpecFileNm{i}", "")
                file_url = item.get(f"ntceSpecDocUrl{i}", "")
                
                if "제안" in file_nm:
                    priority = get_priority(file_nm)
                    if priority <= 3: 
                        rfp_candidates.append({
                            "fileName": file_nm, 
                            "downloadUrl": file_url,
                            "priority": priority
                        })
            
            if rfp_candidates:
                rfp_candidates.sort(key=lambda x: x["priority"])
                best_rfp = rfp_candidates[0]
                bid_deadline = parse_dt(item.get('bidClseDt'))
                
                # 마감일이 없거나, 이미 지났는지 체크 (현재 시각과 비교)
                # None이거나, 현재 시간보다 과거라면 건너뜀
                if not bid_deadline or bid_deadline < datetime.now():
                    continue
                
                filtered_results.append({
                    "notice_no": bid_no,
                    "title": item.get('bidNtceNm', ''),
                    "demand_org": item.get('dminsttNm'),
                    "budget_krw": int(item.get('asignBdgtAmt', 0)) if item.get('asignBdgtAmt') else None,
                    "procurement_clsfc_no": clsfc_no,
                    "procurement_clsfc_nm": item.get('pubPrcrmntClsfcNm'),
                    "joint_venture_method": item.get('cmmnSpldmdMethdNm'),
                    "bid_deadline": bid_deadline,
                    "rfp_file_url": best_rfp["downloadUrl"],
                    "fileName": best_rfp["fileName"] 
                })

        print(f"✔️ 정형 데이터 필터링 완료: 총 {len(filtered_results)}건")
        return filtered_results

    async def process_and_save_bids(self, results, out_dir="pipeline_out"):
        """파일을 다운로드/파싱한 후, 주입받은 self.session을 통해 DB에 적재합니다."""
        base_dir = Path(out_dir)
        dl_dir = base_dir / "downloads"
        dl_dir.mkdir(parents=True, exist_ok=True)
        
        kordoc_cmd = resolve_kordoc_cmd()
        if not kordoc_cmd:
            print(" kordoc이 설치되어 있지 않습니다.")
            return

        # 💡 생성자에서 받은 self.session 사용!
        for r in results:
            print(f"\n[{r['notice_no']}] 처리 중: {r['title']}")
            
            existing = await self.bid_repo.get_by_notice_no(r['notice_no'])
            if existing:
                print(f"  [건너뜀] 이미 DB에 존재하는 공고입니다.")
                continue

            # 파일 다운로드
            safe_name = f"{r['notice_no']}_{re.sub(r'[\\\\/:*?\"<>|]', '_', r['fileName'])}"
            local_path = dl_dir / safe_name
            
            download_success = False
            if not local_path.exists():
                try:
                    resp = requests.get(r["rfp_file_url"], timeout=60)
                    resp.raise_for_status()
                    local_path.write_bytes(resp.content)
                    download_success = True
                except Exception as e:
                    print(f"  [다운로드 실패] {e}")
            else:
                download_success = True

            # 마크다운 파싱
            md_text = None
            status = ParseStatus.ERROR
            
            if download_success:
                parse_res = parse_file(local_path, kordoc_cmd)
                if parse_res.status == "ok" and parse_res.markdown:
                    md_text = parse_res.markdown
                    status = ParseStatus.PENDING 
                    print(f"  [파싱 성공] 크기: {len(md_text)} bytes")
                else:
                    print(f"  [파싱 실패] {parse_res.status}")
            # 파싱된 텍스트가 없으면 저장을 건너뜀
            if not md_text:
                print(f"  [경고] 파싱된 내용이 없어 저장하지 않습니다: {r['notice_no']}")
                continue

            new_notice = BidNotice(
                notice_no=r["notice_no"],
                title=r["title"],
                demand_org=r["demand_org"],
                budget_krw=r["budget_krw"],
                procurement_clsfc_no=r["procurement_clsfc_no"],
                procurement_clsfc_nm=r["procurement_clsfc_nm"],
                joint_venture_method=r["joint_venture_method"],
                bid_deadline=r["bid_deadline"],
                rfp_file_url=r["rfp_file_url"],
                raw_md_text=md_text,
                parse_status=status
            )
            
            try:
                await self.bid_repo.add(new_notice)
                await self.session.commit()
                print(f"[DB 저장 완료] ID: {new_notice.id}")
            except IntegrityError:
                await self.session.rollback()
                print("[DB 에러] 중복 키 또는 무결성 제약 조건 위반")
            except Exception as e:
                await self.session.rollback()
                print(f"[DB 처리 중 알 수 없는 에러] {e}")

        print(f"\n 파이프라인(수집 -> 파싱 -> DB 저장) 완료!")

    # 비동기 실행을 위한 진입점 래핑
    async def run_bid_pipeline(self):
        pipeline_start_time = time.time()
        print("🚀 [백그라운드] 공고 수집 및 파싱 파이프라인 시작...")

        bid_results = self.collect_bids(days_back=30)
        if bid_results:
            await self.process_and_save_bids(bid_results)
        else:
            print("조건에 맞는 공고가 없습니다.")
        pipeline_end_time = time.time()
        elapsed_seconds = pipeline_end_time - pipeline_start_time
        minutes, seconds = divmod(elapsed_seconds, 60)
        
        print(f"\n✅ [백그라운드] 공고 수집 및 파싱 파이프라인 작업이 모두 완료!")
        print(f"⏱️  총 소요 시간: {int(minutes)}분 {seconds:.2f}초")