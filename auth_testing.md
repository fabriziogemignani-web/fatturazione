# Auth testing (Emergent Google Auth)

Create test user + session with mongosh (db: test_database):
```
mongosh --eval "
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({user_id: userId, email: 'test.user.' + Date.now() + '@example.com', name: 'Test User', picture: '', role: 'admin', status: 'approved', created_at: new Date().toISOString()});
db.user_sessions.insertOne({user_id: userId, session_token: sessionToken, expires_at: new Date(Date.now() + 7*24*60*60*1000), created_at: new Date().toISOString()});
print('Session token: ' + sessionToken);
"
```
Users need `status: 'approved'` to access data; `role` one of admin / contabile / operatore.
Use `Authorization: Bearer <token>` for API, or cookie `session_token` (httpOnly, secure, sameSite None, path /) for browser.

Cleanup:
```
mongosh --eval "use('test_database'); db.users.deleteMany({email: /test\.user\./}); db.user_sessions.deleteMany({session_token: /test_session/});"
```
