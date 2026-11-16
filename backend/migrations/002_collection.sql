-- 002_collection: 可恢复采集（卷/块/隔离/入库溯源）。结构以 SQLAlchemy metadata create_all 为准，本文件仅为说明。
-- log_volumes: 每(卷名,代次)一行；identity 卷身份指纹，offset 已消费字节，lines 已消费记录行，
--   pending 待补齐半条记录原始字节，status active/paused/sealed，error 暂停原因。
-- log_chunks: (volume_id,chunk_id) 唯一幂等台账，记录已应用块的基偏移/长度/入库与隔离数，崩溃重发不重复入库。
-- log_quarantine: 坏记录与卷尾/回退半条记录隔离，raw 保留原文，reason 说明。
-- log_ingest: reading_id 唯一，读数 ← 卷行号/块 的溯源。
CREATE TABLE IF NOT EXISTS log_volumes (
  id SERIAL PRIMARY KEY,
  study_id INTEGER NOT NULL REFERENCES flow_studies(id),
  volume_key VARCHAR(180) NOT NULL,
  generation INTEGER NOT NULL,
  identity VARCHAR(120) NOT NULL,
  offset BIGINT NOT NULL DEFAULT 0,
  lines INTEGER NOT NULL DEFAULT 0,
  pending BYTEA NOT NULL DEFAULT ''::bytea,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_log_volumes_key_generation UNIQUE (volume_key, generation)
);
CREATE TABLE IF NOT EXISTS log_chunks (
  id SERIAL PRIMARY KEY,
  volume_id INTEGER NOT NULL REFERENCES log_volumes(id),
  chunk_id VARCHAR(120) NOT NULL,
  base_offset BIGINT NOT NULL,
  length INTEGER NOT NULL,
  stored INTEGER NOT NULL DEFAULT 0,
  quarantined INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_log_chunks_volume_chunk UNIQUE (volume_id, chunk_id)
);
CREATE TABLE IF NOT EXISTS log_quarantine (
  id SERIAL PRIMARY KEY,
  volume_id INTEGER NOT NULL REFERENCES log_volumes(id),
  line_no INTEGER,
  raw TEXT NOT NULL,
  reason VARCHAR(200) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS log_ingest (
  id SERIAL PRIMARY KEY,
  reading_id INTEGER NOT NULL REFERENCES pressure_readings(id),
  volume_id INTEGER NOT NULL REFERENCES log_volumes(id),
  line_no INTEGER NOT NULL,
  chunk_id VARCHAR(120) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_log_ingest_reading UNIQUE (reading_id)
);
