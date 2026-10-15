from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict, replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmark import cli
from benchmark.aggregate_benchmark_results import collect_benchmark_results
from benchmark.calibration import CalibrationResult, ProbeMeasurement, calculate_timeout
from benchmark.campaign import Campaign, campaign_protocol, official_protocol, write_json
from benchmark.campaign_report import collect_campaigns, latest_campaigns, mean_complete, render_campaign_html
from benchmark.config import AppConfig, BenchmarkConfig, DiscoveryConfig, LlmConfig, OpenCodeConfig, PiConfig
from benchmark.generation import GeneratedSolution
from benchmark.runner import TaskRunResult
from benchmark.scorer import score_benchmark
from benchmark.solution import ExtractedCode, LlmUsage
from benchmark.tasks import load_tasks, select_discovery_tasks
from benchmark.workspace import capture_project, task_fingerprint


class CampaignTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = AppConfig(llm=LlmConfig(base_url='https://example.invalid/v1', model='fixture',
                                              quantization='Q4', temperatures=(.4,.2)),
            benchmark=BenchmarkConfig(suite='all',generator='all',output_dir=self.root),
            opencode=OpenCodeConfig(version='pinned-open'),pi=PiConfig(version='pinned-pi'))
        self.calls=[]
        self.fail=None
        self.preferred={('greenfield','pi'):.2,('greenfield','opencode'):.4,
                        ('evolution','pi'):.4,('evolution','opencode'):.2}

    def calibration(self, config):
        sample=ProbeMeasurement(512,10,None,51.2)
        sampling={k:getattr(config.llm,k) for k in ('temperature','top_p','min_p','top_k','repetition_penalty')
                  if getattr(config.llm,k) is not None}
        return CalibrationResult('2026-10-15T00:00:00+00:00',config.llm.model,config.llm.base_url,
            config.benchmark.generation_workers,asdict(config.benchmark.calibration),sampling,
            1,10,(sample,),(sample,),51.2,calculate_timeout(51.2,config.benchmark.calibration))

    def factory(self, config):
        owner=self
        class Generator:
            def generate(self, task, artifact_dir):
                call=(task.suite,config.benchmark.generator,task.id,config.llm.temperature)
                owner.calls.append(call)
                if owner.fail and owner.fail(call):
                    owner.fail=None
                    raise RuntimeError('deliberate interruption')
                return GeneratedSolution(ExtractedCode('fixture',()),1,LlmUsage(10,5,15),
                    generator=config.benchmark.generator,
                    project_snapshot=capture_project(task,task.template_dir) if task.suite=='evolution' else None)
        return Generator()

    def evaluate(self, task, extracted, **kwargs):
        success=kwargs['temperature']==self.preferred[task.suite,kwargs['generator']]
        feature=list(task.score.tests) if success else []
        regression=list(task.score.regression)
        return TaskRunResult(task.id,'passed' if success else 'tests_failed',1,LlmUsage(10,5,15),None,None,None,
            tuple(feature+regression),tuple(set(task.score.tests)-set(feature)),(),generator=kwargs['generator'],
            temperature=kwargs['temperature'],suite=task.suite,task_fingerprint=task_fingerprint(task),
            test_group_results={'feature':{'passed_tests':feature},'regression':{'passed_tests':regression}})

    def run_cli(self, extra=(), *, config=None):
        config=config or self.config
        args=cli._build_parser().parse_args(['run',*extra])
        with patch('benchmark.cli.load_config',return_value=config), patch('benchmark.cli.resolve_model_meta',return_value=None), patch(
            'benchmark.cli._report_quantization_precedence'), patch('benchmark.cli.is_local_server',return_value=False), patch(
            'benchmark.cli.calibrate',side_effect=self.calibration) as calibration, patch(
            'benchmark.cli.create_solution_generator',side_effect=self.factory), patch(
            'benchmark.cli.DockerRunner.evaluate',side_effect=self.evaluate), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code=cli._run(args)
        return code,calibration

    def test_discovery_is_independent_for_each_pair_and_excluded_from_evolution_score(self):
        code,calibration=self.run_cli()
        self.assertEqual(code,0)
        calibration.assert_called_once()
        campaigns=collect_campaigns(self.root)
        self.assertEqual(len(campaigns),1)
        c=campaigns[0]
        self.assertTrue(c['complete'])
        self.assertEqual(c['combined'],100)
        self.assertEqual(c['greenfield'],100)
        self.assertEqual(c['evolution'],100)
        for key,s in c['summaries'].items():
            suite,generator=key.split('/')
            self.assertEqual(s['selected_temperature'],self.preferred[suite,generator])
            self.assertEqual(s['discovery']['selected_temperature'],s['selected_temperature'])
            self.assertEqual(s['calibration']['timeout_seconds'],self.calibration(self.config).timeout_seconds)
            self.assertEqual(s['discovery']['llm_token_usage']['total_tokens'],len(s['discovery']['sample_task_ids'])*2*15)
            self.assertEqual(len(s['tasks']),6 if suite=='evolution' else 37)
            self.assertFalse(any(t['task_id'].startswith('evolution-discovery-') for t in s['tasks']))
            for task in s['tasks']:
                count=sum(call[1:]==(generator,task['task_id'],s['selected_temperature']) for call in self.calls)
                self.assertEqual(count,1,'Greenfield discovery is reused; evolution scored tasks are separate')
        self.assertEqual(len(collect_benchmark_results(self.root)),4,'Nested discovery summaries must not enter aggregation')

    def test_resume_recovers_partial_discovery_and_preserves_finished_pairs_and_selection(self):
        for phase in ('discovery','scored'):
            with self.subTest(phase=phase):
                self.calls=[]
                output=self.root/phase
                config=replace(self.config,benchmark=replace(self.config.benchmark,output_dir=output))
                self.fail=lambda call:call[:2]==('evolution','pi') and (
                    call[2]=='evolution-discovery-medium-001' if phase=='discovery' else 'discovery' not in call[2])
                code,_=self.run_cli(config=config)
                self.assertEqual(code,1)
                c=collect_campaigns(output)[0]
                self.assertIsNone(c['combined'])
                before=[call for call in self.calls if call[:2]!=('evolution','pi')]
                discovery_before=[call for call in self.calls if call[:2]==('evolution','pi') and 'discovery' in call[2]]
                committed={}
                for path in (c['directory']/'evolution/pi/discovery').glob('**/result.json'):
                    result=json.loads(path.read_text())
                    key=('evolution','pi',result['task_id'],result['temperature'])
                    committed[key]=(self.calls.count(key),path.stat().st_mtime_ns,path)
                code,calibration=self.run_cli(['--resume-campaign',str(c['directory'])],config=config)
                self.assertEqual(code,0)
                calibration.assert_not_called()
                self.assertEqual(before,[call for call in self.calls if call[:2]!=('evolution','pi')])
                completed=collect_campaigns(output)[0]
                self.assertTrue(completed['complete'])
                self.assertEqual(completed['summaries']['evolution/pi']['discovery']['llm_token_usage']['total_tokens'],120)
                if phase=='scored':
                    self.assertEqual(discovery_before,[call for call in self.calls if call[:2]==('evolution','pi') and 'discovery' in call[2]])
                else:
                    self.assertTrue(committed)
                    for key,(count,mtime,path) in committed.items():
                        self.assertEqual(self.calls.count(key),count)
                        self.assertEqual(path.stat().st_mtime_ns,mtime)
                before_all=list(self.calls)
                code,calibration=self.run_cli(['--resume-campaign',str(c['directory'])],config=config)
                self.assertEqual(code,0)
                calibration.assert_not_called()
                self.assertEqual(self.calls,before_all)

    def test_protocol_rejects_configuration_or_contract_changes_on_resume(self):
        self.assertEqual(self.run_cli()[0],0)
        c=collect_campaigns(self.root)[0]
        changed=replace(self.config,llm=replace(self.config.llm,context_limit=9000))
        with self.assertRaisesRegex(ValueError,'configuration or task fingerprints changed'):
            self.run_cli(['--resume-campaign',str(c['directory'])],config=changed)
        tasks={s:load_tasks(suite=s) for s in ('greenfield','evolution')}
        discovery={s:select_discovery_tasks(load_tasks(suite=s,role='discovery') if s=='evolution' else tasks[s]) for s in tasks}
        tasks['evolution'][0]=replace(tasks['evolution'][0],version='changed')
        with self.assertRaisesRegex(ValueError,'fingerprints changed'):
            Campaign.resume(c['directory'],campaign_protocol(self.config,tasks,discovery),list(self.preferred))

    def test_no_scores_are_combined_across_campaigns_and_last_complete_wins_over_partial(self):
        self.assertEqual(self.run_cli()[0],0)
        c=collect_campaigns(self.root)[0]
        self.fail=lambda call:call[:2]==('evolution','pi')
        self.assertEqual(self.run_cli()[0],1)
        cs=collect_campaigns(self.root)
        selected=latest_campaigns(cs)
        self.assertEqual(len(selected),1)
        self.assertEqual(selected[0]['id'],c['id'])
        partial=next(x for x in cs if not x['complete'])
        self.assertIsNone(partial['combined'])
        self.assertIsNone(partial['evolution'])
        self.assertEqual(partial['greenfield'],100)
        page=render_campaign_html(cs,[],results_dir=self.root,output_path=self.root/'report.html')
        for label in ('Construção','Features','Combinado','Score / GiB','temperature','metric'):
            if label=='temperature':continue
            self.assertIn(label,page)

    def test_combined_uses_unrounded_equal_suite_weights_and_missing_is_not_zero(self):
        self.assertIsNone(mean_complete([80,None]))
        self.assertEqual(mean_complete([0,100]),50)
        self.assertAlmostEqual(mean_complete([100/3,200/3]),50)
        self.assertEqual(self.run_cli()[0],0)
        c=collect_campaigns(self.root)[0]
        values={'greenfield/pi':(1,3),'greenfield/opencode':(2,3),'evolution/pi':(1,7),'evolution/opencode':(6,7)}
        for key,(earned,denominator) in values.items():
            path=c['directory']/key/'summary.json'
            payload=json.loads(path.read_text())
            # Preserve the real suite denominators while assigning fractional earnings.
            for row in payload['tasks']:
                row['earned_points']=row['available_points']*earned/denominator
            write_json(path,payload)
        scored=collect_campaigns(self.root)[0]
        self.assertAlmostEqual(scored['greenfield'],50)
        self.assertAlmostEqual(scored['evolution'],50)
        self.assertAlmostEqual(scored['combined'],50)
        path=c['directory']/'evolution/pi/summary.json'
        payload=json.loads(path.read_text());payload['tasks'].pop();write_json(path,payload)
        incomplete=collect_campaigns(self.root)[0]
        self.assertIsNone(incomplete['combined'])
        self.assertTrue(incomplete['errors'])

    def test_discovery_ties_choose_lowest_temperature_and_catalogs_do_not_overlap(self):
        first=cli.TemperatureRun(.8,score_benchmark([]),[])
        second=cli.TemperatureRun(.2,score_benchmark([]),[])
        self.assertIs(cli._select_best_temperature_run([first,second]),second)
        scored={t.id for t in load_tasks(suite='evolution')}
        discovery=select_discovery_tasks(load_tasks(suite='evolution',role='discovery'))
        self.assertEqual(len(discovery),4)
        self.assertFalse(scored & {t.id for t in discovery})
        self.assertEqual(len(load_tasks('easy',suite='evolution')),2)
        config=replace(self.config,benchmark=replace(self.config.benchmark,suite='evolution'))
        self.assertEqual(len(cli._discovery_tasks(config,load_tasks('easy',suite='evolution'))),4)

    def test_explicit_single_discovery_candidate_overrides_full_temperature_list(self):
        config=replace(self.config,llm=replace(self.config.llm,discovery=DiscoveryConfig(temperatures=(.4,))))
        self.assertEqual(self.run_cli(config=config)[0],0)
        c=collect_campaigns(self.root)[0]
        self.assertTrue(c['complete'])
        self.assertTrue(all(s['selected_temperature']==.4 for s in c['summaries'].values()))
        self.assertTrue(all(call[-1]==.4 for call in self.calls))

    def test_diagnostic_sweep_cannot_claim_an_official_combined_score_and_html_escapes_model(self):
        config=replace(self.config,llm=replace(self.config.llm,discovery=DiscoveryConfig(enabled=False)))
        self.assertEqual(self.run_cli(config=config)[0],0)
        c=collect_campaigns(self.root)[0]
        self.assertFalse(c['complete'])
        self.assertFalse(official_protocol(c['manifest']))
        self.assertIsNone(c['combined'])
        c['model']='<script>alert("model")</script>'
        page=render_campaign_html([c],[],results_dir=self.root,output_path=self.root/'outside'/'report.html')
        self.assertNotIn('<script>alert',page)
        self.assertIn('&lt;script&gt;',page)
        self.assertIn('../',page)


if __name__=='__main__':
    unittest.main()
