# Password reset (manual procedure, R0)

**Context:** R0 has no email provider (zero budget, D6), so there is no
self-service email reset flow. Until the email epic lands, a locked-out user is
recovered by an operator through a controlled manual procedure. This is
documented per T-010's exclusion note.

## Policy

- There is **no** "forgot password" endpoint in R0. Do not add an unauthenticated
  reset endpoint — that would reintroduce an account-takeover surface.
- Resets are performed by an operator with database access, only after
  verifying the requester out-of-band.

## Procedure

1. **Verify identity out-of-band** (the user contacts you through a channel you
   already trust). Never act on an in-app or emailed request alone.
2. **Set a temporary password** for the user. Generate the argon2id hash with
   the app's own hasher so the format/params match:

   ```bash
   cd backend
   poetry run python - <<'PY'
   import secrets
   from app.modules.identity.security import hash_password
   tmp = secrets.token_urlsafe(12)
   print("temp password:", tmp)
   print("password_hash:", hash_password(tmp))
   PY
   ```

3. **Update the row and force re-login** (revoke existing sessions):

   ```sql
   UPDATE users
      SET password_hash = :hash,
          password_algo = 'argon2id',
          failed_login_count = 0,
          locked_until = NULL
    WHERE email = :email;

   -- Invalidate any active sessions for that user.
   UPDATE sessions s
      SET revoked_at = now()
     FROM users u
    WHERE s.user_id = u.id AND u.email = :email AND s.revoked_at IS NULL;
   ```

4. **Deliver the temporary password** over the same trusted out-of-band channel
   and instruct the user to change it after logging in.
5. **Record an audit event** (the SQL writes to the row directly, so add an
   `audit_events` entry noting the manual reset, actor, and reason).

## Unlocking a throttled account (no password change)

If the user only tripped the login lockout (SEC-04) and knows their password:

```sql
UPDATE users SET failed_login_count = 0, locked_until = NULL WHERE email = :email;
```

## Future

The self-service reset flow (tokenized, email-delivered, single-use, expiring)
is designed in `docs/architecture/security-model.md` and ships with the email
epic in a later release.
