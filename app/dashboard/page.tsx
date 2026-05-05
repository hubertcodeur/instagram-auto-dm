'use client'

import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { Suspense } from 'react'

type Rule = {
  id: string
  keyword: string
  dm_message: string
  is_active: boolean
}

type Account = {
  ig_user_id: string
  ig_username: string
}

function DashboardContent() {
  const params = useSearchParams()
  const connected = params.get('connected')

  const [account, setAccount] = useState<Account | null>(null)
  const [rules, setRules] = useState<Rule[]>([])
  const [keyword, setKeyword] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const saved = localStorage.getItem('ig_account')
    if (saved) {
      const acc = JSON.parse(saved)
      setAccount(acc)
      fetchRules(acc.ig_user_id)
    }
  }, [])

  // Stocker le compte après connexion
  useEffect(() => {
    if (connected) {
      fetch('/api/auth/me')
        .then(r => r.json())
        .then(data => {
          if (data.ig_user_id) {
            localStorage.setItem('ig_account', JSON.stringify(data))
            setAccount(data)
            fetchRules(data.ig_user_id)
          }
        })
    }
  }, [connected])

  async function fetchRules(igUserId: string) {
    const res = await fetch(`/api/rules?ig_user_id=${igUserId}`)
    const data = await res.json()
    setRules(data || [])
  }

  async function addRule() {
    if (!keyword.trim() || !message.trim() || !account) return
    setLoading(true)
    setError('')
    const res = await fetch('/api/rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ig_user_id: account.ig_user_id,
        keyword,
        dm_message: message,
      }),
    })
    const data = await res.json()
    if (data.error) {
      setError(data.error.message || 'Erreur')
    } else {
      setRules(prev => [data, ...prev])
      setKeyword('')
      setMessage('')
    }
    setLoading(false)
  }

  async function deleteRule(id: string) {
    await fetch(`/api/rules?id=${id}`, { method: 'DELETE' })
    setRules(prev => prev.filter(r => r.id !== id))
  }

  if (!account) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-500 mb-4">Aucun compte connecté.</p>
          <a href="/" className="text-purple-600 underline">Connecter Instagram</a>
        </div>
      </main>
    )
  }

  return (
    <main className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-2xl mx-auto">
        {connected && (
          <div className="bg-green-50 text-green-700 rounded-lg p-3 mb-6 text-sm">
            ✅ Compte @{account.ig_username} connecté avec succès !
          </div>
        )}

        <div className="bg-white rounded-2xl shadow p-6 mb-6">
          <div className="flex items-center gap-3 mb-1">
            <div className="w-10 h-10 bg-gradient-to-br from-purple-500 to-pink-400 rounded-full flex items-center justify-center text-white font-bold">
              {account.ig_username?.[0]?.toUpperCase()}
            </div>
            <div>
              <p className="font-semibold text-gray-800">@{account.ig_username}</p>
              <p className="text-xs text-green-500">● Connecté</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-2xl shadow p-6 mb-6">
          <h2 className="font-bold text-gray-800 mb-4">Nouvelle règle</h2>

          <div className="mb-3">
            <label className="text-sm text-gray-500 mb-1 block">Mot-clé (dans le commentaire)</label>
            <input
              value={keyword}
              onChange={e => setKeyword(e.target.value)}
              placeholder="ex: lien, guide, intéressé..."
              className="w-full border border-gray-200 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-300"
            />
          </div>

          <div className="mb-4">
            <label className="text-sm text-gray-500 mb-1 block">Message DM automatique</label>
            <textarea
              value={message}
              onChange={e => setMessage(e.target.value)}
              placeholder="ex: Salut ! Voici le lien que tu cherchais : ..."
              rows={3}
              className="w-full border border-gray-200 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-300 resize-none"
            />
          </div>

          {error && <p className="text-red-500 text-sm mb-3">{error}</p>}

          <button
            onClick={addRule}
            disabled={loading || !keyword.trim() || !message.trim()}
            className="w-full bg-gradient-to-r from-purple-600 to-pink-500 text-white font-semibold py-2 rounded-xl hover:opacity-90 disabled:opacity-40 transition"
          >
            {loading ? 'Ajout...' : 'Ajouter la règle'}
          </button>
        </div>

        <div className="bg-white rounded-2xl shadow p-6">
          <h2 className="font-bold text-gray-800 mb-4">Règles actives ({rules.length})</h2>
          {rules.length === 0 ? (
            <p className="text-gray-400 text-sm text-center py-4">Aucune règle. Ajoutes-en une ci-dessus.</p>
          ) : (
            <div className="space-y-3">
              {rules.map(rule => (
                <div key={rule.id} className="flex items-start justify-between gap-3 p-3 bg-gray-50 rounded-xl">
                  <div>
                    <span className="inline-block bg-purple-100 text-purple-700 text-xs font-semibold px-2 py-0.5 rounded-full mb-1">
                      {rule.keyword}
                    </span>
                    <p className="text-sm text-gray-600">{rule.dm_message}</p>
                  </div>
                  <button
                    onClick={() => deleteRule(rule.id)}
                    className="text-gray-300 hover:text-red-400 transition text-lg leading-none mt-0.5"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  )
}

export default function Dashboard() {
  return (
    <Suspense>
      <DashboardContent />
    </Suspense>
  )
}
