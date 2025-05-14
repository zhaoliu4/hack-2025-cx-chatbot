import { useState, useRef, useEffect } from 'react';
import './ChatBox.css';
import RestartChatButton from './RestartChatButton';
import ChatInput from './ChatInput';
import MessagesContainer from './MessagesContainer';
import type { Message } from './types';

const STORAGE_KEY = 'happy-returns-chat';

interface StoredChat {
  chatId: string | null;
  messages: Message[];
  lastUpdated: number;
}

interface ChatHistory {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

const ChatBox = () => {
  const initialMessage: Message = {
    text: "Hi, I'm the Happy Returns Support Agent, how can I help you today?",
    isUser: false,
    timestamp: new Date()
  };

  // Load chat history from localStorage
  const loadChatHistory = (): StoredChat | null => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      // Convert stored timestamps back to Date objects
      parsed.messages = parsed.messages.map((msg: any) => ({
        ...msg,
        timestamp: new Date(msg.timestamp)
      }));
      return parsed;
    }
    return null;
  };

  // Save chat history to localStorage
  const saveChatHistory = (chatId: string | null, messages: Message[]) => {
    const chatData: StoredChat = {
      chatId,
      messages,
      lastUpdated: Date.now()
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(chatData));
  };

  // Initialize state from localStorage or with default values
  const storedChat = loadChatHistory();
  const [messages, setMessages] = useState<Message[]>(
    storedChat?.messages || [initialMessage]
  );
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [chatId, setChatId] = useState<string | null>(storedChat?.chatId || null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [chatHistory, setChatHistory] = useState<ChatHistory[]>([]);

  // Save to localStorage whenever messages or chatId changes
  useEffect(() => {
    saveChatHistory(chatId, messages);
  }, [messages, chatId]);

  const generateChatId = () => {
    return Math.random().toString(36).substring(2) + Date.now().toString(36);
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const handleNewChat = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('/api/chat/new', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      
      if (!response.ok) {
        throw new Error('Failed to create new chat');
      }

      const data = await response.json();
      setChatId(data.chat_id);
    } catch (error) {
      console.error('Error creating new chat:', error);
      // TEMP: Fallback to local ID generation
      const fallbackId = generateChatId();
      console.log('Using fallback chat ID:', fallbackId);
      setChatId(fallbackId);
    } finally {
      setMessages([{...initialMessage, timestamp: new Date()}]);
      setIsLoading(false);
    }
  };

  const handleSendMessage = async () => {
    if (inputMessage.trim() === '') return;

    const newMessage: Message = {
      text: inputMessage,
      isUser: true,
      timestamp: new Date()
    };

    setMessages(prevMessages => [...prevMessages, newMessage]);
    setInputMessage('');
    setIsLoading(true);

    try {
      const response = await fetch('/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: inputMessage,
          chat_history: chatHistory
        })
      });

      if (!response.ok) {
        throw new Error('Failed to get response');
      }

      const data = await response.json();
      
      // Update chat history
      setChatHistory(data.chat_history || []);
      
      const botResponse: Message = {
        text: data.response || "Sorry, I'm having trouble responding right now.",
        isUser: false,
        timestamp: new Date(),
        qrCode: data.qrCode || undefined
      };
      setMessages(prevMessages => [...prevMessages, botResponse]);
    } catch (error) {
      console.error('Error:', error);
      const errorResponse: Message = {
        text: "Sorry, I'm having trouble responding right now.",
        isUser: false,
        timestamp: new Date(),
        error: true
      };
      setMessages(prevMessages => [...prevMessages, errorResponse]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  return (
    <div className="chat-box">
      <div className="header">
        <div className="header-left">
          <img 
            src="/hr_circle_logo.svg" 
            alt="Happy Returns Logo" 
            className="header-logo"
          />
          <h2 className="header-title">Happy Returns Support</h2>
        </div>
        <RestartChatButton onRestart={handleNewChat} />
      </div>
      <MessagesContainer
        messages={messages}
        isLoading={isLoading}
        messagesEndRef={messagesEndRef}
      />
      <ChatInput
        inputMessage={inputMessage}
        onInputChange={setInputMessage}
        onSendMessage={handleSendMessage}
      />
      <div className="footer">
        <div className="powered-by">
          <img 
            src="/powered-by-happy-returns.png" 
            alt="Powered by Happy Returns"
          />
        </div>
      </div>
    </div>
  );
};

export default ChatBox; 