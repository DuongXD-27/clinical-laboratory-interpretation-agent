import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "LumiLab — Hiểu kết quả xét nghiệm",
    template: "%s · LumiLab",
  },
  description: "Giải thích kết quả xét nghiệm bằng ngôn ngữ dễ hiểu cho người bệnh.",
};

export const viewport: Viewport = {
  colorScheme: "light",
  themeColor: "#f4f8fa",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className="h-full antialiased">
      <body className="lumilab-root min-h-full flex flex-col">{children}</body>
    </html>
  );
}
