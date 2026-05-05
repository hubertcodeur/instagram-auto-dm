import { NextResponse } from 'next/server'

export async function GET() {
  const params = new URLSearchParams({
    client_id: process.env.META_APP_ID!,
    redirect_uri: `${process.env.NEXT_PUBLIC_BASE_URL}/api/auth/callback`,
    scope: 'instagram_business_basic,instagram_business_manage_messages',
    response_type: 'code',
  })

  return NextResponse.redirect(
    `https://www.instagram.com/oauth/authorize?${params.toString()}`
  )
}
