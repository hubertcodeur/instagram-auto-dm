import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

export async function GET(req: NextRequest) {
  const igUserId = req.nextUrl.searchParams.get('ig_user_id')
  if (!igUserId) return NextResponse.json(null)

  const { data } = await supabase
    .from('follow_dm_rules')
    .select('*')
    .eq('ig_user_id', igUserId)
    .maybeSingle()

  return NextResponse.json(data)
}

export async function POST(req: NextRequest) {
  const { ig_user_id, dm_message } = await req.json()
  if (!ig_user_id || !dm_message) {
    return NextResponse.json({ error: 'Missing fields' }, { status: 400 })
  }

  const { data, error } = await supabase
    .from('follow_dm_rules')
    .upsert({ ig_user_id, dm_message, is_active: true, initialized: false }, {
      onConflict: 'ig_user_id',
    })
    .select()
    .single()

  if (error) return NextResponse.json({ error }, { status: 500 })
  return NextResponse.json(data)
}

export async function DELETE(req: NextRequest) {
  const igUserId = req.nextUrl.searchParams.get('ig_user_id')
  if (!igUserId) return NextResponse.json({ error: 'Missing ig_user_id' }, { status: 400 })

  await supabase.from('follow_dm_rules').delete().eq('ig_user_id', igUserId)
  return NextResponse.json({ ok: true })
}
