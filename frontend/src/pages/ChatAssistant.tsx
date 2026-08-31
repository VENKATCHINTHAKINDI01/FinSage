import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Sparkles, MessageCircle } from 'lucide-react';
import AppLayout from '../components/shared/AppLayout';
import { sendChatQuery } from '../api/services';
import { formatChatAnswer } from '../utils/chatResponse';

type Role = 'user' | 'ai';

interface Message {
  id: string;
  role: Role;
  text: string;
}

const uid = () => Math.random().toString(36).slice(2);

const SUGGESTED_PROMPTS = [
  'How can I reduce my tax liability this year?',
  'Should I invest in NPS or PPF for tax savings?',
  'What government schemes am I eligible for?',
  'Explain the difference between old and new tax regime for me',
  'What is my capital gains tax if I sell my mutual funds?',
  'Help me plan my wealth for retirement',
];

export default function ChatAssistant() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: uid(),
      role: 'ai',
      text: "Hi! I'm your FinSage AI assistant. Ask me anything about your taxes, deductions, government benefits, investments, wealth planning, or cross-border tax — I'll answer using your saved profile.",
    },
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [conversationId] = useState(uid());
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const handleSend = useCallback(async (text: string) => {
    if (!text.trim() || isTyping) return;
    setMessages((prev) => [...prev, { id: uid(), role: 'user', text }]);
    setInput('');
    setIsTyping(true);

    try {
      const res = await sendChatQuery(text, conversationId);
      const answer = formatChatAnswer(res);
      setMessages((prev) => [...prev, { id: uid(), role: 'ai', text: answer }]);
    } catch {
      setMessages((prev) => [...prev, {
        id: uid(),
        role: 'ai',
        text: "Sorry, I couldn't process that just now. Please try again in a moment.",
      }]);
    } finally {
      setIsTyping(false);
      inputRef.current?.focus();
    }
  }, [conversationId, isTyping]);

  return (
    <AppLayout title="AI Assistant" subtitle="Ask anything about your taxes, savings, and finances">
      <div className="flex flex-col h-[calc(100vh-160px)] rounded-2xl border border-line overflow-hidden bg-white dark:bg-slate-900 shadow-lg">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 bg-gradient-to-r from-navy to-navy-deep border-b border-white/10 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-saffron to-teal flex items-center justify-center">
              <MessageCircle size={16} className="text-white" />
            </div>
            <div>
              <p className="text-[13.5px] font-bold text-white">FinSage AI Assistant</p>
              <p className="text-[10.5px] text-white/45">Profile-aware · Tax, deductions, benefits, wealth planning & more</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-teal/20 border border-teal/30">
            <span className="w-1.5 h-1.5 rounded-full bg-teal animate-pulse" />
            <span className="text-[10.5px] font-semibold text-teal-light">Live</span>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 bg-slate-50/50 dark:bg-slate-950/30">
          {messages.map((msg) => (
            <div key={msg.id} className={`flex items-end gap-2.5 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
              {msg.role === 'ai' && (
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-primary to-teal flex items-center justify-center shrink-0 mb-0.5">
                  <Sparkles size={13} className="text-white" />
                </div>
              )}
              <div
                className={`max-w-[82%] rounded-2xl px-4 py-3 text-[13px] leading-relaxed whitespace-pre-wrap ${
                  msg.role === 'user'
                    ? 'bg-primary text-white rounded-br-md'
                    : 'bg-white dark:bg-slate-800 border border-line dark:border-white/10 text-ink dark:text-slate-100 shadow-sm rounded-bl-md'
                }`}
              >
                {msg.text}
              </div>
              {msg.role === 'user' && (
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-saffron to-primary flex items-center justify-center shrink-0 mb-0.5 text-white text-[11px] font-bold">
                  U
                </div>
              )}
            </div>
          ))}

          {isTyping && (
            <div className="flex items-end gap-2.5">
              <div className="w-7 h-7 rounded-full bg-gradient-to-br from-primary to-teal flex items-center justify-center shrink-0">
                <Sparkles size={13} className="text-white" />
              </div>
              <div className="bg-white dark:bg-slate-800 border border-line dark:border-white/10 rounded-2xl rounded-bl-md px-4 py-3.5 shadow-sm">
                <div className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full bg-ink-soft typing-dot-1" />
                  <div className="w-2 h-2 rounded-full bg-ink-soft typing-dot-2" />
                  <div className="w-2 h-2 rounded-full bg-ink-soft typing-dot-3" />
                </div>
              </div>
            </div>
          )}

          {messages.length === 1 && (
            <div className="flex flex-wrap gap-2 ml-9">
              {SUGGESTED_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => handleSend(prompt)}
                  className="quick-reply"
                >
                  {prompt}
                </button>
              ))}
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="shrink-0 p-4 border-t border-line bg-white dark:bg-slate-900">
          <div className="flex items-center gap-3">
            <div className="flex-1 relative">
              <input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(input); } }}
                placeholder="Ask about taxes, deductions, benefits, investments…"
                className="w-full h-11 px-4 rounded-xl border border-line bg-paper dark:bg-slate-800 text-[13.5px] text-ink dark:text-slate-100 placeholder:text-ink-soft focus:outline-none focus:ring-2 focus:ring-primary/25 focus:border-primary transition-all"
              />
            </div>
            <button
              onClick={() => handleSend(input)}
              disabled={!input.trim() || isTyping}
              className="w-11 h-11 rounded-xl bg-primary text-white flex items-center justify-center hover:bg-primary-600 disabled:opacity-40 disabled:cursor-not-allowed transition-all hover:shadow-lg hover:shadow-primary/25 active:scale-95"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
