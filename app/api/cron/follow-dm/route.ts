import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { getFollowers, sendDM } from '@/lib/meta'

export async function GET(req: NextRequest) {
  const authHeader = req.headers.get('authorization')
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    return new NextResponse('Unauthorized', { status: 401 })
  }

  const { data: rules } = await supabase
    .from('follow_dm_rules')
    .select('ig_user_id, dm_message, initialized')
    .eq('is_active', true)

  if (!rules || rules.length === 0) {
    return NextResponse.json({ processed: 0 })
  }

  let processed = 0
  for (const rule of rules) {
    const { data: account } = await supabase
      .from('ig_accounts')
      .select('access_token')
      .eq('ig_user_id', rule.ig_user_id)
      .single()

    if (!account) continue

    try {
      await processFollowers(rule.ig_user_id, account.access_token, rule.dm_message, rule.initialized)
      processed++
    } catch (err) {
      console.error(`follow-dm error for ${rule.ig_user_id}:`, err)
    }
  }

  return NextResponse.json({ processed, timestamp: new Date().toISOString() })
}

async function processFollowers(
  igUserId: string,
  accessToken: string,
  dmMessage: string,
  initialized: boolean
) {
  // Fetch current followers (stop early once we hit known followers)
  const { data: knownRows } = await supabase
    .from('known_followers')
    .select('follower_id')
    .eq('ig_user_id', igUserId)

  const knownIds = new Set(knownRows?.map(k => k.follower_id) ?? [])
  const newFollowers: string[] = []
  let after: string | undefined
  let hitKnown = false

  while (!hitKnown) {
    const result = await getFollowers(accessToken, after)

    for (const follower of result.data) {
      if (knownIds.has(follower.id)) {
        hitKnown = true
        break
      }
      newFollowers.push(follower.id)
    }

    if (!result.paging?.next || !result.paging?.cursors?.after) break
    after = result.paging.cursors.after
    await new Promise(r => setTimeout(r, 250))
  }

  if (!initialized) {
    // First run: store all current followers without sending DMs
    const allFollowers: string[] = [...newFollowers, ...Array.from(knownIds)]
    // Fetch remaining pages to get complete list on first init
    if (!hitKnown) {
      while (after) {
        const result = await getFollowers(accessToken, after)
        for (const f of result.data) allFollowers.push(f.id)
        after = result.paging?.cursors?.after
        if (!result.paging?.next) break
        await new Promise(r => setTimeout(r, 250))
      }
    }

    const rows = allFollowers.map(id => ({ ig_user_id: igUserId, follower_id: id, dm_sent: true }))
    for (let i = 0; i < rows.length; i += 500) {
      await supabase.from('known_followers').upsert(rows.slice(i, i + 500), {
        onConflict: 'ig_user_id,follower_id',
        ignoreDuplicates: true,
      })
    }

    await supabase.from('follow_dm_rules').update({ initialized: true }).eq('ig_user_id', igUserId)
    return
  }

  // Send DM to each new follower
  for (const followerId of newFollowers) {
    let dmSent = false
    try {
      await sendDM(followerId, dmMessage, accessToken)
      dmSent = true
    } catch (err) {
      console.error(`DM failed for follower ${followerId}:`, err)
    }

    await supabase.from('known_followers').insert({
      ig_user_id: igUserId,
      follower_id: followerId,
      dm_sent: dmSent,
    })

    await new Promise(r => setTimeout(r, 500))
  }
}
