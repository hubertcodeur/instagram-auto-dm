import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { sendDM, verifyWebhookSignature } from '@/lib/meta'

interface CommentData {
  id: string
  text?: string
  from?: { id: string }
}

interface WebhookBody {
  object: string
  entry?: Array<{
    id: string
    changes?: Array<{ field: string; value: CommentData }>
  }>
}

// Vérification du webhook par Meta (GET)
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const mode = searchParams.get('hub.mode')
  const token = searchParams.get('hub.verify_token')
  const challenge = searchParams.get('hub.challenge')

  if (mode === 'subscribe' && token === process.env.META_WEBHOOK_VERIFY_TOKEN) {
    return new NextResponse(challenge, { status: 200 })
  }
  return new NextResponse('Forbidden', { status: 403 })
}

// Réception des événements Meta (POST)
export async function POST(req: NextRequest) {
  const rawBody = await req.text()

  const signature = req.headers.get('x-hub-signature-256') || ''
  if (!verifyWebhookSignature(rawBody, signature)) {
    return new NextResponse('Invalid signature', { status: 401 })
  }

  let body: WebhookBody
  try {
    body = JSON.parse(rawBody)
  } catch {
    return new NextResponse('Invalid JSON', { status: 400 })
  }

  // Répondre 200 immédiatement (Meta exige < 20s)
  processEvent(body).catch(console.error)
  return new NextResponse('EVENT_RECEIVED', { status: 200 })
}

async function processEvent(body: WebhookBody) {
  if (body.object !== 'instagram') return

  for (const entry of body.entry ?? []) {
    const igUserId = entry.id

    const { data: account } = await supabase
      .from('ig_accounts')
      .select('access_token')
      .eq('ig_user_id', igUserId)
      .single()

    if (!account) continue

    for (const change of entry.changes ?? []) {
      if (change.field === 'comments') {
        await handleComment(change.value, igUserId, account.access_token)
      }
    }
  }
}

async function handleComment(comment: CommentData, igUserId: string, accessToken: string) {
  const commentId = comment.id
  const commentText = comment.text
  const senderId = comment.from?.id

  if (!senderId || !commentId) return
  if (!commentText || typeof commentText !== 'string') return

  const lowerText = commentText.toLowerCase().trim()
  if (!lowerText) return

  // Anti-doublon
  const { data: existing } = await supabase
    .from('sent_dms')
    .select('comment_id')
    .eq('comment_id', commentId)
    .maybeSingle()

  if (existing) return

  const { data: rules } = await supabase
    .from('keyword_rules')
    .select('keyword, dm_message')
    .eq('ig_user_id', igUserId)
    .eq('is_active', true)

  if (!rules) return

  const matchedRule = rules.find(rule =>
    lowerText.includes(rule.keyword.toLowerCase())
  )

  if (!matchedRule) return

  try {
    await sendDM(senderId, matchedRule.dm_message, accessToken)
    await supabase.from('sent_dms').insert({
      comment_id: commentId,
      ig_user_id: igUserId,
      recipient: senderId,
    })
  } catch (err) {
    console.error('DM send error:', err)
  }
}
