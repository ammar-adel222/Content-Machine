"""Durable local jobs, metadata and platform receipts, separate from agent contracts."""
from contextlib import contextmanager,closing
import json,os,sqlite3,time
from pathlib import Path
from uuid import uuid4
from war_workflow.store import Conflict


class Database:
    def __init__(self,root):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True);self.path=self.root/'studio.sqlite'
        with self.connect() as db:db.executescript('''
          CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project TEXT,revision TEXT,kind TEXT,payload TEXT,status TEXT,stage TEXT,issue TEXT,created REAL,updated REAL,cancel INTEGER DEFAULT 0);
          CREATE UNIQUE INDEX IF NOT EXISTS active_project ON jobs(project) WHERE status IN ('queued','running');
          CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
          CREATE TABLE IF NOT EXISTS publications(project TEXT,revision TEXT,platform TEXT,status TEXT,payload TEXT,updated REAL,PRIMARY KEY(project,revision,platform));
          CREATE TABLE IF NOT EXISTS metrics(project TEXT,revision TEXT,platform TEXT,day TEXT,payload TEXT,updated REAL,PRIMARY KEY(project,revision,platform,day));
        ''')

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path,timeout=20)) as db,db:db.row_factory=sqlite3.Row;yield db

    def get(self,key,default=None):
        with self.connect() as db:row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return json.loads(row['value']) if row else default

    def put(self,key,value):
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,json.dumps(value)))

    def enqueue(self,project,revision,kind,payload=None):
        job=uuid4().hex;now=time.time()
        try:
            with self.connect() as db:db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,0)',(job,project,revision,kind,json.dumps(payload or {}),'queued','','',now,now))
        except sqlite3.IntegrityError:raise Conflict('This project already has an active job.') from None
        return self.job(job)

    def job(self,id):
        with self.connect() as db:row=db.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone()
        if not row:raise ValueError('Unknown job.')
        result=dict(row);result['payload']=json.loads(result['payload']);return result

    def latest(self,project):
        with self.connect() as db:row=db.execute('SELECT id FROM jobs WHERE project=? ORDER BY created DESC LIMIT 1',(project,)).fetchone()
        return self.job(row['id']) if row else None

    def update(self,id,**values):
        if not set(values)<={'status','stage','issue','cancel'}:raise ValueError('Invalid job update.')
        values['updated']=time.time()
        with self.connect() as db:db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),id))

    def queued(self):
        with self.connect() as db:return [r['id'] for r in db.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY created")]

    @contextmanager
    def worker_lock(self):
        with (self.root/'worker.lock').open('a+b') as lock:
            lock.seek(0,2)
            if not lock.tell():lock.write(b'0');lock.flush()
            lock.seek(0)
            if os.name=='nt':
                import msvcrt
                try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
                except OSError:raise Conflict('A studio worker is already active.') from None
                try:yield
                finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except OSError:raise Conflict('A studio worker is already active.') from None
                try:yield
                finally:fcntl.flock(lock,fcntl.LOCK_UN)

    def recover(self):
        # Called only after obtaining the OS-released exclusive worker lock.
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='interrupted',issue='Worker stopped. Resume generation from saved receipts; check any uncertain platform result.' WHERE status='running'")
            db.execute("UPDATE publications SET status='uncertain' WHERE status IN ('starting','submitting','uploading')")
            db.execute("UPDATE publications SET status='failed' WHERE status='staging'")

    def publication(self,project,revision,platform):
        with self.connect() as db:row=db.execute('SELECT * FROM publications WHERE project=? AND revision=? AND platform=?',(project,revision,platform)).fetchone()
        return dict(row)|{'payload':json.loads(row['payload'])} if row else None

    def record(self,project,revision,platform,status,payload):
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO publications VALUES (?,?,?,?,?,?)',(project,revision,platform,status,json.dumps(payload),time.time()))
