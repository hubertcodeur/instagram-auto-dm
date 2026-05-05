import { NextRequest, NextResponse } from 'next/server'
import { randomBytes } from 'crypto'

export async function GET(req: NextRequest) {
  const state = randomBytes(32).toString('hex')

  const params = new URLSearchParams({
    client_id: process.env.META_APP_ID!,
    redirect_uri: `${process.env.NEXT_PUBLIC_BASE_URL}/api/auth/callback`,
    scope: 'instagram_business_basic,instagram_business_manage_messages,instagram_business_manage_insights',
    response_type: 'code',
    state,
  })

  const response = NextResponse.redirect(
    `https://api.instagram.com/oauth/authorize?${params.toString()}`
  )

  response.cookies.set('oauth_state', state, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 600,
  })

  return response
}
