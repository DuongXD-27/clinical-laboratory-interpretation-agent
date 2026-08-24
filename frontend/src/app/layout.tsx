import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LumiLab - Hiểu Kết Quả Xét Nghiệm",
  description: "Giải thích kết quả xét nghiệm bằng ngôn ngữ dễ hiểu cho người bệnh.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
