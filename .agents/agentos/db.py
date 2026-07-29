"""
File: .agents/agentos/db.py

Purpose:
    Manage the AgentOS SQLite database and additive schema migrations.

Responsibilities:
    - Open the project-local database.
    - Create compatibility, cache, index, evidence, and audit tables.
    - Report the active schema version.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
SCHEMA_VERSION=3

def connect(root:Path)->sqlite3.Connection:
    """Open the database and apply missing migrations.

    Args:
        root: Absolute AgentOS project root.

    Returns:
        Initialized SQLite connection with named row access.

    Raises:
        sqlite3.Error: Database creation or migration fails.
    """
    path=root/'.agents/state/agentos.sqlite3'; path.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(path); c.row_factory=sqlite3.Row; migrate(c); return c

def migrate(c:sqlite3.Connection)->None:
    """Apply additive migrations in version order.

    Args:
        c: Open SQLite connection.

    Returns:
        None.

    Raises:
        sqlite3.Error: A migration statement fails.
    """
    c.execute("CREATE TABLE IF NOT EXISTS schema_metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL)")
    row=c.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone(); current=int(row['value']) if row else 0
    for v in range(current+1,SCHEMA_VERSION+1):
        (_m1 if v==1 else _m2 if v==2 else _m3)(c)
        c.execute("INSERT INTO schema_metadata(key,value) VALUES('schema_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(v),)); c.commit()

def schema_status(root:Path)->dict:
    """Return current and required schema versions.

    Args:
        root: Absolute AgentOS project root.

    Returns:
        Schema status dictionary.
    """
    with connect(root) as c: row=c.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()
    current=int(row['value']) if row else 0
    return {'current':current,'required':SCHEMA_VERSION,'is_current':current==SCHEMA_VERSION}

def _m1(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS tasks(task_id TEXT PRIMARY KEY,original_request TEXT NOT NULL,intent TEXT,target TEXT,expected_behavior TEXT,current_behavior TEXT,acceptance_criteria TEXT NOT NULL DEFAULT '[]',scope TEXT,risk TEXT NOT NULL,ambiguities TEXT NOT NULL DEFAULT '[]',assumptions TEXT NOT NULL DEFAULT '[]',status TEXT NOT NULL,approved INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS tool_calls(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT NOT NULL,tool_name TEXT NOT NULL,normalized_args TEXT NOT NULL,success INTEGER,failure_signature TEXT,output_summary TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS write_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT NOT NULL,path TEXT NOT NULL,allowed INTEGER NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS environment_profiles(session_id TEXT PRIMARY KEY,profile_json TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    """)
def _m2(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS tool_events(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT NOT NULL,tool_name TEXT NOT NULL,event_type TEXT NOT NULL,classification_json TEXT NOT NULL,args_hash TEXT,decision TEXT,reason TEXT,success INTEGER,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS egress_events(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT NOT NULL,tool_name TEXT NOT NULL,target TEXT,reason_code TEXT,justification TEXT,decision TEXT NOT NULL,success INTEGER,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS file_read_cache(task_id TEXT NOT NULL,path TEXT NOT NULL,range_key TEXT NOT NULL,mtime_ns INTEGER NOT NULL,size INTEGER NOT NULL,content_hash TEXT,summary TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,accessed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(task_id,path,range_key));
    CREATE TABLE IF NOT EXISTS index_metadata(scope TEXT PRIMARY KEY,generation INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS symbol_index(path TEXT NOT NULL,name TEXT NOT NULL,qualname TEXT NOT NULL,kind TEXT NOT NULL,parent_qualname TEXT,line_start INTEGER NOT NULL,line_end INTEGER,signature TEXT,fingerprint TEXT NOT NULL,mtime_ns INTEGER NOT NULL,size INTEGER NOT NULL,generation INTEGER NOT NULL,PRIMARY KEY(path,qualname,line_start));
    CREATE INDEX IF NOT EXISTS idx_symbol_name ON symbol_index(name); CREATE INDEX IF NOT EXISTS idx_symbol_fingerprint ON symbol_index(fingerprint);
    """)
def _m3(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS claims(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT NOT NULL,claim_text TEXT NOT NULL,claim_type TEXT NOT NULL,risk TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS claim_evidence(claim_id INTEGER NOT NULL,tool_call_id INTEGER NOT NULL,evidence_role TEXT NOT NULL,PRIMARY KEY(claim_id,tool_call_id));
    CREATE TABLE IF NOT EXISTS documentation_findings(id INTEGER PRIMARY KEY AUTOINCREMENT,path TEXT NOT NULL,symbol TEXT,line_start INTEGER,severity TEXT NOT NULL,code TEXT NOT NULL,message TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    """)
