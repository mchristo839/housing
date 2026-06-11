"""
Make REVIEW_PACK available in formats other than .xlsx:
  - REVIEW_PACK.csv    -> opens in Google Sheets, Numbers, Notepad, anywhere
  - REVIEW_PACK.html   -> double-click to open in any web browser, sortable

Same data as the .xlsx Review sheet, including auto quality flag column.
"""
import openpyxl, csv, sys, io, html as htmllib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SRC = 'data/scraped/REVIEW_PACK.xlsx'
OUT_CSV = 'data/scraped/REVIEW_PACK.csv'
OUT_HTML = 'data/scraped/REVIEW_PACK.html'

wb = openpyxl.load_workbook(SRC, read_only=True)
ws = wb['Review']

# Pull rows including header
rows = list(ws.iter_rows(values_only=True))
headers = list(rows[0])
data = rows[1:]

# CSV
with open(OUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(headers)
    for r in data:
        w.writerow(['' if c is None else c for c in r])
print(f"Wrote {OUT_CSV}")

# HTML
parts = []
parts.append('<!doctype html><html><head><meta charset="utf-8">')
parts.append('<title>Review pack — supported-housing contracts</title>')
parts.append('<style>')
parts.append('body{font:14px -apple-system,Segoe UI,Roboto,sans-serif;margin:1em;background:#fafafa;color:#222}')
parts.append('h1{margin:0 0 .3em 0;font-size:20px}')
parts.append('.meta{color:#666;margin-bottom:1em}')
parts.append('.toolbar{position:sticky;top:0;background:#fff;padding:8px;border-bottom:1px solid #ccc;z-index:10;box-shadow:0 1px 4px rgba(0,0,0,.04);margin-bottom:8px}')
parts.append('.toolbar input{padding:6px 10px;width:280px;font-size:14px;border:1px solid #bbb;border-radius:4px}')
parts.append('.toolbar select{padding:6px;margin-left:6px}')
parts.append('.counts{margin-left:1em;color:#444;font-size:13px}')
parts.append('table{border-collapse:collapse;width:100%;background:#fff;font-size:13px}')
parts.append('th{background:#1F4E79;color:#fff;padding:8px;text-align:left;position:sticky;top:60px}')
parts.append('td{border:1px solid #ddd;padding:6px;vertical-align:top;max-width:340px}')
parts.append('tr.y{background:#d4edda} tr.n{background:#f8d7da} tr.q{background:#fff3cd}')
parts.append('tr.panlondon td:nth-child(4){background:#fff2cc;font-weight:600}')
parts.append('.flag{color:#a04000;font-weight:600;font-size:12px}')
parts.append('select.mark{font-size:13px;padding:3px;width:62px}')
parts.append('.hidden{display:none}')
parts.append('a{color:#0563C1}')
parts.append('</style></head><body>')
parts.append('<h1>Review pack — supported-housing contracts (London)</h1>')
parts.append(f'<div class="meta">{len(data)} proposed rows from <code>curated_scraped.xlsx</code>. ')
parts.append('Mark Y / N / ? in column A. Marks save automatically in your browser as you go. When done, click <b>Download my marks (CSV)</b> and send me the file — I&rsquo;ll import it and promote the approved rows to the live site.</div>')

parts.append('<div class="toolbar">')
parts.append('Filter: <input id="q" placeholder="type borough, supplier, contract..." oninput="flt()">')
parts.append('<select id="flag" onchange="flt()"><option value="">All quality flags</option><option value="MISCLASSIFIED">MISCLASSIFIED</option><option value="FRAMEWORK">FRAMEWORK</option><option value="PLACEHOLDER">PLACEHOLDER</option><option value="OK">no flag</option></select>')
parts.append('<select id="status" onchange="flt()"><option value="">Any mark</option><option value="Y">Y</option><option value="N">N</option><option value="?">?</option></select>')
parts.append('<button onclick="exportMarks()" style="margin-left:8px;padding:6px 14px;background:#1F4E79;color:#fff;border:none;border-radius:4px;cursor:pointer;font-weight:600">Download my marks (CSV)</button>')
parts.append('<button onclick="bulkApprove()" style="margin-left:6px;padding:6px 10px">Approve all visible</button>')
parts.append('<button onclick="bulkReject()" style="margin-left:6px;padding:6px 10px">Reject all visible</button>')
parts.append('<button onclick="clearMarks()" style="margin-left:6px;padding:6px 10px;color:#a00">Clear all</button>')
parts.append('<span class="counts" id="c"></span>')
parts.append('</div>')

parts.append('<table id="t"><thead><tr>')
for h in headers:
    parts.append(f'<th>{htmllib.escape(str(h))}</th>')
parts.append('</tr></thead><tbody>')

for i, r in enumerate(data):
    company = str(r[3] or '')
    council_raw = str(r[12] or '')
    is_pan = any(k in council_raw.lower() for k in ('capital letters','greater london authority','mopac','mayor','london councils','ministry of housing'))
    flag = str(r[1] or '')
    flag_cls = ''
    if flag.startswith('MISCLASSIFIED'): flag_cls = 'flag-mis'
    elif flag.startswith('FRAMEWORK') or flag.startswith('PLACEHOLDER'): flag_cls = 'flag-fr'
    mark = str(r[0] or '').upper()
    rowcls = ''
    if mark == 'Y': rowcls = 'y'
    elif mark == 'N': rowcls = 'n'
    elif mark == '?': rowcls = 'q'
    if is_pan: rowcls += ' panlondon'
    parts.append(f'<tr class="{rowcls}" data-i="{i}">')
    for j, c in enumerate(r):
        val = '' if c is None else str(c)
        if j == 0:  # Approve dropdown
            opts = ''.join(f'<option value="{v}"{" selected" if v==mark else ""}>{v or "—"}</option>' for v in ('','Y','N','?'))
            parts.append(f'<td><select class="mark" onchange="m(this,{i})">{opts}</select></td>')
        elif j == 10 and val.startswith('http'):  # URL → link
            parts.append(f'<td><a href="{htmllib.escape(val)}" target="_blank">source</a></td>')
        elif j == 1 and val:  # quality flag
            parts.append(f'<td class="flag">{htmllib.escape(val)}</td>')
        else:
            v = htmllib.escape(val)
            if len(v) > 200: v = v[:200] + '…'
            parts.append(f'<td>{v}</td>')
    parts.append('</tr>')

parts.append('</tbody></table>')

parts.append('<script>')
parts.append('const marks={};')
parts.append('function m(sel,i){marks[i]=sel.value; const tr=sel.closest("tr"); tr.className=tr.className.replace(/\\b(y|n|q)\\b/g,"").trim(); const v=sel.value; if(v==="Y")tr.classList.add("y"); else if(v==="N")tr.classList.add("n"); else if(v==="?")tr.classList.add("q"); save(); cnt();}')
parts.append('function save(){try{localStorage.setItem("reviewMarks",JSON.stringify(marks))}catch(e){}}')
parts.append('function load(){try{const j=JSON.parse(localStorage.getItem("reviewMarks")||"{}"); for(const i in j){const s=document.querySelector(`tr[data-i="${i}"] select.mark`); if(s){s.value=j[i]; marks[i]=j[i]; m(s,i);}}}catch(e){}}')
parts.append('function flt(){const q=document.getElementById("q").value.toLowerCase(); const f=document.getElementById("flag").value; const s=document.getElementById("status").value; const trs=document.querySelectorAll("tbody tr"); let shown=0; trs.forEach(tr=>{const t=tr.textContent.toLowerCase(); const flagCell=tr.cells[1].textContent; const markCell=tr.cells[0].querySelector("select").value; let ok=true; if(q && !t.includes(q)) ok=false; if(f==="OK" && flagCell) ok=false; else if(f && f!=="OK" && !flagCell.includes(f)) ok=false; if(s && markCell!==s) ok=false; tr.style.display=ok?"":"none"; if(ok)shown++;}); document.getElementById("c").textContent=shown+" of "+trs.length+" shown"; cnt();}')
parts.append('function cnt(){const trs=document.querySelectorAll("tbody tr"); let y=0,n=0,q=0,u=0; trs.forEach(tr=>{const v=tr.cells[0].querySelector("select").value; if(v==="Y")y++; else if(v==="N")n++; else if(v==="?")q++; else u++;}); document.getElementById("c").textContent=`Y:${y} · N:${n} · ?:${q} · unmarked:${u} (of ${trs.length})`;}')
parts.append('window.onload=()=>{load();cnt();};')
parts.append('function bulkApprove(){if(!confirm("Set Approve=Y on all currently visible rows?"))return; document.querySelectorAll("tbody tr").forEach(tr=>{if(tr.style.display!=="none"){const s=tr.cells[0].querySelector("select"); s.value="Y"; m(s,parseInt(tr.dataset.i));}});}')
parts.append('function bulkReject(){if(!confirm("Set Approve=N on all currently visible rows?"))return; document.querySelectorAll("tbody tr").forEach(tr=>{if(tr.style.display!=="none"){const s=tr.cells[0].querySelector("select"); s.value="N"; m(s,parseInt(tr.dataset.i));}});}')
parts.append('function clearMarks(){if(!confirm("Wipe ALL marks (cannot undo)?"))return; document.querySelectorAll("tbody tr").forEach(tr=>{const s=tr.cells[0].querySelector("select"); s.value=""; m(s,parseInt(tr.dataset.i));}); localStorage.removeItem("reviewMarks");}')
parts.append('window.exportMarks=()=>{const rows=document.querySelectorAll("tbody tr"); const lines=["row_index,supplier,council_raw,source_id,mark,notes"]; rows.forEach(tr=>{const v=tr.cells[0].querySelector("select").value; if(!v)return; const i=tr.dataset.i; const supplier=tr.cells[4].textContent.replace(/"/g,\'""\'); const council=tr.cells[12].textContent.replace(/"/g,\'""\'); const sid=tr.cells[11].textContent.replace(/"/g,\'""\'); const notes=tr.cells[2].textContent.replace(/"/g,\'""\'); lines.push(`${i},"${supplier}","${council}","${sid}",${v},"${notes}"`);}); if(lines.length===1){alert("No marks to export yet — mark some rows Y/N/? first.");return;} const blob=new Blob([lines.join("\\n")],{type:"text/csv"}); const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download="review_marks.csv"; a.click(); a.remove();}')
parts.append('</script>')
parts.append('</body></html>')

with open(OUT_HTML, 'w', encoding='utf-8') as f:
    f.write(''.join(parts))
print(f"Wrote {OUT_HTML}")

# Also write a sync script that loads marks back from a CSV/HTML export
print(f"\nReview options now available:")
print(f"  XLSX  : {SRC}")
print(f"  CSV   : {OUT_CSV}   (open in any spreadsheet app)")
print(f"  HTML  : {OUT_HTML}  (double-click to open in any browser)")
