# 예시: app/core/lifespan.py (FastAPI가 켜질 때 자동으로 스케줄러 실행)
# from apscheduler.schedulers.asyncio import AsyncIOScheduler

# async def start_scheduler():
#     scheduler = AsyncIOScheduler()
#     # 매일 새벽 3시에 자동 실행
#     scheduler.add_job(run_chunking_pipeline, 'cron', hour=3)
#     scheduler.start()