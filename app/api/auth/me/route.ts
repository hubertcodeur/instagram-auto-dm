import { NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

// Retourne le dernier compte connecté
export async function GET() {
  const { data } = await supabase
    .from('ig_accounts')
    .select('ig_user_id, ig_username')
    .order('created_at', { ascending: false })
    .limit(1)
    .single()

  if (!data) return NextResponse.json({ error: 'Not found' }, { status: 404 })
  return NextResponse.json(data)
}
