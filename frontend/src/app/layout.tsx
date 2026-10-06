import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Memory Engine",
  description: "Your Personal Second Brain"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
