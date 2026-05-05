const GRAPH_API = 'https://graph.instagram.com/v21.0'

export async function sendDM(recipientId: string, message: string, accessToken: string) {
  const res = await fetch(`${GRAPH_API}/me/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      recipient: { id: recipientId },
      message: { text: message },
      access_token: accessToken,
    }),
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(`Meta API error: ${JSON.stringify(err)}`)
  }
  return res.json()
}

export async function refreshLongLivedToken(token: string): Promise<{ access_token: string; expires_in: number }> {
  const res = await fetch(
    `${GRAPH_API}/refresh_access_token?grant_type=ig_refresh_token&access_token=${token}`
  )
  if (!res.ok) throw new Error('Token refresh failed')
  return res.json()
}

export async function getIGUserInfo(accessToken: string) {
  const res = await fetch(`${GRAPH_API}/me?fields=id,username&access_token=${accessToken}`)
  if (!res.ok) throw new Error('Failed to get user info')
  return res.json()
}

export function verifyWebhookSignature(payload: string, signature: string): boolean {
  const crypto = require('crypto')
  const expected = crypto
    .createHmac('sha256', process.env.META_APP_SECRET!)
    .update(payload)
    .digest('hex')
  return `sha256=${expected}` === signature
}
