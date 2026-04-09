import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NexusIQ Esports Analytics",
  description: "AI-powered League of Legends team and player analytics frontend",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
