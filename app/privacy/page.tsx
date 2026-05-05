export default function PrivacyPolicy() {
  return (
    <main className="max-w-2xl mx-auto p-8 text-gray-700">
      <h1 className="text-2xl font-bold mb-6 text-gray-900">Privacy Policy — Auto DM App</h1>
      <p className="text-sm text-gray-400 mb-8">Last updated: May 2026</p>

      <section className="mb-6">
        <h2 className="font-semibold text-lg mb-2">1. Data We Collect</h2>
        <p>We collect the following data from your Instagram account via the Meta API:</p>
        <ul className="list-disc ml-6 mt-2 space-y-1">
          <li>Instagram user ID and username</li>
          <li>Access tokens to act on your behalf</li>
          <li>Comment data (text and author ID) from your posts</li>
        </ul>
      </section>

      <section className="mb-6">
        <h2 className="font-semibold text-lg mb-2">2. How We Use Your Data</h2>
        <p>Data is used solely to:</p>
        <ul className="list-disc ml-6 mt-2 space-y-1">
          <li>Send automatic direct messages when someone comments a keyword on your posts</li>
          <li>Store your access token securely to maintain the connection with Instagram</li>
        </ul>
        <p className="mt-2">We do not sell, share, or use your data for advertising.</p>
      </section>

      <section className="mb-6">
        <h2 className="font-semibold text-lg mb-2">3. Data Retention</h2>
        <p>Access tokens are stored until you disconnect your account. Comment logs are kept for deduplication purposes and automatically purged after 90 days.</p>
      </section>

      <section className="mb-6">
        <h2 className="font-semibold text-lg mb-2">4. Third Parties</h2>
        <p>We use the following services:</p>
        <ul className="list-disc ml-6 mt-2 space-y-1">
          <li><strong>Meta / Instagram</strong> — source of all Instagram data</li>
          <li><strong>Supabase</strong> — secure database storage</li>
          <li><strong>Vercel</strong> — hosting</li>
        </ul>
      </section>

      <section className="mb-6">
        <h2 className="font-semibold text-lg mb-2">5. Your Rights</h2>
        <p>You can request deletion of your data at any time by contacting us at <a href="mailto:arabeprogress@gmail.com" className="text-purple-600 underline">arabeprogress@gmail.com</a>.</p>
      </section>

      <section className="mb-6">
        <h2 className="font-semibold text-lg mb-2">6. Data Deletion</h2>
        <p>To delete all your data, send an email to <a href="mailto:arabeprogress@gmail.com" className="text-purple-600 underline">arabeprogress@gmail.com</a> with subject "Data Deletion Request". We will process your request within 30 days.</p>
      </section>

      <section className="mb-6">
        <h2 className="font-semibold text-lg mb-2">7. Contact</h2>
        <p>For any privacy-related questions: <a href="mailto:arabeprogress@gmail.com" className="text-purple-600 underline">arabeprogress@gmail.com</a></p>
      </section>
    </main>
  )
}
