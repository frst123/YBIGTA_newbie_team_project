'use client';

import { useState } from 'react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  toolUsed?: string;
}

export default function Home() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage: Message = { role: 'user', content: input };
    const newMessages = [...messages, userMessage];
    setMessages(newMessages);
    setInput('');
    setLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: newMessages.map((m) => ({
            role: m.role,
            content: m.content,
          })),
        }),
      });

      const data = await response.json();

      if (data.error) {
        setMessages([
          ...newMessages,
          { role: 'assistant', content: `오류: ${data.error}` },
        ]);
      } else {
        setMessages([
          ...newMessages,
          {
            role: 'assistant',
            content: data.result,
            toolUsed: data.toolUsed,
          },
        ]);
      }
    } catch (err) {
      setMessages([
        ...newMessages,
        { role: 'assistant', content: '서버와 통신 중 에러가 발생했습니다.' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main style={{ padding: '20px', maxWidth: '800px', margin: '0 auto', fontFamily: 'sans-serif' }}>
      <header style={{ borderBottom: '1px solid #ccc', pb: '10px', marginBottom: '20px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 'bold' }}>Data Analysis Agent</h1>
        <p style={{ fontSize: '14px', color: '#666' }}>경복궁 리뷰 MCP Server 기반 데이터 분석 비서</p>
      </header>

      <div style={{
        minHeight: '400px',
        maxHeight: '600px',
        overflowY: 'auto',
        border: '1px solid #ddd',
        borderRadius: '8px',
        padding: '16px',
        marginBottom: '16px',
        backgroundColor: '#f9f9f9'
      }}>
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', color: '#aaa', marginTop: '150px' }}>
            질문을 입력하세요.<br />(예: "경복궁 카카오 리뷰 최근 데이터 보여줘", "주요 키워드 5개 알려줘")
          </div>
        )}
        {messages.map((msg, index) => (
          <div
            key={index}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
              marginBottom: '12px'
            }}
          >
            <div
              style={{
                padding: '10px 14px',
                borderRadius: '8px',
                maxWidth: '80%',
                backgroundColor: msg.role === 'user' ? '#0070f3' : '#ffffff',
                color: msg.role === 'user' ? '#ffffff' : '#333333',
                border: msg.role === 'user' ? 'none' : '1px solid #eee',
                boxShadow: '0 1px 2px rgba(0,0,0,0.05)'
              }}
            >
              {msg.content}
            </div>
            {msg.toolUsed && (
              <span style={{ fontSize: '12px', color: '#10b981', marginTop: '4px', fontFamily: 'monospace' }}>
                🔧 사용된 MCP Tool: {msg.toolUsed}
              </span>
            )}
          </div>
        ))}
        {loading && (
          <div style={{ color: '#aaa', fontSize: '14px', fontStyle: 'italic' }}>
            Agent가 MCP 데이터를 조회하고 답변을 생성하는 중...
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '8px' }}>
        <input
          type="text"
          style={{
            flex: 1,
            border: '1px solid #ccc',
            borderRadius: '6px',
            padding: '10px 14px',
            fontSize: '14px'
          }}
          placeholder="질문을 입력하세요..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button
          type="submit"
          disabled={loading}
          style={{
            backgroundColor: loading ? '#ccc' : '#0070f3',
            color: '#fff',
            border: 'none',
            borderRadius: '6px',
            padding: '10px 20px',
            cursor: loading ? 'not-allowed' : 'pointer',
            fontWeight: 'bold'
          }}
        >
          전송
        </button>
      </form>
    </main>
  );
}