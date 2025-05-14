import { useState, useRef, useEffect } from 'react';
import './ChatBox.css';
import RestartChatButton from './RestartChatButton';
import ChatInput from './ChatInput';
import MessagesContainer from './MessagesContainer';
import type { Message } from './types';

const ChatBox = () => {
  const initialMessage: Message = {
    text: "Hi, I'm the Happy Returns Support Agent, how can I help you today?",
    isUser: false,
    timestamp: new Date()
  };

  const [messages, setMessages] = useState<Message[]>([initialMessage]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [chatId, setChatId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

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

  const formatChatHistory = () => {
    const history = [];
    for (let i = 1; i < messages.length; i += 2) {
      const interaction = {
        user_message: messages[i]?.text || '',
        bot_response: messages[i + 1]?.text || ''
      };
      history.push(interaction);
    }
    return history;
  };

  const handleSendMessage = async () => {
    if (inputMessage.trim() === '') return;

    // Create new chat if no chatId exists
    if (!chatId) {
      await handleNewChat();
    }

    const newMessage: Message = {
      text: inputMessage,
      isUser: true,
      timestamp: new Date()
    };

    setMessages([...messages, newMessage]);
    setInputMessage('');
    setIsLoading(true);

    try {
      const chatHistory = formatChatHistory();
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          chat_id: chatId,
          current_message: inputMessage,
          chat_history: chatHistory
        })
      });

      if (!response.ok) {
        throw new Error('Failed to get response');
      }

      const data = await response.json();
      // Handle first message chat ID assignment
      if (!chatId && data.chat_id) {
        setChatId(data.chat_id);
      }
      
      const botResponse: Message = {
        text: data.response || "Sorry, I'm having trouble responding right now.",
        isUser: false,
        timestamp: new Date()
      };
      setMessages(prevMessages => [...prevMessages, botResponse]);
    } catch (error) {
      console.error('Error:', error);
      const errorResponse: Message = {
        text: "Sorry, I'm having trouble responding right now.",
        isUser: false,
        timestamp: new Date()
      };
      setMessages(prevMessages => [...prevMessages, errorResponse]);
    } finally {
      setIsLoading(false);
    }
    

    // Log the structure that will be sent to API
    const chatHistory = formatChatHistory();
    console.log('Future API payload:', {
      chat_id: chatId,
      current_message: inputMessage,
      chat_history: chatHistory
    });
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