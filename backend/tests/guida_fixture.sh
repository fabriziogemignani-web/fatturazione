#!/bin/bash
# Iteration 64 fixture for Guida UI test: setup | clean
set -e
URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)
if [ "$1" = "setup" ]; then
  curl -s -c /tmp/g64.cookie -X POST "$URL/api/auth/login" -H 'Content-Type: application/json' \
    -d '{"email":"fabrizio.gemignani@gmail.com","password":"Fe-Admin-2aOBey8irzL8"}' > /dev/null
  curl -s -b /tmp/g64.cookie -X POST "$URL/api/companies" -H 'Content-Type: application/json' \
    -d '{"denominazione":"TEST_G64 Srl","partita_iva":"12345678903","indirizzo":"Via Test 1","cap":"00100","comune":"Roma","provincia":"RM"}' | tee /tmp/g64.company
  echo
  CID=$(python3 -c "import json;print(json.load(open('/tmp/g64.company'))['id'])")
  mongosh test_database --quiet --eval "
    for (const r of ['operatore','contabile']) {
      db.users.insertOne({user_id:'test_g64_'+r, email:'test.user.g64.'+r+'@example.com', name:'TEST_G64 '+r, role:r, status:'approved', email_verified:true, company_ids:['$CID'], created_at:new Date().toISOString()});
      db.user_sessions.insertOne({user_id:'test_g64_'+r, session_token:'test_session_g64_'+r, expires_at:new Date(Date.now()+86400000), created_at:new Date().toISOString()});
    }
    db.user_sessions.insertOne({user_id:'user_ff7b2b259474', session_token:'test_session_g64_admin', expires_at:new Date(Date.now()+86400000), created_at:new Date().toISOString()});
    db.users.updateOne({user_id:'user_ff7b2b259474'},{\$addToSet:{company_ids:'$CID'}});
  "
  echo "CID=$CID"
elif [ "$1" = "clean" ]; then
  CID=$(python3 -c "import json;print(json.load(open('/tmp/g64.company'))['id'])")
  curl -s -b /tmp/g64.cookie -X DELETE "$URL/api/companies/$CID"; echo
  mongosh test_database --quiet --eval "
    db.users.deleteMany({user_id:{\$in:['test_g64_operatore','test_g64_contabile']}});
    db.user_sessions.deleteMany({session_token:{\$in:['test_session_g64_operatore','test_session_g64_contabile','test_session_g64_admin']}});
    db.users.updateOne({user_id:'user_ff7b2b259474'},{\$pull:{company_ids:'$CID'}});
    print(db.companies.countDocuments({denominazione:/TEST_G64/}), db.users.countDocuments({user_id:/test_g64/}));
  "
  curl -s -b /tmp/g64.cookie -X POST "$URL/api/auth/logout" > /dev/null
fi
