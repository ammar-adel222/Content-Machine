"""SQLite revisions/budgets and immutable, hash-checked artifact receipts."""
from contextlib import contextmanager, closing
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from .models import Artifact, Edit, Limits, Output, Revision
from .planner import ORDER, ROOTS, SPECS, affected, fingerprint, computation_key


class WorkflowError(RuntimeError):pass
class Conflict(WorkflowError):pass
class BudgetExhausted(WorkflowError):pass


def file_hash(path):
    import hashlib
    h=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


class ProjectStore:
    def __init__(self,root):
        self.root=Path(root).resolve();self.db=self.root/'project.sqlite'
        if not self.db.is_file():raise WorkflowError('No project database at that path.')

    @classmethod
    def create(cls,root,topic,*,limits=None,aspect='portrait',target_seconds=105):
        if not topic.strip() or aspect not in ('portrait','landscape') or not 1<=target_seconds<=150:
            raise ValueError('Choose a topic, valid format and 1–150-second target.')
        root=Path(root).resolve();root.mkdir(parents=True,exist_ok=False)
        limits=limits or Limits()
        with closing(sqlite3.connect(root/'project.sqlite')) as db, db:
            db.executescript('''
                CREATE TABLE project (id TEXT PRIMARY KEY, topic TEXT NOT NULL, head TEXT NOT NULL);
                CREATE TABLE revisions (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE requests (id TEXT PRIMARY KEY, digest TEXT NOT NULL, revision TEXT NOT NULL);
                CREATE TABLE budgets (revision TEXT, kind TEXT, used INTEGER, ceiling INTEGER, PRIMARY KEY(revision,kind));
            ''')
            revision=Revision(dirty=ORDER,params={'research':{'topic':topic,'target_seconds':target_seconds},
                'writing':{'target_seconds':target_seconds},'picture':{'aspect':aspect},'visual_review':{'aspect':aspect}})
            db.execute('INSERT INTO project VALUES (?,?,?)',(uuid4().hex,topic,revision.id))
            db.execute('INSERT INTO revisions VALUES (?,?)',(revision.id,revision.model_dump_json()))
            for kind,limit in limits.model_dump().items():db.execute('INSERT INTO budgets VALUES (?,?,0,?)',(revision.id,kind,limit))
        return cls(root)

    @contextmanager
    def connection(self):
        with closing(sqlite3.connect(self.db,timeout=20)) as db, db:
            db.row_factory=sqlite3.Row;yield db

    def metadata(self):
        with self.connection() as db:return dict(db.execute('SELECT * FROM project').fetchone())

    def load(self,revision_id=None):
        revision_id=revision_id or self.metadata()['head']
        with self.connection() as db:row=db.execute('SELECT payload FROM revisions WHERE id=?',(revision_id,)).fetchone()
        if row is None:raise WorkflowError('Unknown project revision.')
        return Revision.model_validate_json(row['payload'])

    def save(self,revision):
        revision=Revision.model_validate(revision.model_dump())
        with self.connection() as db:
            changed=db.execute('UPDATE revisions SET payload=? WHERE id=?',(revision.model_dump_json(),revision.id)).rowcount
            if not changed:raise WorkflowError('Cannot update an unknown revision.')

    def edit(self,request: Edit):
        request=Edit.model_validate(request.model_dump());request_hash=fingerprint(request)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT * FROM requests WHERE id=?',(request.request_id,)).fetchone()
            if existing:
                if existing['digest']!=request_hash:raise Conflict('Edit request ID was reused with different contents.')
                return self.load(existing['revision'])
            head=db.execute('SELECT head FROM project').fetchone()['head']
            if request.parent_revision!=head:raise Conflict('Project changed; reload its latest revision before editing.')
            parent=Revision.model_validate_json(db.execute('SELECT payload FROM revisions WHERE id=?',(head,)).fetchone()['payload'])
            roots=ROOTS[request.kind]
            revision=Revision(parent=head,edit=request,params=parent.params,artifacts=parent.artifacts,
                              drafts=parent.drafts,instructions=parent.instructions,dirty=affected(set(parent.dirty)|set(roots)))
            for stage in roots:
                revision.params[stage]={**revision.params.get(stage,{}),**request.patch}
                revision.instructions[stage]={'notes':request.notes,'scene_ids':request.scene_ids,'object_ids':request.object_ids}
            db.execute('INSERT INTO revisions VALUES (?,?)',(revision.id,revision.model_dump_json()))
            db.execute('UPDATE project SET head=?',(revision.id,))
            db.execute('INSERT INTO requests VALUES (?,?,?)',(request.request_id,request_hash,revision.id))
            for row in db.execute('SELECT kind,ceiling FROM budgets WHERE revision=?',(head,)).fetchall():
                db.execute('INSERT INTO budgets VALUES (?,?,0,?)',(revision.id,row['kind'],row['ceiling']))
        return revision

    def budgets(self,revision_id):
        with self.connection() as db:
            return {r['kind']:{'used':r['used'],'limit':r['ceiling']} for r in db.execute('SELECT * FROM budgets WHERE revision=?',(revision_id,))}

    def consume(self,revision_id,kind,amount=1):
        if kind not in Limits.model_fields or not isinstance(amount,int) or amount<1:raise ValueError('Invalid budget reservation.')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            changed=db.execute('UPDATE budgets SET used=used+? WHERE revision=? AND kind=? AND used+?<=ceiling',
                               (amount,revision_id,kind,amount)).rowcount
            if not changed:raise BudgetExhausted(f'{kind} budget exhausted; completed work is retained.')

    def set_limit(self,revision_id,kind,limit):
        if kind not in Limits.model_fields or not isinstance(limit,int) or not 0<=limit<=500:raise ValueError('Invalid budget limit.')
        with self.connection() as db:
            row=db.execute('SELECT used FROM budgets WHERE revision=? AND kind=?',(revision_id,kind)).fetchone()
            if not row or limit<row['used']:raise ValueError('Limit cannot be below reserved usage.')
            db.execute('UPDATE budgets SET ceiling=? WHERE revision=? AND kind=?',(limit,revision_id,kind))

    def receipt_path(self,stage,key):
        if stage not in SPECS or len(key)!=64 or any(c not in '0123456789abcdef' for c in key):raise ValueError('Invalid artifact reference.')
        return self.root/'artifacts'/stage/(key+'.json')

    def read_artifact(self,stage,artifact_id):
        path=self.receipt_path(stage,artifact_id)
        if not path.is_file():raise WorkflowError('Saved artifact receipt is missing.')
        try:artifact=Artifact.model_validate_json(path.read_text(encoding='utf-8'))
        except (ValueError,OSError):raise WorkflowError('Saved artifact receipt is invalid.') from None
        if artifact.stage!=stage or artifact.id!=artifact_id or artifact.id!=fingerprint(artifact.model_dump(exclude={'id'})):
            raise WorkflowError('Artifact identity does not match its reference.')
        expected=fingerprint({'data':artifact.output.data,'files':artifact.file_hashes,'review':artifact.output.review,'issues':artifact.output.issues})
        if artifact.content_hash!=expected or artifact.view_hashes!={k:fingerprint(v) for k,v in artifact.output.views.items()}:
            raise WorkflowError('Artifact changed after it was saved.')
        for name,file in artifact.output.files.items():
            if not Path(file).is_file() or file_hash(file)!=artifact.file_hashes.get(name):raise WorkflowError('Artifact media is missing or was changed.')
        return artifact

    def cached(self,stage,key):
        self.receipt_path(stage,key)  # Validate the stage/key before constructing a path.
        path=self.root/'receipts'/stage/(key+'.json')
        if not path.exists():return None
        try:
            pointer=json.loads(path.read_text(encoding='utf-8'))
            artifact=self.read_artifact(stage,pointer['id'])
            if pointer['key']!=key or artifact.key!=key:raise ValueError('Wrong cache identity.')
            return artifact
        except (ValueError,KeyError):raise WorkflowError('Invalid computation receipt.') from None

    def write_artifact(self,stage,key,output: Output,version='v1',cache=True):
        output=Output.model_validate(output)
        output.files={k:str(Path(v).resolve()) for k,v in output.files.items()}
        hashes={k:file_hash(v) for k,v in output.files.items()}
        artifact=Artifact(id='0'*64,stage=stage,key=key,version=version,output=output,file_hashes=hashes,
            content_hash=fingerprint({'data':output.data,'files':hashes,'review':output.review,'issues':output.issues}),
            view_hashes={k:fingerprint(v) for k,v in output.views.items()})
        artifact.id=fingerprint(artifact.model_dump(exclude={'id'}))
        path=self.receipt_path(stage,artifact.id);path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix('.'+uuid4().hex+'.tmp')
        try:temporary.write_text(artifact.model_dump_json(indent=2),encoding='utf-8');temporary.replace(path)
        finally:temporary.unlink(missing_ok=True)
        if not cache:return artifact
        pointer=self.root/'receipts'/stage/(key+'.json');pointer.parent.mkdir(parents=True,exist_ok=True)
        temporary=pointer.with_suffix('.'+uuid4().hex+'.tmp')
        try:temporary.write_text(json.dumps({'id':artifact.id,'key':key}),encoding='utf-8');temporary.replace(pointer)
        finally:temporary.unlink(missing_ok=True)
        return artifact

    def approve(self,revision_id):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT head FROM project').fetchone()['head']!=revision_id:raise Conflict('Only the current revision can be approved.')
            revision=self.load(revision_id)
            if revision.status=='approved':
                media=self.read_artifact('mux',revision.artifacts['mux'])
                if not revision.approval or revision.approval.get('video_sha256')!=media.file_hashes.get('video'):
                    raise WorkflowError('Stored approval no longer matches its media.')
                return revision
            if revision.dirty or revision.status!='awaiting_review':raise WorkflowError('Finish the current revision before approval.')
            media=self.read_artifact('mux',revision.artifacts['mux'])
            review=self.read_artifact('final_review',revision.artifacts['final_review'])
            if review.output.review!='pass' or 'video' not in media.file_hashes:raise WorkflowError('A checked final video is required for approval.')
            expected=computation_key('final_review',review.version,revision.params.get('final_review',{}),
                                     revision.instructions.get('final_review',{}),{'mux':media.content_hash})
            if review.key!=expected:raise WorkflowError('Final review does not match the current media.')
            revision.approval={'revision':revision.id,'video_sha256':media.file_hashes['video'],'mux_key':media.key,'review_key':review.key}
            revision.status='approved'
            db.execute('UPDATE revisions SET payload=? WHERE id=?',(revision.model_dump_json(),revision.id))
        return revision

    @contextmanager
    def run_lock(self):
        """OS-released lock: crashed processes cannot leave a stale logical lease."""
        with (self.root/'run.lock').open('a+b') as lock:
            lock.seek(0,2)
            if not lock.tell():lock.write(b'0');lock.flush()
            lock.seek(0)
            if __import__('os').name=='nt':
                import msvcrt
                try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
                except OSError:raise Conflict('Another worker is running this project.') from None
                try:yield
                finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except OSError:raise Conflict('Another worker is running this project.') from None
                try:yield
                finally:fcntl.flock(lock,fcntl.LOCK_UN)
