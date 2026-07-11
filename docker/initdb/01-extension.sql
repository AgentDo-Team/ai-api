-- 컨테이너 최초 기동 시 edudb DB 에 pgvector 확장을 생성한다.
-- (docker-entrypoint-initdb.d 는 데이터 디렉터리가 비어있는 최초 1회만 실행됨)
CREATE EXTENSION IF NOT EXISTS vector;
