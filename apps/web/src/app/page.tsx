'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { getSession } from '@/lib/session';

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    const session = getSession();
    if (!session) router.replace('/login');
    else if (session.user.mustChangePassword) router.replace('/change-password');
    else router.replace('/dashboard');
  }, [router]);
  return null;
}
