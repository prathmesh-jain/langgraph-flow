import { useState } from 'react';

function App() {
  const [streamedText, setStreamedText] = useState<string>('');
  const [loading, setLoading] = useState(false);

  const handleRun = async () => {
    setLoading(true);
    setStreamedText('');
    try {
      const response = await fetch('http://localhost:8000/demo/run', {
        method: 'POST',
      });

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              try {
                const parsed = JSON.parse(data);
                if (parsed.content) {
                  setStreamedText(prev => prev + parsed.content + '\n');
                }
              } catch (e) {
                console.error('Failed to parse SSE data:', e);
              }
            }
          }
        }
      }
    } catch (e) {
      console.error('Failed to run graph:', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-2xl w-full">
        <h1 className="text-2xl font-bold mb-4">LangGraph Demo</h1>
        <button
          onClick={handleRun}
          disabled={loading}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400"
        >
          {loading ? 'Running...' : 'Run Graph'}
        </button>
        {streamedText && (
          <div className="mt-4 p-4 bg-gray-100 rounded">
            <h2 className="text-lg font-semibold mb-2">Streaming Output:</h2>
            <pre className="whitespace-pre-wrap text-sm">{streamedText}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
