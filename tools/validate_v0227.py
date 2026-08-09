#!/usr/bin/env python3
from __future__ import annotations
import json,sys
from pathlib import Path

def main(root_s:str)->int:
    root=Path(root_s).resolve(); sys.path.insert(0,str(root/'.agents'))
    from agentos.db import connect
    from agentos.cli_runtime import command_registry
    from agentos.mcp_runtime import ALL_TOOLS
    with connect(root) as c:
        schema=int(c.execute('select max(version) from schema_migrations').fetchone()[0]); fk=int(c.execute('pragma foreign_keys').fetchone()[0])
    g=json.loads((root/'.agents/config/governance.json').read_text()); cli=command_registry(); names=[t['name'] for t in ALL_TOOLS]
    privacy=[n for n in names if 'data_subject_erasure' in n]
    forbidden=[n for n in names if any(x in n for x in ('erasure_execute','erasure_approve','erasure_review','target_update','target_delete','credential'))]
    result={'ok':(root/'VERSION').read_text().strip()=='0.22.7' and schema==43 and fk==1 and len(cli)==len(set(cli)) and len(names)==len(set(names)) and len(privacy)==3 and not forbidden and g.get('data_subject_rights_policy',{}).get('target_delete_allowed') is False,
            'version':(root/'VERSION').read_text().strip(),'schema':schema,'foreign_keys':fk,'cli_count':len(cli),'mcp_count':len(names),'privacy_mcp':privacy,'forbidden_mcp':forbidden}
    print(json.dumps(result,indent=2)); return 0 if result['ok'] else 1
if __name__=='__main__': raise SystemExit(main(sys.argv[1]))
