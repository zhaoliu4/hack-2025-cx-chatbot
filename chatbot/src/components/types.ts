export interface Message {
  text: string;
  isUser: boolean;
  timestamp: Date;
  qrCode?: string;  // Optional QR code data string
  error?: boolean;
} 