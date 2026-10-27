import hashlib,json,re,sys
from pathlib import Path
role=sys.argv[1]
root=Path('/opt/oai-gnb' if role=='gnb' else '/opt/oai-nr-ue')
exe=root/'bin'/('nr-softmodem' if role=='gnb' else 'nr-uesoftmodem')
paths=[exe, Path('/usr/local/lib/librfsimulator.so'), Path('/usr/local/lib/libtelnetsrv.so'),
       Path('/usr/local/lib/libtelnetsrv_ci.so' if role=='gnb' else '/usr/local/lib/libtelnetsrv_ciUE.so')]
needles=['trigger_n2_ho','trigger_f1_ho','HandoverRequired','HandoverRequest','HandoverNotify',
         'neighbour_list','RRCReconfiguration','reconfigurationWithSync','serveraddr','serverport']
result={'role':role,'inspection':'static_only_no_radio_started','files':[]}
for path in paths:
 item={'path':str(path),'exists':path.exists()}
 if path.is_file():
  data=path.read_bytes()
  strings=[item.decode('ascii') for item in re.findall(rb'[ -~]{8,}',data)]
  item.update(sha256=hashlib.sha256(data).hexdigest(),size=len(data),
              markers={needle:any(needle in s for s in strings) for needle in needles},
              revision_candidates=sorted(set(re.findall(r'\b[0-9a-f]{40}\b','\n'.join(strings))))[:25],
              version_context=[s[:300] for s in strings if re.search(r'Branch:|Abrev|[Vv]ersion:|git_info|GIT_HASH|PACKAGE_VERSION',s)][:25])
 result['files'].append(item)
entry=root/'bin/entrypoint.sh'
result['entrypoint']={'sha256':hashlib.sha256(entry.read_bytes()).hexdigest(),
 'relevant_lines':[line for line in entry.read_text().splitlines() if any(key in line for key in ('USE_ADDITIONAL_OPTIONS','exec ','config_file','gnb.conf','nr-ue.conf','nrue.conf'))]}
result['source_directories']={str(p):p.exists() for p in (Path('/oai-ran'),Path('/opt/oai-src'))}
print(json.dumps(result,indent=2))
