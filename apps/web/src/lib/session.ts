'use client';

import { PublicUser, TokenPair } from './api';

// Skeleton session store. Tokens live in localStorage for the M0 skeleton;
// harden to httpOnly cookies when the dashboard gains real data (M4).
const KEY = 'measurex.session';

export interface StoredSession {
  accessToken: string;
  refreshToken: string;
  user: PublicUser;
}

export function saveSession(tokens: TokenPair): void {
  const session: StoredSession = {
    accessToken: tokens.accessToken,
    refreshToken: tokens.refreshToken,
    user: tokens.user,
  };
  try {
    localStorage.setItem(KEY, JSON.stringify(session));
  } catch {
    // storage unavailable (private mode); callers degrade gracefully
  }
}

export function getSession(): StoredSession | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as StoredSession) : null;
  } catch {
    return null;
  }
}

export function clearSession(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}
