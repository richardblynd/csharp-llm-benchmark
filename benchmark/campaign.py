"""Persist comparable benchmark pairs and validate resumption before model requests."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from benchmark.config import AppConfig, SUPPORTED_GENERATORS
from benchmark.tasks import SUPPORTED_SUITES, Task
from benchmark.workspace import task_fingerprint


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    temporary.replace(path)


def suite_contract(tasks: list[Task], discovery: list[Task]) -> dict:
    def describe(task: Task) -> dict:
        return {'id': task.id, 'version': task.version, 'fingerprint': task_fingerprint(task),
                'available_points': task.score.available_points}
    payload = {'tasks': [describe(t) for t in tasks], 'discovery_tasks': [describe(t) for t in discovery],
               'score_formula_version': 'evolution-v1' if tasks[0].suite == 'evolution' else 'greenfield-v1'}
    return {**payload, 'suite_version': _hash(payload)}


def campaign_protocol(config: AppConfig, catalogs: dict[str, list[Task]], discovery: dict[str, list[Task]]) -> dict:
    llm = asdict(config.llm)
    # Credentials and machine-local cache/output paths do not affect the protocol.
    llm.pop('api_key')
    llm.pop('model_label')
    llm.pop('publisher')
    agents = {}
    for name in SUPPORTED_GENERATORS:
        value = asdict(getattr(config, name)); value.pop('cache_dir')
        agents[name] = value
    value = {'version': 1, 'llm': llm, 'agents': agents, 'docker': asdict(config.docker),
            'generation_workers': config.benchmark.generation_workers,
            'evaluation_workers': config.benchmark.evaluation_workers,
            'calibration': asdict(config.benchmark.calibration),
            'suites': {suite: suite_contract(tasks, discovery.get(suite, [])) for suite, tasks in catalogs.items()}}
    return json.loads(json.dumps(value))


class Campaign:
    def __init__(self, root: Path, data: dict, *, resumed: bool = False):
        self.root = root.resolve()
        self.data = data
        self.resumed = resumed

    @classmethod
    def create(cls, output: Path, protocol: dict, pairs: list[tuple[str, str]], *, full_scope: bool) -> Campaign:
        identity = uuid4().hex
        name = datetime.now().strftime('%Y-%m-%d_%H%M%S') + '_campaign-' + identity[:8]
        data = {'schema_version': 1, 'campaign_id': identity, 'created_at': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat(), 'protocol': protocol,
                'protocol_hash': _hash(protocol), 'full_scope': full_scope, 'status': 'incomplete',
                'pairs': {f'{suite}/{generator}': {'path': f'{suite}/{generator}', 'status': 'pending'}
                          for suite, generator in pairs}}
        campaign = cls(output / name, data)
        campaign.save()
        return campaign

    @classmethod
    def resume(cls, root: Path, protocol: dict, pairs: list[tuple[str, str]]) -> Campaign:
        data = json.loads((root / 'campaign.json').read_text(encoding='utf-8'))
        if data.get('schema_version') != 1 or data.get('protocol_hash') != _hash(protocol) or data.get('protocol') != protocol:
            raise ValueError('Campaign configuration or task fingerprints changed; restore the original settings or start a new campaign.')
        if set(data['pairs']) != {f'{s}/{g}' for s,g in pairs}:
            raise ValueError('Resume the campaign with its original suite and generator selections.')
        return cls(root, data, resumed=True)

    def save(self) -> None:
        self.data['updated_at'] = datetime.now(timezone.utc).isoformat()
        self.data['status'] = 'completed' if all(p['status'] == 'completed' for p in self.data['pairs'].values()) else 'incomplete'
        write_json(self.root / 'campaign.json', self.data)

    def run_dir(self, suite: str, generator: str) -> Path:
        # Derive paths from the supported selections, never from manifest input.
        if suite not in SUPPORTED_SUITES or generator not in SUPPORTED_GENERATORS:
            raise ValueError('Invalid campaign pair')
        return self.root / suite / generator

    def summary_metadata(self, suite: str) -> dict:
        return {'campaign_id': self.data['campaign_id'], 'protocol_hash': self.data['protocol_hash'],
                **self.data['protocol']['suites'][suite]}

    def update_pair(self, suite: str, generator: str, status: str, error: str | None = None) -> None:
        pair = self.data['pairs'][f'{suite}/{generator}']
        pair.update(status=status, error=error)
        if status == 'completed':
            payload = json.loads((self.run_dir(suite, generator) / 'summary.json').read_text(encoding='utf-8'))
            validate_pair_summary(self.data, suite, generator, payload)
        self.save()

    def completed(self, suite: str, generator: str) -> bool:
        if self.data['pairs'][f'{suite}/{generator}']['status'] != 'completed':
            return False
        payload = json.loads((self.run_dir(suite, generator) / 'summary.json').read_text(encoding='utf-8'))
        validate_pair_summary(self.data, suite, generator, payload)
        return True


def validate_pair_summary(campaign: dict, suite: str, generator: str, payload: dict) -> None:
    expected = campaign['protocol']['suites'][suite]
    metadata = payload.get('evaluation', {})
    if (payload.get('campaign_id') != campaign['campaign_id'] or metadata.get('protocol_hash') != campaign['protocol_hash']
            or payload.get('suite') != suite or payload.get('generator') != generator
            or any(metadata.get(key) != value for key,value in expected.items())):
        raise ValueError(f'Incompatible campaign summary: {suite}/{generator}')
    rows = payload.get('tasks', [])
    expected_points = {t['id']: t['available_points'] for t in expected['tasks']}
    if (len(rows) != len(expected_points) or {r['task_id'] for r in rows} != set(expected_points)
            or any(r['available_points'] != expected_points[r['task_id']] for r in rows)):
        raise ValueError(f'Incomplete campaign summary: {suite}/{generator}')
    llm = campaign['protocol']['llm']
    candidates = llm['discovery']['temperatures'] or llm['temperatures']
    if (campaign['full_scope'] and llm['discovery']['enabled']
            and (len(candidates) > 1 or llm['discovery']['temperatures'] is not None)):
        discovery = payload.get('discovery') or {}
        scores = discovery.get('temperature_scores', [])
        if (discovery.get('sample_task_ids') != [t['id'] for t in expected['discovery_tasks']]
                or len(scores) != len(candidates)
                or {row['temperature'] for row in scores} != set(candidates)):
            raise ValueError(f'Incomplete campaign discovery: {suite}/{generator}')
        winner = max(scores, key=lambda row:(row['earned_points'],-row['temperature']))['temperature']
        if discovery.get('selected_temperature') != winner or payload.get('selected_temperature') != winner:
            raise ValueError(f'Campaign temperature differs from discovery: {suite}/{generator}')


def official_protocol(campaign: dict) -> bool:
    protocol = campaign['protocol']; llm = protocol['llm']
    candidates = llm['discovery']['temperatures'] or llm['temperatures']
    selected_by_discovery = llm['discovery']['enabled'] or len(llm['temperatures']) == 1
    return (campaign.get('full_scope', False) and protocol['calibration']['enabled']
            and selected_by_discovery and bool(candidates)
            and set(campaign['pairs']) == {f'{s}/{g}' for s in SUPPORTED_SUITES for g in SUPPORTED_GENERATORS})
