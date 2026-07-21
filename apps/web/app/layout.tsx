import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Alinea Brand Studio",
  description: "品牌生成工作台",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="zh-CN">
      {/* 浏览器插件会向 body 注入自定义属性，忽略这类差异避免误报 hydration 错误 */}
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
