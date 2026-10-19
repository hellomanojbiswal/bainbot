"""Small DB compatibility layer: SQLite locally, PostgreSQL on hosted deployments."""
import os, sqlite3
from pathlib import Path
class Row(dict):
    def __getitem__(self,key):
        return list(self.values())[key] if isinstance(key,int) else super().__getitem__(key)
def pg_row(cursor):
    columns=[c.name for c in cursor.description] if cursor.description else []
    return lambda values:Row(zip(columns,values))
class Connection:
    def __init__(self,path):
        url=os.getenv('DATABASE_URL','')
        self.postgres=bool(url)
        if self.postgres:
            import psycopg
            self.raw=psycopg.connect(url,row_factory=pg_row,connect_timeout=10,prepare_threshold=None)
        else:
            if os.getenv('VERCEL'):raise RuntimeError('Set DATABASE_URL to a persistent PostgreSQL database before deploying.')
            Path(path).parent.mkdir(parents=True,exist_ok=True)
            self.raw=sqlite3.connect(path,timeout=15);self.raw.row_factory=sqlite3.Row
            self.raw.execute('PRAGMA foreign_keys=ON')
    def execute(self,sql,args=()):
        if self.postgres:
            if sql=='BEGIN IMMEDIATE':return self.raw.execute('SELECT pg_advisory_xact_lock(72491821)')
            sql=sql.replace('?','%s')
        return self.raw.execute(sql,args)
    def executescript(self,sql):
        for statement in sql.split(';'):
            if statement.strip():self.execute(statement)
    def __enter__(self):return self
    def __exit__(self,kind,value,tb):
        try:self.raw.rollback() if kind else self.raw.commit()
        finally:self.raw.close()
