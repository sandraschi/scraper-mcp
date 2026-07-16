import { Bot, Loader2, MessageSquare, Send, Trash2, User, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

const STORAGE_KEY = "scraper-mcp-chat-history";

const PERSONALITIES: Record<string, string> = {
  "Scraper Expert": "You are an expert web scraping specialist. Help users design scraping strategies, parse HTML/CSS selectors, handle pagination, and bypass anti-scraping measures. Be technically detailed.",
  "Data Analyst": "You are a data analyst focused on extracting insights from scraped data. Advise on data cleaning, transformation, storage formats, and export pipelines.",
  "Quick Summarizer": "You are a concise assistant. Answer in 1-3 sentences. Be direct and to the point.",
  "Custom": "",
};

const EXAMPLE_PROMPTS = [
  { group: "Scrape", items: ["Scrape all product listings from an e-commerce site", "Extract news headlines from RSS feeds", "Crawl a documentation site for all pages"] },
  { group: "Parse", items: ["Parse HTML tables into structured JSON", "Extract data using CSS selector patterns", "Clean and normalize scraped text content"] },
  { group: "Export", items: ["Export scraped data to CSV format", "Save results to a SQLite database", "Generate a data quality report"] },
];

function saveMessages(msgs: Message[]) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(msgs)); } catch {}
}

function loadMessages(): Message[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return [];
}

export default function FloatingChat() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>(() => {
    const saved = loadMessages();
    if (saved.length > 0) return saved;
    return [{
      role: "assistant",
      content: "I'm your Scraper MCP assistant. I can help with web scraping, data parsing, and export. Ask me anything!",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    }];
  });
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [personality, setPersonality] = useState("Scraper Expert");
  const [showExamples, setShowExamples] = useState(true);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = useCallback(async () => {
    const text = inputValue.trim();
    if (!text || isLoading) return;
    setShowExamples(false);

    const userMsg: Message = {
      role: "user",
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    const updated = [...messages, userMsg];
    setMessages(updated);
    saveMessages(updated);
    setInputValue("");
    setIsLoading(true);

    try {
      const history = updated.map((m) => ({ role: m.role, content: m.content }));
      const systemPrompt = PERSONALITIES[personality] || "";
      const response = await fetch("/api/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, system_prompt: systemPrompt, context: { history } }),
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const reply = data.reply || data.response || "No response from model.";

      const assistantMsg: Message = {
        role: "assistant",
        content: reply,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      const withReply = [...updated, assistantMsg];
      setMessages(withReply);
      saveMessages(withReply);
    } catch {
      const errMsg: Message = {
        role: "assistant",
        content: "Request failed. Check that the backend is running and an LLM provider is configured.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      const withError = [...updated, errMsg];
      setMessages(withError);
      saveMessages(withError);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  }, [messages, isLoading, personality, inputValue]);

  const handleClear = () => {
    const fresh: Message[] = [{
      role: "assistant",
      content: "Conversation cleared. How can I help?",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    }];
    setMessages(fresh);
    saveMessages(fresh);
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-50 p-3.5 rounded-full bg-amber-500 text-zinc-950 shadow-xl hover:bg-amber-400 transition-all hover:scale-105"
        title="Open chat"
      >
        <MessageSquare className="h-5 w-5" />
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 w-96 h-[32rem] flex flex-col rounded-2xl border border-zinc-700 bg-zinc-950 shadow-2xl overflow-hidden" data-testid="chat-page">
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 bg-zinc-900" data-testid="chat-controls">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-amber-400" />
          <span className="text-sm font-medium text-zinc-100">AI Assistant</span>
          <span className="text-[10px] text-zinc-500 bg-zinc-800 px-1.5 py-0.5 rounded font-mono">skill:scraper</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" data-testid="backend-dot" />
          <select
            value={personality}
            onChange={(e) => setPersonality(e.target.value)}
            data-testid="personality-select"
            className="text-[10px] bg-zinc-800 border border-zinc-700 rounded px-1.5 py-0.5 text-zinc-300 focus:outline-none"
          >
            {Object.keys(PERSONALITIES).map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <button onClick={handleClear} data-testid="chat-clear" className="p-1 text-zinc-500 hover:text-red-400 transition-colors" title="Clear">
            <Trash2 className="h-3.5 w-3.5" />
          </button>
          <button onClick={() => setOpen(false)} className="p-1 text-zinc-500 hover:text-zinc-300 transition-colors" title="Close">
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3" data-testid="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-2 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
              msg.role === "user"
                ? "bg-amber-500 text-zinc-950 rounded-tr-none"
                : "bg-zinc-800 text-zinc-200 rounded-tl-none border border-zinc-700"
            }`}>
              <p className="whitespace-pre-wrap text-[13px]">{msg.content}</p>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex gap-2 justify-start">
            <div className="bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-zinc-400 text-xs animate-pulse flex items-center gap-2">
              <Loader2 className="h-3 w-3 animate-spin" />
              Thinking...
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {showExamples && messages.length <= 1 && (
        <div className="px-3 pb-2 flex flex-wrap gap-1.5" data-testid="example-prompts">
          {EXAMPLE_PROMPTS.flatMap((g) => g.items).slice(0, 3).map((p) => (
            <button key={p} type="button" onClick={() => { setInputValue(p); inputRef.current?.focus(); }}
              className="px-2 py-0.5 rounded text-[10px] bg-zinc-800 text-zinc-400 hover:bg-zinc-700 transition-colors border border-zinc-700/50">
              {p}
            </button>
          ))}
        </div>
      )}

      <div className="p-3 border-t border-zinc-800 bg-zinc-900/50">
        <form onSubmit={(e) => { e.preventDefault(); handleSend(); }} className="flex gap-2">
          <input ref={inputRef}
            className="flex-1 bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-amber-500/50 placeholder:text-zinc-500"
            placeholder="Ask about scraping..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            disabled={isLoading}
            data-testid="chat-input"
          />
          <button type="submit" disabled={isLoading || !inputValue.trim()} data-testid="chat-send"
            className="p-2 rounded-xl bg-amber-500 text-zinc-950 hover:bg-amber-400 disabled:opacity-50 transition-all">
            <Send className="h-4 w-4" />
          </button>
        </form>
      </div>
    </div>
  );
}
