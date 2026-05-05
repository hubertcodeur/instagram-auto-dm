import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { getIGUserInfo } from '@/lib/meta'

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const code = searchParams.get('code')

  if (!code) {
    return NextResponse.redirect(`${process.env.NEXT_PUBLIC_BASE_URL}/?error=no_code`)
  }

  // Échanger le code contre un token court
  const tokenRes = await fetch('https://api.instagram.com/oauth/access_token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: process.env.META_APP_ID!,
      client_secret: process.env.META_APP_SECRET!,
      grant_type: 'authorization_code',
      redirect_uri: `${process.env.NEXT_PUBLIC_BASE_URL}/api/auth/callback`,
      code,
    }),
  })

  const tokenData = await tokenRes.json()
  if (!tokenData.access_token) {
    return NextResponse.redirect(`${process.env.NEXT_PUBLIC_BASE_URL}/?error=token_failed`)
  }

  // Obtenir un token long (60 jours)
  const longTokenRes = await fetch(
    `https://graph.instagram.com/access_token?grant_type=ig_exchange_token&client_secret=${process.env.META_APP_SECRET}&access_token=${tokenData.access_token}`
  )
  const longToken = await longTokenRes.json()

  // Récupérer les infos du compte
  const userInfo = await getIGUserInfo(longToken.access_token)

  // Sauvegarder en base
  const expiresAt = new Date(Date.now() + longToken.expires_in * 1000).toISOString()
  await supabase.from('ig_accounts').upsert({
    ig_user_id: userInfo.id,
    ig_username: userInfo.username,
    access_token: longToken.access_token,
    expires_at: expiresAt,
  })

  return NextResponse.redirect(`${process.env.NEXT_PUBLIC_BASE_URL}/dashboard?connected=1`)
}
