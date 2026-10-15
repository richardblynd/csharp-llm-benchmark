"""Rank whole campaigns without mixing independent runs or suite denominators."""
from __future__ import annotations

from datetime import datetime, timezone
import html
import json
import logging
import math
import os
from pathlib import Path
from urllib.parse import quote

from benchmark.campaign import official_protocol, validate_pair_summary


def mean_complete(values: list[float | None]) -> float | None:
    return sum(values) / len(values) if values and all(v is not None for v in values) else None


def _score(summary: dict) -> float:
    rows = summary['tasks']
    available = sum(row['available_points'] for row in rows)
    earned = sum(row['earned_points'] for row in rows)
    if (not available or not math.isfinite(available) or not math.isfinite(earned)
            or any(not 0 <= row['earned_points'] <= row['available_points'] for row in rows)):
        raise ValueError('Invalid campaign points')
    return 100 * earned / available


def collect_campaigns(results_dir: Path) -> list[dict]:
    campaigns = []
    for manifest in sorted(results_dir.glob('*/campaign.json')):
        data = json.loads(manifest.read_text(encoding='utf-8'))
        if data.get('schema_version') != 1:
            logging.warning('Unsupported campaign schema: %s', manifest)
            continue
        values = {}; summaries = {}; errors = []
        for key, pair in data['pairs'].items():
            if pair['status'] != 'completed':
                continue
            suite, generator = key.split('/')
            if suite not in {'greenfield','evolution'} or generator not in {'pi','opencode'}:
                raise ValueError(f'Invalid campaign pair: {key}')
            path = manifest.parent / suite / generator / 'summary.json'
            try:
                summary = json.loads(path.read_text(encoding='utf-8'))
                validate_pair_summary(data, suite, generator, summary)
                values[key] = _score(summary)
                summaries[key] = summary
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(f'{key}: {exc}')
        complete = len(summaries) == 4 and official_protocol(data) and not errors
        full_scope = data.get('full_scope', False)
        suite_scores = {suite: mean_complete([values.get(f'{suite}/{g}') for g in ('pi','opencode')])
                        if full_scope else None for suite in ('greenfield','evolution')}
        llm = data['protocol']['llm']
        display = next(iter(summaries.values()), {})
        campaigns.append({'id': data['campaign_id'], 'directory': manifest.parent,
            'created_at': data['created_at'], 'protocol_hash': data['protocol_hash'],
            'model': display.get('modelLabel') or llm['model'], 'model_id': llm['model'],
            'publisher': display.get('publisher') or '', 'quantization': llm['quantization'],
            'kv': llm.get('kv_cache_quantization'), 'context_limit': llm.get('context_limit'),
            'size_bytes': display.get('model_size_bytes'), 'pairs': values, 'summaries': summaries,
            'greenfield': suite_scores['greenfield'], 'evolution': suite_scores['evolution'],
            'combined': mean_complete(list(suite_scores.values())) if complete else None,
            'combined_pi': mean_complete([values.get(f'{s}/pi') for s in ('greenfield','evolution')]) if full_scope else None,
            'combined_opencode': mean_complete([values.get(f'{s}/opencode') for s in ('greenfield','evolution')]) if full_scope else None,
            'complete': complete, 'status': 'Completa' if complete else 'Parcial / diagnóstica',
            'errors': errors, 'manifest': data})
    return sorted(campaigns, key=lambda c: (c['created_at'],c['id']), reverse=True)


def latest_campaigns(campaigns: list[dict]) -> list[dict]:
    # A newer partial attempt must not replace the last complete campaign.
    groups = {}
    for campaign in sorted(campaigns, key=lambda c:(c['created_at'],c['id']), reverse=True):
        key = campaign['protocol_hash']
        previous = groups.get(key)
        if previous is None or (campaign['complete'] and not previous['complete']):
            groups[key] = campaign
    return sorted(groups.values(), key=lambda c:(c['combined'] is not None,c['combined'] or 0), reverse=True)


def _format(value: float | None) -> str:
    return 'n/a' if value is None else f'{value:.2f}'


def render_campaign_markdown(campaigns: list[dict]) -> str:
    lines = ['# C# benchmark — campanhas', '',
        'Última campanha completa por configuração e versões. Construção e Features têm pesos iguais; o combinado exige as quatro avaliações da mesma campanha.', '',
        '| Modelo | Quantização | Construção PI | Construção OpenCode | Construção | Features PI | Features OpenCode | Features | Combinado | Estado |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for c in latest_campaigns(campaigns):
        scores = [c['pairs'].get('greenfield/pi'),c['pairs'].get('greenfield/opencode'),c['greenfield'],
                  c['pairs'].get('evolution/pi'),c['pairs'].get('evolution/opencode'),c['evolution'],c['combined']]
        text = lambda s: str(s).replace('|','\\|').replace('\n',' ')
        lines.append('| ' + ' | '.join([text(c['model']),text(c['quantization']),*map(_format,scores),c['status']]) + ' |')
    lines += ['', 'Todas as campanhas:', '']
    for c in campaigns:
        lines.append(f'- {c["created_at"]} — {c["model"]} — {c["status"]} — {c["directory"].name}')
    return '\n'.join(lines)+'\n'


def render_campaign_html(campaigns: list[dict], historical: list, *, results_dir: Path, output_path: Path) -> str:
    def esc(value): return html.escape(str(value), quote=True)
    def href(path): return esc(quote(os.path.relpath(path, output_path.parent).replace('\\','/'), safe='/'))
    rows=[]
    for c in latest_campaigns(campaigns):
        values=[c['pairs'].get('greenfield/pi'),c['pairs'].get('greenfield/opencode'),c['greenfield'],
                c['pairs'].get('evolution/pi'),c['pairs'].get('evolution/opencode'),c['evolution'],c['combined']]
        size=(c['size_bytes']/2**30) if c['size_bytes'] else None
        attrs=' '.join(f'data-{s}="{c[s] if c[s] is not None else ""}"' for s in ('greenfield','evolution','combined'))
        details=[]
        for key,summary in sorted(c['summaries'].items()):
            suite,generator=key.split('/')
            agent=summary.get(generator) or {}
            tasks=summary['tasks']
            timeouts=sum(bool((t.get(f'{generator}_metadata') or {}).get('timed_out')) for t in tasks)
            speed=(summary.get('calibration') or {}).get('tokens_per_second')
            tokens=(summary.get('llm_token_usage') or {}).get('total_tokens')
            discovery=(summary.get('discovery') or {})
            cost=(discovery.get('llm_token_usage') or {}).get('total_tokens')
            detail=f'{key}: {_format(c["pairs"][key])}; versão {agent.get("version") or "n/a"}; temperatura {summary.get("selected_temperature")}; '
            detail+=f'{len(tasks)} tarefas; tokens {tokens if tokens is not None else "n/a"}; discovery {cost if cost is not None else "n/a"} tokens; {timeouts} timeout(s); '
            detail+=f'{_format(speed)} tokens/s calibrados; limite {agent.get("timeout_seconds")} s; tempo de sessões {(summary.get("llm_response_time") or {}).get("total_seconds",0):.1f} s'
            details.append(f'<li><a href="{href(c["directory"]/suite/generator/"summary.md")}">{esc(detail)}</a></li>')
            if suite=='evolution':
                details.append('<li>Feature / preservação: '+', '.join(esc(t['task_id'])+f' {_format(100*t["feature_ratio"])}% / {_format(100*t["regression_ratio"])}%' for t in tasks)+'</li>')
        details.extend('<li>'+esc(error)+'</li>' for error in c['errors'])
        details.append(f'<li>Combinado PI: {_format(c["combined_pi"])}; OpenCode: {_format(c["combined_opencode"])}</li>')
        details.append(f'<li><a href="{href(c["directory"]/"campaign.json")}">Manifesto da campanha {esc(c["id"][:8])}</a>; protocolo {esc(c["protocol_hash"][:12])}; {esc(c["created_at"])}</li>')
        rows.append(f'<tr class="campaign" {attrs} data-model="{esc(c["model"])}" data-size="{size or ""}" data-complete="{str(c["complete"]).lower()}">'
            f'<td><details><summary>{esc(c["model"])}</summary><ul>{"".join(details)}</ul></details></td>'
            f'<td>{esc(c["quantization"])} / KV {esc(c["kv"] or "n/a")}<br>contexto {esc(c["context_limit"] or "n/a")}</td>'
            f'<td class="number">{_format(size)}</td>'+''.join(f'<td class="number score" data-index="{i}" data-value="{v if v is not None else ""}">{_format(v)}</td>' for i,v in enumerate(values))+
            f'<td class="number efficiency">n/a</td><td>{esc(c["status"])}</td></tr>')
    history=[]
    for r in historical:
        history.append(f'<tr class="historical" data-model="{esc(r.model)}"><td>{esc(r.model)}</td><td>{esc(r.suite)}</td><td>{esc(r.generator)}</td><td class="number">{_format(r.final_score)}</td><td>{_format(r.available_points)}</td>'
                       f'<td><a href="{href(results_dir/r.run_name/"summary.md")}">{esc(r.run_name)}</a></td></tr>')
    attempts = ''.join(f'<li><a href="{href(c["directory"]/"campaign.json")}">{esc(c["model"])} — {esc(c["created_at"])} — {esc(c["status"])}</a> ({len(c["summaries"])}/{len(c["manifest"]["pairs"])} pares concluídos)</li>' for c in campaigns)
    title='C# LLM Benchmark'
    return '''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>'''+title+'''</title><style>
:root{color-scheme:dark;--bg:#101620;--panel:#192331;--line:#344257;--text:#e8eef6;--muted:#a6b6ca;--accent:#73d2c5}*{box-sizing:border-box}body{font:15px/1.5 system-ui,sans-serif;margin:0;background:var(--bg);color:var(--text)}main{max-width:1600px;margin:auto;padding:36px 24px}h1{font-size:32px;margin:0}h2{font-size:21px}p{color:var(--muted);max-width:1050px}a{color:var(--accent)}.controls{display:flex;gap:18px;align-items:end;flex-wrap:wrap;margin:26px 0}label{display:grid;gap:5px;color:var(--muted)}input,select{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:9px;font:inherit}.table{overflow:auto;border:1px solid var(--line);border-radius:10px}table{width:100%;border-collapse:collapse}th,td{padding:12px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}thead{background:var(--panel)}th{white-space:nowrap;font-size:13px}.number{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.best{color:var(--accent);font-weight:bold;background:#163331}.active{background:#223448}details>summary{cursor:pointer}td:first-child{min-width:220px}td details ul{min-width:420px;padding-left:18px;font-size:13px;white-space:normal}#chart{background:var(--panel);border:1px solid var(--line);border-radius:10px;width:100%;max-width:850px;height:auto;margin-top:18px}#empty{padding:18px;color:var(--muted)}.legend{font-size:13px}.history{margin-top:36px}button{font:inherit;background:none;color:var(--accent);border:0;cursor:pointer}svg text{fill:var(--muted);font-size:12px}svg line{stroke:var(--line)}svg circle{fill:var(--accent);stroke:#fff;stroke-width:1.5}svg circle:hover{r:8}[hidden]{display:none!important}
</style></head><body><main><h1>'''+title+'''</h1>
<p>Construção mede projetos criados do zero. Features mede mudanças em projetos existentes com preservação do comportamento antigo. Cada modalidade é a média de PI e OpenCode; Combinado é a média das modalidades, com pesos iguais.</p>
<p>O ranking usa a última campanha completa por configuração e versões dos desafios e agentes. As quatro avaliações precisam pertencer à mesma campanha. Valores ausentes aparecem como n/a; campanhas parciais ou diagnósticas não disputam o ranking combinado.</p>
<div class="controls"><label>Buscar modelo<input id="search" type="search" placeholder="Nome do modelo"></label><label>Ordenar, filtrar e comparar por<select id="metric"><option value="combined">Combinado</option><option value="greenfield">Construção</option><option value="evolution">Features</option></select></label><label>Score mínimo<input id="minimum" type="number" min="0" max="100" value="0"></label><label>Exibir<select id="scope"><option value="all">Todas as campanhas selecionadas</option><option value="complete">Somente completas</option></select></label></div>
<p class="legend" id="metric-label"></p><div class="table"><table id="ranking"><thead><tr><th rowspan="2">Modelo / detalhes</th><th rowspan="2">Configuração</th><th rowspan="2" class="number">GiB</th><th colspan="3">Construção</th><th colspan="3">Features</th><th rowspan="2">Combinado</th><th rowspan="2">Score / GiB</th><th rowspan="2">Estado</th></tr><tr><th>PI</th><th>OpenCode</th><th>Média</th><th>PI</th><th>OpenCode</th><th>Média</th></tr></thead><tbody>'''+''.join(rows)+'''</tbody></table><div id="empty" hidden>Nenhuma campanha corresponde aos filtros. As execuções anteriores estão no histórico abaixo.</div></div>
<svg id="chart" viewBox="0 0 850 290" role="img" aria-label="Score por tamanho do modelo"><g id="plot"></g></svg>
<details class="history"><summary>Todas as campanhas e tentativas ('''+str(len(campaigns))+''')</summary><ul>'''+attempts+'''</ul></details>
<details class="history" open><summary>Histórico de execuções anteriores ('''+str(len(history))+''')</summary><p>Execuções sem identidade de campanha são apresentadas individualmente. Os catálogos históricos podem conter quantidades diferentes de tarefas; seus scores não formam um combinado oficial.</p><div class="table"><table><thead><tr><th>Modelo</th><th>Modalidade</th><th>Agente</th><th>Score</th><th>Pontos possíveis</th><th>Execução</th></tr></thead><tbody>'''+''.join(history)+'''</tbody></table></div></details>
<p class="legend">Gerado em '''+esc(datetime.now(timezone.utc).isoformat())+'''. Tempo de sessões é a soma das tarefas, incluindo sessões paralelas.</p></main>
<script>
const rows=Array.from(document.querySelectorAll('.campaign')),tbody=document.querySelector('#ranking tbody');
const search=document.querySelector('#search'),metric=document.querySelector('#metric'),minimum=document.querySelector('#minimum'),scope=document.querySelector('#scope');
const names={combined:'Combinado',greenfield:'Construção',evolution:'Features'};
const score=r=>r.dataset[metric.value]===''?null:Number(r.dataset[metric.value]);
const ns='http://www.w3.org/2000/svg';function svg(tag,attrs,text){const e=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;return e;}
function update(){
const low=Math.max(0,Math.min(100,Number(minimum.value)||0));
for(const r of document.querySelectorAll('.historical'))r.hidden=!r.dataset.model.toLowerCase().includes(search.value.toLowerCase());
rows.sort((a,b)=>(score(b)??-1)-(score(a)??-1));
for(const r of rows){r.hidden=!r.dataset.model.toLowerCase().includes(search.value.toLowerCase())||(scope.value==='complete'&&r.dataset.complete!=='true')||(score(r)!==null&&score(r)<low)||(score(r)===null&&low>0);tbody.append(r);const s=score(r),size=Number(r.dataset.size);r.querySelector('.efficiency').textContent=s!==null&&size>0?(s/size).toFixed(2):'n/a';}
const visible=rows.filter(r=>!r.hidden);document.querySelector('#empty').hidden=visible.length>0;
for(const r of rows)for(const td of r.querySelectorAll('.score'))td.classList.remove('best','active');
const index={greenfield:2,evolution:5,combined:6}[metric.value];
for(let i=0;i<7;i++){const cells=visible.map(r=>r.querySelector(`[data-index="${i}"]`));const values=cells.filter(c=>c.dataset.value!=='').map(c=>Number(c.dataset.value));const best=values.length?Math.max(...values):null;for(const c of cells){if(best!==null&&c.dataset.value!==''&&Number(c.dataset.value)===best)c.classList.add('best');if(i===index)c.classList.add('active');}}
document.querySelector('#metric-label').textContent=`Ordenação, faixa de score, gráfico e Score / GiB usam: ${names[metric.value]}. Clique no modelo para ver temperatura, versões, tokens, timeout e preservação por tarefa.`;
const plot=document.querySelector('#plot');plot.replaceChildren();const points=visible.filter(r=>score(r)!==null&&Number(r.dataset.size)>0),max=Math.max(1,...points.map(r=>Number(r.dataset.size)))*1.1;
document.querySelector('#chart').toggleAttribute('hidden',points.length===0);
for(let v=0;v<=100;v+=20){const y=245-v*2;plot.append(svg('line',{x1:55,y1:y,x2:815,y2:y}),svg('text',{x:16,y:y+4},v));}
for(let i=0;i<=4;i++){const x=55+i*190;plot.append(svg('text',{x:x-10,y:268},(i*max/4).toFixed(1)));}
plot.append(svg('text',{x:360,y:287},'Tamanho do modelo (GiB)'),svg('text',{x:58,y:25},names[metric.value]));
for(const r of points){const dot=svg('circle',{cx:55+Number(r.dataset.size)/max*760,cy:245-score(r)*2,r:5,tabindex:0});dot.append(svg('title',{},`${r.dataset.model}: ${score(r).toFixed(2)} / ${Number(r.dataset.size).toFixed(2)} GiB`));dot.addEventListener('click',()=>{r.scrollIntoView({behavior:'smooth',block:'center'});r.querySelector('details').open=true;});plot.append(dot);}
}
for(const el of[search,metric,minimum,scope])el.addEventListener('input',update);update();
</script></body></html>'''
