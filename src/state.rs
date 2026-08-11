use crate::config::StateStoreConfig;
use crate::models::{RecordInfo, RecordState};
use anyhow::{Context, Result};
use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension};
use std::sync::{Arc, Mutex};

pub struct StateStore {
    conn: Arc<Mutex<Connection>>,
}

impl StateStore {
    pub fn new(config: &StateStoreConfig) -> Result<Self> {
        let conn = Connection::open(&config.db_path)
            .with_context(|| format!("Failed to open SQLite database at {}", config.db_path))?;

        // Apply high-performance pragmas for WAL mode durability
        conn.execute_batch(&format!(
            "PRAGMA journal_mode = {};
             PRAGMA synchronous = {};
             PRAGMA busy_timeout = {};",
            config.journal_mode, config.synchronous, config.busy_timeout_ms
        ))
        .context("Failed to set SQLite pragmas")?;

        let store = Self {
            conn: Arc::new(Mutex::new(conn)),
        };
        store.init_tables()?;
        Ok(store)
    }

    fn init_tables(&self) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS records (
                record_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                directory TEXT NOT NULL,
                date_record_day TEXT,
                date_last_write TEXT NOT NULL,
                length_bytes INTEGER NOT NULL,
                duration_seconds REAL NOT NULL,
                speech_count INTEGER NOT NULL,
                story TEXT NOT NULL,
                stats_verbatim_json TEXT NOT NULL,
                state TEXT NOT NULL,
                is_degraded INTEGER NOT NULL,
                attempts INTEGER DEFAULT 0,
                last_error TEXT,
                lease_owner TEXT,
                lease_expires_at INTEGER,
                triage_keywords_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS speeches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT NOT NULL,
                time_frame TEXT NOT NULL,
                script TEXT NOT NULL,
                confidence REAL NOT NULL,
                word_count INTEGER NOT NULL,
                offset_ms INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                words_json TEXT,
                FOREIGN KEY(record_id) REFERENCES records(record_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                record_id TEXT NOT NULL,
                start_ms INTEGER NOT NULL,
                end_ms INTEGER NOT NULL,
                state TEXT NOT NULL,
                transcript_text TEXT,
                confidence REAL,
                attempts INTEGER DEFAULT 0,
                last_error TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(record_id) REFERENCES records(record_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS dead_letter (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT,
                chunk_id TEXT,
                stage TEXT NOT NULL,
                error TEXT NOT NULL,
                context_json TEXT,
                created_at TEXT NOT NULL
            );"
        )
        .context("Failed to create SQLite tables")?;

        // Migration: Add triage_keywords_json and triage_summary columns if missing
        let _ = conn.execute("ALTER TABLE records ADD COLUMN triage_keywords_json TEXT", []);
        let _ = conn.execute("ALTER TABLE records ADD COLUMN triage_summary TEXT", []);
        // Migration: Add priority column for RecordStrike-first processing
        let _ = conn.execute("ALTER TABLE records ADD COLUMN priority INTEGER DEFAULT 0", []);
        // Migration: Add legal evidence scoring columns
        let _ = conn.execute("ALTER TABLE records ADD COLUMN legal_tags TEXT", []);
        let _ = conn.execute("ALTER TABLE records ADD COLUMN intensity_rating INTEGER DEFAULT 0", []);
        let _ = conn.execute("ALTER TABLE records ADD COLUMN pattern_match_score REAL DEFAULT 0.0", []);

        Ok(())
    }

    pub fn insert_or_update_record(&self, record: &RecordInfo) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        let now = Utc::now().to_rfc3339();
        let date_record_day = record.date_record_day.map(|d| d.to_rfc3339());
        let date_last_write = record.date_last_write.to_rfc3339();
        let stats_json = serde_json::to_string(&record.stats_verbatim)?;

        conn.execute(
            "INSERT INTO records (
                record_id, name, directory, date_record_day, date_last_write,
                length_bytes, duration_seconds, speech_count, story, stats_verbatim_json,
                state, is_degraded, triage_summary, created_at, updated_at
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?14)
            ON CONFLICT(record_id) DO UPDATE SET
                state = excluded.state,
                duration_seconds = excluded.duration_seconds,
                speech_count = excluded.speech_count,
                story = excluded.story,
                stats_verbatim_json = excluded.stats_verbatim_json,
                is_degraded = excluded.is_degraded,
                triage_summary = COALESCE(excluded.triage_summary, records.triage_summary),
                updated_at = excluded.updated_at",
            params![
                record.record_id,
                record.name,
                record.directory,
                date_record_day,
                date_last_write,
                record.length_bytes,
                record.duration_seconds,
                record.speech_count,
                record.story,
                stats_json,
                record.state.to_string(),
                if record.is_degraded { 1 } else { 0 },
                record.triage_summary,
                now,
            ],
        )?;

        // Insert speeches
        if !record.speeches.is_empty() {
            conn.execute("DELETE FROM speeches WHERE record_id = ?1", params![record.record_id])?;
            for sp in &record.speeches {
                let words_json = sp.words.as_ref().map(|w| serde_json::to_string(w).unwrap_or_default());
                conn.execute(
                    "INSERT INTO speeches (record_id, time_frame, script, confidence, word_count, offset_ms, duration_ms, words_json)
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
                    params![
                        record.record_id,
                        sp.time_frame,
                        sp.script,
                        sp.confidence,
                        sp.word_count,
                        sp.offset_ms,
                        sp.duration_ms,
                        words_json,
                    ],
                )?;
            }
        }

        Ok(())
    }

    pub fn get_record_state(&self, record_id: &str) -> Result<Option<RecordState>> {
        let conn = self.conn.lock().unwrap();
        let state_str: Option<String> = conn
            .query_row(
                "SELECT state FROM records WHERE record_id = ?1",
                params![record_id],
                |row| row.get(0),
            )
            .optional()?;

        if let Some(s) = state_str {
            let state: RecordState = serde_json::from_str(&format!("\"{}\"", s))?;
            Ok(Some(state))
        } else {
            Ok(None)
        }
    }

    pub fn update_state(&self, record_id: &str, state: RecordState) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        let now = Utc::now().to_rfc3339();
        if state == RecordState::Done || state == RecordState::Exported {
            conn.execute(
                "UPDATE records SET state = ?1, updated_at = ?2, lease_owner = NULL, lease_expires_at = NULL WHERE record_id = ?3",
                params![state.to_string(), now, record_id],
            )?;
        } else {
            conn.execute(
                "UPDATE records SET state = ?1, updated_at = ?2 WHERE record_id = ?3",
                params![state.to_string(), now, record_id],
            )?;
        }
        Ok(())
    }

    pub fn record_dead_letter(&self, record_id: Option<&str>, chunk_id: Option<&str>, stage: &str, error: &str) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        let now = Utc::now().to_rfc3339();
        conn.execute(
            "INSERT INTO dead_letter (record_id, chunk_id, stage, error, created_at)
             VALUES (?1, ?2, ?3, ?4, ?5)",
            params![record_id, chunk_id, stage, error, now],
        )?;

        if let Some(rid) = record_id {
            conn.execute(
                "UPDATE records SET state = ?1, last_error = ?2, updated_at = ?3 WHERE record_id = ?4",
                params![RecordState::DeadLetter.to_string(), error, now, rid],
            )?;
        }

        Ok(())
    }

    /// Atomically claim an unprocessed record using a lock-free lease.
    pub fn claim_unprocessed_record(&self, worker_id: &str, lease_duration_secs: i64) -> Result<Option<RecordInfo>> {
        let mut conn = self.conn.lock().unwrap();
        let tx = conn.transaction()?;

        let now_ts = Utc::now().timestamp();
        let lease_expires_ts = now_ts + lease_duration_secs;
        let now_iso = Utc::now().to_rfc3339();

        let claimed_row: Option<(String, String, String, Option<String>, String, u64)> = tx.query_row(
            "SELECT record_id, name, directory, date_record_day, date_last_write, length_bytes
             FROM records
             WHERE (UPPER(state) = 'DISCOVERED' OR UPPER(state) = 'QUEUED') AND (lease_expires_at IS NULL OR lease_expires_at < ?1)
             ORDER BY COALESCE(priority, 0) DESC, length_bytes ASC
             LIMIT 1",
            params![
                now_ts
            ],
            |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                    row.get(5)?,
                ))
            },
        ).optional()?;

        if let Some((record_id, name, directory, date_record_day_str, date_last_write_str, length_bytes)) = claimed_row {
            tx.execute(
                "UPDATE records
                 SET state = ?1, lease_owner = ?2, lease_expires_at = ?3, updated_at = ?4
                 WHERE record_id = ?5",
                params![
                    RecordState::Queued.to_string(),
                    worker_id,
                    lease_expires_ts,
                    now_iso,
                    record_id
                ],
            )?;
            tx.commit()?;

            let date_record_day = date_record_day_str
                .and_then(|s| chrono::DateTime::parse_from_rfc3339(&s).ok())
                .map(|d| d.with_timezone(&chrono::Utc));
            let date_last_write = chrono::DateTime::parse_from_rfc3339(&date_last_write_str)
                .ok()
                .map(|d| d.with_timezone(&chrono::Utc))
                .unwrap_or_else(chrono::Utc::now);

            let record = RecordInfo::new(
                record_id,
                name,
                directory,
                date_record_day,
                date_last_write,
                length_bytes,
            );
            Ok(Some(record))
        } else {
            Ok(None)
        }
    }

    pub fn touch_heartbeat(&self, record_id: &str, lease_duration_secs: i64) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        let now_ts = Utc::now().timestamp();
        let lease_expires_ts = now_ts + lease_duration_secs;
        let now_iso = Utc::now().to_rfc3339();
        conn.execute(
            "UPDATE records SET lease_expires_at = ?1, updated_at = ?2 WHERE record_id = ?3",
            params![lease_expires_ts, now_iso, record_id],
        )?;
        Ok(())
    }

    pub fn update_triage_result(
        &self,
        record_id: &str,
        state: RecordState,
        keywords_json: &str,
        summary: &str,
        clear_lease: bool,
    ) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        let now = Utc::now().to_rfc3339();
        if clear_lease {
            conn.execute(
                "UPDATE records 
                 SET state = ?1, 
                     triage_keywords_json = ?2, 
                     triage_summary = ?3, 
                     story = CASE WHEN (story IS NULL OR story = '') THEN ?3 ELSE story END, 
                     updated_at = ?4, 
                     lease_owner = NULL, 
                     lease_expires_at = NULL 
                 WHERE record_id = ?5",
                params![state.to_string(), keywords_json, summary, now, record_id],
            )?;
        } else {
            conn.execute(
                "UPDATE records 
                 SET state = ?1, 
                     triage_keywords_json = ?2, 
                     triage_summary = ?3, 
                     story = CASE WHEN (story IS NULL OR story = '') THEN ?3 ELSE story END, 
                     updated_at = ?4 
                 WHERE record_id = ?5",
                params![state.to_string(), keywords_json, summary, now, record_id],
            )?;
        }
        Ok(())
    }
}
