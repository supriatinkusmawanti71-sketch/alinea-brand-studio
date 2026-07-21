import { NextRequest, NextResponse } from "next/server";

type RouteContext = {
  params: Promise<{
    path?: string[];
  }>;
};

const defaultUpstreams = ["http://localhost:8080", "http://localhost:8000"];

function getUpstreams() {
  const configured = process.env.API_INTERNAL_URL?.replace(/\/$/, "");
  return Array.from(new Set([configured, ...defaultUpstreams].filter(Boolean))) as string[];
}

function createTargetUrl(baseUrl: string, path: string[], request: NextRequest) {
  const target = new URL(`/api/v1/${path.join("/")}`, baseUrl);
  target.search = request.nextUrl.search;
  return target;
}

function getForwardedHeaders(request: NextRequest) {
  const headers = new Headers();
  for (const name of ["accept", "authorization", "content-type"]) {
    const value = request.headers.get(name);
    if (value) {
      headers.set(name, value);
    }
  }
  return headers;
}

async function proxyApiRequest(request: NextRequest, context: RouteContext) {
  const { path = [] } = await context.params;
  const hasBody = !["GET", "HEAD"].includes(request.method);
  const body = hasBody ? await request.text() : undefined;

  for (const upstream of getUpstreams()) {
    try {
      const response = await fetch(createTargetUrl(upstream, path, request), {
        method: request.method,
        headers: getForwardedHeaders(request),
        body,
        cache: "no-store",
      });

      const headers = new Headers(response.headers);
      headers.delete("content-encoding");
      headers.delete("content-length");
      return new NextResponse(response.body, {
        status: response.status,
        headers,
      });
    } catch {
      // Try the next local API entrypoint.
    }
  }

  return NextResponse.json(
    {
      detail: "本地 API 没有连通，请确认 Docker 服务正在运行。",
    },
    { status: 503 },
  );
}

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export function GET(request: NextRequest, context: RouteContext) {
  return proxyApiRequest(request, context);
}

export function POST(request: NextRequest, context: RouteContext) {
  return proxyApiRequest(request, context);
}

export function PUT(request: NextRequest, context: RouteContext) {
  return proxyApiRequest(request, context);
}

export function PATCH(request: NextRequest, context: RouteContext) {
  return proxyApiRequest(request, context);
}

export function DELETE(request: NextRequest, context: RouteContext) {
  return proxyApiRequest(request, context);
}
