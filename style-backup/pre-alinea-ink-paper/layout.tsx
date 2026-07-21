import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Brand Agent Studio",
  description: "品牌生成工作台",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="zh-CN">
      {/* 浏览器插件会向 body 注入自定义属性，忽略这类差异避免误报 hydration 错误 */}
      <body suppressHydrationWarning>
        {/* React 会把这些 link 提升到 head；字体加载失败时回退系统字体 */}
        <link href="https://fonts.googleapis.com" rel="preconnect" />
        <link crossOrigin="anonymous" href="https://fonts.gstatic.com" rel="preconnect" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
        {children}
      </body>
    </html>
  );
}
