import { NextRequest, NextResponse } from 'next/server'

export function middleware(request: NextRequest) {
  if (request.nextUrl.pathname.startsWith('/dashboard')) {
    const oauthState = request.cookies.get('oauth_state')
    // Le compte est vérifié côté serveur via /api/auth/me
    // On laisse passer — le dashboard gère lui-même la redirection si pas de compte
    return NextResponse.next()
  }
  return NextResponse.next()
}

export const config = {
  matcher: ['/dashboard/:path*'],
}
