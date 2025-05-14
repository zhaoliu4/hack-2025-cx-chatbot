import React from 'react';
import type { RefObject } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import ReactMarkdown from 'react-markdown';
import copy from 'copy-to-clipboard';

interface Message {
  text: string;
  isUser: boolean;
  timestamp: Date;
  qrCode?: string;
  error?: boolean;
}

interface MessagesContainerProps {
  messages: Message[];
  isLoading: boolean;
  messagesEndRef: RefObject<HTMLDivElement | null>;
}

const ErrorMessage: React.FC = () => (
  <div className="error-message">
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
      <circle cx="10" cy="10" r="9" stroke="currentColor" strokeWidth="2"/>
      <path d="M10 5v6m0 2v2" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
    </svg>
    <span>Something went wrong. Please try again.</span>
  </div>
);

const CopyButton: React.FC<{ text: string }> = ({ text }) => {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = () => {
    copy(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button 
      onClick={handleCopy}
      className="copy-button"
      aria-label="Copy QR code"
    >
      {copied ? (
        <>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M13 4L6 11L3 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <span>Copied!</span>
        </>
      ) : (
        <>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <rect x="3" y="3" width="8" height="8" rx="1" stroke="currentColor" strokeWidth="2"/>
            <path d="M13 6V13C13 13.5523 12.5523 14 12 14H5" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          <span>Copy</span>
        </>
      )}
    </button>
  );
};

const MessagesContainer: React.FC<MessagesContainerProps> = ({
  messages,
  isLoading,
  messagesEndRef
}) => {
  return (
    <div className="messages-container">
      {messages.map((message, index) => (
        <div
          key={index}
          className={`message-row ${message.isUser ? 'user' : 'bot'} ${message.error ? 'error' : ''}`}
        >
          {!message.isUser && (
            <img
              src="/hr_circle_logo_100.png"
              alt="Support Agent"
              className="bot-icon"
            />
          )}
          <div className={`message-bubble ${message.isUser ? 'user' : 'bot'}`}>
            <div className="message-text">
              {message.error ? (
                <ErrorMessage />
              ) : (
                <div className="message-content">
                  <ReactMarkdown>{message.text}</ReactMarkdown>
                </div>
              )}
            </div>
            {message.qrCode && (
              <div className="qr-code-container">
                <CopyButton text={message.qrCode} />
                <QRCodeSVG value={message.qrCode} size={200} />
              </div>
            )}
          </div>
        </div>
      ))}
      {isLoading && (
        <div className="loading-dots">
          <div className="loading-dot" />
          <div className="loading-dot" />
          <div className="loading-dot" />
        </div>
      )}
      <div ref={messagesEndRef} />
    </div>
  );
};

export default MessagesContainer; 