import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PCollab hybrid match",
  description: "Lucene and vector search with a fused shortlist and final confidence score",
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
