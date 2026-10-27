import json,subprocess,sys
role=sys.argv[1]
exe='/opt/oai-gnb/bin/nr-softmodem' if role=='gnb' else '/opt/oai-nr-ue/bin/nr-uesoftmodem'
result={'role':role,'probe':'help_and_loader_only','argv':[exe,'--help']}
for key,argv in [('loader',['ldd',exe]),('help',[exe,'--help'])]:
 try:
  proc=subprocess.run(argv,text=True,capture_output=True,timeout=15)
  result[key]={'exit_code':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr}
 except subprocess.TimeoutExpired:
  result[key]={'status':'timeout'}
print(json.dumps(result,indent=2))
