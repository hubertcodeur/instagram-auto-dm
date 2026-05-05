import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { sendDM, verifyWebhookSignature } from '@/lib/meta'

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

  // Vérifier la signature Meta
  const signature = req.headers.get('x-hub-signature-256') || ''
  if (!verifyWebhookSignature(rawBody, signature)) {
    return new NextResponse('Invalid signature', { status: 401 })
  }

  // Répondre 200 immédiatement (Meta exige < 20s)
  const body = JSON.parse(rawBody)
  processEvent(body).catch(console.error)

  return new NextResponse('EVENT_RECEIVED', { status: 200 })
}

async function processEvent(body: any) {
  if (body.object !== 'instagram') return

  for (const entry of body.entry ?? []) {
    const igUserId = entry.id

    // Récupérer le compte et son token
    const { data: account } = await supabase
      .from('ig_accounts')
      .select('access_token')
      .eq('ig_user_id', igUserId)
      .single()

    if (!account) continue

    // Traiter les commentaires
    for (const change of entry.changes ?? []) {
      if (change.field === 'comments') {
        await handleComment(change.value, igUserId, account.access_token)
      }
    }
  }
}

async function handleComment(comment: any, igUserId: string, accessToken: string) {
  const commentId = comment.id
  const commentText: string = (comment.text || '').toLowerCase()
  const senderId = comment.from?.id

  if (!senderId || !commentId) return

  // Anti-doublon
  const { data: existing } = await supabase
    .from('sent_dms')
    .select('comment_id')
    .eq('comment_id', commentId)
    .single()

  if (existing) return

  // Chercher un mot-clé correspondant
  const { data: rules } = await supabase
    .from('keyword_rules')
    .select('keyword, dm_message')
    .eq('ig_user_id', igUserId)
    .eq('is_active', true)

  if (!rules) return

  const matchedRule = rules.find(rule =>
    commentText.includes(rule.keyword.toLowerCase())
  )

  if (!matchedRule) return

  // Envoyer le DM
  try {
    await sendDM(senderId, matchedRule.dm_message, accessToken)

    // Enregistrer pour éviter les doublons
    await supabase.from('sent_dms').insert({
      comment_id: commentId,
      ig_user_id: igUserId,
      recipient: senderId,
    })
  } catch (err) {
    console.error('DM send error:', err)
  }
}
