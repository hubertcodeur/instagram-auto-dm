import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

export async function GET(req: NextRequest) {
  const igUserId = req.nextUrl.searchParams.get('ig_user_id')
  if (!igUserId) return NextResponse.json({ error: 'Missing ig_user_id' }, { status: 400 })

  const { data, error } = await supabase
    .from('keyword_rules')
    .select('*')
    .eq('ig_user_id', igUserId)
    .order('created_at', { ascending: false })

  if (error) return NextResponse.json({ error }, { status: 500 })
  return NextResponse.json(data)
}

export async function POST(req: NextRequest) {
  const body = await req.json()
  const { ig_user_id, keyword, dm_message } = body

  if (!ig_user_id || !keyword || !dm_message) {
    return NextResponse.json({ error: 'Missing fields' }, { status: 400 })
  }

  const { data, error } = await supabase
    .from('keyword_rules')
    .insert({ ig_user_id, keyword: keyword.trim().toLowerCase(), dm_message })
    .select()
    .single()

  if (error) return NextResponse.json({ error }, { status: 500 })
  return NextResponse.json(data)
}

export async function DELETE(req: NextRequest) {
  const id = req.nextUrl.searchParams.get('id')
  if (!id) return NextResponse.json({ error: 'Missing id' }, { status: 400 })

  const { error } = await supabase.from('keyword_rules').delete().eq('id', id)
  if (error) return NextResponse.json({ error }, { status: 500 })
  return NextResponse.json({ success: true })
}
