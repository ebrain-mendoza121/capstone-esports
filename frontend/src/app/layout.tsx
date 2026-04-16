import type { Metadata } from "next";
import AppNavbar from "@/components/navigation/AppNavbar";
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
      <body>
        <AppNavbar />
        {children}
      </body>
    </html>
  );
}
