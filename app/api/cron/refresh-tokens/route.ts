import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { refreshLongLivedToken } from '@/lib/meta'

// Cron Vercel — refresh tous les tokens qui expirent dans moins de 10 jours
export async function GET(req: NextRequest) {
  const auth = req.headers.get('authorization')
  if (auth !== `Bearer ${process.env.CRON_SECRET}`) {
    return new NextResponse('Unauthorized', { status: 401 })
  }

  const in10Days = new Date(Date.now() + 10 * 24 * 60 * 60 * 1000).toISOString()

  const { data: accounts } = await supabase
    .from('ig_accounts')
    .select('ig_user_id, access_token')
    .lt('expires_at', in10Days)

  if (!accounts?.length) return NextResponse.json({ refreshed: 0 })

  let refreshed = 0
  for (const account of accounts) {
    try {
      const { access_token, expires_in } = await refreshLongLivedToken(account.access_token)
      const expiresAt = new Date(Date.now() + expires_in * 1000).toISOString()
      await supabase
        .from('ig_accounts')
        .update({ access_token, expires_at: expiresAt })
        .eq('ig_user_id', account.ig_user_id)
      refreshed++
    } catch (err) {
      console.error(`Token refresh failed for ${account.ig_user_id}:`, err)
    }
  }

  return NextResponse.json({ refreshed })
}
