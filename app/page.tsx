'use client'

import { useSearchParams } from 'next/navigation'
import { Suspense } from 'react'

function HomeContent() {
  const params = useSearchParams()
  const error = params.get('error')

  return (
    <main className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-purple-50 to-pink-50 p-8">
      <div className="bg-white rounded-2xl shadow-lg p-10 max-w-md w-full text-center">
        <div className="text-5xl mb-4">📲</div>
        <h1 className="text-2xl font-bold text-gray-800 mb-2">Instagram Auto-DM</h1>
        <p className="text-gray-500 mb-8">
          Envoie automatiquement un DM à toute personne qui commente un mot-clé sur tes posts.
        </p>

        {error && (
          <div className="bg-red-50 text-red-600 rounded-lg p-3 mb-6 text-sm">
            Erreur de connexion : {error}
          </div>
        )}

        <a
          href="/api/auth/instagram"
          className="block w-full bg-gradient-to-r from-purple-600 to-pink-500 text-white font-semibold py-3 px-6 rounded-xl hover:opacity-90 transition"
        >
          Connecter mon compte Instagram
        </a>

        <p className="text-xs text-gray-400 mt-6">
          Utilise l&apos;API officielle Meta · 100% conforme Instagram
        </p>
      </div>
    </main>
  )
}

export default function Home() {
  return (
    <Suspense>
      <HomeContent />
    </Suspense>
  )
}
