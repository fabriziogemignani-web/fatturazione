use('test_database');
const roles = [['admin','approved'],['contabile','approved'],['operatore','approved'],['operatore','pending']];
const exp = new Date(Date.now() + 7*24*60*60*1000);
roles.forEach(([r,s]) => {
  const uid = `test-user-T1-${r}-${s}`;
  const tok = `test_session_T1_${r}_${s}`;
  db.users.deleteMany({user_id: uid}); db.user_sessions.deleteMany({user_id: uid});
  db.users.insertOne({user_id: uid, email: `test.user.t1.${r}.${s}@example.com`, name: `TEST_T1 ${r} ${s}`, picture: '', role: r, status: s, created_at: new Date().toISOString()});
  db.user_sessions.insertOne({user_id: uid, session_token: tok, expires_at: exp, created_at: new Date().toISOString()});
});
print('ok');
