import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PCollab AutoSuggestions",
  description: "Atlas Search suggestions for vendor details",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
