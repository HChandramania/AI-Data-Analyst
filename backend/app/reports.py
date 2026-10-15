"""On-demand, bounded, offline HTML from saved evidence only."""

import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.auth import current_user
from app.dashboards import evidence, owned_dashboard, public_dashboard
from app.models import User

router = APIRouter(prefix="/api/v1/reports")
MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_SELECTIONS = 12
RUNTIME = (Path(__file__).parent / "assets" / "plotly-basic.min.js").read_text(encoding="utf-8")


class ExportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="Analysis report", min_length=1, max_length=200)
    analysis_ids: list[UUID] = Field(default_factory=list, max_length=12)
    dashboard_ids: list[UUID] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def bounded(self):
        ids = self.analysis_ids + self.dashboard_ids
        if not 1 <= len(ids) <= MAX_SELECTIONS or len(set(ids)) != len(ids):
            raise ValueError("Choose 1–12 distinct selections.")
        return self


def safe_json(value):
    return (
        json.dumps(value, ensure_ascii=True, allow_nan=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def esc(value):
    return html.escape(str(value), quote=True)


def render_report(title, items):
    sections = []
    chart_data = []
    for item in items:
        table = item.get("table")
        rows = ""
        if table:
            rows = "<div class='table'><table><thead><tr>" + "".join(f"<th>{esc(c)}</th>" for c in table["columns"])
            rows += (
                "</tr></thead><tbody>"
                + "".join(
                    "<tr>" + "".join(f"<td>{esc(row.get(c))}</td>" for c in table["columns"]) + "</tr>"
                    for row in table["rows"]
                )
                + "</tbody></table></div>"
            )
            if table["truncated"]:
                rows += "<p>Only the first 500 result rows are shown.</p>"
        charts = ""
        for chart in item["charts"]:
            index = len(chart_data)
            chart_data.append(chart)
            charts += f"<div class='chart' id='chart-{index}' aria-label='{esc(chart['title'])}'></div>"
            charts += "".join(f"<p>{esc(c)}</p>" for c in chart.get("caveats", []))
        details = "".join(
            f"<details><summary>{label}</summary>"
            f"<pre>{esc(json.dumps(value, indent=2, ensure_ascii=False))}</pre></details>"
            for label, value in [
                ("Dataset versions", item["dataset_versions"]),
                ("Method, assumptions and join details", item["method"]),
                ("Anomaly evidence", item.get("anomalies")),
            ]
            if value
        )
        metric = ""
        if table and len(table["columns"]) == 1 and len(table["rows"]) == 1 and not table["truncated"]:
            column = table["columns"][0]
            value = table["rows"][0].get(column)
            if re.match(r"^(DECIMAL|DOUBLE|FLOAT|.*INT)", table.get("types", {}).get(column, "")) and value is not None:
                metric = f"<div class='metric'>{esc(value)}<span>{esc(column.replace('_', ' '))}</span></div>"
        sources = "".join(
            f"<span class='source'>{esc(v['display_name'])} &middot; v{esc(v['version'])}</span>"
            for v in item["dataset_versions"]
        )
        sections.append(
            "<section class='card'><div class='card-heading'>"
            f"<span class='eyebrow'>ANALYSIS {len(sections) + 1:02d}</span>"
            f"<span class='verified'>Saved evidence</span></div><h2>{esc(item['question'])}</h2>"
            f"<div class='sources'>{sources}</div>"
            f"<p class='timestamp'>Evidence generated: {esc(item['created_at'])}</p>"
            f"<p class='answer'>{esc(item['answer'])}</p>{metric}{charts}"
            f"<details class='supporting' open><summary>Supporting results</summary>{rows}</details>{details}"
            f"<details><summary>SQL</summary><pre>{esc(item['sql'])}</pre></details>"
            f"<p>{esc(item.get('chart_error') or '')}</p></section>"
        )
    document = (
        """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline';
style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'">
<title>"""
        + esc(title)
        + """</title><style>
*{box-sizing:border-box}
body{font:14px/1.6 system-ui,-apple-system,sans-serif;
color:#233047;
background:#f3f5fa;
margin:0;
padding:48px
32px}

.report-header,main,.report-note{max-width:1280px;
margin:auto}
.report-header{padding:36px
40px;
border-radius:20px;
background:#17233b;
color:#fff;
position:relative;
border-top:4px solid #a78bfa}

.report-header h1{font-size:clamp(28px,4vw,44px);
line-height:1.15;
letter-spacing:-1.5px;
margin:12px 0 18px}
.report-header p{color:#b9c6dc;
margin:6px 0}
.eyebrow{font-size:10px;
letter-spacing:1.8px;
font-weight:700;
color:#8270bc}
.report-header .eyebrow{color:#c4b5fd}

.report-note{padding:22px 4px;
color:#64748b;
font-size:12px}
main{display:grid;
grid-template-columns:repeat(2,minmax(0,1fr));
gap:24px;
align-items:start}

.card{min-width:0;
background:white;
padding:28px;
border:1px solid #e0e5ef;
border-radius:16px;
box-shadow:0 4px
18px #17233b05}
.card-heading{display:flex;
justify-content:space-between;
align-items:center;
gap:12px}
.verified{font-size:10px;
color:#247860;
background:#eaf7f1;
padding:4px 9px;
border-radius:20px}

h2{font-size:20px;
line-height:1.35;
letter-spacing:-.4px;
margin:16px 0 12px;
color:#17233b}
.sources{display:flex;
flex-wrap:wrap;
gap:6px}
.source{font-size:10px;
background:#f1f3f8;
color:#596780;
padding:4px 8px;
border-radius:5px}
.timestamp{font-size:10px;
color:#8894a6}
.answer{color:#64748b;
font-size:13px;
margin:18px 0}

.metric{font-size:48px;
line-height:1.15;
letter-spacing:-2px;
font-weight:650;
color:#6545b5;
padding:18px 0
28px;
font-variant-numeric:tabular-nums}
.metric
span{display:block;
font-size:11px;
letter-spacing:.6px;
text-transform:uppercase;
font-weight:500;
color:#78849a;
margin-top:12px}

details{border-top:1px solid #edf0f5;
padding:12px 0}
summary{cursor:pointer;
font-size:12px;
font-weight:600;
color:#52627b}
summary:hover{color:#6545b5}
pre{white-space:pre-wrap;
overflow-wrap:anywhere;
font-size:11px;
background:#f6f7fb;
padding:16px;
border-radius:8px;
line-height:1.7;
color:#52627b}

.table{overflow:auto;
margin-top:12px}
table{border-collapse:collapse;
width:100%;
font-size:12px}
th,td{padding:11px 12px;
border-bottom:1px solid #edf0f5;
text-align:left;
white-space:nowrap}
th{background:#f7f8fc;
color:#7b879a;
font-size:10px;
letter-spacing:.6px;
text-transform:uppercase}
td{font-variant-numeric:tabular-nums}
tbody tr:hover{background:#faf9ff}
.chart{height:320px;
margin:12px 0 20px}

@media(max-width:800px){body{padding:20px 14px}
.report-header{padding:26px 22px}
main{grid-template-columns:1fr}
.card{padding:22px}
.chart{height:300px}
}

.theme-toggle{float:right;border:1px solid #64748b;border-radius:8px;padding:9px 14px;
background:#24334e;color:#fff;cursor:pointer;font:inherit;font-size:12px;margin:0 0 12px 12px}
.theme-toggle:focus-visible{outline:3px solid #c4b5fd;outline-offset:3px}
@media screen{
body[data-theme="dark"]{color-scheme:dark;background:#0c101a;color:#dce3f0}
body[data-theme="dark"] .report-header{background:#171d30;border-top-color:#a78bfa}
body[data-theme="dark"] .card{background:#151b29;border-color:#2b3448;box-shadow:0 6px 24px #0002}
body[data-theme="dark"] h2{color:#eef2fb}
body[data-theme="dark"] .eyebrow,body[data-theme="dark"] .metric{color:#c4b5fd}
body[data-theme="dark"] .report-note,body[data-theme="dark"] .answer,
body[data-theme="dark"] summary,body[data-theme="dark"] .metric span{color:#acbad1}
body[data-theme="dark"] .timestamp{color:#98a8c2}
body[data-theme="dark"] .source{background:#242d40;color:#c0cce0}
body[data-theme="dark"] .verified{background:#183b32;color:#8ce2bf}
body[data-theme="dark"] details,body[data-theme="dark"] th,body[data-theme="dark"] td{border-color:#2b3448}
body[data-theme="dark"] pre,body[data-theme="dark"] th{background:#101624;color:#b9c6dd}
body[data-theme="dark"] tbody tr:hover{background:#20283c}
}
@media print{.theme-toggle{display:none}body{padding:0;
background:white;
font-size:11pt}
.report-header{background:white;
color:#17233b;
border:0;
padding:12px 0}
.report-header p{color:#64748b}
main{display:block}
.card{box-shadow:none;
margin:16px 0;
break-inside:avoid}
.table{overflow:visible}
tr,.chart{break-inside:avoid}
thead{display:table-header-group}
details>*{display:block!important}
}

</style></head><body data-theme="dark"><header class="report-header">
<button class="theme-toggle" type="button" aria-label="Dark theme" aria-pressed="true">Switch to light</button>
<span class="eyebrow">DIGITAL BACK OFFICE / INSIGHTS REPORT</span><h1>"""
        + esc(title)
        + f"</h1><p>{len(items)} analyses &middot; Offline HTML report</p>"
        + f"<p>Report generated: {datetime.now(UTC).isoformat()}</p></header>"
    )
    document += (
        "<p class='report-note'>Saved evidence snapshot; opening this report does not recompute results. "
        "Statistical associations do not establish causation. Query filters, limits, "
        "null handling and source versions apply.</p>"
    )
    document += "<main>" + "".join(sections) + "</main>"
    document += "<script>" + RUNTIME.replace("</script", "<\\/script") + "</script>"
    document += '<script type="application/json" id="chart-data">' + safe_json(chart_data) + "</script>"
    document += """<script>
const plain=v=>String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const printMedia=window.matchMedia('print');
const isDark=()=>document.body.dataset.theme==='dark'&&!printMedia.matches;
const palette=()=>isDark()?{paper:'#151b29',text:'#b9c6dd',grid:'#2b3448'}:
{paper:'white',text:'#64748b',grid:'#edf0f5'};
const applyChartTheme=()=>{
 const p=palette();
 document.querySelectorAll('.chart').forEach(el=>{
  if(el.classList.contains('js-plotly-plot')) Plotly.relayout(el,{
   paper_bgcolor:p.paper,plot_bgcolor:p.paper,'font.color':p.text,'yaxis.gridcolor':p.grid
  });
 });
};
document.querySelector('.theme-toggle').addEventListener('click',event=>{
 const dark=document.body.dataset.theme!=='dark';
 document.body.dataset.theme=dark?'dark':'light';
 event.currentTarget.textContent=dark?'Switch to light':'Switch to dark';
 event.currentTarget.setAttribute('aria-pressed',String(dark));
 applyChartTheme();
});
printMedia.addEventListener('change',applyChartTheme);
JSON.parse(document.getElementById('chart-data').textContent).forEach((c,i)=>{
const p=palette();
const x=c.points.map(p=>typeof p.x==='number'?p.x:plain(p.x)),y=c.points.map(p=>p.y===null?null:Number(p.y));
const trace=c.type==='pie'?{type:'pie',labels:x,values:y}:{type:c.type==='bar'?'bar':'scatter',x,y,
mode:c.type==='line'?'lines+markers':'markers',connectgaps:false,marker:{color:'#8b5cf6',size:7},line:{color:'#8b5cf6',width:3}};
Plotly.newPlot('chart-'+i,[trace],{title:{text:plain(c.title)},paper_bgcolor:p.paper,plot_bgcolor:p.paper,
font:{color:p.text,family:'system-ui, sans-serif',size:11},
colorway:['#8b5cf6','#38bdf8','#34d399','#fbbf24'],xaxis:{title:{text:plain(c.x_label)},showgrid:false,zeroline:false},
yaxis:{title:{text:plain(c.y_label)},gridcolor:p.grid,zeroline:false},
margin:{t:50,b:60,l:65,r:20},bargap:0.4},{responsive:true,displayModeBar:false}).then(applyChartTheme).catch(()=>{
document.getElementById('chart-'+i).textContent='Chart unavailable. See supporting table.';});
});</script></body></html>"""
    result = document.encode("utf-8")
    if len(result) > MAX_REPORT_BYTES:
        raise HTTPException(413)
    return result


@router.post("/export")
def export(body: ExportInput, request: Request, user: User = Depends(current_user)):
    from time import perf_counter

    from app.observability import emit

    operation_started = perf_counter()
    with request.app.state.sessions() as db:
        ids = list(body.analysis_ids)
        for dashboard_id in body.dashboard_ids:
            dashboard = public_dashboard(db, user, owned_dashboard(db, user, dashboard_id))
            if any(c["status"] != "complete" for c in dashboard["cards"]):
                raise HTTPException(409)
            ids.extend(UUID(c["analysis_id"]) for c in dashboard["cards"])
        ids = list(dict.fromkeys(ids))
        if not 1 <= len(ids) <= MAX_SELECTIONS:
            raise HTTPException(422)
        items = [evidence(db, user, aid) for aid in ids]
        if any(item["status"] != "complete" for item in items):
            raise HTTPException(409)
        content = render_report(body.title, items)
    # A new transaction reauthorizes after rendering, including concurrent deletion/version changes.
    with request.app.state.sessions() as db:
        for dashboard_id in body.dashboard_ids:
            owned_dashboard(db, user, dashboard_id)
        for aid in ids:
            evidence(db, user, aid)
    filename = re.sub(r"[^a-zA-Z0-9_-]+", "-", body.title).strip("-")[:60] or "analysis-report"
    emit("export", duration_ms=round((perf_counter() - operation_started) * 1000), outcome="success")
    return Response(
        content,
        media_type="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.html"',
            "X-Content-Type-Options": "nosniff",
        },
    )
