import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Esports Analytics Platform",
  description: "Frontend for the esports capstone project",
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
