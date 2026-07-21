import { redirect } from "next/navigation";

// 旧版工作台已由首页的 AlineStudio 取代；
// 保留此路由仅为兼容旧链接，一律跳回首页。
export default function ProjectPage() {
  redirect("/");
}
