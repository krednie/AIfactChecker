import type { Metadata } from 'next';
import './landing.css';
import './globals.css';
import { SpotlightProvider } from '@/components/ui/spotlight-card';

export const metadata: Metadata = {
  title: 'Alithia — AI Fact Checker',
  description:
    'AI-powered fact-checking for social media posts. Extract claims, verify with RAG, trace origin.',
  keywords: ['fact-check', 'misinformation', 'AI', 'RAG', 'social media'],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SpotlightProvider />
        {children}
      </body>
    </html>
  );
}
