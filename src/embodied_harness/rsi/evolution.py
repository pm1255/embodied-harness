"""Content-addressed evolution history. Rejected candidates are first-class records."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .core import digest


class EvolutionStore:
    """Single-writer append-only ledger; changes to stored history fail verification."""
    def __init__(self, root):
        self.root = Path(root)
        (self.root/'objects').mkdir(parents=True, exist_ok=True)
        self.ledger = self.root/'events.jsonl'
        self.verify()

    def put(self, data: bytes, media_type='application/json'):
        sha = hashlib.sha256(data).hexdigest()
        path = self.root/'objects'/sha
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError('Corrupted immutable artifact')
        else:
            with path.open('xb') as stream:
                stream.write(data)
        return {'sha256':sha, 'bytes':len(data), 'media_type':media_type}

    def record(self, event_id, kind, actor, payload, artifacts=None):
        rows = self.verify()
        for row in rows:
            if row['event_id'] == event_id:
                expected = {'kind':kind, 'actor':actor, 'payload':payload, 'artifacts':artifacts or {}}
                if any(row[key] != value for key,value in expected.items()):
                    raise ValueError('An evolution event cannot be rewritten')
                return row
        row = {'seq':len(rows), 'event_id':event_id, 'kind':kind, 'actor':actor,
               'observed_at':datetime.now(timezone.utc).isoformat(),
               'previous':rows[-1]['hash'] if rows else None,
               'payload':payload, 'artifacts':artifacts or {}}
        for ref in row['artifacts'].values():
            blob = self.root/'objects'/ref['sha256']
            if not blob.is_file() or hashlib.sha256(blob.read_bytes()).hexdigest()!=ref['sha256']:
                raise ValueError('Missing or changed referenced artifact')
        row['hash'] = digest(row)
        with self.ledger.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
            stream.flush()
        return row

    def verify(self):
        rows = []
        if not self.ledger.exists():
            return rows
        for line in self.ledger.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            body = {k:v for k,v in row.items() if k!='hash'}
            if row['seq'] != len(rows) or row['previous'] != (rows[-1]['hash'] if rows else None):
                raise ValueError('Broken evolution lineage')
            if digest(body) != row['hash']:
                raise ValueError('Evolution history was modified')
            for ref in row['artifacts'].values():
                blob = self.root/'objects'/ref['sha256']
                if not blob.is_file() or hashlib.sha256(blob.read_bytes()).hexdigest()!=ref['sha256']:
                    raise ValueError('Evolution artifact was modified')
            rows.append(row)
        return rows
