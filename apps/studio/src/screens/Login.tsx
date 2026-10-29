// Staff sign-in (BRIEF Section 17): local accounts with the roles operator, curator and admin.
import { useState } from 'react';
import { Button, Title } from '@petpop/ui';
import { useSession } from '../store/session';

export function LoginScreen() {
  const login = useSession((s) => s.login);
  const error = useSession((s) => s.loginError);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      await login(username.trim(), password);
    } finally {
      setBusy(false);
    }
  };
  const field = 'w-full rounded-tile border-4 border-line bg-card px-8 py-6 text-4xl outline-none focus:border-accent';
  return (
    <form
      className="flex h-full flex-col justify-center gap-8 px-24"
      data-testid="login"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <div className="font-display text-8xl font-semibold tracking-tight">
        Pet<span className="text-accent">Pop</span> Studio
      </div>
      <Title sub="Staff only: generate, curate and publish library content.">Sign in</Title>
      <input className={field} placeholder="Username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} data-testid="login-username" />
      <input className={field} placeholder="Password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} data-testid="login-password" />
      {error && (
        <p className="text-3xl font-semibold text-accent2" data-testid="login-error">
          {error}
        </p>
      )}
      <Button type="submit" disabled={busy || !username.trim() || !password} data-testid="login-submit">
        {busy ? 'Signing in…' : 'Sign in'}
      </Button>
    </form>
  );
}
