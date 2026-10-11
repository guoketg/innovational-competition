curl -s -X POST http://127.0.0.1:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"dsa_e2e_probe","password":"Probe#2026dsa","nickname":"DSA E2E 探针"}' \
  -o /tmp/_reg.json -w 'HTTP=%{http_code}\n'
echo "--- 响应 ---"
python3 -c "
import json
d=json.load(open('/tmp/_reg.json'))
print('code=', d.get('code'), 'msg=', d.get('message'))
u=(d.get('data') or {}).get('user') or {}
print('user_id=', u.get('id'), 'username=', u.get('username'))
" 2>&1
