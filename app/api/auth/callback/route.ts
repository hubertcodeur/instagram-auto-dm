import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { getIGUserInfo } from '@/lib/meta'

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const code = searchParams.get('code')
  const state = searchParams.get('state')
  const storedState = req.cookies.get('oauth_state')?.value

  if (!state || state !== storedState) {
    return NextResponse.redirect(`${process.env.NEXT_PUBLIC_BASE_URL}/?error=invalid_state`)
  }

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
    console.error('Token exchange failed:', tokenData)
    return NextResponse.redirect(`${process.env.NEXT_PUBLIC_BASE_URL}/?error=token_failed`)
  }

  // Obtenir un token long (60 jours)
  const longTokenRes = await fetch(
    `https://graph.instagram.com/access_token?grant_type=ig_exchange_token&client_secret=${process.env.META_APP_SECRET}&access_token=${tokenData.access_token}`
  )

  if (!longTokenRes.ok) {
    console.error('Long token exchange failed:', await longTokenRes.text())
    return NextResponse.redirect(`${process.env.NEXT_PUBLIC_BASE_URL}/?error=token_exchange_failed`)
  }

  const longToken = await longTokenRes.json()
  if (!longToken.access_token || typeof longToken.expires_in !== 'number') {
    return NextResponse.redirect(`${process.env.NEXT_PUBLIC_BASE_URL}/?error=invalid_token`)
  }

  // Récupérer les infos du compte
  let userInfo: { id: string; username: string }
  try {
    userInfo = await getIGUserInfo(longToken.access_token)
  } catch (err) {
    console.error('Failed to get user info:', err)
    return NextResponse.redirect(`${process.env.NEXT_PUBLIC_BASE_URL}/?error=user_info_failed`)
  }

  const expiresAt = new Date(Date.now() + longToken.expires_in * 1000).toISOString()
  await supabase.from('ig_accounts').upsert({
    ig_user_id: userInfo.id,
    ig_username: userInfo.username,
    access_token: longToken.access_token,
    expires_at: expiresAt,
  })

  const response = NextResponse.redirect(`${process.env.NEXT_PUBLIC_BASE_URL}/dashboard?connected=1`)
  response.cookies.delete('oauth_state')
  return response
}
